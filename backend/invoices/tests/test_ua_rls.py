"""Run against the isolated PostgreSQL role that cannot bypass row policies."""

import pytest
from django.db import DatabaseError, connection, transaction

from invoices.tests.ua_helpers import company_payload

pytestmark = [pytest.mark.postgres_only, pytest.mark.django_db]
TABLES = [
    "legal_entity",
    "legal_entity_bank_account",
    "billing_document_sequence",
    "service_act",
    "service_act_line",
]


def test_billing_tables_have_forced_policies():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        assert cursor.fetchone() == (False, False)
        for table in TABLES:
            cursor.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=%s",
                [table],
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_policies WHERE tablename=%s", [table]
            )
            assert cursor.fetchone()[0] >= 2


def test_empty_and_foreign_context_hide_and_refuse_company(admin_client, org_a, org_b):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    from common.tasks import set_rls_context
    from common.testing import rls_org
    from invoices.models import LegalEntity

    entity = admin_client.post(
        "/api/invoices/billing/legal-entities/", company_payload(), format="json"
    ).data

    def context(value):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_org',%s,false)", [value])

    try:
        context("")
        assert not LegalEntity.objects.filter(pk=entity["id"]).exists()
        context(str(org_b.pk))
        assert not LegalEntity.objects.filter(pk=entity["id"]).exists()
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                LegalEntity.objects.create(
                    org=org_a,
                    legal_name="Forbidden",
                    registration_code="12345678",
                    entity_type="LLC",
                )
    finally:
        set_rls_context(org_a.pk)
    with rls_org(org_a):
        assert LegalEntity.objects.filter(pk=entity["id"]).exists()


def test_related_billing_rows_are_invisible_cross_org(admin_client, org_a, org_b):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    from accounts.models import Account
    from common.testing import rls_org
    from invoices.models import (
        DocumentSequence,
        Invoice,
        LegalEntityBankAccount,
        ServiceAct,
        ServiceActLine,
    )

    entity = admin_client.post(
        "/api/invoices/billing/legal-entities/", company_payload(), format="json"
    ).data
    from invoices.models import LegalEntity

    with rls_org(org_a):
        issuer = LegalEntity.objects.get(pk=entity["id"])
        bank = LegalEntityBankAccount.objects.create(
            org=org_a,
            entity=issuer,
            iban="UA273000010000000000000000001",
            bank_name="Test",
        )
        account = Account.objects.create(org=org_a, name="Test buyer")
        invoice = Invoice.objects.create(
            org=org_a, account=account, invoice_title="Original"
        )
        from invoices.models import InvoiceLineItem

        source = InvoiceLineItem.objects.create(
            org=org_a, invoice=invoice, name="Service", quantity="1", unit_price="1"
        )
        act = ServiceAct.objects.create(org=org_a, invoice=invoice, issuer=issuer)
        line = ServiceActLine.objects.create(
            org=org_a,
            act=act,
            source_line=source,
            quantity="1",
            name="Service",
            unit="послуга",
        )
    with rls_org(org_b):
        assert not LegalEntityBankAccount.objects.filter(pk=bank.pk).exists()
        assert not DocumentSequence.objects.filter(entity=issuer).exists()
        assert not ServiceAct.objects.filter(pk=act.pk).exists()
        assert not ServiceActLine.objects.filter(pk=line.pk).exists()


def test_issued_billing_rows_are_invisible_cross_org(admin_client, org_a, org_b):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    from common.testing import rls_org
    from invoices.models import (
        DocumentSequence,
        LegalEntityBankAccount,
        ServiceAct,
        ServiceActLine,
    )
    from invoices.tests.ua_helpers import act_payload, issued_invoice

    inv = issued_invoice(admin_client, org_a)
    act = admin_client.post(
        "/api/invoices/billing/acts/", act_payload(inv), format="json"
    )
    assert act.status_code == 201, act.content
    with rls_org(org_b):
        assert not LegalEntityBankAccount.objects.filter(
            entity_id=inv["issuer"]["id"]
        ).exists()
        assert not DocumentSequence.objects.filter(
            entity_id=inv["issuer"]["id"]
        ).exists()
        assert not ServiceAct.objects.filter(pk=act.data["id"]).exists()
        assert not ServiceActLine.objects.filter(act_id=act.data["id"]).exists()
