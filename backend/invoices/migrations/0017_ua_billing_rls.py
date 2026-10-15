from django.db import migrations

from common.rls import get_disable_policy_sql, get_enable_policy_sql

TABLES = (
    "legal_entity",
    "legal_entity_bank_account",
    "billing_document_sequence",
    "service_act",
    "service_act_line",
)


def enable(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute(get_enable_policy_sql(table))


def disable(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute(get_disable_policy_sql(table))


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("invoices", "0016_ua_billing_schema")]
    operations = [migrations.RunPython(enable, disable)]
