from invoices.tests.ua_helpers import act_payload, issued_invoice


def test_invoice_display_uses_frozen_parties_after_entity_edit(admin_client, org_a):
    inv = issued_invoice(admin_client, org_a)
    from invoices.models import LegalEntity

    LegalEntity.objects.filter(pk=inv["issuer"]["id"]).update(legal_name="New name")
    stored = admin_client.get("/api/invoices/" + inv["id"] + "/").data["invoice"]
    assert stored["printed_parties"]["seller"]["legal_name"] == "ТОВ Тестові Послуги"
    assert stored["issuer_name"] == "ТОВ Тестові Послуги"


def test_zero_rate_payer_is_exposed_explicitly_on_act(admin_client, org_a):
    inv = issued_invoice(admin_client, org_a, tax_rate="0")
    response = admin_client.post(
        "/api/invoices/billing/acts/", act_payload(inv), format="json"
    )
    assert response.status_code == 201
    assert response.data["vat_status"] == "PAYER"
    assert response.data["vat_rate"] == "0.00"
