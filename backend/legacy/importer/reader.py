"""Verify every input before writes; use a disk index instead of loading 200k rows."""

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .identity import SOURCE_KEY, fingerprint


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_file(root, key):
    root = Path(root).resolve()
    relative = Path(key)
    if relative.is_absolute() or ".." in relative.parts or "\x00" in str(relative):
        raise ValueError("Unsafe snapshot path")
    path = root / relative
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Snapshot symlink is forbidden")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Snapshot path escapes its root")
    return path


class SnapshotReader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.manifest = json.loads(safe_file(self.root, "manifest.json").read_text())
        self.policy = json.loads(
            (Path(__file__).parent / "source_policy.json").read_text()
        )
        if (
            self.manifest.get("format_version") != 1
            or self.manifest.get("source_key") != SOURCE_KEY
        ):
            raise ValueError("Unsupported snapshot identity or format")
        if set(self.manifest["tables"]) != set(self.policy):
            raise ValueError("Snapshot table coverage differs from reviewed policy")
        sql = safe_file(self.root.parent, "source.sql.gz")
        if file_hash(sql) != self.manifest["snapshot_sha256"]:
            raise ValueError("SQL snapshot hash mismatch")
        if (
            "schema_sha256" in self.manifest
            and fingerprint(self.manifest["schema"]) != self.manifest["schema_sha256"]
        ):
            raise ValueError("Snapshot schema checksum mismatch")
        for table, entry in self.manifest["tables"].items():
            if entry["category"] != self.policy[table]["category"]:
                raise ValueError("Snapshot table category mismatch")
            if entry["category"] == "history":
                if entry["file"] != table + ".jsonl":
                    raise ValueError("Unexpected table file")
                if file_hash(safe_file(self.root, entry["file"])) != entry["sha256"]:
                    raise ValueError("Snapshot data hash mismatch: " + table)
        self.manifest_hash = fingerprint(self.manifest)
        self.db = self._index()

    def _index(self):
        cache = safe_file(self.root, ".suitecrm-index-v1.sqlite3")
        if cache.exists():
            db = sqlite3.connect(cache)
            try:
                header = db.execute(
                    "SELECT value FROM metadata WHERE key=?", ("manifest_hash",)
                ).fetchone()
                if not header or header[0] != self.manifest_hash:
                    raise ValueError("Snapshot index belongs to different input")
                return db
            except Exception:
                db.close()
                raise
        fd, name = tempfile.mkstemp(prefix=".suitecrm-index-", dir=self.root)
        os.close(fd)
        db = sqlite3.connect(name)
        try:
            db.execute(
                "CREATE TABLE rows(table_name TEXT,source_id TEXT,raw TEXT,deleted INTEGER,PRIMARY KEY(table_name,source_id))"
            )
            db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")
            for table, entry in self.manifest["tables"].items():
                if entry["category"] != "history":
                    continue
                total = deleted = 0
                excluded = set(self.policy[table].get("exclude_columns", []))
                with safe_file(self.root, entry["file"]).open() as handle:
                    for line in handle:
                        row = json.loads(line)
                        if row["table"] != table or not isinstance(
                            row["source_id"], str
                        ):
                            raise ValueError("Invalid source row identity")
                        if excluded.intersection(row["values"]):
                            raise ValueError(
                                "Credential column reached business export"
                            )
                        if fingerprint(row["values"]) != row["row_sha256"]:
                            raise ValueError("Source row checksum mismatch")
                        db.execute(
                            "INSERT INTO rows VALUES(?,?,?,?)",
                            (table, row["source_id"], line, int(row["deleted"])),
                        )
                        total += 1
                        deleted += int(row["deleted"])
                if (total, deleted) != (entry["total"], entry["deleted"]):
                    raise ValueError("Snapshot row count mismatch")
            db.execute(
                "INSERT INTO metadata VALUES(?,?)",
                ("manifest_hash", self.manifest_hash),
            )
            db.commit()
            db.close()
            os.replace(name, cache)
            cache.chmod(0o600)
            return sqlite3.connect(cache)
        except Exception:
            db.close()
            Path(name).unlink(missing_ok=True)
            raise

    def rows(self, table, active_only=False):
        if table not in self.policy:
            raise ValueError("Unknown source table")
        query = (
            "SELECT raw FROM rows WHERE table_name=?"
            + (" AND deleted=0" if active_only else "")
            + " ORDER BY source_id"
        )
        for item in self.db.execute(query, (table,)):
            yield json.loads(item[0])

    def get(self, table, source_id):
        if source_id in (None, ""):
            return None
        item = self.db.execute(
            "SELECT raw FROM rows WHERE table_name=? AND source_id=?",
            (table, str(source_id)),
        ).fetchone()
        return json.loads(item[0]) if item else None

    def close(self):
        self.db.close()
