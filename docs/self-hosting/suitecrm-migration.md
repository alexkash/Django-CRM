# SuiteCRM snapshot migration

The migration preserves an immutable T0 snapshot. SuiteCRM stays online; this is not an automatic cutover or continuous synchronization. Later SuiteCRM changes require a separately reviewed delta migration.

The importer is specific to the reviewed `suitecrm-coloris` source and its existing destination organization. Its global source identity deliberately prevents rebinding that snapshot to another organization. Importing another source or destination requires a separately reviewed identity namespace and mapping; changing the namespace of this deployment would invalidate its existing deterministic IDs and reconciliation records.

## Evidence and safety

Source: `164.92.244.103`, SuiteCRM 7.12.6. Destination: the existing `/opt/crm` installation on `51.222.37.4`, organization `7bf5683d-d4d0-461e-ba80-8f6c16cf3931`. The approved snapshot is `/opt/crm/migration/20261015T105712Z-1`; SQL SHA256 is `5dadacc31e6c50923fb7caa9feb9fd879cef28038077b8a9ed7ba9e6831375ca`.

SQL dumps, exports, reports, metadata, credentials and customer files stay private on the server. Do not commit them, publish them or print their contents. Full SQL contains credentials that are deliberately absent from the web archive. The source app, its database, DNS, SSH and automations are not changed.

`legacy` stores all exported business rows, original string IDs, deletion flags, typed values, relations and adaptation reasons. Native projections use deterministic UUIDv5 IDs and tracked fingerprints including M2M assignments. Deleted records stay in history. Historical mail never enters the delivery path. Incomplete invoices and quotes remain historical; no balances, payments or line items are invented. Original addresses, long phones and duplicate people remain inspectable. Missing product currencies stay unknown; the catalogue explicitly displays “currency not recorded” without inventing USD or throwing a formatting error. The existing destination currency/settings and owner access are preserved.

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

Full-data authenticated checks succeeded for both roles. PostgreSQL defaults caused native-page timeouts after import. Controlled tests selected `work_mem=32MB`, `max_parallel_workers_per_gather=0`, and `jit=off`; 64MB did not materially improve results. The database memory limit is now 1GB (previously 512MB), with the settings persisted in Compose and applied by configuration reload. RLS, roles and data are unchanged. Ordinary-user endpoints took approximately 7–20 seconds in isolated checks; the live email list took 25.7 seconds with concurrent browser traffic. Administrator lists took 2.3–5.4 seconds in live checks. Further permission-query optimization remains deferred.

## Completion evidence

Actual destination apply completed on 2026-10-15, batch `4e3eaa0f-5ec7-4f1a-bccc-669a7e8e8ccb`. Apply and independent verification both report `verified=true`: all 221 source tables accounted for, 201,605 historical business rows, 21,701 primary native projections, 73,283 total tracked projections, and all 17 files (4,445,894 bytes). Every payload, relation, projection fingerprint and attachment hash reconciled: zero mismatches, zero conflicts, zero new orphan links. Existing source orphan references remain explicit: 73,298 missing parents and 17,079 deleted parents; these are pre-existing graph references, not newly lost records.

| Active source category | Result |
| --- | ---: |
| Companies | 4,812 native accounts |
| Contacts | 8,177 native contacts |
| Leads | 3,399 native leads |
| Deals | 3,064 native opportunities |
| Products | 2 native products, currency unknown |
| Users | 7 tracked users and 7 profiles; owner preserved |
| Emails | 2,234 historical native email records plus source evidence |
| Calls / meetings | 4,230 / 163 in protected history |
| Original tasks | 6 completed tasks |
| Planned calls / meetings | 179 followup tasks |
| Activities | 51,396 native activity records |
| Historical invoices / quotes | 442 / 2; no native financial totals invented |
| Uploads | 17 private files; unidentified associations remain admin-only |

Backend image: `crm-backend:bf3d3ab66ccd`; frontend image: `crm-frontend:8ab48b19be15` (the additional accepted NULL-currency rendering fix). Original images remain available. Full maintenance ran approximately 15:02–16:04 UTC; source HTTP remained 200. The pre-existing destination-record baseline, including owner password hash and membership, passed unchanged.

Private apply/reconciliation reports and recovery evidence: `/opt/crm/migration/deploy-bf3d3ab66ccd/`. The initial post-import backup restored and reconciled before traffic resumed. A final backup including PostgreSQL tuning is `/opt/crm/backups/crm-20261015T162819Z.tar.gz`; its separate restore/reconciliation passed, with evidence under `restore-final/` in that directory. No customer payloads or credentials are included in this repository.

Validation: final backend regression 7,858 passed, 62 skipped (including 44 PostgreSQL-only tests), coverage 95.29%; real PostgreSQL 65 legacy and 44 PostgreSQL-specific tests passed under a non-superuser/non-bypass role. Frontend 1,122 tests passed, Svelte check had zero errors/warnings, production build passed; lint passed with eight existing warnings. Export tests and the actual rollback-owner/read/write/FORCE-RLS/ALTER regression passed. Fresh independent whole-branch review had one Important ownership finding, fixed with an observed failing-then-passing PostgreSQL regression. Three review Minors and ordinary-user latency are disclosed above.

Actual full-snapshot scheduled-job checks produced zero mail, queue dispatch or HTTP calls and no financial/delivery mutations. Live workers answered inspection; native Invoice, Payment, AccountEmailLog and WebhookDelivery counts remained zero. Real browser acceptance covered owner/member login, email search, calls, source→native company→history, catalogue with two unknown currencies, download size/SHA, historical invoices, desktop/mobile layout and zero page errors. The ordinary member saw no unlinked files and direct download returned 404. Test sessions were signed out.

The snapshot was captured at 2026-10-15 10:57 UTC. SuiteCRM remains live and unchanged; later edits are not synchronized. SMTP/Google remain unconfigured, and old SuiteCRM passwords are not activated.

Backups taken inside maintenance retain that maintenance response in `deploy/Caddyfile`. The normal TLS/proxy configuration is also saved as `deploy/Caddyfile.pre-migration`; restore it only after data verification. `restore-check.py` restores data archives only, never executes a backup's scripts/env, and writes a completion sentinel tied to the exact archive SHA256. `rollback.sh` refuses after traffic resumed or when the deployment no longer owns maintenance; it requires that verified pre-apply archive before restoring the exact dedicated destination database. Same-server rollback preserves the dump’s original object owners and ACLs, so the normal `crm_app` migration role retains ALTER rights. A dedicated isolated PostgreSQL regression exercises these exact restore flags, ordinary read/write, FORCE RLS, and a subsequent schema alteration. It does not remove Docker volumes or touch SuiteCRM.

Final runtime acceptance confirmed all seven services running, backend/frontend/database healthy, HTTPS root and health endpoint HTTP 200, `crm_app` NOSUPERUSER/NOBYPASSRLS, the exact reviewed images, and the active 32MB/0/off PostgreSQL settings with a 1GB database limit. The isolated migration PostgreSQL container is stopped; its databases, volumes, snapshot and evidence remain private and retained.
