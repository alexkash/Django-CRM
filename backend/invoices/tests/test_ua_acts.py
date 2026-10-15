from invoices.tests.ua_helpers import act_payload, issued_invoice

BASE = "/api/invoices/billing/acts/"


def create_act(client, inv, quantity="3", **extra):
    response = client.post(BASE, act_payload(inv, quantity, **extra), format="json")
    assert response.status_code == 201, response.content
    return response.data


def test_quarterly_acts_close_annual_invoice_independently_of_payment(
    admin_client, org_a
):
    inv = issued_invoice(admin_client, org_a)
    for i in range(4):
        act = create_act(admin_client, inv)
        issue = admin_client.post(BASE + act["id"] + "/issue/", {}, format="json")
        assert issue.status_code == 200, issue.content
        assert issue.data["subtotal"] == "3000.00"
        assert issue.data["tax_amount"] == "600.00"
        assert issue.data["total_amount"] == "3600.00"
        assert issue.data["number"] == f"АКТ-{i + 1:06d}"
        again = admin_client.post(BASE + act["id"] + "/issue/", {}, format="json")
        assert again.data["number"] == issue.data["number"]
    current = admin_client.get("/api/invoices/" + inv["id"] + "/").data["invoice"]
    assert current["amount_paid"] == "0.00"
    assert current["closure"]["closed_total"] == "14400.00"
    assert current["closure"]["remaining_total"] == "0.00"
    assert current["closure"]["lines"][0]["remaining_quantity"] == "0.00000000"


def test_drafts_do_not_reserve_and_stale_issue_conflicts(admin_client, org_a):
    inv = issued_invoice(admin_client, org_a)
    first, second = (
        create_act(admin_client, inv, "12"),
        create_act(admin_client, inv, "12"),
    )
    assert (
        admin_client.post(BASE + first["id"] + "/issue/", {}, format="json").status_code
        == 200
    )
    assert (
        admin_client.post(
            BASE + second["id"] + "/issue/", {}, format="json"
        ).status_code
        == 409
    )
    assert admin_client.delete(BASE + second["id"] + "/").status_code == 204
    assert admin_client.delete(BASE + first["id"] + "/").status_code == 400


def test_cancel_frees_only_once_and_keeps_archived_pdf(admin_client, org_a):
    inv = issued_invoice(admin_client, org_a)
    act = create_act(admin_client, inv, "12")
    assert (
        admin_client.post(BASE + act["id"] + "/issue/", {}, format="json").status_code
        == 200
    )
    pdf = admin_client.get(BASE + act["id"] + "/pdf/").content
    assert pdf.startswith(b"%PDF-")
    assert (
        admin_client.post(
            "/api/invoices/" + inv["id"] + "/cancel/", {}, format="json"
        ).status_code
        == 400
    )
    for _ in range(2):
        result = admin_client.post(
            BASE + act["id"] + "/cancel/", {"reason": "Виправлення"}, format="json"
        )
        assert result.status_code == 200
    assert admin_client.get(BASE + act["id"] + "/pdf/").content == pdf
    assert (
        admin_client.put(
            BASE + act["id"] + "/", {"issue_date": "2027-04-01"}, format="json"
        ).status_code
        == 400
    )
    replacement = create_act(admin_client, inv, "12")
    assert (
        admin_client.post(BASE + replacement["id"] + "/issue/", {}, format="json").data[
            "number"
        ]
        == "АКТ-000002"
    )


def test_act_period_and_source_line_are_validated(admin_client, org_a):
    inv = issued_invoice(admin_client, org_a)
    act = create_act(admin_client, inv, service_period_end="2028-01-01")
    assert (
        admin_client.post(BASE + act["id"] + "/issue/", {}, format="json").status_code
        == 400
    )
    other = issued_invoice(admin_client, org_a)
    payload = act_payload(inv)
    payload["lines"][0]["source_line_id"] = other["line_items"][0]["id"]
    assert admin_client.post(BASE, payload, format="json").status_code == 400
