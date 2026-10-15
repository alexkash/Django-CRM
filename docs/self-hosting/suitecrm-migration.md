# SuiteCRM snapshot migration

The migration preserves an immutable T0 snapshot. SuiteCRM stays online; this is not an automatic cutover or continuous synchronization. Later SuiteCRM changes require a separately reviewed delta migration.

## Evidence and safety

Source: `164.92.244.103`, SuiteCRM 7.12.6. Destination: the existing `/opt/crm` installation on `51.222.37.4`, organization `7bf5683d-d4d0-461e-ba80-8f6c16cf3931`. The approved snapshot is `/opt/crm/migration/20261015T105712Z-1`; SQL SHA256 is `5dadacc31e6c50923fb7caa9feb9fd879cef28038077b8a9ed7ba9e6831375ca`.

SQL dumps, exports, reports, metadata, credentials and customer files stay private on the server. Do not commit them, publish them or print their contents. Full SQL contains credentials that are deliberately absent from the web archive. The source app, its database, DNS, SSH and automations are not changed.

`legacy` stores all exported business rows, original string IDs, deletion flags, typed values, relations and adaptation reasons. Native projections use deterministic UUIDv5 IDs and tracked fingerprints including M2M assignments. Deleted records stay in history. Historical mail never enters the delivery path. Incomplete invoices and quotes remain historical; no balances, payments or line items are invented. Original addresses, long phones and duplicate people remain inspectable. Missing product currencies stay unknown. The existing destination currency/settings and owner access are preserved.

## Prepare and rehearse

Run `ops/suitecrm/rehearse.sh BACKUP SNAPSHOT_EXPORT EXACT_ORG_UUID` on the destination as root. It refuses arbitrary database names, restores the target backup into a separate database on the isolated migration PostgreSQL container, verifies NOSUPERUSER/NOBYPASSRLS/NOCREATEDB, and runs prepare/apply/verify twice. It never points pytest at the live database.

`ops/suitecrm/run-tests.sh` checks the isolated database/role before fixture writes. The backend suite also runs under its normal SQLite settings with coverage. Real PostgreSQL tests enforce RLS and transaction/locking behavior. Frontend Vitest, Svelte checks/build and isolated desktop/mobile browser checks cover the read/search/download flow and inert email content.

Management commands use `python -m django`, because this deployment's `manage.py` forces upstream settings:

```sh
python -m django import_suitecrm --snapshot /migration/SNAPSHOT/export --org ORG_UUID --prepare --report /reports/prepare.json
python -m django import_suitecrm --snapshot /migration/SNAPSHOT/export --org ORG_UUID --apply --report /reports/apply.json
python -m django verify_suitecrm --org ORG_UUID --batch BATCH_UUID --report /reports/verify.json
```

The three import modes are mutually exclusive. `--resume` continues a failed batch from its durable checkpoint, only for the same source/manifest/org. A second apply on an applied batch verifies without replaying projections. A user edit, missing target, changed manifest or unexplained reconciliation mismatch fails rather than overwriting current data.

## Release and maintenance

Use an immutable reviewed release. Build backend/frontend images sequentially. Save old image IDs, Compose/settings/proxy files and a fresh backup first. During final migration pause worker/beat and put the destination behind a full maintenance response: partial relationship phases must not be readable. The source CRM remains available.

The new runtime mounts `migration-files` as `/app/legacy-private`; it is separate from public media and requires authenticated downloads. Import jobs additionally mount the private snapshot and report directories. Runtime UID is 1000, so derived reader indexes, private file directories and report directories must be readable/writable by that UID without making them public. Keep `DJANGO_SETTINGS_MODULE=selfhost_settings`. Apply migrations and collectstatic before starting the new application/performing the import.

Never run `compose down -v`. Preserve PostgreSQL, Redis and Caddy volumes and all existing secrets/TLS settings. Resume normal traffic and worker/beat only after successful reconciliation and baseline-owner/data checks.

## Recovery and backups

If an apply fails, retain maintenance and reports. A full database restore is safe only while the destination has accepted no later user writes. Stop backend/worker/beat, restore the pre-apply dump and original Compose/settings/images, then restore service. If traffic has already resumed, do not restore an old database over new user work; resolve the batch's own projections using its journal or obtain an explicit recovery decision.

The backup script includes the database, ordinary media, private migrated files, deployment configuration and the immutable source snapshot selected by `deploy/migration-snapshot-path`. Archives are private and retained seven days. Check restoration in a separate database and verify source/target row counts, fingerprints and every attachment hash before considering a backup usable.

## Read access and known boundaries

The `SuiteCRM history` navigation provides module/type/date/search/deleted filters and a private file index. Native account/contact/lead/deal/task cards link their history. Invoices link to the historical list; these amounts do not enter live totals. Unknown stages ask for classification and do not automatically become open/won/lost.

FORCE RLS applies to every history table. Members additionally need their native entity read permission and every business-parent permission. Missing/deleted/unknown parents and unlinked files fail closed. Followup tasks cannot grant access to an otherwise unparented historical event. HTML is plain/escaped text: no scripts, frames, forms or tracking images run.

Existing owner login remains valid. SuiteCRM passwords, sessions and OAuth credentials are not activated. SMTP/Google are not configured by this migration; the existing private file mail backend remains in place. The owner can generate a test login through the existing SSH `deploy/login-link` helper. Do not publish login links or tokens.

## Reviewed limitations

Three presentation/export edges were deferred by the final review: product history has no native catalogue link (the two products remain available in the catalogue); a contact headline may name an unclassified deal alongside the correct open-pipeline amount; and `users_password_link` is currently categorized as history. That authentication table contains zero rows in this exact approved snapshot, so no reset token is imported. Seal it before using the exporter for a later snapshot. The deployment gate accepts only the exact approved snapshot hash.

Full-data authenticated checks succeeded for both roles. During concurrent import, the selected ordinary member’s all-parent permission queries took approximately 13–18 seconds, while administrator reads after startup took under one second. This is a known history-read performance limitation, not permission relaxation. Final live acceptance records timings separately.

## Completion evidence

The final server reports identify snapshot, table coverage, native projections, original orphan links, adaptations and file hashes. `verified=true` requires zero unexplained differences. Final counts and backup/restore evidence are recorded after the actual destination apply; a staging-only run is not completion.

Backups taken inside maintenance retain that maintenance response in `deploy/Caddyfile`. The normal TLS/proxy configuration is also saved as `deploy/Caddyfile.pre-migration`; restore it only after data verification. `restore-check.py` restores data archives only, never executes a backup's scripts/env, and writes a completion sentinel tied to the exact archive SHA256. `rollback.sh` refuses after traffic resumed or when the deployment no longer owns maintenance; it requires that verified pre-apply archive before restoring the exact dedicated destination database. Same-server rollback preserves the dump’s original object owners and ACLs, so the normal `crm_app` migration role retains ALTER rights. A dedicated isolated PostgreSQL regression exercises these exact restore flags, ordinary read/write, FORCE RLS, and a subsequent schema alteration. It does not remove Docker volumes or touch SuiteCRM.
