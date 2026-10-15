/** Shared, credential-free form rules. Monetary values remain decimal strings. */
export const COMPANY_FIELDS = [
  'entity_type',
  'legal_name',
  'registration_code',
  'address',
  'phone',
  'email',
  'city',
  'vat_status',
  'default_vat_rate',
  'vat_registration_number',
  'tax_system_text',
  'signer_name',
  'signer_title',
  'active',
  'invoice_prefix',
  'act_prefix'
];
export const CUSTOMER_BILLING_FIELDS = [
  'legal_name',
  'registration_code',
  'vat_registration_number',
  'legal_address',
  'iban',
  'bank_name',
  'mfo',
  'tax_system_text',
  'signer_name',
  'signer_title'
];
export const PARTY_LABELS = {
  legal_name: 'Повне найменування',
  registration_code: 'ЄДРПОУ / РНОКПП',
  vat_registration_number: 'ІПН платника ПДВ',
  legal_address: 'Юридична адреса',
  iban: 'IBAN',
  bank_name: 'Банк',
  mfo: 'МФО',
  tax_system_text: 'Система оподаткування',
  signer_name: 'ПІБ підписанта',
  signer_title: 'Посада підписанта'
};

export function pickFields(values, fields) {
  return Object.fromEntries(
    fields.filter((key) => Object.hasOwn(values, key)).map((key) => [key, values[key]])
  );
}

export function decimalString(value, places = 2) {
  const text = String(value ?? '')
    .trim()
    .replace(',', '.');
  if (!new RegExp(`^\\d+(?:\\.\\d{1,${places}})?$`).test(text))
    throw new Error('Вкажіть додатне десяткове число.');
  return text;
}

export function uaInvoicePayload(values) {
  const result = pickFields(values, [
    'issuer_id',
    'bank_account_id',
    'account_id',
    'contact_id',
    'payer_id',
    'invoice_title',
    'issue_date',
    'due_date',
    'payment_terms',
    'contract_number',
    'contract_date',
    'order_reference',
    'service_period_start',
    'service_period_end',
    'place_of_issue',
    'notes',
    'terms',
    'draft_parties'
  ]);
  if (result.draft_parties)
    result.draft_parties = Object.fromEntries(
      Object.entries(result.draft_parties).map(([side, fields]) => [
        side,
        Object.fromEntries(
          Object.entries(fields).filter(([, v]) => typeof v === 'string' && v.trim())
        )
      ])
    );
  result.currency = 'UAH';
  result.tax_rate = decimalString(values.tax_rate ?? '0');
  if (!result.payer_id) {
    result.payer_id = null;
    if (result.draft_parties) result.draft_parties.payer = {};
  }
  for (const key of ['contract_date', 'service_period_start', 'service_period_end'])
    if (!result[key]) result[key] = null;
  if (!result.due_date) result.due_date = null;
  result.line_items = (values.line_items ?? []).map((line) => ({
    name: line.name ?? '',
    description: line.description ?? '',
    unit: line.unit ?? 'послуга',
    quantity: decimalString(line.quantity),
    unit_price: decimalString(line.unit_price),
    ...(line.product ? { product: line.product } : {})
  }));
  return result;
}

export function actPayload(values) {
  const result = pickFields(values, [
    'invoice_id',
    'issue_date',
    'service_period_start',
    'service_period_end'
  ]);
  result.lines = (values.lines ?? []).map((line) => ({
    source_line_id: line.source_line_id,
    quantity: decimalString(line.quantity, 8)
  }));
  for (const key of ['service_period_start', 'service_period_end'])
    if (!result[key]) result[key] = null;
  return result;
}

function scaled(value, places) {
  const [whole, fraction = ''] = decimalString(value, places).split('.');
  return BigInt(whole) * 10n ** BigInt(places) + BigInt(fraction.padEnd(places, '0'));
}
/** @param {bigint} a @param {bigint} b @returns {bigint} */
const roundRatio = (a, b) => (a + b / 2n) / b;
const cents = (value) => `${value / 100n}.${String(value % 100n).padStart(2, '0')}`;
export function previewUATotals(lines, rate, status) {
  let net = 0n,
    tax = 0n;
  const r = status === 'NON_PAYER' ? 0n : scaled(rate || '0', 2);
  for (const line of lines) {
    const amount = roundRatio(scaled(line.quantity, 2) * scaled(line.unit_price, 2), 100n);
    net += amount;
    tax += roundRatio(amount * r, 10000n);
  }
  return { subtotal: cents(net), tax_amount: cents(tax), total_amount: cents(net + tax) };
}

export function billingInvoice(raw) {
  const data = pickFields(raw, [
    'id',
    'invoice_number',
    'invoice_title',
    'status',
    'issued_at',
    'issue_date',
    'due_date',
    'payment_terms',
    'contract_number',
    'contract_date',
    'order_reference',
    'service_period_start',
    'service_period_end',
    'place_of_issue',
    'vat_status',
    'tax_rate',
    'subtotal',
    'tax_amount',
    'total_amount',
    'amount_paid',
    'amount_due',
    'draft_parties',
    'closure',
    'notes',
    'terms'
  ]);
  data.parties = raw.printed_parties ?? null;
  data.issuer_name = raw.issuer_name ?? raw.issuer?.legal_name ?? '';
  data.account_name = raw.account?.name ?? '';
  data.issuer = raw.issuer ?? null;
  data.bank_account = raw.bank_account ?? null;
  data.issuer_id = raw.issuer?.id ?? '';
  data.bank_account_id = raw.bank_account?.id ?? '';
  data.account_id = raw.account?.id ?? '';
  data.contact_id = raw.contact?.id ?? '';
  data.payer_id = raw.payer_id ?? '';
  data.line_items = (raw.line_items ?? []).map((line) =>
    pickFields(line, [
      'id',
      'product',
      'name',
      'description',
      'unit',
      'quantity',
      'unit_price',
      'tax_amount',
      'net_amount',
      'total'
    ])
  );
  return data;
}

/** Replace only the untouched starter, never a row the user has edited. */
export function addCatalogLine(lines, product) {
  const line = {
    product: product.id,
    name: product.name,
    description: '',
    quantity: '1',
    unit: product.unit || 'послуга',
    unit_price: decimalString(product.price)
  };
  const first = lines[0];
  const untouched =
    lines.length === 1 &&
    !first.name?.trim() &&
    !first.description?.trim() &&
    !first.product &&
    ['1', '1.00'].includes(String(first.quantity)) &&
    /^0+(?:[.,]0+)?$/.test(String(first.unit_price)) &&
    (!first.unit || first.unit === 'послуга');
  return untouched ? [line] : [...lines, line];
}

/** A zero-priced service can still have quantity left to close. @param {any} invoice */
export function hasRemainingServices(invoice) {
  return Boolean(invoice?.closure?.lines?.some((line) => Number(line.remaining_quantity) > 0));
}
