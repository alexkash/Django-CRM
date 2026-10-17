import { it, expect, vi } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));

it('loads the act chooser through the actual invoice-list normalization contract', async () => {
  const { load } = await import('./+page.server.js');
  const issuer = { id: 'seller', legal_name: 'Seller' };
  const issued_at = '2027-01-01T00:00:00Z';
  const open = { lines: [{ remaining_quantity: '1.00000000' }], remaining_total: '0.00' };
  apiRequest.mockResolvedValue({
    results: [
      {
        id: 'paid',
        closure: open,
        issuer,
        issued_at,
        status: 'Paid',
        account: 'buyer',
        account_name: 'Buyer',
        invoice_number: 'РХ-000001'
      },
      {
        id: 'sent',
        closure: open,
        issuer,
        issued_at,
        status: 'Sent',
        account: 'buyer',
        account_name: 'Buyer',
        invoice_number: 'РХ-000002'
      },
      {
        id: 'closed',
        issuer,
        issued_at,
        status: 'Paid',
        closure: { lines: [{ remaining_quantity: '0.00000000' }], remaining_total: '0.00' }
      },
      { id: 'draft', issuer, issued_at: null, status: 'Draft' },
      { id: 'cancelled', issuer, issued_at, status: 'Cancelled' },
      { id: 'generic', issuer: null, issued_at: null, status: 'Sent' }
    ],
    totals: {}
  });
  const event = /** @type {any} */ ({
    cookies: { get: () => 'session' },
    url: new URL('http://crm.test/invoices/acts/new')
  });
  const result = await load(event);
  expect(result.invoice).toBeNull();
  expect(result.invoices.map((invoice) => invoice.id)).toEqual(['paid', 'sent']);
  expect(result.invoices[0].account.name).toBe('Buyer');
});

it('redirects a stale fully closed invoice link back to the chooser', async () => {
  const { load } = await import('./+page.server.js');
  apiRequest.mockResolvedValue({
    invoice: {
      id: 'closed',
      issuer: { id: 'seller' },
      issued_at: '2027-01-01T00:00:00Z',
      status: 'Paid',
      account: { id: 'buyer', name: 'Buyer' },
      line_items: [],
      payments: [],
      closure: { lines: [{ remaining_quantity: '0.00000000' }], remaining_total: '0.00' }
    }
  });
  const event = /** @type {any} */ ({
    cookies: { get: () => 'session' },
    url: new URL('http://crm.test/invoices/acts/new?invoice=closed')
  });
  await expect(load(event)).rejects.toMatchObject({ status: 303, location: '/invoices/acts/new' });
});
