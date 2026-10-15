"""Lossless, credential-filtered SuiteCRM snapshot export. Never executes PHP."""

from __future__ import annotations
import argparse
import base64
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tarfile


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "type": "bytes",
            "base64": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if isinstance(value, (datetime, date)):
        return (
            value.isoformat(sep=" ")
            if isinstance(value, datetime)
            else value.isoformat()
        )
    raise TypeError("Unsupported source value type: " + type(value).__name__)


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_value,
    )


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or "\x00" in str(relative):
        raise ValueError("Unsafe snapshot path")
    candidate = root / relative
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Snapshot symlink is forbidden")
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        raise ValueError("Snapshot path escapes its root") from None
    return candidate


def file_manifest(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Snapshot symlink root is forbidden")
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Snapshot symlink is forbidden")
        if path.is_file():
            relative = str(path.relative_to(root))
            safe_path(root, relative)
            result.append(
                {
                    "path": relative,
                    "size": path.stat().st_size,
                    "sha256": digest_file(path),
                }
            )
    return result


def check_files_unchanged(before, after):
    if before != after:
        raise ValueError("Snapshot files changed during capture")


def validate_policy(policy, tables):
    unknown = set(tables) - set(policy)
    missing = set(policy) - set(tables)
    if unknown or missing:
        raise ValueError(
            "Snapshot schema differs from reviewed table policy: "
            + repr(sorted(unknown | missing))
        )
    if any(x.get("category") not in ("history", "sealed") for x in policy.values()):
        raise ValueError("Invalid table coverage category")


def export_rows(table, rows, primary_keys, path, policy=None):
    policy = policy or {}
    excluded = set(policy.get("exclude_columns", []))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    occurrences = defaultdict(int)
    counts = {"total": 0, "active": 0, "deleted": 0}
    with path.open("w", encoding="utf-8") as handle:
        for raw in rows:
            raw = dict(raw)
            values = {key: value for key, value in raw.items() if key not in excluded}
            encoded = canonical_json(values)
            row_hash = hashlib.sha256(encoded.encode()).hexdigest()
            if len(primary_keys) == 1:
                source_id = str(raw[primary_keys[0]])
            elif primary_keys:
                source_id = canonical_json([raw[k] for k in primary_keys])
            else:
                occurrences[row_hash] += 1
                source_id = "rowhash:" + row_hash + ":" + str(occurrences[row_hash])
            deleted = bool(int(raw.get("deleted") or 0))
            record = {
                "table": table,
                "source_id": source_id,
                "values": values,
                "row_sha256": row_hash,
                "deleted": deleted,
            }
            handle.write(canonical_json(record) + "\n")
            counts["total"] += 1
            counts["deleted" if deleted else "active"] += 1
    path.chmod(0o600)
    return {
        **counts,
        "file": path.name,
        "sha256": digest_file(path),
        "category": "history",
        "excluded_columns": sorted(excluded),
    }


def sql_identifier(name):
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError("Unsafe SQL identifier")
    return "`" + name + "`"


def export_snapshot(connection, output_dir, policy):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,COLUMN_TYPE,COLUMN_KEY,ORDINAL_POSITION,CHARACTER_SET_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION"
        )
        columns = list(cursor.fetchall())
    schema = {}
    for column in columns:
        schema.setdefault(column["TABLE_NAME"], []).append(column)
    validate_policy(policy, schema)
    manifest = {
        "format_version": 1,
        "source_key": "suitecrm-coloris",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema": schema,
        "tables": {},
    }
    for table, cols in schema.items():
        table_sql = sql_identifier(table)
        with connection.cursor() as cursor:
            if policy[table]["category"] == "sealed":
                active = (
                    "COALESCE(SUM(deleted=0),0)"
                    if any(x["COLUMN_NAME"] == "deleted" for x in cols)
                    else "COUNT(*)"
                )
                cursor.execute(
                    "SELECT COUNT(*) total," + active + " active FROM " + table_sql
                )
                row = cursor.fetchone()
                manifest["tables"][table] = {
                    "category": "sealed",
                    "total": int(row["total"]),
                    "active": int(row["active"]),
                    "deleted": int(row["total"]) - int(row["active"]),
                }
                continue
            pks = [x["COLUMN_NAME"] for x in cols if x["COLUMN_KEY"] == "PRI"]
            expressions = []
            for col in cols:
                name = sql_identifier(col["COLUMN_NAME"])
                if col["DATA_TYPE"] in (
                    "decimal",
                    "numeric",
                    "date",
                    "datetime",
                    "timestamp",
                    "time",
                ):
                    expressions.append("CAST(" + name + " AS CHAR) AS " + name)
                else:
                    expressions.append(name)
            order = (
                " ORDER BY " + ",".join(sql_identifier(k) for k in pks) if pks else ""
            )
            cursor.execute(
                "SELECT " + ",".join(expressions) + " FROM " + table_sql + order
            )
            manifest["tables"][table] = export_rows(
                table, iter(cursor), pks, output_dir / (table + ".jsonl"), policy[table]
            )
    manifest["schema_sha256"] = hashlib.sha256(
        canonical_json(schema).encode()
    ).hexdigest()
    (output_dir / "manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )
    (output_dir / "manifest.json").chmod(0o600)
    return manifest


def archive_tree(root, metadata=False):
    root = Path(root)
    allowed = (
        [
            "custom/Extension/modules",
            "custom/modules",
            "custom/include/language",
            "include/language",
        ]
        if metadata
        else ["."]
    )
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
        for part in allowed:
            folder = root / part
            if not folder.exists():
                continue
            for record in file_manifest(folder):
                path = folder / record["path"]
                archive.add(path, arcname=str(path.relative_to(root)), recursive=False)


def safe_config(root):
    content = (Path(root) / "config.php").read_text(errors="strict")
    result = {}
    for key in [
        "default_timezone",
        "default_currency_iso4217",
        "default_currency_name",
        "default_currency_symbol",
    ]:
        found = re.search(r"['\"]" + key + r"['\"]\s*=>\s*(['\"])(.*?)\1", content)
        if found:
            result[key] = found.group(2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-files")
    parser.add_argument("--archive-files")
    parser.add_argument("--archive-metadata")
    parser.add_argument("--safe-config")
    parser.add_argument("--output")
    parser.add_argument("--policy")
    parser.add_argument("--capture")
    args = parser.parse_args()
    if args.manifest_files:
        print(canonical_json(file_manifest(args.manifest_files)))
        return
    if args.archive_files:
        archive_tree(args.archive_files)
        return
    if args.archive_metadata:
        archive_tree(args.archive_metadata, True)
        return
    if args.safe_config:
        print(canonical_json(safe_config(args.safe_config)))
        return
    if not (args.output and args.policy and args.capture):
        parser.error("export requires output, policy and capture")
    import pymysql

    os.umask(0o077)
    connection = pymysql.connect(
        host=os.environ["SNAPSHOT_DB_HOST"],
        user=os.environ["SNAPSHOT_DB_USER"],
        password=os.environ["SNAPSHOT_DB_PASSWORD"],
        database="suitecrmdb",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.SSDictCursor,
    )
    try:
        manifest = export_snapshot(
            connection, args.output, json.loads(Path(args.policy).read_text())
        )
    finally:
        connection.close()
    capture = json.loads(Path(args.capture).read_text())
    manifest.update(capture)
    manifest["snapshot_sha256"] = capture["sql_sha256"]
    (Path(args.output) / "manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )
    print(
        canonical_json(
            {
                "tables": len(manifest["tables"]),
                "history_rows": sum(
                    t["total"]
                    for t in manifest["tables"].values()
                    if t["category"] == "history"
                ),
                "snapshot_sha256": manifest["snapshot_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
