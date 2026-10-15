from django.db import migrations

TABLES = (
    "legacy_source",
    "legacy_import_batch",
    "legacy_record",
    "legacy_relation",
    "legacy_file",
    "legacy_projection",
)


def enable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from common.rls import get_enable_policy_sql

    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(get_enable_policy_sql(table))
        cursor.execute(
            "CREATE INDEX legacy_record_search_gin ON legacy_record USING GIN (to_tsvector('simple', search_text))"
        )


def disable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS legacy_record_search_gin")
        for table in TABLES:
            cursor.execute('ALTER TABLE "' + table + '" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("legacy", "0001_initial")]
    operations = [migrations.RunPython(enable, disable)]
