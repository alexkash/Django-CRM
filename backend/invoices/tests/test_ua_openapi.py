"""The generated contract describes the actual extended invoice envelopes."""

import pytest
from django.urls import path
from drf_spectacular.generators import SchemaGenerator

from invoices.api_views import InvoiceDetailView, InvoiceListView, InvoicePDFView


@pytest.fixture
def invoice_schema():
    return SchemaGenerator(
        patterns=[
            path("api/invoices/", InvoiceListView.as_view()),
            path("api/invoices/<uuid:pk>/", InvoiceDetailView.as_view()),
            path("api/invoices/<uuid:pk>/pdf/", InvoicePDFView.as_view()),
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
    assert row["properties"]["is_overdue"]["type"] == "boolean"
    assert row["properties"]["line_items_count"]["type"] == "integer"
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
    assert "custom_fields" in request["properties"]
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
    path_item = next(v for k, v in schema["paths"].items() if k.endswith("/{id}/"))
    update = resolve(
        schema, path_item["put"]["requestBody"]["content"]["application/json"]["schema"]
    )
    assert "invoice_title" not in update.get("required", [])
    assert "custom_fields" in update["properties"]


def test_invoice_detail_documents_frozen_parties_as_an_object(invoice_schema):
    schema = invoice_schema
    op = next(v for k, v in schema["paths"].items() if k.endswith("/{id}/"))["get"]
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


@pytest.fixture
def billing_schema():
    from invoices.billing.views import (
        BankAccountDetailView,
        LegalEntityDetailView,
        ServiceActListView,
        ServiceActPDFView,
    )

    return SchemaGenerator(
        patterns=[
            path("api/invoices/billing/acts/", ServiceActListView.as_view()),
            path(
                "api/invoices/billing/acts/<uuid:pk>/pdf/", ServiceActPDFView.as_view()
            ),
            path(
                "api/invoices/billing/legal-entities/<uuid:pk>/",
                LegalEntityDetailView.as_view(),
            ),
            path(
                "api/invoices/billing/legal-entities/<uuid:pk>/bank-accounts/<uuid:bank_id>/",
                BankAccountDetailView.as_view(),
            ),
        ]
    ).get_schema(request=None, public=True)


def test_act_creation_requires_parent_and_lines(billing_schema):
    op = billing_schema["paths"]["/api/invoices/billing/acts/"]["post"]
    body = resolve(
        billing_schema, op["requestBody"]["content"]["application/json"]["schema"]
    )
    assert {"invoice_id", "lines"} <= set(body.get("required", []))
    assert body["properties"]["lines"]["minItems"] == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/invoices/billing/legal-entities/{id}/",
        "/api/invoices/billing/legal-entities/{id}/bank-accounts/{bank_id}/",
    ],
)
def test_billing_put_requests_are_partial(billing_schema, endpoint):
    item = billing_schema["paths"][endpoint]
    body = resolve(
        billing_schema,
        item["put"]["requestBody"]["content"]["application/json"]["schema"],
    )
    assert not body.get("required")
    assert "active" in body["properties"]


def test_act_list_documents_filters_and_pagination(billing_schema):
    op = billing_schema["paths"]["/api/invoices/billing/acts/"]["get"]
    params = {p["name"]: p for p in op.get("parameters", [])}
    assert {
        "invoice",
        "account",
        "issuer",
        "status",
        "period_start",
        "period_end",
        "limit",
        "offset",
    } <= params.keys()
    assert params["invoice"]["schema"]["format"] == "uuid"
    assert params["period_start"]["schema"]["format"] == "date"
    assert params["limit"]["schema"]["type"] == "integer"
    assert set(params["status"]["schema"]["enum"]) == {"Draft", "Issued", "Cancelled"}


@pytest.mark.parametrize("kind", ["invoice", "act"])
def test_pdf_download_contract_has_binary_body_and_variant(
    invoice_schema, billing_schema, kind
):
    schema = invoice_schema if kind == "invoice" else billing_schema
    op = next(v["get"] for k, v in schema["paths"].items() if k.endswith("/pdf/"))
    body = op["responses"]["200"]["content"]["application/pdf"]["schema"]
    assert body == {"type": "string", "format": "binary"}
    variant = next(p for p in op["parameters"] if p["name"] == "variant")
    assert set(variant["schema"]["enum"]) == {"clean", "stamped"}
    assert not variant.get("required", False)


def test_invoice_list_documents_fixed_filters_and_pagination(invoice_schema):
    op = invoice_schema["paths"]["/api/invoices/"]["get"]
    params = {p["name"]: p for p in op.get("parameters", [])}
    assert {
        "search",
        "status",
        "account",
        "contact",
        "opportunity",
        "assigned_to",
        "created_by",
        "issue_date_gte",
        "issue_date_lte",
        "due_date_gte",
        "due_date_lte",
        "sort",
        "limit",
        "offset",
    } <= params.keys()
    assert params["account"]["schema"]["format"] == "uuid"
    assert params["due_date_gte"]["schema"]["format"] == "date"
    assert params["limit"]["schema"]["type"] == "integer"
    assert "cf_<key>" in op["description"]
