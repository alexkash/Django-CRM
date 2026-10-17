"""Regression coverage for the branding in generated invoice PDFs."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from PIL import Image
from weasyprint import CSS, HTML

from accounts.models import Account
from invoices.models import Invoice, InvoiceLineItem, InvoiceTemplate
from invoices.pdf import format_currency, generate_invoice_pdf


def logo_image():
    image = BytesIO()
    Image.new("RGB", (16, 16), "navy").save(image, format="PNG")
    return ContentFile(image.getvalue())


@pytest.fixture
def invoice(org_a):
    return Invoice.objects.create(
        org=org_a,
        account=Account.objects.create(name="Example customer", org=org_a),
        client_name="Example customer",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("use_default", [False, True])
@pytest.mark.parametrize("currency", ["USD", "UAH"])
def test_template_logo_takes_precedence_over_org_logo(invoice, use_default, currency):
    invoice.currency = currency
    invoice.org.logo.save("company.png", logo_image(), save=False)
    template = InvoiceTemplate.objects.create(
        org=invoice.org,
        name="Company stationery",
        is_default=use_default,
    )
    template.logo.save("stationery.png", logo_image())
    if not use_default:
        invoice.template = template

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        pdf = generate_invoice_pdf(invoice)

    html = renderer.call_args.kwargs["string"]
    assert f'src="{template.logo.url}"' in html
    assert f'src="{invoice.org.logo.url}"' not in html
    assert pdf.startswith(b"%PDF-")
    assert b"/Subtype /Image" in pdf


@pytest.mark.django_db
def test_org_logo_is_used_when_template_has_no_logo(invoice):
    invoice.org.logo.save("company.png", logo_image(), save=False)
    invoice.template = InvoiceTemplate.objects.create(
        org=invoice.org, name="Plain stationery"
    )

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)

    assert f'src="{invoice.org.logo.url}"' in renderer.call_args.kwargs["string"]


@pytest.mark.django_db
@pytest.mark.parametrize("has_invoice_text", [False, True])
def test_payment_terms_and_footer_are_printed(invoice, has_invoice_text):
    invoice.template = InvoiceTemplate.objects.create(
        org=invoice.org,
        name="Payment details",
        default_terms="IBAN UA000000000000000000000000001",
        default_notes="Default service notes",
        footer_text="Billing contact: finance@example.test",
    )
    if has_invoice_text:
        invoice.terms = "IBAN UA000000000000000000000000002"
        invoice.notes = "Document-specific service notes"

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)

    html = renderer.call_args.kwargs["string"]
    assert "Billing contact: finance@example.test" in html
    if has_invoice_text:
        assert "IBAN UA000000000000000000000000002" in html
        assert "Document-specific service notes" in html
        assert "IBAN UA000000000000000000000000001" not in html
    else:
        assert "IBAN UA000000000000000000000000001" in html
        assert "Default service notes" in html


@pytest.mark.django_db
def test_uah_invoice_prints_a_ukrainian_payment_document(invoice):
    invoice.currency = "UAH"
    invoice.issue_date = date(2026, 10, 16)
    invoice.due_date = date(2026, 10, 30)
    invoice.client_name = "ТОВ «Приклад замовника»"
    invoice.client_address_line = "м. Київ, вул. Прикладна, 2"
    invoice.org.company_name = "ТОВ «Приклад постачальника»"
    invoice.org.tax_id = "12345678"
    invoice.terms = "IBAN UA000000000000000000000000001"
    InvoiceLineItem.objects.create(
        invoice=invoice,
        org=invoice.org,
        name="Технічна підтримка",
        quantity=Decimal("2"),
        unit_price=Decimal("1200.50"),
    )
    invoice.recalculate_totals()

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        pdf = generate_invoice_pdf(invoice)

    html = renderer.call_args.kwargs["string"]
    assert '<html lang="uk">' in html
    for text in (
        "Рахунок на оплату",
        "16.10.2026",
        "30.10.2026",
        "ТОВ «Приклад постачальника»",
        "ТОВ «Приклад замовника»",
        "12345678",
        "IBAN UA000000000000000000000000001",
        "Технічна підтримка",
        "2 401,00 грн",
        "Дві тисячі чотириста одна гривня 00 копійок",
    ):
        assert text in html
    assert "Yours Sincerely" not in html
    assert "Copyright" not in html
    assert "Без ПДВ" not in html  # A zero generic tax is not a VAT status.
    assert pdf.startswith(b"%PDF-")


def test_uah_currency_uses_ukrainian_number_format():
    assert format_currency(Decimal("1234567.89"), "UAH") == "1 234 567,89 грн"
    assert format_currency(Decimal("1234.50"), "USD") == "$1,234.50"


@pytest.mark.django_db
def test_custom_uah_html_is_still_used(invoice):
    invoice.currency = "UAH"
    invoice.template = InvoiceTemplate.objects.create(
        org=invoice.org,
        name="Custom stationery",
        template_html="<h1>Власна форма {{invoice.invoice_number}}</h1>",
    )
    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)

    assert renderer.call_args.kwargs["string"] == (
        f"<h1>Власна форма {invoice.invoice_number}</h1>"
    )


@pytest.mark.django_db
def test_custom_uah_html_keeps_compatible_default_styles(invoice):
    invoice.currency = "UAH"
    invoice.template = InvoiceTemplate.objects.create(
        org=invoice.org,
        name="Existing custom stationery",
        template_html='<div class="header">Власна форма</div>',
    )
    with patch("invoices.pdf.CSS", wraps=CSS) as stylesheet:
        generate_invoice_pdf(invoice)

    assert ".line-items-table" in stylesheet.call_args.kwargs["string"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("billing_postcode", "02002"),
        ("billing_state", "Київська область"),
        ("billing_country", "PL"),
        ("client_postcode", "79007"),
        ("client_state", "Львівська область"),
        ("client_country", "PL"),
    ],
)
def test_uah_partial_addresses_preserve_existing_components(invoice, field, value):
    invoice.currency = "UAH"
    invoice.org.address_line = "ORG-ADDRESS-NOT-FROM-INVOICE"
    setattr(invoice, field, value)

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)

    html = renderer.call_args.kwargs["string"]
    assert value in html
    if field.startswith("billing_"):
        assert "ORG-ADDRESS-NOT-FROM-INVOICE" not in html
        assert f"<div>{value}</div>" in html


@pytest.mark.django_db
def test_uah_complete_client_address_includes_country(invoice):
    invoice.currency = "UAH"
    invoice.client_address_line = "ul. Testowa 20"
    invoice.client_city = "Warszawa"
    invoice.client_postcode = "00-001"
    invoice.client_country = "PL"

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)

    assert "ul. Testowa 20, Warszawa, 00-001, PL" in renderer.call_args.kwargs["string"]


@pytest.mark.django_db
@pytest.mark.parametrize("currency", ["UAH", "USD"])
@pytest.mark.parametrize(
    ("discount_type", "discount_value"),
    [("PERCENTAGE", "10"), ("FIXED", "20")],
)
def test_printed_line_explains_its_discount(
    invoice, currency, discount_type, discount_value
):
    invoice.currency = currency
    InvoiceLineItem.objects.create(
        invoice=invoice,
        org=invoice.org,
        name="Discounted support",
        quantity=Decimal("2"),
        unit_price=Decimal("100"),
        discount_type=discount_type,
        discount_value=Decimal(discount_value),
    )
    invoice.recalculate_totals()

    with patch("invoices.pdf.HTML", wraps=HTML) as renderer:
        generate_invoice_pdf(invoice)

    html = renderer.call_args.kwargs["string"]
    if currency == "UAH":
        assert "Знижка за позицією: 20,00 грн" in html
        assert "180,00 грн" in html
    else:
        assert "Line discount: $20.00" in html
        assert "$180.00" in html
