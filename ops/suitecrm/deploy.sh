#!/usr/bin/env bash
# Run on the destination as root with a git-archived immutable reviewed release.
set -euo pipefail
umask 077
release=${1:?release directory required}
verified=${2:?verified rehearsal report required}
snapshot=${3:?snapshot export directory required}
mode=${4:---prepare}
[[ "$mode" == --prepare || "$mode" == --apply ]] || exit 2
commit=$(cat "$release/RELEASE_COMMIT")
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || exit 2
short=${commit:0:12}
org=7bf5683d-d4d0-461e-ba80-8f6c16cf3931
source_dir=$(dirname "$snapshot")
snapshot_id=$(basename "$source_dir")
[[ "$source_dir" == /opt/crm/migration/20261015T105712Z-1 ]] || exit 2
python3 - "$verified" "$snapshot/manifest.json" "$org" <<'PY'
import json,sys
report,manifest=map(lambda p:json.load(open(p)),sys.argv[1:3])
assert report['verified'] and report['org_id']==sys.argv[3]
assert report['source_key']==manifest['source_key']=='suitecrm-coloris'
assert report['snapshot_sha256']==manifest['snapshot_sha256']=='5dadacc31e6c50923fb7caa9feb9fd879cef28038077b8a9ed7ba9e6831375ca'
assert report['history_total']==201605 and report['files']['verified']==17
assert report['new_orphans']==0 and not report['conflicts']
PY
cd /opt/crm
exec 9>/run/lock/crm-suitecrm-deploy.lock
flock -n 9 || exit 3
work="/opt/crm/migration/deploy-$short"
mkdir -p "$work"
if [[ "$mode" == --prepare ]]; then
    docker build -f "$release/Dockerfile" -t "crm-backend:$short" "$release" > "$work/build-backend.log" 2>&1
    docker build --target runtime -f "$release/frontend/Dockerfile" -t "crm-frontend:$short" "$release/frontend" > "$work/build-frontend.log" 2>&1
    printf 'Sequential release builds complete: %s\n' "$commit"
    exit 0
