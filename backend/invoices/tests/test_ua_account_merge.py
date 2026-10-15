"""Billing identity groups and frozen payer particulars survive account merges."""


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
