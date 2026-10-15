"""Visibility is all-parent, including inherited body/join/file evidence."""

from accounts.models import Account
from legacy.models import LegacyRecord
from legacy.tests.helpers import make_context


def test_projection_cannot_ground_a_foreign_org_record(
    org_a, org_b, regular_user, user_profile
):
    from legacy.models import LegacyProjection, LegacySource
    from tasks.access import visible_tasks_qs
    from tasks.models import Task

    source = LegacySource.objects.create(org=org_b, key="foreign-source")
    record = LegacyRecord.objects.create(
        org=org_b,
        source=source,
        source_table="accounts",
        source_pk="foreign",
        payload_sha256="0" * 64,
    )
    task = Task.objects.create(
        org=org_a,
        title="Local task",
        created_by=regular_user,
        status="New",
        priority="High",
    )
    # Simulate a malformed mapping inserted outside model validation. Even on
    # SQLite without RLS, it must never confer cross-organization readability.
    LegacyProjection.objects.bulk_create(
        [
            LegacyProjection(
                org=org_a,
                record=record,
                target_model="tasks.Task",
                target_id=task.pk,
                role="native",
                projected_sha256="0" * 64,
            )
        ]
    )
    assert not visible_tasks_qs(user_profile).filter(pk=task.pk).exists()


def linked_context(org, tmp_path, owner):
    from legacy.importer.crm_records import project_accounts
    from legacy.importer.relations import project_relations

    ctx = make_context(
        org,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Visible"}, {"id": "b", "name": "Hidden"}],
            "emails": [
                {
                    "id": "e",
                    "name": "Secret phrase",
                    "parent_type": "Accounts",
                    "parent_id": "a",
                }
            ],
            "emails_text": [{"email_id": "e", "description": "Sensitive body"}],
            "emails_beans": [
                {"id": "j", "email_id": "e", "bean_module": "Accounts", "bean_id": "b"}
            ],
            "calls": [{"id": "orphan", "name": "Unparented"}],
        },
    )
    project_accounts(ctx)
    project_relations(ctx)
    Account.objects.filter(pk=ctx.native_id("accounts", "a")).update(created_by=owner)
    return ctx


def test_every_business_parent_must_be_visible(
    org_a, tmp_path, regular_user, user_profile
):
    from legacy.access import visible_records

    ctx = linked_context(org_a, tmp_path, regular_user)
    ids = set(visible_records(user_profile).values_list("id", flat=True))
    assert ctx.record_id("accounts", "a") in ids
    assert ctx.record_id("emails", "e") not in ids
    assert ctx.record_id("emails_text", "0") not in ids
    assert ctx.record_id("calls", "orphan") not in ids
    Account.objects.filter(pk=ctx.native_id("accounts", "b")).update(
        created_by=regular_user
    )
    ids = set(visible_records(user_profile).values_list("id", flat=True))
    assert ctx.record_id("emails", "e") in ids
    assert ctx.record_id("emails_text", "0") in ids


def test_deleted_or_missing_parent_hides_payload(
    org_a, tmp_path, regular_user, user_profile
):
    from legacy.access import visible_records
    from legacy.importer.crm_records import project_accounts
    from legacy.importer.relations import project_relations

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Visible"}],
            "emails": [
                {
                    "id": "e",
                    "name": "Secret",
                    "parent_type": "Accounts",
                    "parent_id": "a",
                    "account_id": "missing",
                }
            ],
        },
    )
    project_accounts(ctx)
    project_relations(ctx)
    Account.objects.filter(org=org_a).update(created_by=regular_user)
    assert (
        not visible_records(user_profile)
        .filter(pk=ctx.record_id("emails", "e"))
        .exists()
    )
    assert LegacyRecord.objects.filter(org=org_a).count() == 2


def test_unknown_parent_cannot_be_ignored_when_a_known_parent_is_visible(
    org_a, tmp_path, regular_user, user_profile
):
    from legacy.access import visible_records
    from legacy.importer.crm_records import project_accounts
    from legacy.importer.relations import project_relations

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Visible"}],
            "emails": [
                {
                    "id": "e",
                    "name": "Secret",
                    "parent_type": "UnrecognizedModule",
                    "parent_id": "other",
                    "account_id": "a",
                }
            ],
        },
    )
    project_accounts(ctx)
    project_relations(ctx)
    Account.objects.filter(org=org_a).update(created_by=regular_user)
    assert (
        not visible_records(user_profile)
        .filter(pk=ctx.record_id("emails", "e"))
        .exists()
    )


def test_native_feed_and_followup_do_not_bypass_parent_history_policy(
    org_a, tmp_path, regular_user, user_profile
):
    from common.views.dashboard_views import _readable_activities
    from legacy.importer.crm_records import project_accounts, project_contacts
    from legacy.importer.history import project_events
    from legacy.importer.relations import project_relations
    from tasks.access import has_task_access, visible_tasks_qs
    from tasks.models import Task

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Hidden"}],
            "contacts": [{"id": "c", "last_name": "Mine", "account_id": "a"}],
            "calls": [
                {
                    "id": "held",
                    "name": "Sensitive held",
                    "status": "Held",
                    "date_start": "2020-01-01 10:00:00",
                    "parent_type": "Contacts",
                    "parent_id": "c",
                },
                {
                    "id": "planned",
                    "name": "Sensitive planned",
                    "status": "Planned",
                    "date_start": "2020-01-01 10:00:00",
                    "parent_type": "Contacts",
                    "parent_id": "c",
                },
            ],
        },
    )
    project_accounts(ctx)
    project_contacts(ctx)
    project_relations(ctx)
    project_events(ctx)
    from contacts.models import Contact

    Contact.objects.filter(org=org_a).update(created_by=regular_user)
    Task.objects.filter(org=org_a).update(created_by=regular_user)
    assert not _readable_activities(user_profile).exists()
    assert not visible_tasks_qs(user_profile).exists()
    assert not has_task_access(user_profile, Task.objects.get(org=org_a))
    Account.objects.filter(org=org_a).update(created_by=regular_user)
    assert _readable_activities(user_profile).count() == 2
    assert visible_tasks_qs(user_profile).count() == 1


def test_unparented_planned_event_cannot_gain_history_access_from_its_followup(
    org_a, tmp_path, user_profile
):
    from legacy.access import visible_records
    from legacy.importer.history import project_events
    from tasks.access import visible_tasks_qs
    from tasks.models import Task

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "calls": [
                {
                    "id": "orphan-planned",
                    "name": "Unparented planned",
                    "status": "Planned",
                    "date_start": "2020-01-01 10:00:00",
                }
            ]
        },
    )
    project_events(ctx)
    task = Task.objects.get(org=org_a)
    task.assigned_to.add(user_profile)
    assert (
        not visible_records(user_profile)
        .filter(pk=ctx.record_id("calls", "orphan-planned"))
        .exists()
    )
    assert not visible_tasks_qs(user_profile).filter(pk=task.pk).exists()
