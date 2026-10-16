import { it, expect, vi } from 'vitest';
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));
it('loads every page of acts in the invoice card', async () => {
  const { load } = await import('./+page.server.js');
  const first = Array.from({ length: 10 }, (_, i) => ({ id: `act-${i}` }));
  const last = [{ id: 'act-10' }, { id: 'act-11' }];
  apiRequest.mockImplementation((path) => {
    if (path === '/invoices/parent/')
      return {
        invoice: {
          id: 'parent',
          issuer: { id: 'seller' },
          issued_at: '2027-01-01T00:00:00Z',
          status: 'Paid',
          account: { id: 'buyer' },
          line_items: [],
          payments: []
        }
      };
    const url = new URL('http://api.test' + path);
    expect(url.searchParams.get('invoice')).toBe('parent');
    return url.searchParams.get('offset') === '10'
      ? { results: last, next: null, count: 12 }
      : { results: first, next: 'http://api.test/next', count: 12 };
  });
  const result = await load(
    /** @type{any} */ ({ cookies: { get: () => 'session' }, params: { id: 'parent' } })
  );
  if (!result) throw Error('Expected invoice detail data');
  expect(result.acts.map((act) => act.id)).toEqual([...first, ...last].map((act) => act.id));
});
