#!/usr/bin/env bash
# Private, restorable database + files + immutable source evidence.
set -euo pipefail
umask 077
cd /opt/crm
mkdir -p backups
exec 9>/run/lock/crm-backup.lock
flock -n 9 || exit 0
stage=$(mktemp -d /opt/crm/backups/.staging-XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
docker compose exec -T db pg_dump -U postgres -Fc crm_db </dev/null > "$stage/database.dump"
tar -czf "$stage/media.tar.gz" media
if [[ -d migration-files ]]; then
    tar -czf "$stage/migration-files.tar.gz" migration-files
fi
if [[ -f deploy/migration-snapshot-path ]]; then
    snapshot=$(cat deploy/migration-snapshot-path)
    [[ "$snapshot" =~ ^migration/[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || exit 2
    [[ -d "$snapshot" && ! -L "$snapshot" ]] || exit 2
    tar -czf "$stage/source-snapshot.tar.gz" "$snapshot"
fi
cp backend.env db.env frontend.env compose.yaml "$stage/"
cp -r deploy "$stage/"
archive="/opt/crm/backups/crm-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar -czf "$archive" -C "$stage" .
find /opt/crm/backups -maxdepth 1 -type f -name 'crm-????????T??????Z.tar.gz' -mtime +7 -delete
printf 'Created %s\n' "$archive"
