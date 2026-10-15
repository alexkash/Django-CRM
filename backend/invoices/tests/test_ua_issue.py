from unittest.mock import patch

from invoices.tests.ua_helpers import create_invoice


def test_issue_is_explicit_idempotent_and_does_not_send_email(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    url = "/api/invoices/" + inv["id"] + "/issue/"
    with patch(
        "invoices.tasks.send_invoice_to_client.delay",
        side_effect=AssertionError("Issue must not send mail"),
    ):
        response = admin_client.post(url, {}, format="json")
    assert response.status_code == 200, response.content
    result = response.data["invoice"]
    assert result["invoice_number"] == "РХ-000001"
    assert result["issued_at"]
    assert result["status"] == "Sent"
    assert result["sent_at"] is None
    from invoices.models import DocumentSequence, Invoice

    stored = Invoice.objects.get(pk=inv["id"])
    before = stored.pdf_clean_sha256
    again = admin_client.post(url, {}, format="json")
    assert again.status_code == 200
    stored.refresh_from_db()
    assert stored.pdf_clean_sha256 == before
    assert (
        DocumentSequence.objects.get(entity=stored.issuer, kind="INVOICE").last_value
        == 1
    )


def test_render_failure_rolls_back_both_archives_and_number(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    from invoices.billing.pdf import render_ua_pdf

    count = 0

    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("Second PDF render failed")
        return render_ua_pdf(*args, **kwargs)

    with patch("invoices.billing.services.render_ua_pdf", side_effect=interrupted):
        response = admin_client.post(
            "/api/invoices/" + inv["id"] + "/issue/", {}, format="json"
        )
    assert response.status_code == 500
    from invoices.models import DocumentSequence, Invoice

    stored = Invoice.objects.with_blobs().get(pk=inv["id"])
    assert stored.status == "Draft"
    assert stored.issued_at is None
    assert stored.print_snapshot == {}
    assert stored.archived_pdf_clean is None
    assert (
        DocumentSequence.objects.get(entity=stored.issuer, kind="INVOICE").last_value
        == 0
    )


def test_issue_requires_complete_period_and_customer_details(admin_client, org_a):
    inv = create_invoice(admin_client, org_a, service_period_start=None)
    assert (
        admin_client.post(
            "/api/invoices/" + inv["id"] + "/issue/", {}, format="json"
        ).status_code
        == 400
    )


def test_issued_print_fields_and_lines_are_locked(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    url = "/api/invoices/" + inv["id"] + "/"
    assert admin_client.post(url + "issue/", {}, format="json").status_code == 200
    for change in [
        {"notes": "changed"},
        {"issue_date": "2027-12-01"},
        {"draft_parties": {"customer": {"legal_name": "changed"}}},
        {"line_items": []},
    ]:
        assert admin_client.put(url, change, format="json").status_code == 400
    assert (
        admin_client.post(
            url + "line-items/", {"name": "New", "unit_price": "1"}, format="json"
        ).status_code
        == 400
    )


def test_ua_admin_cannot_bypass_draft_or_issued_workflow(
    admin_client, org_a, admin_user
):
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    from invoices.models import Invoice

    inv = create_invoice(admin_client, org_a)
    request = RequestFactory().get("/admin/")
    admin_user.is_superuser = True
    admin_user.is_staff = True
    request.user = admin_user
    obj = Invoice.objects.get(pk=inv["id"])
    assert not site._registry[Invoice].has_change_permission(request, obj)
    assert not site._registry[Invoice].has_delete_permission(request, obj)
