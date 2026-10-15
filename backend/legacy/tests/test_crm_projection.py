from datetime import datetime, timezone

from accounts.models import Account
from contacts.models import Contact
from leads.models import Lead
from legacy.tests.helpers import make_context, people_tables
from opportunity.models import Opportunity


def projectors():
    try:
        from legacy.importer import crm_records
    except ImportError as exc:
        raise AssertionError("CRM projectors not implemented") from exc
    return crm_records


def test_leap_day_stage_audit_preserves_latest_timestamp(org_a, tmp_path):
    ctx = make_context(
        org_a,
        tmp_path,
        {
            "opportunities": [
                {"id": "deal", "name": "Leap day", "sales_stage": "Prospecting"}
            ],
            "opportunities_audit": [
                {
                    "id": "late",
                    "parent_id": "deal",
                    "field_name": "sales_stage",
                    "date_created": "2024-02-29 12:00:00",
                },
                {
                    "id": "early",
                    "parent_id": "deal",
                    "field_name": "sales_stage",
                    "date_created": "2024-02-29 10:00:00",
                },
            ],
        },
    )
    projectors().project_opportunities(ctx)
    assert Opportunity.objects.get(org=org_a).stage_changed_at == datetime(
        2024, 2, 29, 12, tzinfo=timezone.utc
    )


def test_duplicate_email_keeps_both_contacts(org_a, tmp_path):
    m = projectors()
    tables = {
        "contacts": [
            {"id": "1", "first_name": "First", "last_name": "Person"},
            {"id": "001", "first_name": "Second", "last_name": "Person"},
        ],
        "email_addresses": [{"id": "address", "email_address": "shared@example.com"}],
        "email_addr_bean_rel": [
            {
                "id": "r1",
                "bean_id": "1",
                "bean_module": "Contacts",
                "email_address_id": "address",
                "primary_address": 1,
            },
            {
                "id": "r2",
                "bean_id": "001",
                "bean_module": "Contacts",
                "email_address_id": "address",
                "primary_address": 1,
            },
        ],
    }
    ctx = make_context(org_a, tmp_path, tables)
    m.project_contacts(ctx)
    assert Contact.objects.filter(org=org_a).count() == 2
    assert Contact.objects.filter(org=org_a, email__isnull=False).count() == 1
    second = Contact.objects.get(org=org_a, email__isnull=True)
    assert second.custom_fields["suitecrm_original_email"] == "shared@example.com"
    assert not second.is_sample


def test_company_duplicates_preserve_names_and_source_dates(
    org_a, admin_user, tmp_path
):
    m = projectors()
    from legacy.importer.people import project_people

    tables = people_tables(admin_user.email)
    tables["accounts"] = [
        {"id": "1", "name": "Acme", "created_by": "1"},
        {"id": "001", "name": "Acme", "created_by": "1"},
    ]
    ctx = make_context(org_a, tmp_path, tables)
    project_people(ctx)
    m.project_accounts(ctx)
    assert Account.objects.filter(org=org_a).count() == 2
    assert Account.objects.filter(org=org_a, name="Acme").count() == 1
    other = Account.objects.filter(org=org_a).exclude(name="Acme").get()
    assert other.name.startswith("Acme [SuiteCRM:")
    assert other.custom_fields["suitecrm_original_name"] == "Acme"
    assert other.created_at == datetime(2017, 1, 8, 11, 20, tzinfo=timezone.utc)
    assert other.created_by_id == admin_user.id


def test_long_phone_preserved_without_native_truncation(org_a, tmp_path):
    m = projectors()
    original = "1234567890" * 10
    ctx = make_context(
        org_a,
        tmp_path,
        {
            "contacts": [
                {
                    "id": "1",
                    "first_name": "Phone",
                    "last_name": "Probe",
                    "phone_work": original,
                }
            ]
        },
    )
    m.project_contacts(ctx)
    contact = Contact.objects.get(org=org_a)
    assert contact.phone is None
    assert contact.custom_fields["suitecrm_original_work_phone"] == original


def test_converted_lead_does_not_create_extra_customers(org_a, tmp_path):
    m = projectors()
    ctx = make_context(
        org_a,
        tmp_path,
        {
            "leads": [
                {
                    "id": "1",
                    "first_name": "Converted",
                    "last_name": "Lead",
                    "status": "Converted",
                    "converted": 1,
                }
            ]
        },
    )
    m.project_leads(ctx)
    assert Lead.objects.get(org=org_a).status == "converted"
    assert Lead.objects.get(org=org_a).stage.stage_type == "won"
    assert Account.objects.filter(org=org_a).count() == 0
    assert Contact.objects.filter(org=org_a).count() == 0
    assert Opportunity.objects.filter(org=org_a).count() == 0


