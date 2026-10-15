"""Restore a private backup into the isolated PG container and verify restored bytes."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--archive", required=True)
parser.add_argument("--stage", required=True)
parser.add_argument("--database", required=True)
parser.add_argument("--image", required=True)
parser.add_argument("--org", required=True)
parser.add_argument("--batch")
args = parser.parse_args()
if not re.fullmatch(r"crm_restore_check_[a-z0-9_]{1,40}", args.database):
    raise ValueError("Only isolated restore-check databases are allowed")
if not re.fullmatch(r"crm-backend:[a-f0-9]{8,40}", args.image):
    raise ValueError("An immutable release image is required")
if not re.fullmatch(r"[a-f0-9-]{36}", args.org):
    raise ValueError("Exact org UUID required")
os.umask(0o077)
stage = Path(args.stage)
stage.mkdir(mode=0o700, parents=True, exist_ok=False)


def extract_regular(archive, destination):
    with tarfile.open(archive) as tar:
        for member in tar:
            relative = Path(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("Unsafe backup member")
            target = destination / relative
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with tar.extractfile(member) as incoming, target.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                target.chmod(0o600)
            else:
                raise ValueError("Non-regular backup member")


# Select data archives only. Restored env files or deployment scripts are never executed.
with tarfile.open(args.archive) as tar:
    wanted = {
        "database.dump",
        "media.tar.gz",
        "migration-files.tar.gz",
        "source-snapshot.tar.gz",
    }
    for member in tar:
        name = member.name.removeprefix("./")
        if name not in wanted:
            continue
        if not member.isfile():
            raise ValueError("Regular data archive required")
        with tar.extractfile(member) as incoming, (stage / name).open("wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
if not (stage / "database.dump").is_file():
    raise ValueError("Database dump missing")
for name in ("media", "migration-files", "source-snapshot"):
    archive = stage / (name + ".tar.gz")
    if archive.exists():
        extract_regular(archive, stage)
base = dict(
    line.split("=", 1)
    for line in Path("/opt/crm/migration-tools/test-postgres.env")
    .read_text()
    .splitlines()
    if line and not line.startswith("#")
)
assert (
    base["DBHOST"] == "127.0.0.1"
    and base["DBPORT"] == "54390"
    and base["DBUSER"] == "crm_migration_test"
)
base["DBNAME"] = args.database
(stage / "restore.env").write_text(
    "\n".join(f"{key}={value}" for key, value in base.items()) + "\n"
)
(stage / "restore.env").chmod(0o600)
(stage / "restore_settings.py").write_text(
    "from crm.test_settings_postgres import *\nMEDIA_ROOT='/restore/media'\nLEGACY_FILE_ROOT='/restore/migration-files'\nEMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'\n"
)
subprocess.run(
    [
        "docker",
        "exec",
        "crm-migration-tests-pg",
        "createdb",
        "-U",
        "migration_admin",
        "-O",
        "crm_migration_test",
        args.database,
    ],
    check=True,
)
with (
    (stage / "database.dump").open("rb") as data,
    (stage / "pg-restore.log").open("w") as log,
):
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "crm-migration-tests-pg",
            "pg_restore",
            "-U",
            "migration_admin",
            "--role=crm_migration_test",
            "--no-owner",
            "--no-acl",
            "-d",
            args.database,
        ],
        stdin=data,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
command = [
    "docker",
    "run",
    "--rm",
    "--network",
    "host",
    "--memory=1024m",
    "--env-file",
    str(stage / "restore.env"),
    "-e",
    "PYTHONPATH=/app:/restore",
    "-e",
    "DJANGO_SETTINGS_MODULE=restore_settings",
    "-v",
    str(stage) + ":/restore",
    "-w",
    "/app",
]
if (stage / "migration").is_dir():
    command += ["-v", str(stage / "migration") + ":/migration:ro"]
command += [args.image]
with (stage / "schema.log").open("w") as log:
    subprocess.run(
        command + ["python", "-m", "django", "migrate", "--noinput"],
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
check = """import django;django.setup()
from django.db import connection
with connection.cursor() as c:
 c.execute("SELECT current_database(),rolsuper,rolbypassrls,rolcreatedb FROM pg_roles WHERE rolname=current_user")
 r=c.fetchone();assert r[0].startswith("crm_restore_check_") and r[1:]==(False,False,False)
print("Isolated restored database role verified")"""
with (stage / "role.log").open("w") as log:
    subprocess.run(
        command + ["python", "-c", check],
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
if args.batch:
    with (stage / "verify.log").open("w") as log:
        subprocess.run(
            command
            + [
                "python",
                "-m",
                "django",
                "verify_suitecrm",
                "--org",
                args.org,
                "--batch",
                args.batch,
                "--report",
                "/restore/verify.json",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    report = json.loads((stage / "verify.json").read_text())
    assert report["verified"] and report["files"]["verified"] == 17
archive_digest = hashlib.sha256()
with Path(args.archive).open("rb") as incoming:
    for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
        archive_digest.update(chunk)
(stage / "result.json").write_text(
    json.dumps(
        {
            "verified": True,
            "archive_sha256": archive_digest.hexdigest(),
            "database": args.database,
            "org_id": args.org,
            "batch": args.batch,
        }
    )
)
(stage / "result.json").chmod(0o600)

print(
    "Backup restored and checked in isolated database"
    + (" including source rows and every restored file" if args.batch else "")
)
