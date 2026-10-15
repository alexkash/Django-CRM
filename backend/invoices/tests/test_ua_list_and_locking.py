"""Regression contracts from PR2 hosted Codex review."""

from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from invoices.tests.ua_helpers import act_payload, create_invoice


@pytest.mark.parametrize(
    "method,suffix",
    [("post", "issue/"), ("post", "cancel/"), ("delete", ""), ("put", "")],
)
def test_disappearing_act_during_parent_lock_returns_not_found(
    admin_client, org_a, method, suffix
):
    from invoices.billing import services
    from invoices.models import ServiceAct

    inv = create_invoice(admin_client, org_a)
    assert (
        admin_client.post(
            f"/api/invoices/{inv['id']}/issue/", {}, format="json"
        ).status_code
        == 200
    )
    created = admin_client.post(
        "/api/invoices/billing/acts/", act_payload(inv), format="json"
    )
    assert created.status_code == 201
    uid = created.data["id"]
    original = services.get_invoice_or_error

    def disappear_before_parent_lock(*args, **kwargs):
        # Deterministically expose the gap after the visibility probe; the next
        # actual row query must tolerate the draft having been deleted.
        ServiceAct.objects.filter(pk=uid).delete()
        return original(*args, **kwargs)

    with patch.object(
        services, "get_invoice_or_error", side_effect=disappear_before_parent_lock
    ):
        response = getattr(admin_client, method)(
            f"/api/invoices/billing/acts/{uid}/{suffix}", {}, format="json"
        )
    assert response.status_code == 404, response.content


def test_ua_invoice_list_query_count_does_not_grow_per_row(admin_client, org_a):
    expected = {}
    for index in range(5):
        inv = create_invoice(admin_client, org_a)
        if index % 2 == 0:
            assert (
                admin_client.post(
                    f"/api/invoices/{inv['id']}/issue/", {}, format="json"
                ).status_code
                == 200
            )
            act = admin_client.post(
                "/api/invoices/billing/acts/", act_payload(inv), format="json"
            )
            assert act.status_code == 201
            assert (
                admin_client.post(
                    f"/api/invoices/billing/acts/{act.data['id']}/issue/",
                    {},
                    format="json",
                ).status_code
                == 200
            )
        expected[inv["id"]] = admin_client.get(f"/api/invoices/{inv['id']}/").data[
            "invoice"
        ]["closure"]
    with CaptureQueriesContext(connection) as small:
        assert admin_client.get("/api/invoices/?limit=1").status_code == 200
    with CaptureQueriesContext(connection) as large:
        result = admin_client.get("/api/invoices/?limit=5")
    assert result.status_code == 200, result.content
    assert {row["id"]: row["closure"] for row in result.data["results"]} == expected

    def selected(queries):
        return [
            q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("SELECT")
        ]

    assert len(selected(large)) <= len(selected(small)) + 1
    assert all(
        "archived_pdf_" not in sql
        and "signature_png" not in sql
        and "stamp_png" not in sql
        for sql in selected(large)
    )
