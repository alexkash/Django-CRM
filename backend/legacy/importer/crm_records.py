"""Native projections for editable CRM entities, preserving all source values separately."""

from accounts.models import Account
from contacts.models import Contact
from invoices.models import Product
from leads.models import Lead
from opportunity.models import Opportunity

from .contracts import source_time
from .fields import (
    choice,
    country,
    currency,
    decimal,
    email,
    integer,
    original_fields,
    phone,
    url,
)
from .identity import stable_id
from .stages import deal_stage, lead_stage


def _ordered(ctx, table, rows):
    return sorted(
        list(rows if rows is not None else ctx.reader.rows(table, True)),
        key=lambda r: (r["values"].get("date_entered") or "", r["source_id"]),
    )


def _audit(ctx, data):
    return {"created_by_id": ctx.actor(data), "updated_by_id": ctx.updater(data)}


def _address(data, prefix):
    return {
        "address_line": data.get(prefix + "street"),
        "city": data.get(prefix + "city"),
        "state": data.get(prefix + "state"),
        "postcode": data.get(prefix + "postalcode"),
        "country": country(data.get(prefix + "country")),
    }


def project_accounts(ctx, rows=None):
    used = {
        name.lower()
        for name in Account.objects.filter(org=ctx.org).values_list("name", flat=True)
    }
    for row in _ordered(ctx, "accounts", rows):
        d = row["values"]
        key = row["source_id"]
        old = ctx.native_id("accounts", key)
        if old:
            ctx.write("accounts", row, Account(id=old))
            continue
        original = str(d.get("name") or "")
        name = original or f"SuiteCRM account {key}"
        if name.lower() in used:
            name = f"{name} [SuiteCRM:{key}]"
        if name.lower() in used:
            name = f"{original} [SuiteCRM:{stable_id('accounts', key)}]"
        if len(name) > 255:
            raise ValueError(
                "Source company name cannot be represented without truncation"
            )
        used.add(name.lower())
        address = ctx.primary_email("Accounts", key)
        custom = original_fields(ctx, "accounts", d, address)
        obj = Account(
            id=stable_id("accounts", key),
            org=ctx.org,
            name=name,
            email=email(address),
            phone=phone(d.get("phone_office")),
            website=url(d.get("website")),
            industry=choice(Account, "industry", d.get("industry")),
            number_of_employees=integer(d.get("employees")),
            description=d.get("description"),
            annual_revenue=decimal(d.get("annual_revenue")),
            currency=currency(ctx, d.get("currency_id")),
            custom_fields=custom,
            **_address(d, "billing_address_"),
            **_audit(ctx, d),
        )
        ctx.write(
            "accounts",
            row,
            obj,
            adaptations=[
                {"field": "name", "reason": "duplicate_name", "original": original}
            ]
            if name != original
            else [],
        )
    return ctx.results


def _people(ctx, table, model, module, rows):
    used = {
        x.lower()
        for x in model.objects.filter(org=ctx.org)
        .exclude(email__isnull=True)
        .exclude(email="")
        .values_list("email", flat=True)
    }
    for row in _ordered(ctx, table, rows):
        key = row["source_id"]
        d = row["values"]
        old = ctx.native_id(table, key)
        if old:
            ctx.write(table, row, model(id=old))
            continue
        original = ctx.primary_email(module, key)
        address = email(original)
        adaptations = []
        if address and address in used:
            adaptations.append(
                {"field": "email", "reason": "duplicate_email", "original": original}
            )
            address = None
        if address:
            used.add(address)
        work = d.get("phone_work") or d.get("phone_mobile")
        native_phone = phone(work)
        if work and native_phone is None:
            adaptations.append(
                {
                    "field": "phone",
                    "reason": "original_phone_preserved",
                    "original": work,
                }
            )
        values = {
            "id": stable_id(table, key),
            "org": ctx.org,
            "first_name": d.get("first_name") or "",
            "last_name": d.get("last_name") or "",
            "email": address,
            "phone": native_phone,
            "description": d.get("description"),
            "custom_fields": original_fields(ctx, table, d, original),
            **_address(d, "primary_address_"),
            **_audit(ctx, d),
        }
        if table == "contacts":
            values.update(
                title=d.get("title"), organization=d.get("account_name") or ""
            )
        else:
            label = d.get("status") or "New"
            stage = lead_stage(ctx, label)
            values.update(
                title=" ".join(
                    str(d.get(k) or "") for k in ("first_name", "last_name")
                ).strip()
                or d.get("account_name")
                or f"SuiteCRM lead {key}",
                job_title=d.get("title"),
                company_name=d.get("account_name"),
                website=url(d.get("website")),
                salutation=d.get("salutation"),
                source=choice(Lead, "source", d.get("lead_source")),
                industry=choice(Lead, "industry", d.get("industry")),
                status=stage.maps_to_status,
                stage=stage,
                currency=currency(ctx, d.get("currency_id")),
            )
        ctx.write(table, row, model(**values), adaptations=adaptations)
    return ctx.results


def project_contacts(ctx, rows=None):
    return _people(ctx, "contacts", Contact, "Contacts", rows)


def project_leads(ctx, rows=None):
    return _people(ctx, "leads", Lead, "Leads", rows)


def project_opportunities(ctx, rows=None):
    changes = {}
    for audit in ctx.reader.rows("opportunities_audit"):
        d = audit["values"]
        if d.get("field_name") == "sales_stage":
            at = source_time(d.get("date_created"))
            if at and at > changes.get(str(d.get("parent_id")), at.replace(year=1)):
                changes[str(d.get("parent_id"))] = at
    for row in _ordered(ctx, "opportunities", rows):
        d = row["values"]
        key = row["source_id"]
        old = ctx.native_id("opportunities", key)
        if old:
            ctx.write("opportunities", row, Opportunity(id=old))
            continue
        pipeline, stage = deal_stage(ctx, d.get("sales_stage") or "")
        probability = d.get("probability")
        try:
            probability = (
                int(probability)
                if probability is not None and 0 <= int(probability) <= 100
                else None
            )
        except (ValueError, TypeError):
            probability = None
        closed = source_time(d.get("date_closed"))
        obj = Opportunity(
            id=stable_id("opportunities", key),
            org=ctx.org,
            name=str(d.get("name") or f"SuiteCRM deal {key}"),
            pipeline=pipeline,
            stage=stage.code,
            amount=decimal(d.get("amount")),
            currency=currency(ctx, d.get("currency_id")),
            probability=probability,
            description=d.get("description"),
            closed_on=closed.date() if closed else None,
            stage_changed_at=changes.get(key),
            custom_fields=original_fields(ctx, "opportunities", d),
            **_audit(ctx, d),
        )
        ctx.write("opportunities", row, obj)
    return ctx.results


def project_products(ctx, rows=None):
    for row in _ordered(ctx, "aos_products", rows):
        d = row["values"]
        key = row["source_id"]
        old = ctx.native_id("aos_products", key)
        if old:
            ctx.write("aos_products", row, Product(id=old))
            continue
        price = decimal(d.get("price"))
        if price is None:
            raise ValueError(
                "Source product price cannot be represented without guessing"
            )
        obj = Product(
            id=stable_id("aos_products", key),
            org=ctx.org,
            name=d.get("name") or f"SuiteCRM product {key}",
            description=d.get("description"),
            sku=d.get("part_number") or None,
            price=price,
            currency=currency(ctx, d.get("currency_id")),
            **_audit(ctx, d),
        )
        ctx.write("aos_products", row, obj)
    return ctx.results
