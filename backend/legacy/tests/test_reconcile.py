from django.test import override_settings

from accounts.models import Account
from legacy.importer.contracts import set_org
from legacy.models import LegacyRecord, LegacyRelation
from legacy.tests.test_import_run import context, run


def test_every_snapshot_table_and_file_is_reconciled(org_a, tmp_path):
    from legacy.importer.reconcile import reconcile

    ctx = context(org_a, tmp_path / "snapshot")
    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        run(ctx, "prepare")
        run(ctx, "apply")
        report = reconcile(ctx)
    assert set(report["tables"]) == set(ctx.reader.manifest["tables"])
    assert report["org_id"] == str(org_a.pk)
    assert report["source_key"] == ctx.source.key
    assert report["verified"] and report["new_orphans"] == 0
    assert report["source_orphans"]["missing"] == 1
    assert report["files"]["verified"] == 1
    assert report["file_hash_mismatches"] == []
    assert report["tables"]["sugarfeed"]["history_total"] == 2
    for table, row in report["tables"].items():
        assert (
            row["native_active"]
            + row["history_only_active"]
            + row["deleted_history"]
            + row["sealed"]
            == row["source_total"]
        ), table
    set_org(org_a.pk)


def test_changed_payload_or_removed_relation_cannot_verify(org_a, tmp_path):
    from legacy.importer.reconcile import reconcile

    ctx = context(org_a, tmp_path / "snapshot")
    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        run(ctx, "prepare")
        run(ctx, "apply")
        LegacyRecord.objects.filter(
            source=ctx.source, source_table="accounts", source_pk="1"
        ).update(payload={"name": "tampered"})
        LegacyRelation.objects.filter(
            source=ctx.source, role="account"
        ).first().delete()
        report = reconcile(ctx)
    assert not report["verified"]
    assert report["history_mismatches"] and report["relation_mismatches"]


def test_user_edit_is_reported_without_overwrite(org_a, tmp_path):
    from legacy.importer.reconcile import reconcile

    ctx = context(org_a, tmp_path / "snapshot")
    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        run(ctx, "prepare")
        run(ctx, "apply")
        pk = ctx.native_id("accounts", "1")
        Account.objects.filter(pk=pk).update(name="User decision")
        report = reconcile(ctx)
    assert not report["verified"] and report["conflicts"]
    assert Account.objects.get(pk=pk).name == "User decision"
