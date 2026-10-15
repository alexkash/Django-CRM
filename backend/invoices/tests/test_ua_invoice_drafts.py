import pytest

from invoices.tests.ua_helpers import create_invoice, invoice_payload


def test_ua_draft_retains_issuer_units_and_decimal_totals(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    assert inv["issuer"]["legal_name"] == "ТОВ Тестові Послуги"
    assert inv["invoice_number"].startswith("DRAFT-")
    assert inv["subtotal"] == "12000.00"
    assert inv["tax_amount"] == "2400.00"
    assert inv["total_amount"] == "14400.00"
    assert inv["line_items"][0]["unit"] == "місяць"
    assert inv["line_items"][0]["tax_amount"] == "2400.00"
    assert inv["public_link_enabled"] is False
    assert inv["reminder_enabled"] is False
    from invoices.models import DocumentSequence

    assert not DocumentSequence.objects.filter(
        entity_id=inv["issuer"]["id"], last_value__gt=0
    ).exists()


@pytest.mark.parametrize(
    "extra",
    [
        {"shipping_amount": "1"},
        {"discount_value": "1"},
        {"currency": "EUR"},
        {"public_link_enabled": True},
        {"reminder_enabled": True},
    ],
)
def test_ua_draft_rejects_unsupported_financial_modes(admin_client, org_a, extra):
    body = invoice_payload(admin_client, org_a, **extra)
    response = admin_client.post("/api/invoices/", body, format="json")
    assert response.status_code == 400, response.content


def test_ua_cannot_be_demoted_and_bank_must_match_issuer(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    assert (
        admin_client.put(
            "/api/invoices/" + inv["id"] + "/", {"issuer_id": None}, format="json"
        ).status_code
        == 400
    )
    other = invoice_payload(admin_client, org_a)
    response = admin_client.put(
        "/api/invoices/" + inv["id"] + "/",
        {"bank_account_id": other["bank_account_id"]},
        format="json",
    )
    assert response.status_code == 400


def test_non_payer_print_mode_does_not_mean_zero_rate_payer(admin_client, org_a):
    body = invoice_payload(admin_client, org_a, tax_rate="0")
    assert (
        admin_client.patch(
            "/api/invoices/billing/legal-entities/" + body["issuer_id"] + "/",
            {"vat_status": "NON_PAYER", "default_vat_rate": "0"},
            format="json",
        ).status_code
        == 200
    )
    inv = admin_client.post("/api/invoices/", body, format="json").data["invoice"]
    assert inv["vat_status"] == "NON_PAYER"
    assert inv["tax_amount"] == "0.00"
    assert inv["total_amount"] == "12000.00"


def test_foreign_or_hidden_payer_is_rejected(admin_client, user_client, org_a, org_b):
    from accounts.models import Account
    from conftest import rls_org

    body = invoice_payload(admin_client, org_a)
    with rls_org(org_b):
        foreign = Account.objects.create(org=org_b, name="Foreign Payer")
    body["payer_id"] = str(foreign.pk)
    assert admin_client.post("/api/invoices/", body, format="json").status_code == 400


@pytest.mark.parametrize("status", ["Draft", "Sent", "Paid"])
def test_existing_generic_invoice_cannot_change_document_mode(
    admin_client, org_a, status
):
    from decimal import Decimal

    from invoices.models import Invoice

    body = invoice_payload(admin_client, org_a)
    invoice = Invoice.objects.create(
        org=org_a,
        account_id=body["account_id"],
        contact_id=body["contact_id"],
        invoice_title="Existing generic invoice",
        currency="UAH",
        tax_rate=Decimal("20.00"),
        status=status,
        public_link_enabled=True,
    )
    number = invoice.invoice_number
    url = f"/api/invoices/{invoice.pk}/"
    response = admin_client.put(
        url,
        {"issuer_id": body["issuer_id"], "bank_account_id": body["bank_account_id"]},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "issuer_id" in response.data["errors"]
    invoice.refresh_from_db()
    assert invoice.issuer_id is None
    assert invoice.bank_account_id is None
    assert invoice.status == status
    assert invoice.invoice_number == number
    assert invoice.public_link_enabled is True
    assert admin_client.get(url).data["invoice"]["issuer"] is None
