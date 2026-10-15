"""Hash-verified files live outside the public media tree."""

import os
import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from legacy.models import LegacyFile

from .identity import stable_id
from .reader import file_hash, safe_file


def private_root():
    root = Path(
        getattr(
            settings, "LEGACY_FILE_ROOT", Path(settings.BASE_DIR) / "legacy-private"
        )
    ).resolve()
    media = getattr(settings, "MEDIA_ROOT", None)
    if media and root.is_relative_to(Path(media).resolve()):
        raise ValueError("Historical files must be outside public media")
    return root


def project_files(ctx):
    root = private_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    uploads = ctx.reader.root.parent / "upload"
    for entry in ctx.reader.manifest["files"]:
        source = safe_file(uploads, entry["path"])
        if (
            source.stat().st_size != entry["size"]
            or file_hash(source) != entry["sha256"]
        ):
            raise ValueError("Source file checksum mismatch")
        key = str(ctx.source.pk) + "/" + entry["sha256"]
        target = safe_file(root, key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists():
            if file_hash(target) != entry["sha256"]:
                raise ValueError("Stored file checksum mismatch")
        else:
            fd, temp = tempfile.mkstemp(dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as out, source.open("rb") as incoming:
                    shutil.copyfileobj(incoming, out)
                if file_hash(temp) != entry["sha256"]:
                    raise ValueError("Copied file checksum mismatch")
                os.replace(temp, target)
            finally:
                Path(temp).unlink(missing_ok=True)
        # A raw upload filename is not evidence of association by itself.
        LegacyFile.objects.get_or_create(
            source=ctx.source,
            original_name=entry["path"],
            defaults={
                "id": stable_id("upload", entry["path"], "file"),
                "org": ctx.org,
                "storage_key": key,
                "size": entry["size"],
                "sha256": entry["sha256"],
            },
        )
