import hashlib
from pathlib import Path

import pytest
from django.test import override_settings

from legacy.models import LegacyFile
from legacy.tests.helpers import make_context


def test_all_files_are_private_and_hash_checked(org_a, tmp_path):
    from legacy.importer.files import project_files

    ctx = make_context(org_a, tmp_path / "snapshot", {})
    upload = ctx.reader.root.parent / "upload"
    upload.mkdir()
    content = b"private attachment"
    (upload / "unidentified").write_bytes(content)
    ctx.reader.manifest["files"] = [
        {
            "path": "unidentified",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    ]
    private = tmp_path / "private"
    with override_settings(LEGACY_FILE_ROOT=private):
        project_files(ctx)
        f = LegacyFile.objects.get(org=org_a)
        assert f.record_id is None
        assert (private / f.storage_key).read_bytes() == content
        assert Path(f.storage_key).is_absolute() is False
        (upload / "unidentified").write_bytes(b"changed")
        with pytest.raises(ValueError, match="checksum"):
            project_files(ctx)
