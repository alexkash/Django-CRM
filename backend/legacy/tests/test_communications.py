from accounts.models import AccountEmail
from cases.models import Case
from contacts.models import Contact
from legacy.tests.helpers import make_context


def test_message_keeps_all_headers_and_bodies_without_creating_people(org_a, tmp_path):
    try:
        from legacy.importer.communications import project_communications
    except ModuleNotFoundError as exc:
        raise AssertionError("Email projection not implemented") from exc
    ctx = make_context(
        org_a,
        tmp_path,
        {
            "emails": [
                {
                    "id": "e",
                    "name": "Subject",
                    "type": "out",
                    "status": "sent",
                    "date_sent_received": "2020-02-03 11:12:13",
                    "message_id": "<original@example.com>",
                }
            ],
            "emails_text": [
                {
                    "email_id": "e",
                    "from_addr": "Sender <sender@example.com>",
                    "to_addrs": "Target <target@example.com>",
                    "cc_addrs": "cc@example.com",
                    "bcc_addrs": "hidden@example.com",
                    "description": "Привіт",
                    "description_html": "<p>Привіт</p>",
                }
            ],
        },
    )
    project_communications(ctx)
    message = AccountEmail.objects.get(org=org_a)
    assert message.is_historical
    assert message.body_text == "Привіт"
    assert message.message_body == "<p>Привіт</p>"
    assert message.to_addresses == [{"name": "Target", "address": "target@example.com"}]
    assert message.bcc_addresses == [{"name": "", "address": "hidden@example.com"}]
    assert message.source_message_id == "<original@example.com>"
    assert not message.scheduled_later
    assert Contact.objects.filter(org=org_a).count() == 0
    assert Case.objects.filter(org=org_a).count() == 0


def test_structured_addresses_without_body_headers_are_preserved(org_a, tmp_path):
    from unittest.mock import patch

    from accounts.models import AccountEmailLog
    from accounts.tasks import send_email
    from legacy.importer.communications import project_communications

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "emails": [{"id": "e", "name": "Subject", "status": "sent"}],
            "email_addresses": [{"id": "a", "email_address": "blind@example.com"}],
            "emails_email_addr_rel": [
                {
                    "id": "r",
                    "email_id": "e",
                    "email_address_id": "a",
                    "address_type": "bcc",
                }
            ],
        },
    )
    with patch("celery.app.task.Task.apply_async") as dispatch:
        project_communications(ctx)
    dispatch.assert_not_called()
    message = AccountEmail.objects.get(org=org_a)
    assert message.bcc_addresses == [{"name": "", "address": "blind@example.com"}]
    with patch("django.core.mail.EmailMessage.send") as transport:
        send_email.run(str(message.pk), str(org_a.pk))
    transport.assert_not_called()
    assert not AccountEmailLog.objects.filter(email=message).exists()


def test_email_matching_does_not_choose_between_duplicate_source_people(
    org_a, tmp_path
):
    from legacy.importer.communications import project_communications
    from legacy.importer.crm_records import project_contacts

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "contacts": [
                {"id": "c1", "last_name": "One"},
                {"id": "c2", "last_name": "Two"},
                {"id": "c3", "last_name": "Three"},
            ],
            "email_addresses": [
                {"id": "shared", "email_address": "shared@example.com"},
                {"id": "unique", "email_address": "unique@example.com"},
            ],
            "email_addr_bean_rel": [
                {
                    "id": "a1",
                    "bean_module": "Contacts",
                    "bean_id": "c1",
                    "primary_address": 1,
                    "email_address_id": "shared",
                },
                {
                    "id": "a2",
                    "bean_module": "Contacts",
                    "bean_id": "c2",
                    "primary_address": 1,
                    "email_address_id": "shared",
                },
                {
                    "id": "a3",
                    "bean_module": "Contacts",
                    "bean_id": "c3",
                    "primary_address": 1,
                    "email_address_id": "unique",
                },
            ],
            "emails": [{"id": "e", "name": "Message"}],
            "emails_text": [
                {"email_id": "e", "to_addrs": "shared@example.com, unique@example.com"}
            ],
        },
    )
    project_contacts(ctx)
    project_communications(ctx)
    message = AccountEmail.objects.get(org=org_a)
    assert list(message.recipients.values_list("last_name", flat=True)) == ["Three"]
