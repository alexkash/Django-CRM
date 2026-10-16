# Issuing companies and billing schema

Organization administrators can manage issuing companies at `/api/invoices/billing/legal-entities/`, their `bank-accounts/`, and private `scans/signature/` or `scans/stamp/`. Members may read company particulars and active bank accounts; source scans and writes require organization administrator access. Company and bank lookups are scoped to the authenticated organization.

Companies support ФОП/ТОВ, VAT payer or non-payer, signer particulars, active/archive state, and separate invoice/act number prefixes. PNG/JPEG scans are normalized to PNG, limited to 2 MiB and 16 megapixels, and stored privately in the database. Include binary columns in backups. Account API writes accept structured legal, tax, bank and signer details. Account merge treats these particulars as one identity group.

This first PR adds UAH to supported currency choices and additive nullable invoice fields, draft act tables, counters, constraints, and forced PostgreSQL row policies. Existing invoices retain generic calculation and lifecycle behavior. Ordinary queries defer PDF/image binary columns, including existing payment and timesheet joins. Issuing Ukrainian invoices, PDF generation, act allocation, and the web editor arrive in the dependent PRs. No existing invoice is automatically assigned an issuer.
