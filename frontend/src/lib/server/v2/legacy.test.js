import { beforeEach, describe, expect, it, vi } from 'vitest';
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));
const { listLegacy, getLegacy, getEntityHistory, entityHistorySection } =
  await import('./legacy.js');
const event = /** @type {any} */ ({ cookies: { get: () => 'private-token' } });
const id = '11111111-1111-4111-8111-111111111111';
beforeEach(() => apiRequest.mockReset());
describe('private history server reader', () => {
  it('defaults deleted off and preserves pagination/source values without inventing dates', async () => {
    const response = {
      results: [{ id, source_created_at: null, title: 'Old' }],
      count: 51,
      next: '?offset=50',
      previous: null
    };
    apiRequest.mockResolvedValue(response);
    expect(await listLegacy(event, { q: 'a&b', offset: '50' })).toEqual(response);
    const [path, options, locals] = apiRequest.mock.calls[0];
    const url = new URL(path, 'http://api.test');
    expect(url.searchParams.get('deleted')).toBe('false');
    expect(url.searchParams.get('q')).toBe('a&b');
    expect(url.searchParams.get('offset')).toBe('50');
    expect(options).toEqual({});
    expect(locals.cookies).toBe(event.cookies);
  });
  it('preserves original long fields and unknown invoice totals', async () => {
    const response = {
      id,
      kind: 'invoice',
      source_created_at: '2017-01-01T00:00:00Z',
      fields: { phone_work: '123'.repeat(50), total_amount: null },
      adaptations: ['unknown_total']
    };
    apiRequest.mockResolvedValue(response);
    expect(await getLegacy(event, id)).toEqual(response);
  });
  it('distinguishes upstream error from an empty history', async () => {
    apiRequest.mockRejectedValue(new Error('Unavailable'));
    await expect(listLegacy(event, {})).rejects.toThrow();
    const section = await entityHistorySection(event, 'accounts', id);
    expect(section.error).toBeTruthy();
    apiRequest.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    expect((await getEntityHistory(event, 'accounts', id)).count).toBe(0);
  });
});
