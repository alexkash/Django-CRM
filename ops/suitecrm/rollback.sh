#!/usr/bin/env bash
# Explicit recovery only while this release still owns full maintenance.
set -euo pipefail
umask 077
work=${1:?deployment evidence directory required}
[[ "$work" =~ ^/opt/crm/migration/deploy-[a-f0-9]{12}$ ]] || exit 2
[[ -f "$work/maintenance-active" && ! -f "$work/applied" ]] || exit 3
cd /opt/crm
cmp -s deploy/Caddyfile "$work/maintenance.Caddyfile" || exit 4
[[ $(curl --max-time 15 -s -o /dev/null -w '%{http_code}' https://51.222.37.4/) == 503 ]] || exit 4
backup=$(cat "$work/pre-apply-backup")
[[ -f "$backup" && -f "$work/restore-before/result.json" ]] || exit 5
python3 - "$backup" "$work/restore-before/result.json" <<'PYVERIFY'
import hashlib,json,sys
h=hashlib.sha256()
with open(sys.argv[1],'rb') as incoming:
    for chunk in iter(lambda:incoming.read(1024*1024),b''):h.update(chunk)
r=json.load(open(sys.argv[2]));assert r['verified'] and r['archive_sha256']==h.hexdigest() and r['batch'] is None
PYVERIFY
# A prior verified restore is required before destructive recovery.
[[ -f "$work/restore-before/database.dump" ]] || exit 5
mkdir -m 700 "$work/rollback"
python3 - "$backup" "$work/rollback/database.dump" <<'PY'
import shutil,sys,tarfile
with tarfile.open(sys.argv[1]) as tar:
    matches=[m for m in tar.getmembers() if m.name.removeprefix('./')=='database.dump' and m.isfile()]
    assert len(matches)==1
    with tar.extractfile(matches[0]) as incoming,open(sys.argv[2],'wb') as outgoing:
        shutil.copyfileobj(incoming,outgoing)
PY
docker compose stop backend worker beat > "$work/rollback/stop.log" 2>&1
# Exact dedicated destination database only; no Docker volume is removed.
docker compose exec -T db psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='crm_db' AND pid<>pg_backend_pid()" </dev/null > "$work/rollback/connections.log" 2>&1
docker compose exec -T db dropdb -U postgres crm_db </dev/null
docker compose exec -T db createdb -U postgres crm_db </dev/null
docker compose exec -T db pg_restore -U postgres --no-owner -d crm_db < "$work/rollback/database.dump" > "$work/rollback/restore.log" 2>&1
cp "$work/before/compose.yaml" compose.yaml
cat "$work/before/selfhost_settings.py" > deploy/selfhost_settings.py
cp "$work/before/backup.sh" deploy/backup.sh
docker compose up -d --no-deps backend frontend worker beat > "$work/rollback/start.log" 2>&1
cat "$work/before/Caddyfile" > deploy/Caddyfile
docker compose exec -T proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile </dev/null > "$work/rollback/caddy.log" 2>&1
rm "$work/maintenance-active"
touch "$work/rolled-back"
printf 'Pre-apply database and release restored; source CRM untouched.\n'
