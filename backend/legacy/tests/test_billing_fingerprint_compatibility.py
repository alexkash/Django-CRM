"""Adding blank billing fields preserves fingerprints from the deployed schema."""

import pytest
from django.apps import apps
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings

from legacy.importer.identity import object_fingerprint


@pytest.fixture(scope="module")
def deployed_apps():
    with override_settings(MIGRATION_MODULES={}):
        return (
            MigrationLoader(None)
            .project_state(
                [
                    ("accounts", "0011_alter_account_currency"),
                    (
                        "invoices",
                        "0015_alter_estimate_currency_alter_invoice_currency_and_more",
                    ),
                ]
            )
            .apps
        )


def baseline_record(org, deployed_apps, label):
    model = apps.get_model(label)
    current = model.objects.create(org=org, name="Existing imported record")
    current.refresh_from_db()
    old = deployed_apps.get_model(label).objects.get(pk=current.pk)
    return current, object_fingerprint(old)


@pytest.mark.parametrize("label", ["accounts.Account", "invoices.Product"])
def test_blank_billing_additions_keep_deployed_fingerprint(org_a, deployed_apps, label):
    current, previous = baseline_record(org_a, deployed_apps, label)
    assert object_fingerprint(current) == previous


@pytest.mark.parametrize(
    "label,field",
    [
        ("accounts.Account", field)
        for field in (
            "legal_name",
            "registration_code",
            "vat_registration_number",
            "legal_address",
            "iban",
            "bank_name",
            "mfo",
            "tax_system_text",
            "signer_name",
            "signer_title",
        )
    ]
    + [("invoices.Product", "unit")],
)
def test_new_billing_edits_are_still_detected(org_a, deployed_apps, label, field):
    current, previous = baseline_record(org_a, deployed_apps, label)
    type(current).objects.filter(pk=current.pk).update(**{field: "Edited"})
    current.refresh_from_db()
    assert object_fingerprint(current) != previous


@pytest.mark.parametrize("label", ["accounts.Account", "invoices.Product"])
def test_existing_business_edits_are_still_detected(org_a, deployed_apps, label):
    current, previous = baseline_record(org_a, deployed_apps, label)
    type(current).objects.filter(pk=current.pk).update(name="User decision")
    current.refresh_from_db()
    assert object_fingerprint(current) != previous
