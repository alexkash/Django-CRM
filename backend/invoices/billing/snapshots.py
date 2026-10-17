"""Freeze printable party data, units, dates and exact monetary values."""

import logging
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import NotFound, ValidationError

from accounts.access import visible_accounts_qs

from .assets import MAX_SCAN_SIZE, normalize_scan
from .formatting import amount_in_words_uk
from .models import LegalEntity
from .validators import validate_mfo, validate_registration_code, validate_ua_iban

PARTY_FIELDS = (
    "legal_name",
    "registration_code",
    "vat_registration_number",
    "legal_address",
    "iban",
    "bank_name",
    "mfo",
    "tax_system_text",
    "signer_name",
    "signer_title",
    "phone",
    "email",
)


def document_logo(invoice):
    """Freeze the issuer logo, with a bounded optional organization fallback."""
    png = (
        LegalEntity.objects.filter(pk=invoice.issuer_id, org_id=invoice.org_id)
        .values_list("logo_png", flat=True)
        .get()
    )
    if png:
        return bytes(png)
    logo = invoice.org.logo
    if not logo:
        return None
    try:
        with logo.open("rb") as stream:
            data = stream.read(MAX_SCAN_SIZE + 1)
        mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
        normalized = normalize_scan(SimpleUploadedFile("logo", data, mime))
        return normalized["png"]
    except Exception:
        # Storage backends raise different IO exceptions. A missing/invalid
        # optional fallback image must not prevent issuing a valid document.
        logging.getLogger(__name__).warning(
            "Optional organization logo unavailable for invoice %s", invoice.pk
        )
        return None


def party(account):
    data = {field: str(getattr(account, field, "") or "") for field in PARTY_FIELDS}
    data["legal_name"] = data["legal_name"] or account.name
    data["legal_address"] = data["legal_address"] or account.address_line or ""
    return data


def validate_period(start, end):
    if not start or not end or start > end:
        raise ValidationError(
            {"service_period": "Вкажіть коректний початок і кінець періоду послуг."}
        )


def invoice_snapshot(invoice, *, actor=None, preview=False):
    entity, bank = invoice.issuer, invoice.bank_account
    if (
        not entity
        or not bank
        or bank.entity_id != entity.pk
        or bank.org_id != invoice.org_id
    ):
        raise ValidationError("Перевірте нашу компанію та банківський рахунок.")
    if not preview and (not entity.active or not bank.active):
        raise ValidationError("Компанія або рахунок архівовані.")
    if actor:
        accounts = visible_accounts_qs(actor.profile)
        customer = accounts.filter(pk=invoice.account_id).first()
        payer = (
            accounts.filter(pk=invoice.payer_id).first()
            if invoice.payer_id
            else customer
        )
    else:
        customer, payer = invoice.account, invoice.payer or invoice.account
    if customer is None or payer is None:
        raise NotFound("Document party not found")
    customer_data = party(customer)
    overrides = invoice.draft_parties or {}
    customer_data.update(overrides.get("customer", {}))
    if invoice.payer_id:
        payer_data = party(payer)
        payer_data.update(overrides.get("payer", {}))
    else:
        payer_data = customer_data.copy()
    seller = {field: str(getattr(entity, field, "") or "") for field in PARTY_FIELDS}
    seller["legal_address"] = entity.address
    bank_data = {"iban": bank.iban, "bank_name": bank.bank_name, "mfo": bank.mfo}
    seller.update(bank_data)
    if not preview:
        validate_period(invoice.service_period_start, invoice.service_period_end)
        if bool(invoice.contract_number) != bool(invoice.contract_date):
            raise ValidationError(
                {"contract_number": "Вкажіть номер і дату договору разом."}
            )
        for label, data in [
            ("seller", seller),
            ("customer", customer_data),
            ("payer", payer_data),
        ]:
            if any(
                not data.get(field, "").strip()
                for field in (
                    "legal_name",
                    "registration_code",
                    "legal_address",
                    "signer_name",
                )
            ):
                raise ValidationError(
                    {label: "Потрібні найменування, код, адреса та підписант."}
                )
            for field, validator in (
                ("registration_code", validate_registration_code),
                ("iban", validate_ua_iban),
                ("mfo", validate_mfo),
            ):
                try:
                    data[field] = validator(data.get(field, ""))
                except ValidationError as exc:
                    raise ValidationError({label: {field: exc.detail}}) from exc
    lines = []
    for item in invoice.line_items.order_by("order", "id"):
        lines.append(
            {
                "source_line_id": str(item.pk),
                "name": item.name or item.description,
                "description": item.description if item.name else "",
                "unit": item.unit,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "net_amount": str(item.subtotal),
                "vat_amount": str(item.tax_amount),
                "total_amount": str(item.total),
            }
        )
    if not preview and not lines:
        raise ValidationError({"line_items": "Додайте хоча б одну позицію."})
    return {
        "kind": "invoice",
        "template_version": 1,
        "draft": preview,
        "number": "без номера" if preview else invoice.invoice_number,
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
        "place": invoice.place_of_issue or entity.city,
        "service_period_start": invoice.service_period_start.isoformat()
        if invoice.service_period_start
        else "",
        "service_period_end": invoice.service_period_end.isoformat()
        if invoice.service_period_end
        else "",
        "contract_number": invoice.contract_number,
        "contract_date": invoice.contract_date.isoformat()
        if invoice.contract_date
        else "",
        "order_reference": invoice.order_reference,
        "seller": seller,
        "bank": bank_data,
        "customer": customer_data,
        "payer": payer_data,
        "lines": lines,
        "vat_status": invoice.vat_status,
        "vat_rate": str(invoice.tax_rate),
        "subtotal": str(invoice.subtotal),
        "tax_amount": str(invoice.tax_amount),
        "total_amount": str(invoice.total_amount),
        "amount_words": amount_in_words_uk(Decimal(invoice.total_amount)),
        "notes": invoice.notes,
        "terms": invoice.terms,
        "signature_sha256": entity.signature_sha256,
        "stamp_sha256": entity.stamp_sha256,
    }
