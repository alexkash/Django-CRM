"""Company branding is private at rest and frozen with issued documents."""

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from invoices.models import Invoice
from invoices.tests.ua_helpers import (
    act_payload,
    company_payload,
    create_invoice,
    scan_bytes,
)

BASE = "/api/invoices/billing/legal-entities/"


def upload_logo(client, entity_id):
    return client.put(
        f"{BASE}{entity_id}/scans/logo/",
        {"file": SimpleUploadedFile("company.jpg", scan_bytes("JPEG"), "image/jpeg")},
        format="multipart",
    )


def test_logo_upload_is_private_normalized_and_admin_only(
    admin_client, user_client, org_b_client
):
    entity = admin_client.post(BASE, company_payload(), format="json").data
    url = f"{BASE}{entity['id']}/scans/logo/"
    response = upload_logo(admin_client, entity["id"])
    assert response.status_code == 200, response.content
    image = admin_client.get(url)
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    assert image["Cache-Control"] == "private, no-store"
    assert user_client.get(url).status_code == 403
    assert org_b_client.get(url).status_code == 404
    assert user_client.put(url, {}, format="multipart").status_code == 403
    detail = admin_client.get(f"{BASE}{entity['id']}/").data
    assert detail["logo_sha256"] == response.data["sha256"]
    assert "logo_png" not in detail
    assert admin_client.delete(url).status_code == 204
    assert admin_client.get(url).status_code == 404


def test_invalid_logo_preserves_previous_upload(admin_client):
    entity = admin_client.post(BASE, company_payload(), format="json").data
    url = f"{BASE}{entity['id']}/scans/logo/"
    assert upload_logo(admin_client, entity["id"]).status_code == 200
    before = admin_client.get(url).content
    for name, data, mime in [
        ("logo.svg", b"<svg/>", "image/svg+xml"),
        ("logo.png", b"broken", "image/png"),
        ("huge.png", b"x" * (2 * 1024 * 1024 + 1), "image/png"),
    ]:
        response = admin_client.put(
            url, {"file": SimpleUploadedFile(name, data, mime)}, format="multipart"
        )
        assert response.status_code == 400
        assert admin_client.get(url).content == before


def test_company_logo_is_frozen_and_inherited_by_partial_acts(admin_client, org_a):
    org_a.logo.save("org.png", ContentFile(scan_bytes()))
    inv = create_invoice(admin_client, org_a)
    entity_id = inv["issuer"]["id"]
    url = f"{BASE}{entity_id}/scans/logo/"
    assert upload_logo(admin_client, entity_id).status_code == 200
    logo = admin_client.get(url).content
    invoice_url = f"/api/invoices/{inv['id']}/"
    issued = admin_client.post(invoice_url + "issue/", {}, format="json")
    assert issued.status_code == 200, issued.content
    inv = issued.data["invoice"]
    stored = Invoice.objects.get(pk=inv["id"])
    assert "logo_png" not in stored.print_snapshot
    assert "branding_logo_png" in stored.get_deferred_fields()
    assert (
        Invoice.objects.filter(pk=stored.pk)
        .values_list("branding_logo_png", flat=True)
        .get()
        == logo
    )
    clean = admin_client.get(invoice_url + "pdf/?variant=clean").content
    assert b"/Subtype /Image" in clean

    assert admin_client.delete(url).status_code == 204
    org_a.logo.delete()
    assert admin_client.get(invoice_url + "pdf/?variant=clean").content == clean

    act = admin_client.post(
        "/api/invoices/billing/acts/", act_payload(inv), format="json"
    )
    assert act.status_code == 201, act.content
    act_url = "/api/invoices/billing/acts/" + act.data["id"] + "/"
    assert admin_client.post(act_url + "issue/", {}, format="json").status_code == 200
    assert b"/Subtype /Image" in admin_client.get(act_url + "pdf/").content


def test_org_logo_is_used_when_issuer_has_no_logo(admin_client, org_a):
    org_a.logo.save("org-fallback.png", ContentFile(scan_bytes()))
    inv = create_invoice(admin_client, org_a)
    url = f"/api/invoices/{inv['id']}/"
    response = admin_client.post(url + "issue/", {}, format="json")
    assert response.status_code == 200, response.content
    assert b"/Subtype /Image" in admin_client.get(url + "pdf/").content


def test_missing_optional_org_logo_does_not_block_issue(admin_client, org_a):
    org_a.logo = "org_logos/missing-qa-image.png"
    org_a.save(update_fields=["logo"])
    inv = create_invoice(admin_client, org_a)
    url = f"/api/invoices/{inv['id']}/"
    response = admin_client.post(url + "issue/", {}, format="json")
    assert response.status_code == 200, response.content