def test_source_currency_name_and_default_resolve_to_uah(org_a, tmp_path):
    import json

    from legacy.importer.contracts import ImportContext
    from legacy.importer.fields import currency
    from legacy.importer.reader import SnapshotReader
    from legacy.tests.helpers import make_snapshot

    folder = make_snapshot(
        tmp_path,
        {
            "currencies": [
                {"id": "currency-ua", "name": "Гривня", "iso4217": "UAH"},
                {"id": "currency-us", "name": "Долар США", "iso4217": "USD"},
            ]
        },
    )
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["safe_config"]["default_currency_iso4217"] = "UAH"
    path.write_text(json.dumps(manifest))
    ctx = ImportContext(org_a, SnapshotReader(folder))
    assert currency(ctx, "Гривня") == "UAH"
    assert currency(ctx, "-99") == "UAH"
    assert currency(ctx, "Долар США") == "USD"


def test_custom_field_keeps_source_label_without_executing_php(org_a, tmp_path):
    import hashlib
    import json

    from common.models import CustomFieldDefinition
    from legacy.importer.contracts import ImportContext
    from legacy.importer.fields import project_definitions
    from legacy.importer.reader import SnapshotReader
    from legacy.tests.helpers import make_snapshot

    folder = make_snapshot(
        tmp_path,
        {
            "fields_meta_data": [
                {
                    "id": "f1",
                    "custom_module": "Accounts",
                    "name": "sold_estaff_c",
                    "vname": "LBL_SOLD_ESTAFF",
                    "type": "bool",
                    "required": 0,
                }
            ]
        },
    )
    key = "custom/Extension/modules/Accounts/Ext/Language/en_us.fields.php"
    path = folder.parent / "metadata" / key
    path.parent.mkdir(parents=True)
    marker = tmp_path / "should-not-exist"
    path.write_text(
        "<?php $mod_strings['LBL_SOLD_ESTAFF'] = 'Купил E-Staff'; system('touch "
        + str(marker)
        + "');"
    )
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["metadata_files"] = [
        {
            "path": key,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    ]
    manifest_path.write_text(json.dumps(manifest))
    ctx = ImportContext(org_a, SnapshotReader(folder))
    project_definitions(ctx)
    assert (
        CustomFieldDefinition.objects.get(org=org_a, key="sold_estaff_c").label
        == "Купил E-Staff"
    )
    assert not marker.exists()


def test_source_website_cannot_become_a_script_link(org_a, tmp_path):
    m = projectors()
    ctx = make_context(
        org_a,
        tmp_path,
        {
            "accounts": [
                {
                    "id": "1",
                    "name": "Safe URL",
                    "website": "javascript:alert(document.domain)",
                }
            ]
        },
    )
    m.project_accounts(ctx)
    assert Account.objects.get(org=org_a).website is None
    assert (
        ctx.reader.get("accounts", "1")["values"]["website"]
        == "javascript:alert(document.domain)"
    )


def test_unused_source_dropdown_choices_are_preserved(org_a, tmp_path):
    import hashlib
    import json

    from common.models import CustomFieldDefinition
    from legacy.importer.contracts import ImportContext
    from legacy.importer.fields import project_definitions
    from legacy.importer.reader import SnapshotReader
    from legacy.tests.helpers import make_snapshot

    folder = make_snapshot(
        tmp_path,
        {
            "fields_meta_data": [
                {
                    "id": "f2",
                    "custom_module": "Opportunities",
                    "name": "product_service_c",
                    "vname": "LBL_PRODUCT_SERVICE",
                    "type": "enum",
                    "ext1": "product_service_list",
                }
            ]
        },
    )
    key = "custom/include/language/en_us.lang.php"
    path = folder.parent / "metadata" / key
    path.parent.mkdir(parents=True)
    path.write_text(
        "<?php $app_list_strings['product_service_list']=array ('estaff'=>'E-Staff', 'unused'=>'Unused option');"
    )
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["metadata_files"] = [
        {
            "path": key,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    ]
    manifest_path.write_text(json.dumps(manifest))
    ctx = ImportContext(org_a, SnapshotReader(folder))
    project_definitions(ctx)
    options = CustomFieldDefinition.objects.get(
        org=org_a, key="product_service_c"
    ).options
    assert options == [
        {"value": "estaff", "label": "E-Staff"},
        {"value": "unused", "label": "Unused option"},
    ]


def test_fractional_probability_is_preserved_only_in_history_not_truncated(
    org_a, tmp_path
):
    from legacy.importer.crm_records import project_opportunities

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "opportunities": [
                {
                    "id": "fractional",
                    "name": "Fractional confidence",
                    "sales_stage": "Unknown",
                    "probability": 13.5,
                }
            ]
        },
    )
    project_opportunities(ctx)
    assert Opportunity.objects.get(org=org_a).probability is None
    assert (
        ctx.reader.get("opportunities", "fractional")["values"]["probability"] == 13.5
    )
