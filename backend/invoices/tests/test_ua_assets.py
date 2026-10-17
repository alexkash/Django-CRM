from django.core.files.uploadedfile import SimpleUploadedFile

from invoices.tests.ua_helpers import company_payload, scan_bytes

BASE = "/api/invoices/billing/legal-entities/"


def test_scans_are_private_and_normalized(admin_client, user_client, org_b_client):
    created = admin_client.post(BASE, company_payload(), format="json")
    assert created.status_code == 201
    url = BASE + created.data["id"] + "/scans/signature/"
    response = admin_client.put(
        url,
        {"file": SimpleUploadedFile("scan.jpg", scan_bytes("JPEG"), "image/jpeg")},
        format="multipart",
    )
    assert response.status_code == 200, response.data
    image = admin_client.get(url)
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")
    assert image["Cache-Control"] == "private, no-store"
    assert user_client.get(url).status_code == 403
    assert org_b_client.get(url).status_code == 404
    assert "signature_png" not in admin_client.get(BASE + created.data["id"] + "/").data
    assert admin_client.delete(url).status_code == 204
    assert admin_client.get(url).status_code == 404


def test_invalid_scan_keeps_previous_image(admin_client):
    created = admin_client.post(BASE, company_payload(), format="json")
    assert created.status_code == 201
    url = BASE + created.data["id"] + "/scans/stamp/"
    assert (
        admin_client.put(
            url,
            {"file": SimpleUploadedFile("scan.png", scan_bytes(), "image/png")},
            format="multipart",
        ).status_code
        == 200
    )
    before = admin_client.get(url).content
    for name, data, mime in [
        ("x.svg", b"<svg/>", "image/svg+xml"),
        ("x.png", b"broken", "image/png"),
        ("huge.png", b"x" * (2 * 1024 * 1024 + 1), "image/png"),
        ("fake.png", scan_bytes(), "text/html"),
    ]:
        response = admin_client.put(
            url, {"file": SimpleUploadedFile(name, data, mime)}, format="multipart"
        )
        assert response.status_code == 400, response.data
        assert admin_client.get(url).content == before


def test_scan_pixel_and_animation_limits_are_enforced(admin_client):
    import io

    from PIL import Image

    created = admin_client.post(BASE, company_payload(), format="json")
    assert created.status_code == 201
    url = BASE + created.data["id"] + "/scans/stamp/"
    oversized = io.BytesIO()
    Image.new("1", (4001, 4001)).save(oversized, "PNG")
    animated = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(
        animated,
        "PNG",
        save_all=True,
        append_images=[Image.new("RGB", (10, 10), "blue")],
    )
    for data in (oversized.getvalue(), animated.getvalue()):
        assert len(data) < 2 * 1024 * 1024
        result = admin_client.put(
            url,
            {"file": SimpleUploadedFile("scan.png", data, "image/png")},
            format="multipart",
        )
        assert result.status_code == 400, result.content
