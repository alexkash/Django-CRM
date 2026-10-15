"""One all-parent read policy, evaluated by the database before pagination/search."""

from django.db import connection
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.shortcuts import get_object_or_404

from common.permissions import is_org_admin
from legacy.models import LegacyProjection, LegacyRecord

NATIVE_TABLES = {"accounts", "contacts", "leads", "opportunities", "tasks"}
EVENT_TABLES = {
    "calls",
    "meetings",
    "emails",
    "emails_text",
    "notes",
    "sugarfeed",
    "email_addresses",
    "accounts_contacts",
    "accounts_opportunities",
    "opportunities_contacts",
    "emails_beans",
    "emails_email_addr_rel",
    "email_addr_bean_rel",
    "calls_contacts",
    "calls_leads",
    "calls_users",
    "meetings_contacts",
    "meetings_leads",
    "meetings_users",
    "aos_invoices",
    "aos_quotes",
}
ACTOR_ROLES = (
    "created_by",
    "modified_user_id",
    "assigned_user_id",
    "participant_user",
    "address",
)


def read_rules(profile):
    from accounts.access import visible_accounts_qs
    from contacts.access import visible_contacts_qs
    from leads.access import visible_leads_qs
    from opportunity.access import visible_deals_qs
    from tasks.access import _base_visible_tasks_qs

    return {
        "accounts.Account": visible_accounts_qs(profile),
        "contacts.Contact": visible_contacts_qs(profile),
        "leads.Lead": visible_leads_qs(profile),
        "opportunity.Opportunity": visible_deals_qs(profile),
        "tasks.Task": _base_visible_tasks_qs(profile),
    }


def _readable_records_cte(profile):
    """Shared policy CTE, kept at one SQL level for every consumer."""
    qs = LegacyRecord.objects.filter(org=profile.org)
    rules = read_rules(profile)
    readable = Q(pk__in=[])
    for label, visible in rules.items():
        readable |= Q(target_model=label, target_id__in=visible.values("pk"))
    projections = LegacyProjection.objects.filter(
        org=profile.org, target_model__in=rules
    )
    good = projections.filter(readable)
    bad = projections.exclude(readable)
    known = (
        NATIVE_TABLES
        | EVENT_TABLES
        | {
            t + suffix
            for t in NATIVE_TABLES
            | {"calls", "meetings", "notes", "aos_invoices", "aos_quotes"}
            for suffix in ("_audit", "_cstm")
        }
    )
    eligible = qs.filter(source_deleted=False, source_table__in=known).exclude(
        id__in=bad.values("record_id")
    )
    # A historical invoice does not inherit financial permission from its company.
    # Its own source creator/assignee must also be this authenticated identity.
    from legacy.models import LegacyRelation

    actor_records = LegacyProjection.objects.filter(
        org=profile.org, target_model="common.User", target_id=profile.user_id
    ).values("record_id")
    financial_owned = LegacyRelation.objects.filter(
        org=profile.org,
        role__in=["created_by", "assigned_user_id"],
        to_record_id__in=actor_records,
        state="resolved",
        source_deleted=False,
    ).values("from_record_id")
    eligible = eligible.exclude(
        Q(source_table__in=["aos_invoices", "aos_quotes"]) & ~Q(id__in=financial_owned)
    )
    eligible_sql, eligible_params = eligible.values("id").query.sql_with_params()
    anchors = good.filter(role="native", record__source_table__in=NATIVE_TABLES)
    good_sql, good_params = anchors.values("record_id").query.sql_with_params()
    # Graph edges represent dependencies, not general undirected relationships.
    # Join/body evidence also depends on the ends it describes. UNION terminates
    # cycles; a cycle with no readable native anchor never becomes grounded.
    roles = ",".join(["%s"] * len(ACTOR_ROLES))
    sql = f"""
    WITH RECURSIVE eligible(id) AS ({eligible_sql}),
    anchors(id) AS ({good_sql}),
    relevant AS (
        SELECT source_record_id witness,from_record_id child,to_record_id parent,state
        FROM legacy_relation WHERE org_id=%s AND NOT source_deleted
        AND role NOT IN ({roles}) AND to_table <> 'users'
    ), edges(child,parent) AS (
        SELECT child,parent FROM relevant WHERE child IS NOT NULL
        UNION SELECT witness,child FROM relevant WHERE child IS NOT NULL AND witness<>child
        UNION SELECT witness,parent FROM relevant WHERE witness<>parent OR parent IS NULL
    ), bad(id) AS (
        SELECT id FROM legacy_record WHERE org_id=%s AND id NOT IN (SELECT id FROM eligible)
        UNION SELECT witness FROM relevant WHERE state<>'resolved'
        UNION SELECT child FROM edges WHERE parent IS NULL
        UNION SELECT e.child FROM edges e JOIN bad b ON e.parent=b.id
    ), grounded(id) AS (
        SELECT id FROM anchors
        UNION SELECT e.child FROM edges e JOIN grounded g ON e.parent=g.id
    ), readable(id) AS (
        SELECT id FROM grounded WHERE id NOT IN (SELECT id FROM bad)
    )
    """
    org_param = LegacyRecord._meta.get_field("org").get_db_prep_value(
        profile.org_id, connection
    )
    params = (
        *eligible_params,
        *good_params,
        org_param,
        *ACTOR_ROLES,
        org_param,
    )
    return sql, params


def visible_records(profile):
    qs = LegacyRecord.objects.filter(org=profile.org)
    if is_org_admin(profile):
        return qs
    sql, params = _readable_records_cte(profile)
    return qs.filter(id__in=RawSQL(sql + " SELECT id FROM readable", params))


def readable_record(profile, pk):
    return get_object_or_404(visible_records(profile), pk=pk)


def readable_projection_filter(queryset, profile):
    """Apply history's stricter source-parent rule to imported native feed rows."""
    if is_org_admin(profile):
        return queryset
    sql, params = _readable_records_cte(profile)
    org_param = LegacyProjection._meta.get_field("org").get_db_prep_value(
        profile.org_id, connection
    )
    blocked = RawSQL(
        sql
        + """ SELECT target_id FROM legacy_projection
        WHERE org_id=%s AND target_model=%s
        AND record_id NOT IN (SELECT id FROM readable)""",
        (*params, org_param, queryset.model._meta.label),
    )
    return queryset.exclude(pk__in=blocked)
