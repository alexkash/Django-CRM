"""The generated contract describes the actual extended invoice envelopes."""

import pytest
from django.urls import path
from drf_spectacular.generators import SchemaGenerator

from invoices.api_views import InvoiceDetailView, InvoiceListView


@pytest.fixture
def invoice_schema():
    return SchemaGenerator(
        patterns=[
            path("api/invoices/", InvoiceListView.as_view()),
            path("api/invoices/<uuid:pk>/", InvoiceDetailView.as_view()),
        ]
    ).get_schema(request=None, public=True)


def resolve(schema, node):
    return (
        schema["components"]["schemas"][node["$ref"].split("/")[-1]]
        if "$ref" in node
        else node
    )


def test_invoice_list_envelope_and_closure_are_documented(invoice_schema):
    schema = invoice_schema
    body = resolve(
        schema,
        schema["paths"]["/api/invoices/"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"],
    )
    assert {"count", "next", "previous", "results", "totals"} <= body[
        "properties"
    ].keys()
    row = resolve(schema, body["properties"]["results"]["items"])
    closure = resolve(schema, row["properties"]["closure"])
    assert closure["type"] == "object"
    assert closure.get("nullable") is True
    assert not {"archived_pdf_clean", "archived_pdf_stamped"} & row["properties"].keys()


def test_invoice_create_and_partial_update_contracts(invoice_schema):
    schema = invoice_schema
    create = schema["paths"]["/api/invoices/"]["post"]
    request = resolve(
        schema, create["requestBody"]["content"]["application/json"]["schema"]
    )
    assert {"account_id", "contact_id", "invoice_title"} <= set(request["required"])
    assert {
        "issuer_id",
        "bank_account_id",
        "payer_id",
        "service_period_start",
        "service_period_end",
    } <= request["properties"].keys()
    response = resolve(
        schema, create["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert {"error", "message", "invoice"} <= response["properties"].keys()
    path_item = next(v for k, v in schema["paths"].items() if k != "/api/invoices/")
    update = resolve(
        schema, path_item["put"]["requestBody"]["content"]["application/json"]["schema"]
    )
    assert "invoice_title" not in update.get("required", [])


def test_invoice_detail_documents_frozen_parties_as_an_object(invoice_schema):
    schema = invoice_schema
    op = next(v for k, v in schema["paths"].items() if k != "/api/invoices/")["get"]
    response = resolve(
        schema, op["responses"]["200"]["content"]["application/json"]["schema"]
    )
    assert {
        "invoice",
        "attachments",
        "comments",
        "history",
        "custom_field_definitions",
    } <= response["properties"].keys()
    row = resolve(schema, response["properties"]["invoice"])
    assert row["properties"]["printed_parties"]["type"] == "object"
    assert row["properties"]["printed_parties"].get("nullable") is True
