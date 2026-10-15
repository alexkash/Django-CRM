"""Billing identity groups and frozen payer particulars survive account merges."""

from invoices.tests.ua_helpers import issued_invoice


def test_merging_a_payer_moves_link_without_rewriting_issued_pdf(admin_client, org_a):
    from accounts.models import Account
    from invoices.models import Invoice

    keeper = Account.objects.create(org=org_a, name="Keeper")
    loser = Account.objects.create(
        org=org_a,
        name="Payer duplicate",
        legal_name="ТОВ Старий Платник",
        registration_code="80000001",
        legal_address="м. Київ",
        signer_name="Тестовий Платник",
    )
    inv = issued_invoice(admin_client, org_a, payer_id=str(loser.pk))
    before = Invoice.objects.get(pk=inv["id"])
    frozen = (before.print_snapshot, before.pdf_clean_sha256, before.pdf_stamped_sha256)
    result = admin_client.post(
        "/api/accounts/" + str(keeper.pk) + "/merge/",
        {"merge_id": str(loser.pk)},
        format="json",
    )
    assert result.status_code == 200, result.content
    before.refresh_from_db()
    assert before.payer_id == keeper.pk
    assert not Account.objects.filter(pk=loser.pk).exists()
    assert (
        before.print_snapshot,
        before.pdf_clean_sha256,
        before.pdf_stamped_sha256,
    ) == frozen


def test_partial_keeper_billing_profile_cannot_mix_another_company_bank(
    admin_client, org_a
):
    from accounts.models import Account

    keeper = Account.objects.create(
        org=org_a, name="Primary", registration_code="80000001"
    )
    loser = Account.objects.create(
        org=org_a,
        name="Secondary",
        registration_code="80000002",
        legal_name="ТОВ Інша Компанія",
        iban="UA273000010000000000000000001",
        bank_name="Інший банк",
        signer_name="Інша Особа",
    )
    result = admin_client.post(
        "/api/accounts/" + str(keeper.pk) + "/merge/",
        {"merge_id": str(loser.pk)},
        format="json",
    )
    assert result.status_code == 200, result.content
    keeper.refresh_from_db()
    assert keeper.registration_code == "80000001"
    assert keeper.legal_name == ""
    assert keeper.iban == ""
    assert keeper.signer_name == ""


def test_empty_keeper_billing_profile_takes_whole_source_group(admin_client, org_a):
    from accounts.models import Account

    keeper = Account.objects.create(org=org_a, name="Empty primary")
    loser = Account.objects.create(
        org=org_a,
        name="Full secondary",
        registration_code="80000002",
        legal_name="ТОВ Платник",
        iban="UA273000010000000000000000001",
        bank_name="Тестовий банк",
        signer_name="Тестова Особа",
    )
    result = admin_client.post(
        "/api/accounts/" + str(keeper.pk) + "/merge/",
        {"merge_id": str(loser.pk)},
        format="json",
    )
    assert result.status_code == 200
    keeper.refresh_from_db()
    assert (
        keeper.registration_code,
        keeper.legal_name,
        keeper.iban,
        keeper.signer_name,
    ) == ("80000002", "ТОВ Платник", "UA273000010000000000000000001", "Тестова Особа")
