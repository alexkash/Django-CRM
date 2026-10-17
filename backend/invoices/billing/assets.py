"""Decode untrusted raster scans before storing a private normalized PNG."""

import hashlib
import io
import warnings

from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_SCAN_SIZE = 2 * 1024 * 1024
MAX_PIXELS = 16_000_000


def normalize_scan(upload):
    if upload.size > MAX_SCAN_SIZE or upload.content_type not in (
        "image/png",
        "image/jpeg",
    ):
        raise ValidationError({"file": "Завантажте PNG/JPEG до 2 MiB."})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                if (
                    image.format not in ("PNG", "JPEG")
                    or getattr(image, "n_frames", 1) != 1
                    or image.width * image.height > MAX_PIXELS
                ):
                    raise ValueError("Invalid scan dimensions or format")
                if (image.format == "PNG") != (upload.content_type == "image/png"):
                    raise ValueError("MIME does not match image")
                image.load()
                out = io.BytesIO()
                image.convert("RGBA").save(out, "PNG")
                png = out.getvalue()
                if len(png) > MAX_SCAN_SIZE:
                    raise ValueError("Normalized image too large")
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError({"file": "Некоректне або завелике зображення."}) from exc
    return {"png": png, "sha256": hashlib.sha256(png).hexdigest()}
