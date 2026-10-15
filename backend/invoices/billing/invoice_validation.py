"""Opt-in validation used by the existing invoice serializer and line APIs."""

from decimal import Decimal

from rest_framework import serializers

from accounts.access import visible_accounts_qs

from .models import LegalEntity, LegalEntityBankAccount
from .money import LineInput, calculate_ua_totals

UA_WRITE_FIELDS = (
    "issuer_id",
    "bank_account_id",
    "payer_id",
    "contract_number",
    "contract_date",
    "order_reference",
    "service_period_start",
    "service_period_end",
    "place_of_issue",
    "draft_parties",
)
PRINT_FIELDS = {
    "invoice_title",
    "account_id",
    "contact_id",
    "client_name",
    "client_email",
    "client_phone",
    "issue_date",
    "due_date",
    "payment_terms",
    "notes",
    "terms",
    "billing_period",
    "po_number",
    "template_id",
    "line_items",
    *UA_WRITE_FIELDS,
}


def validate_ua_invoice(serializer, attrs):
    old = serializer.instance
    issuer_id = attrs.get("issuer_id", old.issuer_id if old else None)
    if old and bool(old.issuer_id) != bool(issuer_id):
        raise serializers.ValidationError(
            {
                "issuer_id": "Формат рахунку обирається під час створення і не змінюється."
            }
        )
    if not issuer_id:
        if any(
            attrs.get(k) not in (None, "", {})
            for k in UA_WRITE_FIELDS
            if k != "issuer_id"
        ):
            raise serializers.ValidationError({"issuer_id": "Оберіть нашу компанію."})
        return attrs
    if old and old.issued_at:
        for key, value in attrs.items():
            if key in PRINT_FIELDS or key.startswith(("billing_", "client_")):
                if key == "line_items" or value != getattr(old, key, None):
                    raise serializers.ValidationError(
                        {key: "Виписаний документ не редагується."}
                    )
    entity = LegalEntity.objects.filter(org=serializer.org, pk=issuer_id).first()
    if entity is None or (not entity.active and not (old and old.issued_at)):
        raise serializers.ValidationError({"issuer_id": "Компанія недоступна."})
    bank_id = attrs.get("bank_account_id", old.bank_account_id if old else None)
    bank = (
        LegalEntityBankAccount.objects.filter(
            org=serializer.org, pk=bank_id, entity=entity
        ).first()
        if bank_id
        else None
    )
    if bank is None or (not bank.active and not (old and old.issued_at)):
        raise serializers.ValidationError(
            {"bank_account_id": "Оберіть активний рахунок цієї компанії."}
        )
    payer_id = attrs.get("payer_id", old.payer_id if old else None)
    if (
        payer_id
        and (not old or payer_id != old.payer_id)
        and not visible_accounts_qs(serializer.profile).filter(pk=payer_id).exists()
    ):
        raise serializers.ValidationError({"payer_id": "Платник недоступний."})
    for field in ("public_link_enabled", "reminder_enabled"):
        if attrs.get(field, False):
            raise serializers.ValidationError(
                {field: "Недоступно для української форми."}
            )
        attrs[field] = False

    def val(field, default):
        return attrs.get(field, getattr(old, field, default) if old else default)

    if val("currency", "UAH") != "UAH":
        raise serializers.ValidationError(
            {"currency": "Українська форма підтримує UAH."}
        )
    if any(Decimal(str(val(k, 0))) != 0 for k in ("discount_value", "shipping_amount")):
        raise serializers.ValidationError(
            "Українська форма першої версії без знижок і доставки."
        )
    start, end = val("service_period_start", None), val("service_period_end", None)
    if start and end and start > end:
        raise serializers.ValidationError(
            {"service_period_end": "Закінчення раніше початку."}
        )
    rate = val("tax_rate", entity.default_vat_rate)
    if entity.vat_status == "NON_PAYER" and rate != 0:
        raise serializers.ValidationError({"tax_rate": "Компанія не є платником ПДВ."})
    attrs["vat_status"] = old.vat_status if old and old.issued_at else entity.vat_status
    if not old or not old.issued_at:
        attrs["tax_rate"] = rate
    attrs["currency"] = "UAH"
    lines = attrs.get("line_items")
    if lines is not None:
        for line in lines:
            if line.get("discount_value", 0) != 0:
                raise serializers.ValidationError({"line_items": "Знижки недоступні."})
            line["tax_rate"] = rate
            line["unit"] = (
                line.get("unit")
                or (line.get("product").unit if line.get("product") else "")
                or "послуга"
            )
        try:
            calculate_ua_totals(
                [
                    LineInput(
                        line.get("quantity", Decimal(1)),
                        line.get("unit_price", Decimal(0)),
                    )
                    for line in lines
                ],
                attrs["vat_status"],
                rate,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"line_items": str(exc)}) from exc
    if lines is None and old and not old.issued_at:
        try:
            calculate_ua_totals(
                [
                    LineInput(line.quantity, line.unit_price)
                    for line in old.line_items.all()
                ],
                attrs["vat_status"],
                rate,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"tax_rate": str(exc)}) from exc
    if "draft_parties" in attrs:
        parties = attrs["draft_parties"]
        allowed = {
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
        }
        if not isinstance(parties, dict) or any(
            key not in ("customer", "payer")
            or not isinstance(data, dict)
            or any(
                k not in allowed or not isinstance(v, str) or len(v) > 500
                for k, v in data.items()
            )
            for key, data in parties.items()
        ):
            raise serializers.ValidationError(
                {"draft_parties": "Некоректні реквізити сторони."}
            )
    return attrs


def validate_ua_line(attrs, invoice, instance=None):
    """Standalone line writes obey the same UA mode as nested writes."""
    if not invoice.issuer_id:
        return attrs
    value = attrs.get("discount_value", instance.discount_value if instance else 0)
    if value != 0:
        raise serializers.ValidationError(
            {"discount_value": "Знижки недоступні для українського рахунку."}
        )
    attrs["tax_rate"] = invoice.tax_rate
    attrs["unit"] = attrs.get("unit", instance.unit if instance else "") or "послуга"
    rows = invoice.line_items.all()
    if instance:
        rows = rows.exclude(pk=instance.pk)
    inputs = [LineInput(line.quantity, line.unit_price) for line in rows]
    inputs.append(
        LineInput(
            attrs.get("quantity", instance.quantity if instance else Decimal(1)),
            attrs.get("unit_price", instance.unit_price if instance else Decimal(0)),
        )
    )
    try:
        calculate_ua_totals(
            inputs,
            invoice.vat_status or invoice.issuer.vat_status,
            Decimal(str(invoice.tax_rate)),
        )
    except ValueError as exc:
        raise serializers.ValidationError({"line_items": str(exc)}) from exc
    return attrs
