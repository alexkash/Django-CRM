"""Synthetic parties and image data; no real company scans."""

import io

from PIL import Image


def company_payload(**overrides):
    return {
        "entity_type": "LLC",
        "legal_name": "ТОВ Тестові Послуги",
        "registration_code": "12345678",
        "address": "м. Київ, вулиця Тестова, 1",
        "city": "Київ",
        "vat_status": "PAYER",
        "default_vat_rate": "20.00",
        "signer_name": "Тестовий Виконавець",
        "signer_title": "Директор",
        **overrides,
    }


def scan_bytes(fmt="PNG"):
    out = io.BytesIO()
    Image.new("RGB", (40, 24), (20, 70, 160)).save(out, fmt)
    return out.getvalue()
