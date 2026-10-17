/**
 * The shell's token refresh and org switch send the visitor's signed address
 * (`$lib/server/relay.js`): the API writes an audit row for each, and without
 * it the row records this server.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@sentry/sveltekit', () => ({
  sentryHandle:
    () =>
    (/** @type {any} */ { event, resolve }) =>
      resolve(event),
  handleErrorWithSentry: () => () => {}
}));
// `sequence` needs SvelteKit's request store, which only a running server has.
// Sentry's handle is a pass-through here, so the app's own handle is the last.
vi.mock('@sveltejs/kit/hooks', () => ({
  sequence: (/** @type {any[]} */ ...handles) => handles[handles.length - 1]
}));
vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn() } }));

const axios = (await import('axios')).default;
const { env: privateEnv } = await import('$env/dynamic/private');
const { handle } = await import('./hooks.server.js');

const SECRET = 'r'.repeat(48);
const VISITOR = '198.51.100.7';
const BROWSER = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/142.0 Safari/537.36';
const SIGNED = {
  'X-Forwarded-For': VISITOR,
  'X-BottleCRM-Relay-Secret': SECRET,
  'X-BottleCRM-Client-IP': VISITOR,
  'X-BottleCRM-User-Agent': BROWSER
};
const ORG = '11111111-2222-3333-4444-555555555555';

/** @param {Record<string, unknown>} claims */
const jwt = (claims) =>
  ['h', Buffer.from(JSON.stringify(claims)).toString('base64url'), 's'].join('.');
const hourFromNow = () => Math.floor(Date.now() / 1000) + 3600;

/** @param {Record<string, string>} jar */
function event(jar) {
  return /** @type {any} */ ({
    url: new URL('http://app.test/login'),
    request: new Request('http://app.test/login', { headers: { 'user-agent': BROWSER } }),
    route: { id: '/(no-layout)/login' },
    locals: {},
    cookies: {
      get: (/** @type {string} */ name) => jar[name],
      set: vi.fn(),
      delete: vi.fn()
    },
    getClientAddress: () => VISITOR
  });
}

const resolve = vi.fn(async () => new Response('ok'));

/** @param {string} path */
const callTo = (path) =>
  vi.mocked(axios.post).mock.calls.find(([url]) => String(url).endsWith(path));

beforeEach(() => {
  privateEnv.RELAY_SECRET = SECRET;
  vi.mocked(axios.post).mockReset();
});

afterEach(() => {
  delete privateEnv.RELAY_SECRET;
});

describe('hooks.server.js relays the visitor', () => {
  it('on a token refresh', async () => {
    vi.mocked(axios.post).mockResolvedValue({
      data: { access: jwt({ user_id: 'u', exp: hourFromNow() }) }
    });

    await handle({
      event: event({ jwt_access: jwt({ user_id: 'u', exp: 1 }), jwt_refresh: 'r-1' }),
      resolve
    });

    const [, body, config] = /** @type {any[]} */ (callTo('/auth/refresh-token/'));
    expect(body).toEqual({ refresh: 'r-1' });
    expect(config.headers).toEqual(SIGNED);
  });

  it('on an org switch', async () => {
    vi.mocked(axios.post).mockResolvedValue({
      data: {
        access_token: jwt({ user_id: 'u', org_id: ORG, exp: hourFromNow() }),
        refresh_token: 'r-2',
        current_org: { id: ORG, name: 'Acme' }
      }
    });

    await handle({
      event: event({
        jwt_access: jwt({ user_id: 'u', exp: hourFromNow() }),
        jwt_refresh: 'r-1',
        org: ORG
      }),
      resolve
    });

    const [, , config] = /** @type {any[]} */ (callTo('/auth/switch-org/'));
    expect(config.headers).toMatchObject(SIGNED);
    expect(config.headers.Authorization).toMatch(/^Bearer /);
  });

  it('sends only the pre-1.12 X-Forwarded-For without a secret', async () => {
    delete privateEnv.RELAY_SECRET;
    vi.mocked(axios.post).mockResolvedValue({ data: {} });

    await handle({
      event: event({ jwt_access: jwt({ user_id: 'u', exp: 1 }), jwt_refresh: 'r-3' }),
      resolve
    });

    expect(/** @type {any[]} */ (callTo('/auth/refresh-token/'))[2].headers).toEqual({
      'X-Forwarded-For': VISITOR
    });
  });
});

describe('restoring a session after the access cookie expires', () => {
  it('restores the user and org from the refresh cookie on a protected route', async () => {
    const access = jwt({ user_id: 'returning-user', org_id: ORG, exp: hourFromNow() });
    vi.mocked(axios.post).mockResolvedValue({ data: { access, refresh: 'rotated' } });
    const returning = event({ jwt_refresh: 'still-valid', org: ORG });
    returning.url = new URL('http://app.test/leads');

    await handle({ event: returning, resolve });

    expect(returning.locals.user.id).toBe('returning-user');
    expect(returning.locals.org.id).toBe(ORG);
    expect(returning.cookies.set).toHaveBeenCalledWith(
      'jwt_refresh',
      'rotated',
      expect.objectContaining({ maxAge: 2592000, httpOnly: true, sameSite: 'lax' })
    );
    expect(returning.cookies.set).toHaveBeenCalledWith('jwt_access', access, expect.any(Object));
  });

  it('clears an expired or revoked refresh cookie and requires sign-in', async () => {
    vi.mocked(axios.post).mockRejectedValue({ response: { status: 401 } });
    const returning = event({ jwt_refresh: 'revoked', org: ORG });
    returning.url = new URL('http://app.test/leads');

    await expect(handle({ event: returning, resolve })).rejects.toMatchObject({
      status: 307,
      location: '/login'
    });

    expect(returning.locals.user).toBeUndefined();
    for (const name of ['jwt_access', 'jwt_refresh', 'org']) {
      expect(returning.cookies.delete).toHaveBeenCalledWith(name, { path: '/' });
    }
  });

  it('shares one rotation between concurrent requests without access cookies', async () => {
    const access = jwt({ user_id: 'returning-user', exp: hourFromNow() });
    vi.mocked(axios.post).mockResolvedValue({ data: { access, refresh: 'rotated-once' } });
    const requests = [event({ jwt_refresh: 'shared' }), event({ jwt_refresh: 'shared' })];

    await Promise.all(requests.map((request) => handle({ event: request, resolve })));

    expect(axios.post).toHaveBeenCalledTimes(1);
    for (const request of requests) {
      expect(request.locals.user.id).toBe('returning-user');
      expect(request.cookies.set).toHaveBeenCalledWith(
        'jwt_refresh',
        'rotated-once',
        expect.objectContaining({ maxAge: 2592000 })
      );
    }
  });
});
