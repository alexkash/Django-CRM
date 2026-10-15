from datetime import datetime, timezone

from common.models import Activity
from legacy.tests.helpers import make_context
from tasks.models import Task


def test_planned_call_has_one_open_task_and_held_call_has_none(org_a, tmp_path):
    try:
        from legacy.importer.history import project_events
    except ModuleNotFoundError as exc:
        raise AssertionError("Event projection not implemented") from exc
    from legacy.importer.crm_records import project_accounts
    from legacy.importer.relations import project_relations

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Parent"}],
            "calls": [
                {
                    "id": "held",
                    "name": "Completed call",
                    "status": "Held",
                    "date_start": "2020-02-03 11:12:13",
                    "parent_type": "Accounts",
                    "parent_id": "a",
                    "duration_hours": 1,
                    "duration_minutes": 30,
                },
                {
                    "id": "planned",
                    "name": "Overdue call",
                    "status": "Planned",
                    "date_start": "2020-02-03 12:00:00",
                    "parent_type": "Accounts",
                    "parent_id": "a",
                },
            ],
        },
    )
    project_accounts(ctx)
    project_relations(ctx)
    project_events(ctx)
    assert Task.objects.filter(org=org_a, status="New").count() == 1
    assert Activity.objects.filter(org=org_a, action="LEGACY_CALL").count() == 2
    event = Activity.objects.get(org=org_a, entity_name="Completed call")
    assert event.created_at == datetime(2020, 2, 3, 11, 12, 13, tzinfo=timezone.utc)
    assert event.metadata["duration_minutes"] == 30
    task = Task.objects.get(org=org_a)
    assert str(task.due_date) == "2020-02-03"


def test_multi_parent_payload_stays_in_protected_archive(org_a, tmp_path):
    from legacy.importer.crm_records import project_accounts
    from legacy.importer.history import project_events
    from legacy.importer.relations import project_relations
    from legacy.models import LegacyRecord

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "calls": [
                {
                    "id": "c",
                    "name": "Sensitive",
                    "status": "Held",
                    "date_start": "2020-01-01 10:00:00",
                    "parent_type": "Accounts",
                    "parent_id": "a",
                    "account_id": "b",
                }
            ],
        },
    )
    project_accounts(ctx)
    project_relations(ctx)
    project_events(ctx)
    assert Activity.objects.filter(org=org_a, action="LEGACY_CALL").count() == 0
    assert LegacyRecord.objects.filter(org=org_a, kind="call").count() == 1


def test_sugarfeed_and_audit_keep_original_date_without_dispatch(org_a, tmp_path):
    from unittest.mock import patch

    from legacy.importer.crm_records import project_accounts
    from legacy.importer.history import project_events
    from legacy.importer.relations import project_relations
    from webhooks.models import WebhookDelivery

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "A"}],
            "sugarfeed": [
                {
                    "id": "s",
                    "related_module": "Accounts",
                    "related_id": "a",
                    "description": "Old change",
                }
            ],
            "accounts_audit": [
                {
                    "id": "au",
                    "parent_id": "a",
                    "date_created": "2016-06-01 12:00:00",
                    "field_name": "name",
                }
            ],
        },
    )
    with patch("celery.app.task.Task.apply_async") as dispatch:
        project_accounts(ctx)
        project_relations(ctx)
        project_events(ctx)
    dispatch.assert_not_called()
    events = Activity.objects.filter(org=org_a)
    assert events.count() == 2
    assert {event.created_at.year for event in events} == {2016, 2017}
    assert not events.exclude(action="LEGACY_CHANGE").exists()
    assert not WebhookDelivery.objects.filter(org=org_a).exists()


def test_completed_source_task_uses_due_date_and_recorded_priority(org_a, tmp_path):
    from legacy.importer.history import project_events

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "tasks": [
                {
                    "id": "t",
                    "name": "Original task",
                    "status": "Completed",
                    "priority": "High",
                    "date_start": "2017-01-10 10:00:00",
                    "date_due": "2017-02-11 10:00:00",
                }
            ]
        },
    )
    project_events(ctx)
    task = Task.objects.get(org=org_a)
    assert task.status == "Completed"
    assert task.priority == "High"
    assert str(task.due_date) == "2017-02-11"
