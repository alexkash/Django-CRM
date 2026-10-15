"""Exercise database-enforced isolation with a real unprivileged role."""

import pytest
from django.db import connection

from legacy.models import LegacyRecord, LegacySource


@pytest.mark.postgres_only
def test_postgres_force_rls_hides_foreign_and_empty_context(org_a, org_b):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL policy behavior requires PostgreSQL")
    with connection.cursor() as c:
        c.execute(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        assert c.fetchone() == (False, False), "Test role must enforce RLS"
        c.execute("SELECT set_config('app.current_org',%s,false)", [str(org_a.id)])
    source = LegacySource.objects.create(key="rls-probe", org=org_a)
    record = LegacyRecord.objects.create(
        source=source,
        org=org_a,
        source_table="accounts",
        source_pk="001",
        payload_sha256="a" * 64,
    )
    assert set(LegacyRecord.objects.values_list("id", flat=True)) == {record.id}
    with connection.cursor() as c:
        c.execute("SELECT set_config('app.current_org',%s,false)", [str(org_b.id)])
    assert LegacyRecord.objects.count() == 0
    with connection.cursor() as c:
        c.execute("SELECT set_config('app.current_org','',false)")
    assert LegacyRecord.objects.count() == 0
    with connection.cursor() as c:
        c.execute("SELECT set_config('app.current_org',%s,false)", [str(org_a.id)])
