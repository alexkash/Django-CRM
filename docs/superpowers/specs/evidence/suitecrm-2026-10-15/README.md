# Read-only migration assessment evidence

Source count snapshot timestamp: `2026-10-15T10:13:18.777044+00:00`.

Collected on 2026-10-15 from SuiteCRM 7.12.6 at `164.92.244.103` and the deployed
Django-CRM application at `51.222.37.4`. No business rows were imported or edited.

- `table-counts.tsv`: exact source counts from one consistent, read-only InnoDB snapshot.
  `active` means `deleted=0`; it does not imply a user or record is operationally active.
  For tables without a deleted column, all rows are counted as active.
- `quality-checks.sql` and `quality-results.tsv`: read-only integrity queries and results.
- `profile-source.py`: exact schema/count snapshot plus aggregate upload-file checks.
- `profile-target.py`: deployed Django model fields and constraints.

The scripts run over existing SSH access, use the source database's local root socket,
and do not embed passwords. They do not print customer names, addresses, email bodies,
password hashes, or access tokens. Do not replace them with exports of raw business rows
in this repository. Full schema JSON outputs used for this assessment are cached locally
under `/tmp/suitecrm-migration-audit`, outside version control; regenerate if unavailable.

Reproduce with the source script sent to `ssh root@164.92.244.103 python3 -`, and the
target script sent to `ssh crm 'cd /opt/crm; sudo docker compose exec -T backend python -'`.
Quality checks run through `ssh root@164.92.244.103 'mysql --batch suitecrmdb'`.
Do not use one SSH command's stdin for a second unrelated command.

Counts describe the assessment snapshot, not a future migration cutoff. The actual import
must reconcile against its own immutable snapshot and complete file manifest.
