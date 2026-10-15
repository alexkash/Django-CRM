"""Historical data must not weaken identity, tenancy, or outbound mail gates."""

import importlib
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import AccountEmail, AccountEmailLog
from accounts.tasks import send_email


def models():
    try:
        return importlib.import_module("legacy.models")
    except ModuleNotFoundError as exc:
        raise AssertionError("Legacy history models are not implemented") from exc


def make_source(org):
    return models().LegacySource.objects.create(
        key="suitecrm-coloris", org=org, version="7.12.6"
    )


def test_legacy_source_cannot_change_org(org_a, org_b):
    source = make_source(org_a)
    source.org = org_b
    with pytest.raises(ValidationError):
        source.full_clean()


def test_record_parent_must_belong_to_org(org_a, org_b):
    source = make_source(org_a)
    record = models().LegacyRecord(
        source=source,
        org=org_b,
        source_table="accounts",
        source_pk="1",
        payload={"id": "1"},
        payload_sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        record.full_clean()


def test_source_record_identity_is_unique(org_a):
    source = make_source(org_a)
    fields = dict(
        source=source,
        org=org_a,
        source_table="accounts",
        source_pk="001",
        payload={"id": "001"},
        payload_sha256="a" * 64,
    )
    models().LegacyRecord.objects.create(**fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        models().LegacyRecord.objects.create(**fields)


def test_projection_role_does_not_duplicate(org_a):
    source = make_source(org_a)
    record = models().LegacyRecord.objects.create(
        source=source,
        org=org_a,
        source_table="accounts",
        source_pk="1",
        payload={},
        payload_sha256="a" * 64,
    )
    import uuid

    fields = dict(
        record=record,
        org=org_a,
        target_model="accounts.Account",
        target_id=uuid.uuid4(),
        role="native",
        projected_sha256="b" * 64,
    )
    models().LegacyProjection.objects.create(**fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        models().LegacyProjection.objects.create(**fields)


def test_batch_hash_identity_is_unique(org_a):
    source = make_source(org_a)
    fields = dict(source=source, org=org_a, snapshot_sha256="c" * 64)
    models().LegacyImportBatch.objects.create(**fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        models().LegacyImportBatch.objects.create(**fields)


def test_historical_mail_task_never_sends(org_a):
    email = AccountEmail.objects.create(
        org=org_a,
        from_email="sender@example.com",
        is_historical=True,
        message_subject="Historical",
        message_body="Body",
    )
    from contacts.models import Contact

    contact = Contact.objects.create(
        org=org_a,
        first_name="Mail",
        last_name="Recipient",
        email="recipient@example.com",
    )
    email.recipients.add(contact)
    # Patch only the external transport; execute the real Celery task body.
    with patch("django.core.mail.EmailMessage.send") as transport:
        send_email.run(str(email.id), str(org_a.id))
    transport.assert_not_called()
    assert AccountEmailLog.objects.filter(email=email).count() == 0


def test_unknown_stage_has_no_automatic_probability():
    from opportunity.workflow import aging_thresholds, stage_probability

    assert stage_probability("PROSPECTING", "unknown") is None
    assert aging_thresholds("unknown", 14, 7) is None


def test_unknown_stage_is_not_an_open_contact_deal(org_a,admin_user,admin_client):
    from contacts.models import Contact
    from opportunity.models import DealPipeline, DealStage, Opportunity
    contact=Contact.objects.create(org=org_a,first_name='Stage',last_name='Probe')
    pipeline=DealPipeline.objects.create(org=org_a,name='SuiteCRM')
    stage=DealStage.objects.create(org=org_a,pipeline=pipeline,code='LEGACY',label='Needs review',kind='unknown')
    deal=Opportunity(org=org_a,pipeline=pipeline,name='Unclassified deal',stage=stage.code,created_by=admin_user,amount=100,currency='USD')
    Opportunity.objects.bulk_create([deal]);deal.contacts.add(contact)
    result=admin_client.get(f'/api/contacts/{contact.id}/')
    assert result.status_code==200
    assert result.data['open_deals']['count']==0
