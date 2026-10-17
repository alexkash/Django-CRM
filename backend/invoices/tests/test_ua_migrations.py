"""The additive schema preserves generic invoice numbers and is reversible empty."""

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from common.testing import rls_org


@pytest.mark.django_db(transaction=True)
def test_ua_migration_preserves_generic_invoice():
    if settings.MIGRATION_MODULES:
        pytest.skip("Run this migration test without --no-migrations")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    before = [
        ("common", "0051_add_uah_currency"),
        ("invoices", "0015_add_uah_currency"),
        ("accounts", "0010_add_uah_currency"),
    ]
    after = [
        ("common", "0051_add_uah_currency"),
        ("invoices", "0017_ua_billing_rls"),
        ("accounts", "0011_account_billing_details"),
    ]
    try:
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        org = apps.get_model("common", "Org").objects.create(name="Migration Org")
        with rls_org(org):
            account = apps.get_model("accounts", "Account").objects.create(
                name="Migration Client", org=org
            )
            invoice = apps.get_model("invoices", "Invoice").objects.create(
                org=org,
                account=account,
                invoice_title="Original",
                invoice_number="INV-ORIGINAL",
            )
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            saved = apps.get_model("invoices", "Invoice").objects.get(pk=invoice.pk)
            assert saved.invoice_number == "INV-ORIGINAL"
            assert saved.issuer_id is None
            assert saved.print_snapshot == {}
            assert (
                apps.get_model("accounts", "Account")
                .objects.get(pk=account.pk)
                .legal_name
                == ""
            )
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            old = (
                executor.loader.project_state(before)
                .apps.get_model("invoices", "Invoice")
                .objects.get(pk=invoice.pk)
            )
            assert old.invoice_number == "INV-ORIGINAL"
    finally:
        MigrationExecutor(connection).migrate(latest)
