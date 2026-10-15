import { it, expect, vi } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));

it('loads the act chooser through the actual invoice-list normalization contract', async () => {
  const { load } = await import('./+page.server.js');
  const issuer = { id: 'seller', legal_name: 'Seller' };
  const issued_at = '2027-01-01T00:00:00Z';
  apiRequest.mockResolvedValue({
    results: [
      {
        id: 'paid',
        issuer,
        issued_at,
        status: 'Paid',
        account: 'buyer',
        account_name: 'Buyer',
        invoice_number: 'РХ-000001'
      },
      {
        id: 'sent',
        issuer,
        issued_at,
        status: 'Sent',
        account: 'buyer',
        account_name: 'Buyer',
        invoice_number: 'РХ-000002'
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
