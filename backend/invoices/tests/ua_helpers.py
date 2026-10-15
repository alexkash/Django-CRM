"""Synthetic parties and image data; no real company scans."""

import io

from PIL import Image


def company_payload(**overrides):
    return {
        "entity_type": "LLC",
        "legal_name": "ТОВ Тестові Послуги",
        "registration_code": "12345678",
        "address": "м. Київ, вулиця Тестова, 1",
        "city": "Київ",
        "vat_status": "PAYER",
        "default_vat_rate": "20.00",
        "signer_name": "Тестовий Виконавець",
        "signer_title": "Директор",
        **overrides,
    }


def scan_bytes(fmt="PNG"):
    out = io.BytesIO()
    Image.new("RGB", (40, 24), (20, 70, 160)).save(out, fmt)
    return out.getvalue()


def invoice_payload(client, org, **overrides):
    from accounts.models import Account
    from contacts.models import Contact

    entity = client.post(
        "/api/invoices/billing/legal-entities/", company_payload(), format="json"
    )
    assert entity.status_code == 201, entity.content
    bank = client.post(
        "/api/invoices/billing/legal-entities/" + entity.data["id"] + "/bank-accounts/",
        {
            "iban": "UA273000010000000000000000001",
            "bank_name": "Тестовий банк",
            "mfo": "300001",
        },
        format="json",
    )
    assert bank.status_code == 201, bank.content
    account = Account.objects.create(
        org=org,
        name="Synthetic Buyer " + entity.data["id"],
        legal_name="ТОВ Тестовий Клієнт",
        registration_code="87654321",
        legal_address="м. Київ, вул. Тестова, 2",
        signer_name="Тестовий Замовник",
        signer_title="Директор",
    )
    contact = Contact.objects.create(
        org=org,
        account=account,
        first_name="Test",
        last_name="Buyer",
        email="buyer-" + entity.data["id"] + "@example.test",
    )
    return {
        "invoice_title": "Технічна підтримка",
        "issuer_id": entity.data["id"],
        "bank_account_id": bank.data["id"],
        "account_id": str(account.pk),
        "contact_id": str(contact.pk),
        "client_name": account.legal_name,
        "client_email": "buyer@example.test",
        "currency": "UAH",
        "tax_rate": "20.00",
        "contract_number": "TEST-2027",
        "contract_date": "2027-01-01",
        "service_period_start": "2027-01-01",
        "service_period_end": "2027-12-31",
        "place_of_issue": "Київ",
        "line_items": [
            {
                "name": "Технічна підтримка",
                "quantity": "12",
                "unit": "місяць",
                "unit_price": "1000.00",
            }
        ],
        **overrides,
    }


def create_invoice(client, org, **overrides):
    response = client.post(
        "/api/invoices/", invoice_payload(client, org, **overrides), format="json"
    )
    assert response.status_code == 201, response.content
    return response.data["invoice"]


def issued_invoice(client, org, **overrides):
    inv = create_invoice(client, org, **overrides)
    response = client.post("/api/invoices/" + inv["id"] + "/issue/", {}, format="json")
    assert response.status_code == 200, response.content
    return response.data["invoice"]


def act_payload(inv, quantity="3", **overrides):
    return {
        "invoice_id": inv["id"],
        "issue_date": "2027-03-31",
        "service_period_start": "2027-01-01",
        "service_period_end": "2027-03-31",
        "lines": [{"source_line_id": inv["line_items"][0]["id"], "quantity": quantity}],
        **overrides,
    }
