import pytest

from invoices.tests.ua_helpers import create_invoice


def test_snapshot_freezes_both_parties_contract_unit_and_tax(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    assert (
        admin_client.post(
            "/api/invoices/" + inv["id"] + "/issue/", {}, format="json"
        ).status_code
        == 200
    )
    from invoices.models import Invoice

    stored = Invoice.objects.get(pk=inv["id"])
    snapshot = stored.print_snapshot
    assert snapshot["customer"]["legal_name"] == "ТОВ Тестовий Клієнт"
    assert snapshot["seller"]["legal_name"] == "ТОВ Тестові Послуги"
    assert snapshot["contract_number"] == "TEST-2027"
    assert snapshot["lines"][0]["unit"] == "місяць"
    assert snapshot["tax_amount"] == "2400.00"
    assert snapshot["total_amount"] == "14400.00"
    assert stored.snapshot_version == 1
    assert (
        "archived_pdf_clean"
        not in admin_client.get("/api/invoices/" + inv["id"] + "/").data["invoice"]
    )


def test_same_recipient_payer_inherits_completed_document_particulars(
    admin_client, org_a
):
    from accounts.models import Account
    from invoices.models import Invoice

    inv = create_invoice(admin_client, org_a)
    stored = Invoice.objects.get(pk=inv["id"])
    Account.objects.filter(pk=stored.account_id).update(
        registration_code="", legal_address="", signer_name=""
    )
    corrections = {
        "legal_name": "ТОВ Уточнений Замовник",
        "registration_code": "11223344",
        "legal_address": "м. Львів, Тестова, 3",
        "signer_name": "Уточнений Підписант",
    }
    url = f"/api/invoices/{stored.pk}/"
    response = admin_client.put(
        url, {"draft_parties": {"customer": corrections}}, format="json"
    )
    assert response.status_code == 200, response.content
    response = admin_client.post(url + "issue/", {}, format="json")
    assert response.status_code == 200, response.content
    stored.refresh_from_db()
    assert stored.print_snapshot["payer"] == stored.print_snapshot["customer"]
    for field, value in corrections.items():
        assert stored.print_snapshot["customer"][field] == value


def test_clearing_separate_payer_ignores_old_payer_corrections(admin_client, org_a):
    from accounts.models import Account
    from invoices.models import Invoice

    payer = Account.objects.create(
        org=org_a,
        name="Separate payer",
        legal_name="Old payer",
        registration_code="11112222",
        legal_address="Old address",
        signer_name="Old signer",
    )
    inv = create_invoice(
        admin_client,
        org_a,
        payer_id=str(payer.pk),
        draft_parties={"payer": {"legal_name": "Old payer override"}},
    )
    url = f"/api/invoices/{inv['id']}/"
    corrections = {
        "legal_name": "ТОВ Виправлений Одержувач",
        "registration_code": "55667788",
    }
    response = admin_client.put(
        url,
        {
            "payer_id": None,
            "draft_parties": {
                "customer": corrections,
                "payer": {"legal_name": "Stale hidden override"},
            },
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    assert admin_client.get(url).data["invoice"]["payer_id"] is None
    response = admin_client.post(url + "issue/", {}, format="json")
    assert response.status_code == 200, response.content
    stored = Invoice.objects.get(pk=inv["id"])
    assert stored.print_snapshot["payer"] == stored.print_snapshot["customer"]
    assert stored.print_snapshot["payer"]["legal_name"] == corrections["legal_name"]


@pytest.mark.parametrize("side", ["customer", "payer"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("registration_code", "12AB"),
        ("iban", "not-an-iban"),
        ("mfo", "12ab56"),
        ("legal_name", "  \t"),
    ],
)
def test_issue_validates_document_overrides_with_customer_format_rules(
    admin_client, org_a, side, field, value
):
    from accounts.models import Account
    from invoices.models import DocumentSequence, Invoice

    payer = Account.objects.create(
        org=org_a,
        name="Separate payer",
        legal_name="ТОВ Платник",
        registration_code="11223344",
        legal_address="м. Київ",
        signer_name="Підписант",
    )
    inv = create_invoice(
        admin_client,
        org_a,
        payer_id=str(payer.pk) if side == "payer" else None,
        draft_parties={side: {field: value}},
    )
    response = admin_client.post(f"/api/invoices/{inv['id']}/issue/", {}, format="json")
    assert response.status_code == 400, response.content
    assert side in response.data
    stored = Invoice.objects.get(pk=inv["id"])
    assert stored.issued_at is None
    assert stored.invoice_number.startswith("DRAFT-")
    assert (
        DocumentSequence.objects.get(entity=stored.issuer, kind="INVOICE").last_value
        == 0
    )
