"""Public customer write contracts and bank insert races from hosted review."""

from unittest.mock import patch

import pytest
from django.urls import path
from drf_spectacular.generators import SchemaGenerator

from invoices.tests.ua_helpers import company_payload

BASE = "/api/invoices/billing/legal-entities/"
IBAN = "UA273000010000000000000000001"
SECOND_IBAN = "UA973000010000000000000000002"


@pytest.mark.parametrize("method", ["post", "put", "patch"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("registration_code", "12AB"),
        ("iban", "UA000000000000000000000000000"),
        ("mfo", "12ab56"),
    ],
)
def test_customer_write_refuses_invalid_billing_particulars(
    admin_client, org_a, method, field, value
):
    from accounts.models import Account

    account = Account.objects.create(org=org_a, name="Existing buyer")
    url = "/api/accounts/" if method == "post" else f"/api/accounts/{account.pk}/"
    response = getattr(admin_client, method)(
        url, {"name": "Synthetic buyer", field: value}, format="json"
    )
    assert response.status_code == 400, response.content
    assert field in response.data.get("errors", response.data)
    account.refresh_from_db()
    assert account.name == "Existing buyer"


def test_customer_details_accept_normalized_or_empty_banking_data(admin_client, org_a):
    from accounts.models import Account

    response = admin_client.post(
        "/api/accounts/",
        {
            "name": "Normalized buyer",
            "registration_code": "12345678",
            "iban": "ua273000010000000000000000001",
            "mfo": "300001",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    account = Account.objects.get(org=org_a, name="Normalized buyer")
    assert account.iban == IBAN
    response = admin_client.patch(
        f"/api/accounts/{account.pk}/",
        {"registration_code": "", "iban": "", "mfo": ""},
        format="json",
    )
    assert response.status_code == 200, response.content
    account.refresh_from_db()
    assert (account.registration_code, account.iban, account.mfo) == ("", "", "")


def test_account_update_openapi_documents_billing_particulars():
    from accounts.views import AccountDetailView

    schema = SchemaGenerator(
        patterns=[path("api/accounts/<uuid:pk>/", AccountDetailView.as_view())]
    ).get_schema(request=None, public=True)
    operations = next(iter(schema["paths"].values()))
    expected = {
        "legal_name",
        "registration_code",
        "vat_registration_number",
        "legal_address",
        "iban",
        "bank_name",
        "mfo",
        "tax_system_text",
        "signer_name",
        "signer_title",
    }
    for method in ("put", "patch"):
        body = operations[method]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        if "$ref" in body:
            body = schema["components"]["schemas"][body["$ref"].split("/")[-1]]
        assert expected <= body["properties"].keys()


@pytest.mark.parametrize("method", ["post", "patch"])
def test_bank_duplicate_discovered_after_precheck_is_a_field_error(
    admin_client, method
):
    from invoices.billing.serializers import BankAccountSerializer
    from invoices.models import LegalEntityBankAccount

    entity = admin_client.post(BASE, company_payload(), format="json").data["id"]
    collection = BASE + entity + "/bank-accounts/"
    first = admin_client.post(
        collection, {"iban": IBAN, "bank_name": "First"}, format="json"
    )
    assert first.status_code == 201
    second = None
    url = collection
    if method == "patch":
        second = admin_client.post(
            collection, {"iban": SECOND_IBAN, "bank_name": "Second"}, format="json"
        )
        assert second.status_code == 201
        url += second.data["id"] + "/"
    # Both competing requests can validate before either insert/update commits.
    # Keep a real conflicting row and let the actual database constraint reject it.
    with patch.object(
        BankAccountSerializer, "validate_iban", lambda self, value: value
    ):
        response = getattr(admin_client, method)(
            url, {"iban": IBAN, "bank_name": "Collision"}, format="json"
        )
    assert response.status_code == 400, response.content
    assert "iban" in response.data
    assert (
        admin_client.get(collection + first.data["id"] + "/").data["bank_name"]
        == "First"
    )
    if second:
        assert (
            LegalEntityBankAccount.objects.get(pk=second.data["id"]).iban == SECOND_IBAN
        )
