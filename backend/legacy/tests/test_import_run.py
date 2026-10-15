"""End-to-end import contracts over a complete synthetic disk manifest."""

import hashlib
import json
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import override_settings

from accounts.models import Account, AccountEmail
from contacts.models import Contact
from invoices.models import Invoice, Payment
from legacy.importer.contracts import ImportConflict, ImportContext, set_org
from legacy.importer.reader import SnapshotReader
from legacy.models import LegacyImportBatch, LegacyProjection, LegacyRecord
from legacy.tests.helpers import make_snapshot, people_tables


def context(org, root):
    tables = people_tables("import-owner@example.invalid")
    tables["users"][0]["is_admin"] = 1
    tables.update(
        {
            "accounts": [
                {
                    "id": "1",
                    "name": "Repeated",
                    "created_by": "1",
                    "assigned_user_id": "1",
                },
                {"id": "001", "name": "Repeated", "created_by": "1"},
                {"id": "deleted", "name": "Deleted", "deleted": 1},
            ],
            "contacts": [
                {"id": "c1", "last_name": "One", "phone_work": "12345;".__mul__(20)},
                {"id": "c2", "last_name": "Two"},
            ],
            "leads": [
                {
                    "id": "l",
                    "first_name": "Converted",
                    "last_name": "Person",
                    "status": "Converted",
                }
            ],
            "opportunities": [
                {
                    "id": "o",
                    "name": "Unclassified",
                    "sales_stage": "Original label",
                    "amount": None,
                }
            ],
            "accounts_opportunities": [
                {"id": "r1", "account_id": "1", "opportunity_id": "o"},
                {"id": "r2", "account_id": "001", "opportunity_id": "o"},
                {"id": "r3", "account_id": "absent", "opportunity_id": "o"},
            ],
            "emails": [
                {
                    "id": "e",
                    "name": "Historical",
                    "status": "sent",
                    "type": "out",
                    "parent_type": "Accounts",
                    "parent_id": "1",
                }
            ],
            "emails_text": [
                {
                    "email_id": "e",
                    "description": "Original text",
                    "description_html": "<script>never()</script>",
                    "bcc_addrs": "hidden@example.invalid",
                }
            ],
            "calls": [
                {
                    "id": "planned",
                    "name": "Planned old call",
                    "status": "Planned",
                    "date_start": "2020-01-01 11:00:00",
                    "parent_type": "Accounts",
                    "parent_id": "1",
                },
                {
                    "id": "held",
                    "name": "Held old call",
                    "status": "Held",
                    "date_start": "2020-01-01 11:00:00",
                    "parent_type": "Accounts",
                    "parent_id": "1",
                },
            ],
            "aos_invoices": [
                {
                    "id": "invoice",
                    "name": "Paid evidence",
                    "status": "Paid",
                    "total_amount": None,
                    "total_amt": "123.45",
                }
            ],
            "sugarfeed": [
                {
                    "id": "feed-1",
                    "related_module": "Accounts",
                    "related_id": "1",
                    "description": "Same text",
                },
                {
                    "id": "feed-2",
                    "related_module": "Accounts",
                    "related_id": "1",
                    "description": "Same text",
                },
            ],
        }
    )
    tables["email_addresses"].append(
        {"id": "shared", "email_address": "same@example.invalid"}
    )
    tables["email_addr_bean_rel"].extend(
        {
            "id": "c" + str(n),
            "bean_module": "Contacts",
            "bean_id": "c" + str(n),
            "email_address_id": "shared",
            "primary_address": 1,
        }
        for n in (1, 2)
    )
    folder = make_snapshot(root, tables)
    upload = folder.parent / "upload"
    upload.mkdir()
    content = b"private synthetic file\n"
    (upload / "orphan.bin").write_bytes(content)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = [
        {
            "path": "orphan.bin",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    ]
    manifest_path.write_text(json.dumps(manifest))
    return ImportContext(org, SnapshotReader(folder))


def run(ctx, mode, **kwargs):
    from legacy.importer.runner import run_import

    try:
        return run_import(ctx, mode, **kwargs)
    finally:
        set_org(ctx.org.pk)


def test_prepare_has_no_business_writes_and_clears_context(org_a, tmp_path):
    from legacy.importer.runner import run_import

    ctx = context(org_a, tmp_path)
    report = run_import(ctx, "prepare")
    if connection.vendor == "postgresql":
        with connection.cursor() as c:
            c.execute("SELECT current_setting('app.current_org',true)")
            assert c.fetchone()[0] in ("", None)
    set_org(org_a.pk)
    assert report["prepared"] and not report["verified"]
    assert not LegacyRecord.objects.filter(org=org_a).exists()
    assert not Account.objects.filter(org=org_a).exists()
    assert LegacyImportBatch.objects.get(org=org_a).state == "PREPARED"


def test_second_apply_is_idempotent_and_no_side_effects(org_a, tmp_path):
    ctx = context(org_a, tmp_path / "snapshot")
    baseline = Account.objects.create(org=org_a, name="Existing target")
    with (
        override_settings(LEGACY_FILE_ROOT=tmp_path / "private"),
        patch("celery.app.task.Task.apply_async") as dispatch,
        patch("django.core.mail.EmailMessage.send") as mail,
    ):
        run(ctx, "prepare")
        first = run(ctx, "apply")
        ids = set(
            LegacyProjection.objects.filter(org=org_a).values_list(
                "target_model", "target_id", "role"
            )
        )
        second = run(ImportContext(org_a, SnapshotReader(ctx.reader.root)), "apply")
    assert first["verified"] and second["verified"]
    assert ids == set(
        LegacyProjection.objects.filter(org=org_a).values_list(
            "target_model", "target_id", "role"
        )
    )
    assert first["tables"] == second["tables"]
    assert Account.objects.filter(pk=baseline.pk, name="Existing target").exists()
    assert Contact.objects.filter(org=org_a).count() == 2
    assert Contact.objects.filter(org=org_a, email__isnull=False).count() == 1
    assert AccountEmail.objects.get(org=org_a).is_historical
    assert (
        not Invoice.objects.filter(org=org_a).exists()
        and not Payment.objects.filter(org=org_a).exists()
    )
    dispatch.assert_not_called()
    mail.assert_not_called()


def test_failed_phase_can_resume_without_duplicates(org_a, tmp_path):
    ctx = context(org_a, tmp_path / "snapshot")

    def fail(phase):
        if phase == "core":
            raise RuntimeError("injected")

    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        run(ctx, "prepare")
        with pytest.raises(RuntimeError, match="injected"):
            run(ctx, "apply", on_phase=fail)
        assert LegacyImportBatch.objects.get(org=org_a).checkpoint == "core"
        report = run(ImportContext(org_a, SnapshotReader(ctx.reader.root)), "resume")
    assert report["verified"]
    assert Account.objects.filter(org=org_a).count() == 2


def test_resume_detects_assignment_edit_without_overwrite(
    org_a, tmp_path, user_profile
):
    ctx = context(org_a, tmp_path / "snapshot")

    def fail(phase):
        if phase == "relations":
            raise RuntimeError("injected")

    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        run(ctx, "prepare")
        with pytest.raises(RuntimeError):
            run(ctx, "apply", on_phase=fail)
        account = Account.objects.get(pk=ctx.native_id("accounts", "1"))
        account.assigned_to.add(user_profile)
        with pytest.raises(ImportConflict):
            run(ImportContext(org_a, SnapshotReader(ctx.reader.root)), "resume")
    assert account.assigned_to.filter(pk=user_profile.pk).exists()


def test_apply_requires_prepare(org_a, tmp_path):
    ctx = context(org_a, tmp_path)
    with pytest.raises(ImportConflict):
        run(ctx, "apply")


def test_management_commands_write_private_reports_and_fail_verification(
    org_a, tmp_path
):
    import io
    import os

    from django.core.management import CommandError, call_command

    ctx = context(org_a, tmp_path / "snapshot")
    report_path = tmp_path / "report.json"
    stdout = io.StringIO()
    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        call_command(
            "import_suitecrm",
            "--snapshot",
            str(ctx.reader.root),
            "--org",
            str(org_a.pk),
            "--prepare",
            "--report",
            str(report_path),
            stdout=stdout,
        )
        set_org(org_a.pk)
        call_command(
            "import_suitecrm",
            "--snapshot",
            str(ctx.reader.root),
            "--org",
            str(org_a.pk),
            "--apply",
            "--report",
            str(report_path),
            stdout=stdout,
        )
        set_org(org_a.pk)
        batch = LegacyImportBatch.objects.get(org=org_a)
        call_command(
            "verify_suitecrm",
            "--org",
            str(org_a.pk),
            "--batch",
            str(batch.pk),
            "--report",
            str(report_path),
            stdout=stdout,
        )
        assert json.loads(report_path.read_text())["verified"]
        assert os.stat(report_path).st_mode & 0o777 == 0o600
        assert (
            "Repeated" not in stdout.getvalue()
            and "same@example.invalid" not in stdout.getvalue()
        )
        set_org(org_a.pk)
        Account.objects.filter(pk=Account.objects.filter(org=org_a).first().pk).update(
            name="User edit"
        )
        with pytest.raises(CommandError):
            call_command(
                "verify_suitecrm",
                "--org",
                str(org_a.pk),
                "--batch",
                str(batch.pk),
                "--report",
                str(report_path),
                stdout=stdout,
            )
        assert not json.loads(report_path.read_text())["verified"]
    set_org(org_a.pk)


def test_change_between_phases_is_not_adopted_as_imported_state(org_a, tmp_path):
    ctx = context(org_a, tmp_path / "snapshot")

    def edit(phase):
        if phase == "core":
            Account.objects.filter(org=org_a, name="Repeated").update(
                name="Concurrent user decision"
            )

    with override_settings(LEGACY_FILE_ROOT=tmp_path / "private"):
        run(ctx, "prepare")
        with pytest.raises(ImportConflict):
            run(ctx, "apply", on_phase=edit)
    assert Account.objects.filter(org=org_a, name="Concurrent user decision").exists()


def test_scheduled_jobs_do_not_dispatch_imported_history(org_a, tmp_path):
    from accounts.tasks import send_email
    from invoices.tasks import (
        check_expired_estimates,
        check_overdue_invoices,
        generate_recurring_invoices,
        process_payment_reminders,
    )
    from opportunity.tasks import check_goal_milestones, check_stale_opportunities
    from webhooks.models import WebhookDelivery
    from webhooks.tasks import dispatch_due_deliveries

    ctx = context(org_a, tmp_path / "snapshot")
    with (
        override_settings(LEGACY_FILE_ROOT=tmp_path / "private"),
        patch("celery.app.task.Task.apply_async") as dispatch,
        patch("django.core.mail.EmailMessage.send") as mail,
    ):
        run(ctx, "prepare")
        run(ctx, "apply")
        email = AccountEmail.objects.get(org=org_a)
        send_email.run(str(email.pk), str(org_a.pk))
        for job in (
            generate_recurring_invoices,
            check_overdue_invoices,
            process_payment_reminders,
            check_expired_estimates,
            check_stale_opportunities,
            check_goal_milestones,
            dispatch_due_deliveries,
        ):
            job.run()
        set_org(org_a.pk)
        assert not Invoice.objects.filter(org=org_a).exists()
        assert not Payment.objects.filter(org=org_a).exists()
        assert not WebhookDelivery.objects.filter(org=org_a).exists()
    dispatch.assert_not_called()
    mail.assert_not_called()
