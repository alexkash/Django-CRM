"""Historical messages are inert projections; no delivery or recipient creation."""

from collections import defaultdict
from email.utils import getaddresses

from accounts.models import AccountEmail
from legacy.models import LegacyRelation

from .contracts import source_time
from .fields import email
from .identity import stable_id
from .relations import add_members, native_parents


def addresses(value):
    return [
        {"name": name, "address": address}
        for name, address in getaddresses([str(value or "")])
        if address
    ]


def project_communications(ctx):
    bodies = {}
    for row in ctx.reader.rows("emails_text", True):
        key = str(row["values"].get("email_id"))
        if key in bodies:
            raise ValueError("Multiple active bodies for one historical email")
        bodies[key] = row["values"]
    address_index = {
        r["source_id"]: r["values"].get("email_address", "")
        for r in ctx.reader.rows("email_addresses", True)
    }
    structured = {}
    for link in ctx.reader.rows("emails_email_addr_rel", True):
        d = link["values"]
        kind = str(d.get("address_type") or "").lower()
        if kind in ("from", "to", "cc", "bcc"):
            structured.setdefault((str(d.get("email_id")), kind), []).extend(
                addresses(address_index.get(str(d.get("email_address_id"))))
            )
    contact_emails = defaultdict(set)
    contact_ids = {r["source_id"] for r in ctx.reader.rows("contacts", True)}
    for link in ctx.reader.rows("email_addr_bean_rel", True):
        d = link["values"]
        source_contact = str(d.get("bean_id"))
        address = address_index.get(str(d.get("email_address_id")), "")
        if (
            d.get("bean_module") == "Contacts"
            and source_contact in contact_ids
            and email(address)
        ):
            contact_emails[email(address)].add(source_contact)
    for row in ctx.reader.rows("emails", True):
        d = row["values"]
        body = bodies.get(row["source_id"], {})
        headers = {
            field: addresses(body.get(column))
            for field, column in [
                ("from_addresses", "from_addr"),
                ("to_addresses", "to_addrs"),
                ("cc_addresses", "cc_addrs"),
                ("bcc_addresses", "bcc_addrs"),
            ]
        }
        for kind in ("from", "to", "cc", "bcc"):
            known = {a["address"].casefold() for a in headers[kind + "_addresses"]}
            headers[kind + "_addresses"].extend(
                a
                for a in structured.get((row["source_id"], kind), [])
                if a["address"].casefold() not in known
            )
        parents = native_parents(ctx, "emails", row["source_id"])
        accounts = {pk for tab, pk in parents if tab == "accounts"}
        sender = headers["from_addresses"]
        obj = AccountEmail(
            id=stable_id("emails", row["source_id"]),
            org=ctx.org,
            is_historical=True,
            source_status=d.get("status") or "",
            source_message_id=d.get("message_id") or "",
            sent_at=source_time(d.get("date_sent_received")),
            message_subject=d.get("name"),
            message_body=body.get("description_html"),
            body_text=body.get("description") or "",
            from_email=email(sender[0]["address"]) or "" if sender else "",
            from_account_id=next(iter(accounts)) if len(accounts) == 1 else None,
            created_by_id=ctx.actor(d),
            updated_by_id=ctx.updater(d),
            **headers,
        )
        message = ctx.write("emails", row, obj)
        matched = set()
        for kind in ("to", "cc", "bcc"):
            for address in headers[kind + "_addresses"]:
                candidates = contact_emails.get(email(address["address"]), set())
                if len(candidates) == 1:
                    contact_key = next(iter(candidates))
                    pk = ctx.native_id("contacts", contact_key)
                    if pk:
                        matched.add(pk)
                        LegacyRelation.objects.get_or_create(
                            source=ctx.source,
                            org=ctx.org,
                            source_record_id=ctx.record_id("emails", row["source_id"]),
                            from_record_id=ctx.record_id("emails", row["source_id"]),
                            to_record_id=ctx.record_id("contacts", contact_key),
                            from_table="emails",
                            from_source_id=row["source_id"],
                            to_table="contacts",
                            to_source_id=contact_key,
                            role="recipient_match",
                            defaults={
                                "id": stable_id(
                                    "email_recipient", row["source_id"], contact_key
                                )
                            },
                        )
        add_members(message, "recipients", matched)
        add_members(
            message, "recipients", [pk for tab, pk in parents if tab == "contacts"]
        )
