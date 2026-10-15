"""Lossless encoding and snapshot containment at the migration boundary."""

import base64
import importlib
import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


def subject():
    try:
        return importlib.import_module("ops.suitecrm.export")
    except ModuleNotFoundError as exc:
        raise AssertionError("SuiteCRM snapshot exporter is not implemented") from exc


class ExportTests(unittest.TestCase):
    def test_export_preserves_decimal_null_and_zero_date(self):
        row = {
            "amount": Decimal("123456789.123456"),
            "nullable": None,
            "zero_date": "0000-00-00",
            "body": "Київ\nПривіт",
            "blob": b"\x00\xff",
        }
        decoded = json.loads(subject().canonical_json(row))
        self.assertEqual(decoded["amount"], "123456789.123456")
        self.assertIsNone(decoded["nullable"])
        self.assertEqual(decoded["zero_date"], "0000-00-00")
        self.assertEqual(decoded["body"], "Київ\nПривіт")
        self.assertEqual(base64.b64decode(decoded["blob"]["base64"]), b"\x00\xff")

    def test_duplicate_keyless_rows_are_not_collapsed(self):
        with TemporaryDirectory() as tmp:
            result = subject().export_rows(
                "audit",
                [{"value": "same"}, {"value": "same"}],
                [],
                Path(tmp) / "rows.jsonl",
            )
            rows = [
                json.loads(x)
                for x in (Path(tmp) / "rows.jsonl").read_text().splitlines()
            ]
            self.assertEqual(result["total"], 2)
            self.assertNotEqual(rows[0]["source_id"], rows[1]["source_id"])
            again = subject().export_rows(
                "audit",
                [{"value": "same"}, {"value": "same"}],
                [],
                Path(tmp) / "again.jsonl",
            )
            self.assertEqual(result["sha256"], again["sha256"])

    def test_source_ids_keep_leading_zeroes(self):
        with TemporaryDirectory() as tmp:
            subject().export_rows(
                "contacts",
                [{"id": "1"}, {"id": "001"}],
                ["id"],
                Path(tmp) / "rows.jsonl",
            )
            rows = [
                json.loads(x)
                for x in (Path(tmp) / "rows.jsonl").read_text().splitlines()
            ]
            self.assertEqual([x["source_id"] for x in rows], ["1", "001"])

    def test_unknown_table_blocks_export(self):
        with self.assertRaises(ValueError):
            subject().validate_policy({"accounts": {}}, ["accounts", "surprise"])

    def test_symlink_and_traversal_are_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "upload"
            root.mkdir()
            outside = Path(tmp) / "secret"
            outside.write_text("private")
            (root / "link").symlink_to(outside)
            with self.assertRaises(ValueError):
                subject().file_manifest(root)
            with self.assertRaises(ValueError):
                subject().safe_path(root, "../secret")

    def test_changed_file_blocks_snapshot(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "file").write_bytes(b"first")
            before = subject().file_manifest(root)
            (root / "file").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                subject().check_files_unchanged(before, subject().file_manifest(root))

    def test_users_secret_fields_do_not_reach_business_rows(self):
        with TemporaryDirectory() as tmp:
            policy = {
                "category": "history",
                "exclude_columns": ["user_hash", "pwd_last_changed"],
            }
            subject().export_rows(
                "users",
                [
                    {
                        "id": "1",
                        "user_name": "admin",
                        "user_hash": "SECRET-PASSWORD",
                        "pwd_last_changed": "secret-date",
                    }
                ],
                ["id"],
                Path(tmp) / "rows.jsonl",
                policy,
            )
            data = (Path(tmp) / "rows.jsonl").read_text()
            self.assertNotIn("SECRET-PASSWORD", data)
            self.assertNotIn("secret-date", data)
            self.assertIn("admin", data)


if __name__ == "__main__":
    unittest.main()
