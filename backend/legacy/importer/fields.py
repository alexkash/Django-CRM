"""Conservative native-field projections; originals remain in immutable history."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email

from common.models import CustomFieldDefinition
from common.utils import COUNTRIES, CURRENCY_CODES
from common.validators import flexible_phone_validator

MODULES = {
    "accounts": "Account",
    "contacts": "Contact",
    "leads": "Lead",
    "opportunities": "Opportunity",
    "tasks": "Task",
    "aos_invoices": "Invoice",
    "aos_quotes": "Estimate",
    "cases": "Case",
}


def flag(value):
    return str(value).lower() in ("1", "true", "yes")


def email(value):
    value = str(value or "").strip().lower()
    try:
        validate_email(value)
    except ValidationError:
        return None
    return value


def url(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        URLValidator(schemes=["http", "https"])(value)
    except ValidationError:
        return None
    return value


def choice(model, field, value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().casefold()
    return next(
        (
            key
            for key, label in model._meta.get_field(field).choices
            if normalized in (str(key).casefold(), str(label).casefold())
        ),
        None,
    )


def integer(value):
    try:
        result = int(str(value))
        return result if 0 <= result <= 2147483647 else None
    except (TypeError, ValueError):
        return None


def phone(value):
    value = str(value or "").strip()
    if (
        not value
        or any(c in value for c in ",;/\n\r")
        or value.count("+") > 1
        or len([c for c in value if c.isdigit()]) > 15
    ):
        return None
    try:
        flexible_phone_validator(value)
    except ValidationError:
        return None
    return value


def decimal(value, nonnegative=True):
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or (nonnegative and result < 0):
            return None
        if result.quantize(Decimal("0.01")) != result:
            return None
        return result.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def country(value):
    value = str(value or "").strip().lower()
    return next(
        (
            code
            for code, label in COUNTRIES
            if value in (str(code).lower(), str(label).lower())
        ),
        None,
    )


def currency(ctx, value):
    if value in (None, ""):
        return None
    if str(value) == "-99":
        code = ctx.reader.manifest.get("safe_config", {}).get(
            "default_currency_iso4217"
        )
    else:
        row = ctx.reader.get("currencies", value)
        if row:
            code = row["values"].get("iso4217")
        else:
            aliases = {
                r["values"].get("iso4217")
                for r in ctx.reader.rows("currencies")
                if str(value).strip().casefold()
                in {
                    str(r["values"].get("name") or "").casefold(),
                    str(r["values"].get("iso4217") or "").casefold(),
                }
            }
            if len(aliases) > 1:
                raise ValueError("Source currency alias is ambiguous")
            code = next(iter(aliases), None)
    if code and code not in dict(CURRENCY_CODES):
        raise ValueError("Source currency is unsupported by the CRM: " + str(code))
    return code


def define(ctx, target, key, label, field_type="text", options=None):
    cache = getattr(ctx, "field_definitions", None)
    if cache is None:
        ctx.field_definitions = cache = {}
    cache_key = (target, key)
    if cache_key in cache:
        return cache[cache_key]
    definition, created = CustomFieldDefinition.objects.get_or_create(
        org=ctx.org,
        target_model=target,
        key=key,
        defaults={
            "label": label,
            "field_type": field_type,
            "options": options,
            "is_required": False,
        },
    )
    if not created and (
        definition.field_type != field_type or definition.label != label
    ):
        raise ValueError(
            "Existing custom-field definition conflicts with migration namespace"
        )
    cache[cache_key] = definition
    return definition


def original_fields(ctx, table, data, primary_email=""):
    target = MODULES[table]
    fields = {}
    originals = [
        ("name", "suitecrm_original_name", "Исходное название SuiteCRM"),
        (
            "phone_work",
            "suitecrm_original_work_phone",
            "Исходный рабочий телефон SuiteCRM",
        ),
        (
            "phone_office",
            "suitecrm_original_work_phone",
            "Исходный рабочий телефон SuiteCRM",
        ),
        (
            "phone_mobile",
            "suitecrm_original_mobile_phone",
            "Исходный мобильный телефон SuiteCRM",
        ),
        ("status", "suitecrm_original_status", "Исходный статус SuiteCRM"),
    ]
    for source, key, label in originals:
        value = data.get(source)
        if value not in (None, ""):
            define(ctx, target, key, label)
            fields[key] = str(value)
    if primary_email:
        define(ctx, target, "suitecrm_original_email", "Исходный email SuiteCRM")
        fields["suitecrm_original_email"] = primary_email
    custom = (
        ctx.reader.get(table + "_cstm", data.get("id"))
        if table + "_cstm" in ctx.reader.policy
        else None
    )
    if custom:
        for key, value in custom["values"].items():
            if key in ("id_c", "date_entered", "date_modified") or value in (None, ""):
                continue
            definition = CustomFieldDefinition.objects.filter(
                org=ctx.org, target_model=target, key=key
            ).first()
            if definition:
                if definition.field_type == "checkbox":
                    value = flag(value)
                elif definition.field_type == "number":
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        continue
                else:
                    value = str(value)
                fields[key] = value
    return fields


def project_definitions(ctx):
    from .labels import source_labels, source_lists

    labels = source_labels(ctx.reader)
    lists = source_lists(ctx.reader)
    for row in ctx.reader.rows("fields_meta_data", True):
        d = row["values"]
        table = {
            "Accounts": "accounts",
            "Contacts": "contacts",
            "Leads": "leads",
            "Opportunities": "opportunities",
            "Cases": "cases",
            "AOS_Invoices": "aos_invoices",
            "AOS_Quotes": "aos_quotes",
        }.get(d.get("custom_module"))
        if table not in MODULES:
            continue
        key = d.get("name")
        if not key or len(key) > 64:
            continue
        kind = {
            "varchar": "text",
            "text": "textarea",
            "bool": "checkbox",
            "float": "number",
            "decimal": "number",
            "int": "number",
            "date": "date",
            "enum": "dropdown",
        }.get(d.get("type"))
        if not kind:
            continue
        options = None
        if kind == "dropdown":
            values = sorted(
                {
                    str(r["values"][key])
                    for r in ctx.reader.rows(table + "_cstm")
                    if r["values"].get(key) not in (None, "")
                }
            )
            options = lists.get(d.get("ext1"), [])
            known = {item["value"] for item in options}
            options = options + [
                {"value": v, "label": v} for v in values if v not in known
            ]
            if not options:
                continue
        define(
            ctx,
            MODULES[table],
            key,
            labels.get(
                (d.get("custom_module"), d.get("vname")),
                labels.get(("", d.get("vname")), key),
            ),
            kind,
            options,
        )
