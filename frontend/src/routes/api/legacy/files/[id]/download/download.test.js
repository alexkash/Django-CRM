import { afterEach, expect, it, vi } from 'vitest';
vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_DJANGO_API_URL: 'http://api.test' } }));
const { GET } = await import('./+server.js');
afterEach(() => vi.restoreAllMocks());
const id = '11111111-1111-4111-8111-111111111111';
it.each([403, 404])('preserves upstream refusal %s without a file', async (status) => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('private bytes', { status }));
  const response = await GET(
    /** @type {any} */ ({
      params: { id },
      cookies: { get: () => 'token' },
      request: new Request('http://ui.test/')
    })
  );
  expect(response.status).toBe(status);
  expect(await response.text()).not.toContain('private bytes');
});
it('streams successful downloads privately with nosniff', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('bytes', { headers: { 'Content-Disposition': 'attachment; filename="x.txt"' } })
  );
  const response = await GET(
    /** @type {any} */ ({
      params: { id },
      cookies: { get: () => 'token' },
      request: new Request('http://ui.test/')
    })
  );
  expect(response.headers.get('Cache-Control')).toBe('private, no-store');
  expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
  expect(await response.text()).toBe('bytes');
});
