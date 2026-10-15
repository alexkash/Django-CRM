"""Normalize source links without signals, inferred parents, or discarded orphans."""

from collections import defaultdict

from django.apps import apps

from legacy.models import LegacyRecord, LegacyRelation

from .identity import stable_id

MODULES = {
    "Accounts": "accounts",
    "Contacts": "contacts",
    "Leads": "leads",
    "Opportunities": "opportunities",
    "Tasks": "tasks",
    "Calls": "calls",
    "Meetings": "meetings",
    "Emails": "emails",
    "Notes": "notes",
    "Users": "users",
    "Cases": "cases",
    "AOS_Invoices": "aos_invoices",
    "AOS_Quotes": "aos_quotes",
    "AOS_Products": "aos_products",
    "Documents": "documents",
    "Campaigns": "campaigns",
    "Prospects": "prospects",
    "ProspectLists": "prospect_lists",
    "Project": "project",
}
NATIVE = {
    "accounts": "accounts.Account",
    "contacts": "contacts.Contact",
    "leads": "leads.Lead",
    "opportunities": "opportunity.Opportunity",
    "tasks": "tasks.Task",
}
ACTOR_ROLES = {
    "created_by",
    "modified_user_id",
    "assigned_user_id",
    "participant_user",
    "address",
}


def add_members(obj, field, ids):
    """Direct through writes deliberately bypass m2m_changed/webhook dispatch."""
    manager = getattr(obj, field)
    through = manager.through
    left, right = manager.source_field_name, manager.target_field_name
    through.objects.bulk_create(
        [through(**{left + "_id": obj.pk, right + "_id": pk}) for pk in set(ids) if pk],
        ignore_conflicts=True,
    )


def native_parents(ctx, table, key):
    relations = LegacyRelation.objects.filter(
        source=ctx.source,
        from_record_id=ctx.record_id(table, key),
        source_deleted=False,
        state="resolved",
        to_table__in=NATIVE,
    ).exclude(role__in=ACTOR_ROLES)
    found = {}
    for edge in relations.select_related("to_record"):
        pk = ctx.native_id(edge.to_table, edge.to_record.source_pk)
        if pk:
            found[(edge.to_table, str(pk))] = (edge.to_table, pk)
    return list(found.values())


