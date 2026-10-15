"""Source events retain their actual dates; only explicitly Planned events stay open."""

from zoneinfo import ZoneInfo

from django.apps import apps

from common.models import Activity
from tasks.models import Task

from .contracts import ImportConflict, source_time
from .identity import stable_id
from .relations import NATIVE, add_members, native_parents


def project_task(ctx, table, row, status, role):
    d = row["values"]
    start = source_time(d.get("date_due") if table == "tasks" else d.get("date_start"))
    timezone = (
        ctx.reader.manifest.get("safe_config", {}).get("default_timezone") or "UTC"
    )
    parents = native_parents(ctx, table, row["source_id"])
    # A task supports only one scalar parent. All original links remain history.
    scalar = [
        (tab, pk)
        for tab, pk in parents
        if tab in ("accounts", "leads", "opportunities", "cases")
    ]
    kwargs = {}
    if len(scalar) == 1:
        tab, pk = scalar[0]
        kwargs[
            {
                "accounts": "account_id",
                "leads": "lead_id",
                "opportunities": "opportunity_id",
                "cases": "case_id",
            }[tab]
        ] = pk
    title = d.get("name") or f"SuiteCRM {table}:{row['source_id']}"
    if len(title) > 200:
        # The full title remains in source history; do not truncate native fields.
        title = f"SuiteCRM {table}:{row['source_id']}"
    priority = d.get("priority") if table == "tasks" else "Medium"
    if priority not in dict(Task.PRIORITY_CHOICES):
        raise ImportConflict("Unmapped source task priority")
    task = Task(
        id=stable_id(table, row["source_id"], role),
        org=ctx.org,
        title=title,
        status=status,
        priority=priority,
        due_date=start.astimezone(ZoneInfo(timezone)).date() if start else None,
        description=d.get("description"),
        created_by_id=ctx.actor(d),
        updated_by_id=ctx.updater(d),
        **kwargs,
    )
    task = ctx.write(table, row, task, role)
    add_members(task, "contacts", [pk for tab, pk in parents if tab == "contacts"])
    add_members(
        task,
        "assigned_to",
        [ctx.native_id("users", d.get("assigned_user_id"), "profile")],
    )

    ctx.restamp_projection(ctx.record_id(table, row["source_id"]), role)


def project_events(ctx):
    for table in (
        "calls",
        "meetings",
        "tasks",
        "notes",
        "sugarfeed",
        *[t for t in ctx.reader.policy if t.endswith("_audit")],
    ):
        for row in ctx.reader.rows(table, True):
            d = row["values"]
            key = row["source_id"]
            if table == "tasks":
                statuses = {
                    "Completed": "Completed",
                    "Not Started": "New",
                    "In Progress": "In Progress",
                    "Pending Input": "In Progress",
                    "Deferred": "New",
                }
                if d.get("status") not in statuses:
                    raise ImportConflict("Unmapped source task status")
                project_task(ctx, table, row, statuses[d["status"]], "native")
            if table in ("calls", "meetings") and d.get("status") == "Planned":
                project_task(ctx, table, row, "New", "followup")
            parents = native_parents(ctx, table, key)
            # Native Activity reads authorize one card, not all legacy parents.
            # Multi-parent payloads are shown only through the stricter history API.
            if len(parents) != 1:
                continue
            tab, pk = parents[0]
            when = (
                d.get("date_start")
                if table in ("calls", "meetings")
                else d.get("date_created") or d.get("date_entered")
            )
            if not source_time(when):
                continue
            action = {
                "calls": "LEGACY_CALL",
                "meetings": "LEGACY_MEETING",
                "notes": "LEGACY_NOTE",
            }.get(table, "LEGACY_CHANGE")
            title = str(d.get("name") or table)
            if len(title) > 255:
                title = f"SuiteCRM {table}:{key}"
            metadata = {"legacy_record_id": str(ctx.record_id(table, key))}
            for field in (
                "status",
                "direction",
                "duration_hours",
                "duration_minutes",
                "date_start",
                "date_end",
                "location",
                "field_name",
                "before_value_string",
                "after_value_string",
            ):
                if field in d:
                    metadata[field] = d[field]
            event = Activity(
                id=stable_id(table, key, "event:" + str(pk)),
                org=ctx.org,
                user_id=ctx.native_id("users", d.get("created_by"), "profile"),
                action=action,
                entity_type=apps.get_model(NATIVE[tab]).__name__,
                entity_id=pk,
                entity_name=title,
                description=d.get("description") or "",
                metadata=metadata,
                created_by_id=ctx.actor(d),
                updated_by_id=ctx.updater(d),
            )
            event_row = {**row, "values": {**d, "date_entered": when}}
            ctx.write(table, event_row, event, "event:" + str(pk))
