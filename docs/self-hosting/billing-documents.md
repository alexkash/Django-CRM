# Ukrainian invoices and service acts

> The billing API and PDF lifecycle are available in this backend PR. The web settings and editors described below arrive in its dependent UI PR.

A single CRM organization can issue documents from several of its own legal entities: ФОП or ТОВ, with or without VAT. These issuing companies share the CRM's customer and product catalog. Choose the company on each invoice; products are not automatically assigned to a company.

## Set up the parties

Open **Settings → Наші компанії**. An organization administrator adds the legal name, registration code, address, tax status, signer and bank accounts. Enter an IBAN with its checksum, the bank name and optional МФО. A company may have several bank accounts. Archive unused companies or bank accounts rather than removing records used by documents.

The optional signature and stamp are raster images for printing. Upload PNG or JPEG, up to 2 MiB and 16 megapixels; transparent PNG is useful for a clean background. The application decodes and normalizes the image, rejects animation, and applies the size limit to the normalized PNG too. Original scan access is administrator-only. These images do not implement electronic signing.

On the customer's account, enter **Юридичні реквізити для документів**: full name, code, address, bank details and representative. Existing customer records remain valid without these fields; the required document particulars are checked when issuing. You can override customer or payer particulars in a draft for that document.

## Create and issue an invoice

From **Invoices**, choose **Рахунок (Україна)**. Select your company, one of its active IBANs, the customer and contact. The payer defaults to the customer. Enter the contract reference, document date, service period, and line items with their units, quantities and prices **excluding VAT**.

The invoice shows the amount excluding VAT, VAT separately, and the final amount including VAT. Non-payers display **Без ПДВ**. A VAT payer with a numeric zero rate remains a payer; it is not silently reclassified as a non-payer. Tax classification and the selected rate are operator inputs.

Save a draft, inspect its PDF and use **Виписати рахунок** when ready. Issuing is separate from sending an email and does not record a payment. A draft PDF has a **ЧЕРНЕТКА** label and does not allocate a document number.

Two PDF links are available: **PDF без сканів** and **PDF з підписом і печаткою**. They open a PDF that can be printed through the browser's PDF viewer. The issued PDFs, printed particulars, text and totals are frozen. Subsequent company, client, bank, scan, template or payment changes do not rewrite that document. Missing optional scans do not prevent issuing.

Invoices and acts have separate increasing sequences for each issuing company. Numbers are allocated on issue, start at one, and are not reused after cancellation. Prefixes can be changed before the first document of that type is issued. There is no automatic annual reset.

The first Ukrainian form supports UAH, one invoice VAT rate, and no discounts or shipping. Generic invoices retain their existing behavior. Payment recording and explicit email sending on a Ukrainian invoice require it to be issued first. Anonymous portal links and automatic reminders are disabled for this form.

## Close services with partial acts

Use **Створити частковий акт** on an issued invoice. Select the quantities to close, set the act date and service period, save its draft, review it and use **Виписати акт**. The act's period must be inside the invoice's service period; its preparation date may be later. Its parties and contract come from the issued invoice, including the historical particulars.

For annual support, a convenient invoice line is `12 місяць × monthly net price`. Close `1` each month or `3` each quarter. A source quantity of one can also be closed fractionally, with up to eight decimal places. For twelve equal parts use `0.08333333` initially and **Весь залишок** for the final part. Decimal quantities travel as strings, without rounding to two places in the act editor.

The application distributes the remaining net and VAT budgets as each act is issued; the final part takes the exact remaining cents. This also handles very small amounts and zero-priced services. Only issued acts consume the available quantity. Drafts do not reserve it: if another act closes the balance first, issuance returns a conflict and the draft remains available for correction.

Payment and service closure are independent. The invoice separately displays **Оплачено**, **Закрито актами**, and **Залишилось закрити**. An advance payment does not generate an act. A partially closed invoice can remain unpaid.

To correct an issued act, cancel it with a reason and create another. Cancellation releases its allocation once and retains the original PDF and number. An invoice cannot be cancelled while it has an issued act. **Створити на основі** creates a fresh invoice draft with the company, contract, units and prices, but without the old service period, payment, acts, number or PDF archives.

## Access and storage

Acts inherit access from their parent invoice. A hidden invoice does not become accessible through act lists, totals, downloads or lifecycle actions. The new database tables have forced PostgreSQL row policies, and the API also filters organization and record access explicitly. Scan administration is narrower than document access: a user allowed to open a document may print its stamped PDF without being given the source image.

Normalized scans and the two issued PDF variants are stored in private binary database columns, not publicly served media. Each PDF is limited to 10 MiB. Normal list, detail and related queries defer those columns; download endpoints fetch the selected bytes only. Include these columns in complete PostgreSQL backups and account for their storage size. Restore the database as a whole so the snapshots, quantities, counters, hashes and archives remain consistent.

Schema changes are additive to existing records; historical invoices are not automatically assigned an issuing entity. Once new documents have been issued, preserve the schema and archives and fix forward. Do not reverse the numbering constraints on live data where different issuing companies can use the same printed number.

Scheduling, monthly work lists, notifications, electronic signatures, incoming documents, industry-specific forms and tax invoices are outside this first version. Ordinary service examples guided the forms; specialized transactions may require a different form.