def project_relations(ctx):
    records = {
        (t, k): (pk, deleted)
        for t, k, pk, deleted in LegacyRecord.objects.filter(
            source=ctx.source
        ).values_list("source_table", "source_pk", "pk", "source_deleted")
    }
    # MySQL source references compare case-insensitively. Only use an unambiguous
    # spelling match; exact source IDs and their evidence never change.
    aliases = defaultdict(list)
    for table, key in records:
        aliases[(table, key.casefold())].append(key)

    def resolve(table, key):
        key = str(key)
        if (table, key) in records:
            return key, records[(table, key)]
        matches = aliases.get((table, key.casefold()), [])
        if len(matches) == 1:
            return matches[0], records[(table, matches[0])]
        return key, (None, False)

    pending = {}

    def edge(witness, ft, fid, tt, tid, role):
        if fid in (None, "") or tid in (None, ""):
            return
        fid, tid = str(fid), str(tid)
        _, (fp, fd) = resolve(ft, fid)
        _, (tp, td) = resolve(tt, tid)
        identity = [witness["table"], witness["source_id"], ft, fid, tt, tid, role]
        pk = stable_id("relations", str(identity), "edge")
        pending[pk] = LegacyRelation(
            id=pk,
            org=ctx.org,
            source=ctx.source,
            source_record_id=ctx.record_id(witness["table"], witness["source_id"]),
            from_record_id=fp,
            to_record_id=tp,
            from_table=ft,
            from_source_id=fid,
            to_table=tt,
            to_source_id=tid,
            role=role,
            state="missing"
            if not fp or not tp
            else "deleted_parent"
            if td or fd
            else "resolved",
            source_deleted=witness["deleted"],
        )
        if len(pending) >= 500:
            flush()

    def flush():
        LegacyRelation.objects.bulk_create(
            list(pending.values()), ignore_conflicts=True, batch_size=500
        )
        pending.clear()

    explicit = {
        "accounts_contacts": (
            "contacts",
            "contact_id",
            "accounts",
            "account_id",
            "account",
        ),
        "accounts_opportunities": (
            "opportunities",
            "opportunity_id",
            "accounts",
            "account_id",
            "account",
        ),
        "opportunities_contacts": (
            "opportunities",
            "opportunity_id",
            "contacts",
            "contact_id",
            "contact",
        ),
        "emails_text": ("emails_text", None, "emails", "email_id", "content"),
        "emails_email_addr_rel": (
            "emails",
            "email_id",
            "email_addresses",
            "email_address_id",
            "address",
        ),
    }
    for event in ("calls", "meetings"):
        for module in ("contacts", "leads", "users"):
            explicit[event + "_" + module] = (
                event,
                event[:-1] + "_id",
                module,
                module[:-1] + "_id",
                "participant_user" if module == "users" else "participant",
            )
    for table, (ft, fk, tt, tk, role) in explicit.items():
        for row in ctx.reader.rows(table):
            d = row["values"]
            edge(row, ft, d.get(fk) if fk else row["source_id"], tt, d.get(tk), role)
    # Reviewed source relationship definitions supply remaining join/direct FKs.
    # Table and field names are dictionary keys, never executed as SQL or PHP.
    rules = defaultdict(list)
    for row in ctx.reader.rows("relationships", True):
        d = row["values"]
        lt = d.get("lhs_table")
        rt = d.get("rhs_table")
        if lt not in ctx.reader.policy or rt not in ctx.reader.policy:
            continue
        join = d.get("join_table")
        if join and join in ctx.reader.policy and join not in explicit:
            rules[join].append(
                (lt, d.get("join_key_lhs"), rt, d.get("join_key_rhs"), d)
            )
        elif not join:
            if d.get("lhs_key") == "id" and d.get("rhs_key") not in (None, "", "id"):
                rules[rt].append((rt, None, lt, d["rhs_key"], d))
            elif d.get("rhs_key") == "id" and d.get("lhs_key") not in (None, "", "id"):
                rules[lt].append((lt, None, rt, d["lhs_key"], d))
    for table, entry in ctx.reader.manifest["tables"].items():
        if entry["category"] != "history" or not entry["total"]:
            continue
        for row in ctx.reader.rows(table):
            d = row["values"]
            key = row["source_id"]
            for ft, fk, tt, tk, rule in rules.get(table, []):
                col = rule.get("relationship_role_column")
                if col and str(d.get(col) or "") != str(
                    rule.get("relationship_role_column_value") or ""
                ):
                    continue
                # Join normalization: business child points toward its parent.
                if fk and ft == "accounts":
                    ft, tt, fk, tk = tt, ft, tk, fk
                role = (
                    "account"
                    if tt == "accounts"
                    else "participant_user"
                    if tt == "users"
                    else "related"
                )
                edge(row, ft, d.get(fk) if fk else key, tt, d.get(tk), role)
            if d.get("parent_id"):
                tt = MODULES.get(d.get("parent_type"))
                if tt:
                    edge(row, table, key, tt, d["parent_id"], "parent")
            if table == "emails_beans":
                edge(
                    row,
                    "emails",
                    d.get("email_id"),
                    MODULES.get(d.get("bean_module"), "unknown"),
                    d.get("bean_id"),
                    "parent",
                )
            if table == "email_addr_bean_rel":
                edge(
                    row,
                    "email_addresses",
                    d.get("email_address_id"),
                    MODULES.get(d.get("bean_module"), "unknown"),
                    d.get("bean_id"),
                    "address_owner",
                )
            if table == "sugarfeed":
                edge(
                    row,
                    table,
                    key,
                    MODULES.get(d.get("related_module"), "unknown"),
                    d.get("related_id"),
                    "parent",
                )
            if table.endswith("_cstm"):
                edge(row, table, key, table[:-5], d.get("id_c"), "fields")
            if table.endswith("_audit"):
                edge(row, table, key, table[:-6], d.get("parent_id"), "audit")
            for fk, tt in [
                ("account_id", "accounts"),
                ("contact_id", "contacts"),
                ("opportunity_id", "opportunities"),
                ("billing_account_id", "accounts"),
                ("billing_contact_id", "contacts"),
            ]:
                if table not in explicit:
                    edge(
                        row,
                        table,
                        key,
                        tt,
                        d.get(fk),
                        "account" if tt == "accounts" else "related",
                    )
            for actor in ("created_by", "modified_user_id", "assigned_user_id"):
                edge(row, table, key, "users", d.get(actor), actor)
    flush()
    project_native_links(ctx)


def project_native_links(ctx):
    from accounts.models import Account

    for table, label in NATIVE.items():
        model = apps.get_model(label)
        for row in ctx.reader.rows(table, True):
            pk = ctx.native_id(table, row["source_id"])
            if not pk:
                continue
            obj = model.objects.get(pk=pk)
            assignee = ctx.native_id(
                "users", row["values"].get("assigned_user_id"), "profile"
            )
            if hasattr(obj, "assigned_to") and assignee:
                add_members(obj, "assigned_to", [assignee])
            parents = native_parents(ctx, table, row["source_id"])
            accounts = {key for tab, key in parents if tab == "accounts"}
            if table == "contacts":
                for account_id in accounts:
                    add_members(Account.objects.get(pk=account_id), "contacts", [pk])
            if table in ("contacts", "opportunities") and len(accounts) == 1:
                account_id = next(iter(accounts))
                model.objects.filter(pk=pk).update(account_id=account_id)
                if table == "contacts":
                    add_members(Account.objects.get(pk=account_id), "contacts", [pk])
                ctx.restamp_projection(ctx.record_id(table, row["source_id"]))
            if hasattr(obj, "contacts"):
                add_members(
                    obj, "contacts", [key for tab, key in parents if tab == "contacts"]
                )
