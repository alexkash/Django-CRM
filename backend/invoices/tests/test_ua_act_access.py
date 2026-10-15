from invoices.tests.ua_helpers import act_payload, issued_invoice

BASE = "/api/invoices/billing/acts/"


def test_act_visibility_always_follows_invoice(
    admin_client, user_client, org_b_client, org_a, user_profile
):
    inv = issued_invoice(admin_client, org_a)
    response = admin_client.post(BASE, act_payload(inv), format="json")
    assert response.status_code == 201, response.content
    uid = response.data["id"]
    for client in (user_client, org_b_client):
        assert client.get(BASE).data["results"] == []
        for suffix in ("", "pdf/"):
            assert client.get(BASE + uid + "/" + suffix).status_code == 404
        for action in ("issue/", "cancel/"):
            assert (
                client.post(BASE + uid + "/" + action, {}, format="json").status_code
                == 404
            )
        assert client.post(BASE, act_payload(inv), format="json").status_code == 404
    from invoices.models import Invoice

    Invoice.objects.get(pk=inv["id"]).assigned_to.add(user_profile)
    assert user_client.get(BASE + uid + "/").status_code == 200
