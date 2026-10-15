import { expect, it, vi } from 'vitest';
import {
  accountListQuery,
  contactListQuery,
  leadListQuery,
  ticketListQuery,
  invoiceListQuery,
  dealListQuery
} from './list-queries.js';
import { withParams, withoutParam } from '$lib/v2/filters.js';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));
const { listAccounts } = await import('./accounts.js');

it.each([accountListQuery, contactListQuery, leadListQuery, ticketListQuery, invoiceListQuery])(
  'forwards the selected page together with filters',
  (builder) => {
    const query = builder(new URL('https://crm.test/list?search=Acme&limit=25&offset=25'));
    expect(query.get('offset')).toBe('25');
    expect(query.get('limit')).toBe('25');
  }
);
it('forwards deal-list pages without paginating the board', () => {
  expect(
    dealListQuery(new URL('https://crm.test/pipeline?offset=25&limit=25'), []).params.get('offset')
  ).toBe('25');
  expect(
    dealListQuery(new URL('https://crm.test/pipeline?view=board&offset=25'), []).params.has(
      'offset'
    )
  ).toBe(false);
});
it('loads a different slice after following the account next-page URL', async () => {
  apiRequest.mockImplementation(async (path) => {
    const start = Number(new URL(path, 'https://api.test').searchParams.get('offset') ?? 0);
    return {
      active_accounts: {
        open_accounts_count: 51,
        open_accounts: Array.from({ length: 25 }, (_, i) => ({
          id: `account-${start + i}`,
          name: `Account ${start + i}`
        }))
      }
    };
  });
  const result = await listAccounts(
    /** @type {any} */ ({ cookies: { get: () => undefined } }),
    accountListQuery(new URL('https://crm.test/accounts?offset=25'))
  );
  expect(result.results.map((row) => row.id)).toEqual(
    Array.from({ length: 25 }, (_, i) => `account-${25 + i}`)
  );
});
it('returns to page one when a filter changes or is removed', () => {
  const url = new URL('https://crm.test/accounts?city=Kyiv&limit=25&offset=50');
  expect(withParams(url, { city: 'Lviv' })).toBe('/accounts?city=Lviv&limit=25');
  expect(withoutParam(url, 'city')).toBe('/accounts?limit=25');
});

it('uses the filtered invoice count rather than the org-wide summary for paging', async () => {
  const { listInvoices } = await import('./invoices.js');
  apiRequest.mockResolvedValue({ results: [], count: 12, totals: { count: 100 } });
  const result = await listInvoices(
    /** @type {any} */ ({ cookies: {} }),
    new URLSearchParams('limit=5&offset=5')
  );
  expect(result.pagination).toMatchObject({ count: 12, offset: 5, limit: 5, next: 10 });
});
it('filters completed tasks before slicing the open task queue', async () => {
  const { load } = await import('../../../routes/(app)/tasks/+page.server.js');
  const rows = [
    ...Array.from({ length: 5 }, (_, i) => ({
      id: `closed-${i}`,
      title: 'Closed',
      status: 'Completed'
    })),
    { id: 'open', title: 'Open', status: 'New' }
  ];
  apiRequest.mockImplementation(async (path) => {
    if (!path.startsWith('/tasks/')) return {};
    const q = new URL(path, 'https://api.test').searchParams;
    const statuses = q.getAll('status');
    const selected = rows.filter((row) => !statuses.length || statuses.includes(row.status));
    return {
      tasks: selected.slice(0, Number(q.get('limit'))),
      tasks_count: selected.length,
      totals: { count: 6 }
    };
  });
  const result = await load(
    /** @type {any} */ ({
      url: new URL('https://crm.test/tasks?limit=5'),
      cookies: { get: () => undefined },
      locals: {}
    })
  );
  if (!result) throw new Error('List loader returned no data');
  expect(result.tasks.map((task) => task.id)).toEqual(['open']);
  expect(result.pagination.count).toBe(1);
});
