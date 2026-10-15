import importlib

import pytest

from legacy.tests.helpers import make_snapshot


def test_stable_id_preserves_source_identity():
    try:
        stable_id = importlib.import_module("legacy.importer.identity").stable_id
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "Deterministic migration identities not implemented"
        ) from exc
    assert stable_id("contacts", "1") != stable_id("contacts", "001")
    assert stable_id("contacts", "1") != stable_id("leads", "1")
    assert stable_id("contacts", "1") == stable_id("contacts", "1")
    assert stable_id("contacts", "1", "native") != stable_id("contacts", "1", "history")


def test_snapshot_rejects_changed_input_before_db_write(tmp_path):
    try:
        Reader = importlib.import_module("legacy.importer.reader").SnapshotReader
    except ModuleNotFoundError as exc:
        raise AssertionError("Snapshot integrity reader not implemented") from exc
    folder = make_snapshot(tmp_path, {"accounts": [{"id": "001", "name": "Acme"}]})
    with (folder / "accounts.jsonl").open("a") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError):
        Reader(folder)


def test_same_sql_with_changed_manifest_cannot_rebind_source(org_a, tmp_path):
    import json

    from legacy.importer.contracts import ImportConflict, ImportContext
    from legacy.importer.reader import SnapshotReader
    from legacy.tests.helpers import make_context

    ctx = make_context(org_a, tmp_path, {})
    path = ctx.reader.root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["safe_config"]["default_currency_iso4217"] = "EUR"
    path.write_text(json.dumps(manifest))
    ctx.reader.close()
    (ctx.reader.root / ".suitecrm-index-v1.sqlite3").unlink()
    with pytest.raises(ImportConflict):
        ImportContext(org_a, SnapshotReader(ctx.reader.root))
