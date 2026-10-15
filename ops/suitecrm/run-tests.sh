#!/usr/bin/env bash
# Destination-only isolated PostgreSQL checks; production env files are forbidden.
set -euo pipefail
app=${1:-/opt/crm/migration-tests/next}
[[ "$app" == /opt/crm/migration-tests/* ]] || exit 2
env_file=/opt/crm/migration-tools/test-postgres.env
run() {
    docker run --rm --network host --memory=768m --env-file "$env_file" \
        -e DJANGO_SETTINGS_MODULE=crm.test_settings_postgres -v "$app:/app" -w /app \
        crm-backend:c6414afc "$@"
}
run python -c 'import os,django;assert os.environ["DBNAME"]=="crm_migration_checks";assert os.environ["DBUSER"]=="crm_migration_test";assert os.environ["DBHOST"]=="127.0.0.1" and os.environ["DBPORT"]=="54390";django.setup();from django.db import connection;c=connection.cursor();c.execute("SELECT current_database(),rolsuper,rolbypassrls,rolcreatedb FROM pg_roles WHERE rolname=current_user");assert c.fetchone()==("crm_migration_checks",False,False,False);print("Isolated database and non-bypass role checked before fixtures")'
run pytest legacy/tests --reuse-db --ds=crm.test_settings_postgres --no-cov -q
run pytest -m postgres_only --reuse-db --ds=crm.test_settings_postgres --no-cov -q