fi
# This stamp is written only after the independent code review/fix pass.
[[ $(cat "$release/REVIEWED_COMMIT") == "$commit" ]] || exit 4
[[ ! -f "$work/applied" ]] || exit 5
docker image inspect "crm-backend:$short" >/dev/null
docker image inspect "crm-frontend:$short" >/dev/null
mkdir -m 700 "$work/before"
cp compose.yaml "$work/before/compose.yaml"
cp deploy/Caddyfile deploy/selfhost_settings.py deploy/backup.sh "$work/before/"
cp deploy/Caddyfile deploy/Caddyfile.pre-migration
install -d -m 700 -o 1000 -g 1000 "$work/reports" migration-files
# Prepare and validate maintenance before changing running services.
python3 - "$work" <<'PY'
import sys
from pathlib import Path
work=Path(sys.argv[1]);text=Path('deploy/Caddyfile').read_text()
prefix,sep,_=text.partition('  encode zstd gzip')
assert sep and 'https://51.222.37.4 {' in prefix
(work/'maintenance.Caddyfile').write_text(prefix+'  header Retry-After 120\n  respond "CRM temporarily unavailable during data migration. Please try again later." 503\n}\n')
PY
proxy_id=$(docker compose ps -q proxy)
docker cp "$work/maintenance.Caddyfile" "$proxy_id:/tmp/migration-maintenance.Caddyfile"
docker compose exec -T proxy caddy validate --config /tmp/migration-maintenance.Caddyfile --adapter caddyfile </dev/null > "$work/caddy-before.log" 2>&1
# In-place writes retain the inode of the existing file bind mount.
cat "$work/maintenance.Caddyfile" > deploy/Caddyfile
docker compose exec -T proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null > "$work/caddy-maintenance.log" 2>&1
[[ $(curl --max-time 15 -s -o /dev/null -w '%{http_code}' https://51.222.37.4/) == 503 ]] || exit 6
touch "$work/maintenance-active"
docker compose stop worker beat > "$work/pause.log" 2>&1
/opt/crm/deploy/backup.sh > "$work/backup-before.log"
backup=$(sed -n 's/^Created //p' "$work/backup-before.log")
[[ -f "$backup" ]] || exit 7
printf '%s\n' "$backup" > "$work/pre-apply-backup"
# No automatic destructive restore: on failure keep maintenance and evidence.
trap 'printf "Deployment stopped; maintenance retained. Private evidence: %s\n" "$work" >&2' ERR
python3 "$release/ops/suitecrm/restore-check.py" --archive "$backup" --stage "$work/restore-before" --database "crm_restore_check_${short}_before" --image "crm-backend:$short" --org "$org" > "$work/restore-before.log" 2>&1
python3 - "$short" <<'PY'
import re,sys
from pathlib import Path
short=sys.argv[1];path=Path('compose.yaml');text=path.read_text()
text,n=re.subn(r'crm-backend:[^\s\x27\x22]+','crm-backend:'+short,text);assert n==1
text,n=re.subn(r'crm-frontend:[^\s\x27\x22]+','crm-frontend:'+short,text);assert n==1
if './migration-files:/app/legacy-private' not in text:
    text=text.replace('    - ./media:/app/media','    - ./media:/app/media\n    - ./migration-files:/app/legacy-private',1)
path.write_text(text)
settings=Path('deploy/selfhost_settings.py');text=settings.read_text()
assert 'LEGACY_FILE_ROOT' not in text
settings.write_text(text+"\nLEGACY_FILE_ROOT = '/app/legacy-private'\n")
PY
cat > "$work/import.override.yaml" <<'YAML'
services:
  backend:
    mem_limit: 1g
YAML
# Reader's private derived index was created by the root rehearsal process.
# Giving the existing deployment UID access changes permissions, not source bytes.
chown -R 1000:1000 "$source_dir"
job() {
    docker compose -f compose.yaml -f "$work/import.override.yaml" run --rm -T --no-deps \
        -e PYTHONPATH=/app -v "$source_dir:/migration/$snapshot_id:ro" \
        -v "$work/reports:/reports" -v "$release/ops/suitecrm:/migration-ops:ro" \
        backend "$@"
}
job python -c 'import django;django.setup();from django.db import connection;c=connection.cursor();c.execute("SELECT current_database(),rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user");assert c.fetchone()==("crm_db",False,False);print("Destination database and RLS role verified")' > "$work/role.log" 2>&1
job python -m django migrate --noinput > "$work/migrate.log" 2>&1
job python -m django collectstatic --noinput > "$work/collectstatic.log" 2>&1
job python /migration-ops/baseline.py capture /reports/baseline.json "$org" > "$work/baseline.log" 2>&1
# New readers enforce source-parent permissions before any import can be read.
docker compose up -d --no-deps backend frontend > "$work/start-app.log" 2>&1
inside_snapshot="/migration/$snapshot_id/export"
job python -m django import_suitecrm --snapshot "$inside_snapshot" --org "$org" --prepare --report /reports/prepare.json > "$work/prepare.log" 2>&1
job python -m django import_suitecrm --snapshot "$inside_snapshot" --org "$org" --apply --report /reports/apply.json > "$work/apply.log" 2>&1
batch=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["batch_id"])' "$work/reports/apply.json")
job python -m django verify_suitecrm --org "$org" --batch "$batch" --report /reports/verify.json > "$work/verify.log" 2>&1
job python /migration-ops/baseline.py verify /reports/baseline.json "$org" > "$work/baseline-verify.log" 2>&1
install -m 700 "$release/ops/suitecrm/backup.sh" deploy/backup.sh
printf 'migration/%s\n' "$snapshot_id" > deploy/migration-snapshot-path
/opt/crm/deploy/backup.sh > "$work/backup-after.log"
backup_after=$(sed -n 's/^Created //p' "$work/backup-after.log")
python3 "$release/ops/suitecrm/restore-check.py" --archive "$backup_after" --stage "$work/restore-after" --database "crm_restore_check_${short}_after" --image "crm-backend:$short" --org "$org" --batch "$batch" > "$work/restore-after.log" 2>&1
cat "$work/before/Caddyfile" > deploy/Caddyfile
docker compose exec -T proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null > "$work/caddy-live.log" 2>&1
rm "$work/maintenance-active"
docker compose up -d --no-deps worker beat > "$work/resume.log" 2>&1
touch "$work/applied"
printf 'Applied and reconciled batch %s; private reports: %s/reports\n' "$batch" "$work"
