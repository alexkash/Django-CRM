from django.db import transaction
from django.utils import timezone

from invoices.tests.ua_helpers import company_payload


def test_separate_sequences_and_locked_prefix(admin_client, org_a):
    from invoices.billing.numbering import next_document_number
    from invoices.models import LegalEntity

    first = admin_client.post(
        "/api/invoices/billing/legal-entities/", company_payload(), format="json"
    ).data
    second = admin_client.post(
        "/api/invoices/billing/legal-entities/",
        company_payload(legal_name="Other"),
        format="json",
    ).data
    with transaction.atomic():
        a = LegalEntity.objects.get(pk=first["id"])
        b = LegalEntity.objects.get(pk=second["id"])
        assert next_document_number(org=org_a, entity=a, kind="INVOICE") == "РХ-000001"
        assert next_document_number(org=org_a, entity=b, kind="INVOICE") == "РХ-000001"
        assert next_document_number(org=org_a, entity=a, kind="ACT") == "АКТ-000001"
        assert next_document_number(org=org_a, entity=a, kind="INVOICE") == "РХ-000002"
    assert (
        admin_client.patch(
            "/api/invoices/billing/legal-entities/" + first["id"] + "/",
            {"invoice_prefix": "NEW-"},
            format="json",
        ).status_code
        == 400
    )


def test_legacy_allocator_ignores_ua_prefixes(admin_client, org_a):
    from invoices.models import Invoice, LegalEntity

    entity = admin_client.post(
        "/api/invoices/billing/legal-entities/", company_payload(), format="json"
    ).data
    issuer = LegalEntity.objects.get(pk=entity["id"])
    prefix = f"INV-{timezone.localdate():%Y%m%d}-"
    Invoice.objects.create(
        org=org_a, issuer=issuer, invoice_title="UA", invoice_number=prefix + "X000001"
    )
    Invoice.objects.create(
        org=org_a,
        issuer=issuer,
        invoice_title="UA",
        invoice_number=prefix + "123000001",
    )
    generic = Invoice.objects.create(org=org_a, invoice_title="Generic")
    assert generic.invoice_number == prefix + "0001"
