#!/usr/bin/env bash
# Run on the destination as root. Uses only the isolated migration PostgreSQL.
set -euo pipefail
umask 077
backup=${1:?backup archive required}
snapshot=${2:?snapshot export directory required}
org=${3:?exact destination org UUID required}
rehearsal_db=${4:-crm_migration_rehearsal_20261015}
[[ "$rehearsal_db" =~ ^crm_migration_rehearsal_[0-9]{8}$ ]] || exit 2
[[ "$org" =~ ^[a-fA-F0-9-]{36}$ ]] || exit 2
[[ -f "$backup" && -f "$snapshot/manifest.json" ]] || exit 2
stage="/opt/crm/migration/$rehearsal_db"
mkdir -m 700 "$stage"
python3 - "$backup" "$stage" <<'PY'
import sys,tarfile
from pathlib import Path
backup,stage=sys.argv[1],Path(sys.argv[2])
with tarfile.open(backup) as tar:
    members=[m for m in tar.getmembers() if m.name.lstrip('./')=='database.dump' and m.isfile()]
    if len(members)!=1:raise ValueError('One database dump required')
    with tar.extractfile(members[0]) as incoming,(stage/'database.dump').open('wb') as out:
        import shutil
        shutil.copyfileobj(incoming,out)
base=Path('/opt/crm/migration-tools/test-postgres.env').read_text().splitlines()
env=dict(line.split('=',1) for line in base if line and not line.startswith('#'))
assert env['DBHOST']=='127.0.0.1' and env['DBPORT']=='54390'
assert env['DBUSER']=='crm_migration_test' and env['DBNAME']=='crm_migration_checks'
env['DBNAME']=stage.name
(stage/'rehearsal.env').write_text('\n'.join(f'{key}={value}' for key,value in env.items())+'\n')
(stage/'rehearsal.env').chmod(0o600)
PY
docker exec crm-migration-tests-pg createdb -U migration_admin -O crm_migration_test "$rehearsal_db"
docker exec -i crm-migration-tests-pg pg_restore -U migration_admin --role=crm_migration_test --no-owner --no-acl -d "$rehearsal_db" < "$stage/database.dump" > "$stage/restore.log" 2>&1
run() {
    docker run --rm --network host --memory=1024m \
        --env-file "$stage/rehearsal.env" \
        -e DJANGO_SETTINGS_MODULE=crm.test_settings_postgres \
        -v /opt/crm/migration-tests/app:/app -v /opt/crm/migration:/migration \
        -w /app crm-backend:c6414afc "$@"
}
run python -c 'import django;django.setup();from django.db import connection;c=connection.cursor();c.execute("SELECT current_database(),rolsuper,rolbypassrls,rolcreatedb FROM pg_roles WHERE rolname=current_user");r=c.fetchone();assert r[0].startswith("crm_migration_rehearsal_") and r[1:]==(False,False,False);print("Isolated restore role verified")' > "$stage/role.log" 2>&1
run python -m django migrate --noinput > "$stage/migrate.log" 2>&1
inside_snapshot="/migration/${snapshot#/opt/crm/migration/}"
inside_stage="/migration/$rehearsal_db"
# File root is intentionally outside all public media. Persist it across runs.
cat > /opt/crm/migration-tests/app/rehearsal_settings.py <<'PY'
from crm.test_settings_postgres import *
LEGACY_FILE_ROOT='/migration/rehearsal-private-files'
EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
PY
run_custom() {
    docker run --rm --network host --memory=1024m \
        --env-file "$stage/rehearsal.env" -e DJANGO_SETTINGS_MODULE=rehearsal_settings \
        -v /opt/crm/migration-tests/app:/app -v /opt/crm/migration:/migration \
        -w /app crm-backend:c6414afc "$@"
}
run_custom python -m django import_suitecrm --snapshot "$inside_snapshot" --org "$org" --prepare --report "$inside_stage/prepare.json" > "$stage/prepare.log" 2>&1
run_custom python -m django import_suitecrm --snapshot "$inside_snapshot" --org "$org" --apply --report "$inside_stage/apply.json" > "$stage/apply.log" 2>&1
batch=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["batch_id"])' "$stage/apply.json")
run_custom python -m django verify_suitecrm --org "$org" --batch "$batch" --report "$inside_stage/verify.json" > "$stage/verify.log" 2>&1
run_custom python -m django import_suitecrm --snapshot "$inside_snapshot" --org "$org" --apply --report "$inside_stage/repeat.json" > "$stage/repeat.log" 2>&1
run_custom python -m django verify_suitecrm --org "$org" --batch "$batch" --report "$inside_stage/verify-repeat.json" > "$stage/verify-repeat.log" 2>&1
python3 - "$stage" <<'PY'
import json,sys
from pathlib import Path
stage=Path(sys.argv[1]);a=json.loads((stage/'apply.json').read_text());b=json.loads((stage/'repeat.json').read_text())
assert a['verified'] and b['verified'] and a['tables']==b['tables']
assert a['projections_total']==b['projections_total'] and not a['new_orphans'] and not b['new_orphans']
print('Rehearsal verified twice:',a['history_total'],'historical rows;',a['native_primary'],'native projections;',a['files']['verified'],'files')
PY
