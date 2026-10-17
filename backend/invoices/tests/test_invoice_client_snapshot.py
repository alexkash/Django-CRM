"""The invoice builder selects an account; its PDF needs a client snapshot."""

from unittest.mock import patch

import pytest
from weasyprint import HTML

from accounts.models import Account
from contacts.models import Contact
from invoices.models import Invoice
from invoices.pdf import generate_invoice_pdf


@pytest.fixture
def customer(org_a, admin_user):
    account = Account.objects.create(
        org=org_a,
        created_by=admin_user,
        name="ТОВ «Замовник для рахунку»",
        email="billing@customer.example.test",
        phone="+380441234567",
        address_line="ul. Testowa 20",
        city="Warszawa",
        state="Mazowieckie",
        postcode="00-001",
        country="PL",
    )
    contact = Contact.objects.create(
        org=org_a,
        account=account,
        first_name="Тестовий",
        last_name="Контакт",
        email="person@customer.example.test",
        created_by=admin_user,
    )
    return account, contact


def create_invoice(client, customer, **fields):
    account, contact = customer
    with patch("invoices.api_views.create_invoice_history.delay"):
        response = client.post(
            "/api/invoices/",
            {
                "account_id": str(account.pk),
                "contact_id": str(contact.pk),
                "invoice_title": "UI-equivalent invoice",
                "currency": "UAH",
                "line_items": [
                    {"name": "Support", "quantity": "12", "unit_price": "1000"}
                ],
                **fields,
            },
            format="json",
        )
    assert response.status_code == 201, response.content
    return Invoice.objects.get(pk=response.json()["invoice"]["id"])


@pytest.mark.django_db
def test_builder_creation_copies_the_selected_accounts_billing_details(
    admin_client, customer
):
    invoice = create_invoice(admin_client, customer)
    assert invoice.client_name == "ТОВ «Замовник для рахунку»"
    assert invoice.client_email == "billing@customer.example.test"
    assert invoice.client_phone == "+380441234567"
    assert (
        invoice.client_address_line,
        invoice.client_city,
        invoice.client_state,
        invoice.client_postcode,
        invoice.client_country,
    ) == ("ul. Testowa 20", "Warszawa", "Mazowieckie", "00-001", "PL")
    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)
    html = renderer.call_args.kwargs["string"]
    assert "ТОВ «Замовник для рахунку»" in html
    assert "ul. Testowa 20, Warszawa, Mazowieckie, 00-001, PL" in html


@pytest.mark.django_db
def test_explicit_snapshot_fields_are_preserved(admin_client, customer):
    invoice = create_invoice(
        admin_client,
        customer,
        client_name="Explicit payer",
        client_email="explicit@example.test",
        client_address_line="Explicit billing address",
        client_city="Explicit city",
        client_country="UA",
        client_postcode="",
    )
    assert invoice.client_name == "Explicit payer"
    assert invoice.client_email == "explicit@example.test"
    assert invoice.client_address_line == "Explicit billing address"
    assert invoice.client_city == "Explicit city"
    assert invoice.client_country == "UA"
    assert invoice.client_postcode == ""


@pytest.mark.django_db
def test_later_account_changes_do_not_rewrite_the_copied_client(admin_client, customer):
    invoice = create_invoice(admin_client, customer)
    account, _ = customer
    account.name = "Renamed later"
    account.city = "Changed later"
    account.save()
    invoice.notes = "Changed document notes"
    invoice.save()
    invoice.refresh_from_db()
    assert invoice.client_name == "ТОВ «Замовник для рахунку»"
    assert invoice.client_city == "Warszawa"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("account_field", "invoice_field", "length"),
    [
        ("city", "client_city", 101),
        ("state", "client_state", 101),
        ("postcode", "client_postcode", 21),
    ],
)
def test_copied_fields_return_validation_errors_before_insert(
    admin_client, customer, account_field, invoice_field, length
):
    account, contact = customer
    setattr(account, account_field, "X" * length)
    account.save()
    with patch("invoices.api_views.create_invoice_history.delay"):
        response = admin_client.post(
            "/api/invoices/",
            {
                "account_id": str(account.pk),
                "contact_id": str(contact.pk),
                "invoice_title": "Oversize account snapshot",
            },
            format="json",
        )
    assert response.status_code == 400, response.content
    assert invoice_field in response.json()
    assert not Invoice.objects.exists()


@pytest.mark.django_db
def test_ua_creation_keeps_legal_parties_independent_of_legacy_address_limits(
    admin_client, org_a
):
    from invoices.tests.ua_helpers import invoice_payload

    payload = invoice_payload(admin_client, org_a)
    Account.objects.filter(pk=payload["account_id"]).update(city="X" * 101)
    with patch("invoices.api_views.create_invoice_history.delay"):
        response = admin_client.post("/api/invoices/", payload, format="json")
    assert response.status_code == 201, response.content
