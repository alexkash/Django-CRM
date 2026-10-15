import { describe, it, expect } from 'vitest';

describe('billing form payloads', () => {
  it('keeps prices and quantities as decimal strings and discards server-owned fields', async () => {
    const { uaInvoicePayload } = await import('./billing-forms.js');
    const body = uaInvoicePayload({
      issuer_id: 'issuer',
      bank_account_id: 'bank',
      account_id: 'account',
      contact_id: 'contact',
      invoice_title: 'Support',
      tax_rate: '20,00',
      org: 'forged',
      status: 'Paid',
      archived_pdf_clean: 'forged',
      line_items: [
        { name: 'Support', quantity: '12', unit_price: '1000,01', unit: 'місяць', total: '1' }
      ]
    });
    expect(body.tax_rate).toBe('20.00');
    expect(body.line_items[0]).toEqual({
      name: 'Support',
      description: '',
      quantity: '12',
      unit_price: '1000.01',
      unit: 'місяць'
    });
    expect(body).not.toHaveProperty('org');
    expect(body).not.toHaveProperty('status');
    expect(body).not.toHaveProperty('archived_pdf_clean');
  });
  it('rounds each line before summing VAT using integer arithmetic', async () => {
    const { previewUATotals } = await import('./billing-forms.js');
    expect(
      previewUATotals(
        [
          { quantity: '1', unit_price: '0.03' },
          { quantity: '1', unit_price: '0.03' }
        ],
        '20',
        'PAYER'
      )
    ).toEqual({ subtotal: '0.06', tax_amount: '0.02', total_amount: '0.08' });
  });
  it('rejects malformed numbers before they can turn into JSON null', async () => {
    const { decimalString } = await import('./billing-forms.js');
    for (const value of ['NaN', 'Infinity', '-1', '1.2.3'])
      expect(() => decimalString(value)).toThrow();
    expect(decimalString('0.08333333', 8)).toBe('0.08333333');
  });
});

describe('catalogue lines in the Ukrainian builder', () => {
  it('replaces the untouched starter row so required blank inputs do not block saving', async () => {
    const { addCatalogLine } = await import('$lib/v2/billing.js');
    const rows = addCatalogLine(
      [{ name: '', description: '', quantity: '1', unit: 'послуга', unit_price: '0.00' }],
      { id: 'p', name: 'Support', unit: 'місяць', price: '1000.00' }
    );
    expect(rows).toEqual([
      {
        product: 'p',
        name: 'Support',
        description: '',
        quantity: '1',
        unit: 'місяць',
        unit_price: '1000.00'
      }
    ]);
  });
  it('preserves a manually edited row when adding another catalogue item', async () => {
    const { addCatalogLine } = await import('$lib/v2/billing.js');
    const original = {
      name: 'Manual service',
      description: '',
      quantity: '2',
      unit: 'год',
      unit_price: '20.00'
    };
    const rows = addCatalogLine([original], {
      id: 'p',
      name: 'Support',
      unit: 'місяць',
      price: '1000.00'
    });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual(original);
  });
});

describe('clearing a separate invoice payer', () => {
  it('sends an explicit null and discards hidden payer corrections', async () => {
    const { uaInvoicePayload } = await import('./billing-forms.js');
    const body = uaInvoicePayload({
      payer_id: '',
      draft_parties: {
        customer: { legal_name: 'Corrected recipient' },
        payer: { legal_name: 'Previous separate payer' }
      }
    });
    expect(body.payer_id).toBeNull();
    expect(body.draft_parties.customer.legal_name).toBe('Corrected recipient');
    expect(body.draft_parties.payer).toEqual({});
  });
});

it('sends an explicit null to recalculate a cleared due date on draft update', async () => {
  const { uaInvoicePayload } = await import('./billing-forms.js');
  const body = uaInvoicePayload({ issue_date: '2027-02-01', due_date: '' });
  expect(body).toHaveProperty('due_date', null);
});
