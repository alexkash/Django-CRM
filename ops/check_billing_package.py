"""Run with the installed wheel's Python from a neutral directory (no checkout import)."""

from decimal import Decimal
from importlib.resources import files
import io

import django
from PIL import Image

django.setup()
from invoices.billing.pdf import render_ua_pdf  # noqa: E402
from invoices.billing.formatting import amount_in_words_uk  # noqa: E402

root = files("invoices").joinpath("templates/invoices/pdf/ua")
for resource in [
    "invoice.html",
    "act.html",
    "lines.html",
    "seller-signature.html",
    "billing.css",
    "fonts/DejaVuSans.ttf",
    "fonts/LICENSE",
]:
    assert root.joinpath(resource).read_bytes(), resource
party = {
    "legal_name": "ТОВ Тест",
    "registration_code": "12345678",
    "legal_address": "м. Київ",
    "signer_name": "Тестова Особа",
    "signer_title": "Директор",
    "iban": "UA273000010000000000000000001",
    "bank_name": "Тестовий банк",
    "mfo": "300001",
}
snapshot = {
    "kind": "invoice",
    "draft": False,
    "number": "РХ-000001",
    "issue_date": "2027-01-01",
    "place": "Київ",
    "due_date": "2027-01-31",
    "service_period_start": "2027-01-01",
    "service_period_end": "2027-12-31",
    "contract_number": "TEST-1",
    "contract_date": "2027-01-01",
    "order_reference": "",
    "seller": party,
    "customer": party,
    "payer": party,
    "bank": party,
    "vat_status": "PAYER",
    "vat_rate": "20.00",
    "subtotal": "12000.00",
    "tax_amount": "2400.00",
    "total_amount": "14400.00",
    "amount_words": amount_in_words_uk(Decimal("14400.00")),
    "lines": [
        {
            "name": "Технічна підтримка",
            "description": "",
            "unit": "місяць",
            "quantity": "12",
            "unit_price": "1000.00",
            "net_amount": "12000.00",
            "vat_amount": "2400.00",
            "total_amount": "14400.00",
        }
    ],
}
out = io.BytesIO()
Image.new("RGBA", (40, 20), (25, 60, 140, 180)).save(out, "PNG")
for kind in ["invoice", "act"]:
    sample = {
        **snapshot,
        "kind": kind,
        "invoice_number": "РХ-000001",
        "invoice_date": "2027-01-01",
    }
    pdf = render_ua_pdf(sample, signature=out.getvalue(), stamp=None)
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1000
print(
    "Installed billing package: templates, CSS, font/license, invoice and act PDF render OK"
)
