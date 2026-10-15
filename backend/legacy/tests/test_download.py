import hashlib

from django.test import override_settings

from legacy.models import LegacyFile
from legacy.tests.test_access import linked_context


def test_hidden_second_parent_hides_record_and_file(
    org_a, tmp_path, regular_user, user_client, admin_client, org_b_client
):
    ctx = linked_context(org_a, tmp_path / "snapshot", regular_user)
    content = b"private file"
    private = tmp_path / "private"
    private.mkdir()
    (private / "blob").write_bytes(content)
    file = LegacyFile.objects.create(
        org=org_a,
        source=ctx.source,
        record_id=ctx.record_id("emails", "e"),
        storage_key="blob",
        original_name="original.txt",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    url = f"/api/legacy/files/{file.pk}/download/"
    with override_settings(LEGACY_FILE_ROOT=private):
        assert user_client.get(url).status_code == 404
        assert org_b_client.get(url).status_code == 404
        response = admin_client.get(url)
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == content
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Content-Disposition"].startswith("attachment;")
        (private / "blob").write_bytes(b"changed")
        assert admin_client.get(url).status_code == 409


def test_unidentified_files_are_discoverable_only_by_admin(
    org_a, tmp_path, regular_user, user_client, admin_client
):
    ctx = linked_context(org_a, tmp_path / "snapshot", regular_user)
    file = LegacyFile.objects.create(
        org=org_a,
        source=ctx.source,
        storage_key="private-key",
        original_name="unknown.bin",
        size=0,
        sha256=hashlib.sha256(b"").hexdigest(),
    )
    response = admin_client.get("/api/legacy/files/")
    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == str(file.pk)
    assert "storage_key" not in response.json()["results"][0]
    assert user_client.get("/api/legacy/files/").json()["count"] == 0
