"""Our-company settings enforce organization and administrator boundaries."""

from invoices.tests.ua_helpers import company_payload

BASE = "/api/invoices/billing/legal-entities/"


def test_admin_creates_company_and_two_sequences(admin_client):
    response = admin_client.post(BASE, company_payload(), format="json")
    assert response.status_code == 201, response.content
    assert response.data["legal_name"] == "ТОВ Тестові Послуги"
    assert "signature_png" not in response.data
    from invoices.models import DocumentSequence

    assert DocumentSequence.objects.filter(entity_id=response.data["id"]).count() == 2


def test_member_reads_but_cannot_change_company(admin_client, user_client):
    response = admin_client.post(BASE, company_payload(), format="json")
    assert response.status_code == 201
    uid = response.data["id"]
    assert user_client.get(BASE).status_code == 200
    assert (
        user_client.patch(
            BASE + uid + "/", {"legal_name": "Changed"}, format="json"
        ).status_code
        == 403
    )
    assert user_client.post(BASE, company_payload(), format="json").status_code == 403


def test_other_org_cannot_read_or_change_company(admin_client, org_b_client):
    response = admin_client.post(BASE, company_payload(), format="json")
    assert response.status_code == 201
    uid = response.data["id"]
    assert org_b_client.get(BASE + uid + "/").status_code == 404
    assert (
        org_b_client.patch(
            BASE + uid + "/", {"active": False}, format="json"
        ).status_code
        == 404
    )
    assert org_b_client.get(BASE).data["results"] == []


def test_banks_are_nested_under_their_actual_company(admin_client):
    first = admin_client.post(BASE, company_payload(), format="json")
    second = admin_client.post(
        BASE, company_payload(legal_name="ФОП Тестовий"), format="json"
    )
    assert first.status_code == second.status_code == 201
    a, b = first.data["id"], second.data["id"]
    bank = admin_client.post(
        BASE + a + "/bank-accounts/",
        {
            "iban": "UA273000010000000000000000001",
            "bank_name": "Тестовий банк",
            "mfo": "300001",
        },
        format="json",
    )
    assert bank.status_code == 201, bank.data
    assert (
        admin_client.get(
            BASE + b + "/bank-accounts/" + bank.data["id"] + "/"
        ).status_code
        == 404
    )
    assert (
        admin_client.post(
            BASE + a + "/bank-accounts/",
            {"iban": "UA000", "bank_name": "Bank"},
            format="json",
        ).status_code
        == 400
    )


def test_existing_account_accepts_new_billing_fields(admin_client):
    response = admin_client.post(
        "/api/accounts/",
        {
            "name": "Synthetic Customer",
            "legal_name": "ТОВ Клієнт",
            "registration_code": "12345678",
            "signer_name": "Тестова Особа",
            "legal_address": "м. Київ",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    from accounts.models import Account

    account = Account.objects.get(name="Synthetic Customer")
    assert account.legal_name == "ТОВ Клієнт"
    assert account.registration_code == "12345678"


def test_number_constraints_allow_company_sequences_without_weakening_generic_uniqueness(
    admin_client, org_a
):
    import pytest
    from django.db import IntegrityError, transaction

    from invoices.models import Invoice

    a = admin_client.post(BASE, company_payload(), format="json").data["id"]
    b = admin_client.post(
        BASE, company_payload(legal_name="Another issuer"), format="json"
    ).data["id"]
    for issuer_id in (a, b, None):
        Invoice.objects.create(
            org=org_a,
            issuer_id=issuer_id,
            invoice_title="Fixture",
            invoice_number="SAME-000001",
        )
    for issuer_id in (a, None):
        with pytest.raises(IntegrityError), transaction.atomic():
            Invoice.objects.create(
                org=org_a,
                issuer_id=issuer_id,
                invoice_title="Duplicate",
                invoice_number="SAME-000001",
            )


def test_member_bank_reads_follow_archive_and_reactivation(admin_client, user_client):
    entity = admin_client.post(BASE, company_payload(), format="json").data["id"]
    collection = BASE + entity + "/bank-accounts/"
    created = admin_client.post(
        collection,
        {"iban": "UA273000010000000000000000001", "bank_name": "Test bank"},
        format="json",
    )
    assert created.status_code == 201
    bank = created.data["id"]
    detail = collection + bank + "/"
    assert user_client.get(detail).status_code == 200
    assert [row["id"] for row in user_client.get(collection).data["results"]] == [bank]
    assert (
        admin_client.patch(detail, {"active": False}, format="json").status_code == 200
    )
    assert user_client.get(collection).data["results"] == []
    assert user_client.get(detail).status_code == 404
    assert admin_client.get(detail).data["active"] is False
    assert [row["id"] for row in admin_client.get(collection).data["results"]] == [bank]
    assert (
        admin_client.patch(detail, {"active": True}, format="json").status_code == 200
    )
    assert user_client.get(detail).status_code == 200
