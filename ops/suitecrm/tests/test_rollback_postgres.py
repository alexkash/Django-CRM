"""Exercise the actual rollback restore flags on destination-only isolated PostgreSQL."""

import os
import shlex
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("SUITECRM_ISOLATED_PG") == "1", "isolated PostgreSQL opt-in"
)
class RollbackOwnershipTests(unittest.TestCase):
    def test_restore_preserves_owner_rls_and_future_migration_rights(self):
        container = "crm-migration-tests-pg"
        source = "crm_restore_check_rollback_fixture"
        target = "crm_restore_check_rollback_result"
        owner = "crm_rollback_owner"

        def run(*args, data=None, check=True):
            return subprocess.run(
                ["docker", "exec", "-i", container, *args],
                input=data,
                capture_output=True,
                check=check,
            )

        def sql(database, query, user="migration_admin", check=True):
            return run(
                "psql",
                "-XAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                user,
                "-d",
                database,
                data=query.encode(),
                check=check,
            )

        sql(
            "postgres",
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='crm_rollback_owner') THEN CREATE ROLE crm_rollback_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB; END IF; END $$;",
        )
        for database in (source, target):
            run("dropdb", "-U", "migration_admin", "--if-exists", database)
            run("createdb", "-U", "migration_admin", "-O", owner, database)
        try:
            sql(
                source,
                "CREATE TABLE recovery_probe (tenant text, value integer); INSERT INTO recovery_probe VALUES ('a',1),('b',2); ALTER TABLE recovery_probe OWNER TO crm_rollback_owner; ALTER TABLE recovery_probe ENABLE ROW LEVEL SECURITY; ALTER TABLE recovery_probe FORCE ROW LEVEL SECURITY; CREATE POLICY tenant_scope ON recovery_probe USING (tenant=current_setting('app.current_org',true)) WITH CHECK (tenant=current_setting('app.current_org',true));",
            )
            dump = run("pg_dump", "-U", "migration_admin", "-Fc", source).stdout
            script = Path(__file__).resolve().parents[1] / "rollback.sh"
            line = next(
                line
                for line in script.read_text().splitlines()
                if " exec -T db pg_restore " in line
            )
            command = shlex.split(line)
            command = command[command.index("pg_restore") : command.index("<")]
            command[command.index("-U") + 1] = "migration_admin"
            command[command.index("-d") + 1] = target
            run(*command, data=dump)
            actual = (
                sql(
                    target,
                    "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname='recovery_probe';",
                )
                .stdout.decode()
                .strip()
            )
            self.assertEqual(
                actual, owner, "Rollback must retain dump object ownership"
            )
            self.assertEqual(
                sql(
                    target, "SELECT count(*) FROM recovery_probe;", owner
                ).stdout.strip(),
                b"0",
            )
            self.assertEqual(
                sql(
                    target,
                    "SET app.current_org='a'; SELECT value FROM recovery_probe;",
                    owner,
                )
                .stdout.decode()
                .splitlines()[-1],
                "1",
            )
            sql(
                target,
                "SET app.current_org='a'; INSERT INTO recovery_probe VALUES ('a',3); ALTER TABLE recovery_probe ADD COLUMN future_migration text;",
                owner,
            )
            refused = sql(
                target,
                "SET app.current_org='a'; INSERT INTO recovery_probe VALUES ('b',4);",
                owner,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(b"row-level security", refused.stderr)
        finally:
            for database in (source, target):
                run("dropdb", "-U", "migration_admin", database)


if __name__ == "__main__":
    unittest.main()
