from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from invoices.tests.ua_helpers import create_invoice, issued_invoice


def test_draft_cannot_be_sent_or_paid_before_issue(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    base = "/api/invoices/" + inv["id"] + "/"
    assert admin_client.post(base + "send/", {}, format="json").status_code == 400
    assert admin_client.post(base + "mark-paid/", {}, format="json").status_code == 400
    assert (
        admin_client.post(
            base + "payments/",
            {
                "amount": "1",
                "payment_date": "2027-01-01",
                "payment_method": "BANK_TRANSFER",
            },
            format="json",
        ).status_code
        == 400
    )
    from invoices.models import Payment

    assert not Payment.objects.filter(invoice_id=inv["id"]).exists()


@pytest.mark.parametrize("overdue", [False, True])
def test_deleting_last_payment_never_unissues_document(admin_client, org_a, overdue):
    from datetime import timedelta

    due = (timezone.localdate() + timedelta(days=-1 if overdue else 30)).isoformat()
    inv = issued_invoice(admin_client, org_a, due_date=due)
    base = "/api/invoices/" + inv["id"] + "/"
    assert admin_client.post(base + "mark-paid/", {}, format="json").status_code == 200
    from invoices.models import Invoice, Payment

    paid = Invoice.objects.get(pk=inv["id"])
    before = (
        paid.invoice_number,
        paid.issued_at,
        paid.pdf_clean_sha256,
        paid.pdf_stamped_sha256,
    )
    payment = Payment.objects.get(invoice=paid)
    assert (
        admin_client.delete(base + "payments/" + str(payment.pk) + "/").status_code
        == 200
    )
    paid.refresh_from_db()
    assert paid.status == ("Overdue" if overdue else "Sent")
    assert (
        paid.invoice_number,
        paid.issued_at,
        paid.pdf_clean_sha256,
        paid.pdf_stamped_sha256,
    ) == before


def test_duplicate_retains_issuer_units_and_contract_but_resets_period(
    admin_client, org_a
):
    inv = issued_invoice(admin_client, org_a)
    response = admin_client.post(
        "/api/invoices/" + inv["id"] + "/duplicate/", {}, format="json"
    )
    assert response.status_code == 201, response.content
    copy = response.data["invoice"]
    assert copy["issuer"]["id"] == inv["issuer"]["id"]
    assert copy["bank_account"]["id"] == inv["bank_account"]["id"]
    assert copy["contract_number"] == "TEST-2027"
    assert copy["service_period_start"] is None
    assert copy["service_period_end"] is None
    assert copy["issued_at"] is None
    assert copy["invoice_number"].startswith("DRAFT-")
    assert copy["line_items"][0]["unit"] == "місяць"
    assert copy["amount_paid"] == "0.00"
    assert copy["closure"]["closed_total"] == "0.00"


def test_anonymous_routes_cannot_publish_ua_even_if_flag_is_changed(
    admin_client, unauthenticated_client, org_a
):
    inv = issued_invoice(admin_client, org_a)
    from invoices.models import Invoice

    obj = Invoice.objects.get(pk=inv["id"])
    Invoice.objects.filter(pk=obj.pk).update(public_link_enabled=True)
    for suffix in ["", "pdf/"]:
        result = unauthenticated_client.get(
            "/api/public/invoice/" + obj.public_token + "/" + suffix
        )
        assert result.status_code == 404


def test_issued_send_uses_frozen_pdf(admin_client, org_a):
    inv = issued_invoice(admin_client, org_a)
    with patch("invoices.api_views.send_invoice_to_client.delay"):
        assert (
            admin_client.post(
                "/api/invoices/" + inv["id"] + "/send/", {}, format="json"
            ).status_code
            == 200
        )
    from invoices.models import Invoice
    from invoices.pdf import generate_invoice_pdf

    obj = Invoice.objects.get(pk=inv["id"])
    before = generate_invoice_pdf(obj)
    obj.issuer.legal_name = "Changed"
    obj.issuer.save()
    assert generate_invoice_pdf(obj) == before


def test_standalone_line_api_cannot_add_ua_discounts(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    base = "/api/invoices/" + inv["id"] + "/line-items/"
    response = admin_client.post(
        base,
        {
            "name": "Discounted",
            "unit_price": "10",
            "quantity": "1",
            "discount_value": "1",
            "discount_type": "FIXED",
        },
        format="json",
    )
    assert response.status_code == 400


def test_admin_model_payment_cannot_bypass_issue(admin_client, org_a):
    from django.core.exceptions import ValidationError

    from invoices.models import Invoice, Payment

    inv = create_invoice(admin_client, org_a)
    invoice = Invoice.objects.get(pk=inv["id"])
    with pytest.raises(ValidationError):
        Payment.objects.create(
            org=org_a,
            invoice=invoice,
            amount=Decimal(1),
            payment_date=timezone.localdate(),
            payment_method="BANK_TRANSFER",
        )
    assert not Payment.objects.filter(invoice=invoice).exists()


def test_standalone_ua_line_response_matches_saved_half_up_vat(admin_client, org_a):
    inv = create_invoice(admin_client, org_a, tax_rate="50")
    response = admin_client.post(
        "/api/invoices/" + inv["id"] + "/line-items/",
        {"name": "Tiny", "quantity": "1", "unit_price": "0.05"},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.data["line_item"]["tax_amount"] == "0.03"


def test_issue_rechecks_tax_status_after_company_change(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    assert (
        admin_client.patch(
            "/api/invoices/billing/legal-entities/" + inv["issuer"]["id"] + "/",
            {"vat_status": "NON_PAYER", "default_vat_rate": "0"},
            format="json",
        ).status_code
        == 200
    )
    response = admin_client.post(
        "/api/invoices/" + inv["id"] + "/issue/", {}, format="json"
    )
    assert response.status_code == 400


def test_draft_pdf_cannot_read_hidden_current_customer_requisites(
    admin_client, user_client, user_profile, org_a
):
    inv = create_invoice(admin_client, org_a)
    from invoices.models import Invoice

    Invoice.objects.get(pk=inv["id"]).assigned_to.add(user_profile)
    response = user_client.get("/api/invoices/" + inv["id"] + "/pdf/")
    assert response.status_code == 404


def test_standalone_line_overflow_is_validation_error_without_partial_write(
    admin_client, org_a
):
    inv = create_invoice(admin_client, org_a)
    response = admin_client.post(
        "/api/invoices/" + inv["id"] + "/line-items/",
        {"name": "Overflow", "quantity": "1", "unit_price": "9999999999.99"},
        format="json",
    )
    assert response.status_code == 400, response.content
    from invoices.models import Invoice

    current = Invoice.objects.get(pk=inv["id"])
    assert current.line_items.count() == 1
    assert str(current.total_amount) == "14400.00"


def test_header_tax_change_overflow_is_validation_error(admin_client, org_a):
    inv = create_invoice(
        admin_client,
        org_a,
        line_items=[
            {
                "name": "Large",
                "quantity": "1",
                "unit": "послуга",
                "unit_price": "7500000000.00",
            }
        ],
    )
    response = admin_client.put(
        "/api/invoices/" + inv["id"] + "/", {"tax_rate": "100.00"}, format="json"
    )
    assert response.status_code == 400, response.content
    from invoices.models import Invoice

    current = Invoice.objects.get(pk=inv["id"])
    assert str(current.tax_rate) == "20.00"
    assert str(current.total_amount) == "9000000000.00"


def test_copy_of_maximum_length_title_stays_a_valid_draft(admin_client, org_a):
    from invoices.models import Invoice

    title = "П" * Invoice._meta.get_field("invoice_title").max_length
    inv = create_invoice(admin_client, org_a, invoice_title=title)
    response = admin_client.post(
        f"/api/invoices/{inv['id']}/duplicate/", {}, format="json"
    )
    assert response.status_code == 201, response.content
    copy = Invoice.objects.get(pk=response.data["invoice"]["id"])
    assert copy.invoice_title == ("Копія " + title)[:100]
    assert (
        len(copy.invoice_title) <= Invoice._meta.get_field("invoice_title").max_length
    )
    assert copy.status == "Draft" and copy.issued_at is None
