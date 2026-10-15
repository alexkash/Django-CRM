"""Synthetic, checksum-complete disk snapshots; no real customer data."""

import gzip
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_snapshot(root, tables):
    policy = (
        json.loads(
            (Path(__file__).parents[3] / "ops/suitecrm/table-policy.json").read_text()
        )
        if (Path(__file__).parents[3] / "ops/suitecrm/table-policy.json").exists()
        else json.loads(
            (Path(__file__).parents[1] / "importer/source_policy.json").read_text()
        )
    )
    root = Path(root)
    folder = root / "export"
    folder.mkdir(parents=True, exist_ok=True)
    sql = gzip.compress(b"-- synthetic source snapshot\n")
    (root / "source.sql.gz").write_bytes(sql)
    manifest = {
        "format_version": 1,
        "source_key": "suitecrm-coloris",
        "snapshot_sha256": hashlib.sha256(sql).hexdigest(),
        "captured_at_utc": "2026-10-15T10:00:00+00:00",
        "tables": {},
        "files": [],
        "safe_config": {"default_currency_iso4217": "USD"},
    }
    for table, rule in policy.items():
        values = tables.get(table, [])
        if rule["category"] == "sealed":
            manifest["tables"][table] = {
                "category": "sealed",
                "total": len(values),
                "active": len(values),
                "deleted": 0,
            }
            continue
        lines = []
        for i, original in enumerate(values):
            value = dict(original)
            value.setdefault("date_entered", "2017-01-08 11:20:00")
            value.setdefault("date_modified", "2020-01-08 11:20:00")
            key = str(value.get("id", value.get("id_c", i)))
            lines.append(
                canonical(
                    {
                        "table": table,
                        "source_id": key,
                        "values": value,
                        "row_sha256": hashlib.sha256(
                            canonical(value).encode()
                        ).hexdigest(),
                        "deleted": bool(value.get("deleted", 0)),
                    }
                )
            )
        content = ("\n".join(lines) + "\n" if lines else "").encode()
        (folder / (table + ".jsonl")).write_bytes(content)
        deleted = sum(bool(v.get("deleted", 0)) for v in values)
        manifest["tables"][table] = {
            "category": "history",
            "file": table + ".jsonl",
            "sha256": hashlib.sha256(content).hexdigest(),
            "total": len(values),
            "active": len(values) - deleted,
            "deleted": deleted,
            "excluded_columns": rule.get("exclude_columns", []),
        }
    (folder / "manifest.json").write_text(canonical(manifest))
    return folder


def make_context(org, root, tables):
    from legacy.importer.contracts import ImportContext
    from legacy.importer.reader import SnapshotReader

    ctx = ImportContext(org, SnapshotReader(make_snapshot(root, tables)))
    ctx.stage_history()
    return ctx


def people_tables(email):
    return {
        "users": [
            {
                "id": "1",
                "user_name": "legacy-admin",
                "first_name": "Legacy",
                "last_name": "Owner",
                "status": "Active",
                "is_admin": "0",
            }
        ],
        "email_addresses": [{"id": "u-email", "email_address": email}],
        "email_addr_bean_rel": [
            {
                "id": "u-link",
                "bean_id": "1",
                "bean_module": "Users",
                "email_address_id": "u-email",
                "primary_address": 1,
            }
        ],
    }
