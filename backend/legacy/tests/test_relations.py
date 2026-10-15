from accounts.models import Account
from contacts.models import Contact
from legacy.models import LegacyRelation
from legacy.tests.helpers import make_context
from opportunity.models import Opportunity


def relation_projector():
    try:
        from legacy.importer.relations import project_relations
    except ModuleNotFoundError as exc:
        raise AssertionError("Relationship projection not implemented") from exc
    return project_relations


def test_account_contact_links_restore_both_native_directions(org_a, tmp_path):
    project = relation_projector()
    from legacy.importer.crm_records import project_accounts, project_contacts

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Company"}],
            "contacts": [{"id": "c", "first_name": "Contact", "last_name": "Person"}],
            "accounts_contacts": [
                {"id": "r", "account_id": "a", "contact_id": "c", "deleted": 0}
            ],
        },
    )
    project_accounts(ctx)
    project_contacts(ctx)
    project(ctx)
    account = Account.objects.get(org=org_a)
    contact = Contact.objects.get(org=org_a)
    assert account.contacts.filter(pk=contact.pk).exists()
    contact.refresh_from_db()
    assert contact.account_id == account.id
    assert LegacyRelation.objects.filter(
        org=org_a, role="account", state="resolved"
    ).exists()


def test_multiple_or_missing_companies_are_not_guessed(org_a, tmp_path):
    project = relation_projector()
    from legacy.importer.crm_records import project_accounts, project_opportunities

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "opportunities": [
                {"id": "o", "name": "Deal", "sales_stage": "Prospecting"}
            ],
            "accounts_opportunities": [
                {"id": "r1", "account_id": "a", "opportunity_id": "o"},
                {"id": "r2", "account_id": "b", "opportunity_id": "o"},
                {"id": "r3", "account_id": "missing", "opportunity_id": "o"},
            ],
        },
    )
    project_accounts(ctx)
    project_opportunities(ctx)
    project(ctx)
    assert Opportunity.objects.get(org=org_a).account_id is None
    assert LegacyRelation.objects.filter(org=org_a, role="account").count() == 3
    assert LegacyRelation.objects.filter(org=org_a, state="missing").count() == 1


def test_deleted_parent_is_preserved_as_source_problem(org_a, tmp_path):
    from legacy.importer.crm_records import project_contacts

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "Deleted", "deleted": 1}],
            "contacts": [{"id": "c", "last_name": "Person"}],
            "accounts_contacts": [{"id": "r", "account_id": "a", "contact_id": "c"}],
        },
    )
    project_contacts(ctx)
    relation_projector()(ctx)
    assert Contact.objects.get(org=org_a).account_id is None
    edge = LegacyRelation.objects.get(org=org_a, role="account")
    assert edge.state == "deleted_parent"
    assert edge.to_record.source_deleted


def test_multiple_company_memberships_keep_all_m2m_links(org_a, tmp_path):
    from legacy.importer.crm_records import project_accounts, project_contacts

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "contacts": [{"id": "c", "last_name": "Person"}],
            "accounts_contacts": [
                {"id": "r1", "account_id": "a", "contact_id": "c"},
                {"id": "r2", "account_id": "b", "contact_id": "c"},
            ],
        },
    )
    project_accounts(ctx)
    project_contacts(ctx)
    relation_projector()(ctx)
    contact = Contact.objects.get(org=org_a)
    assert contact.account_id is None
    assert contact.account_contacts.count() == 2
