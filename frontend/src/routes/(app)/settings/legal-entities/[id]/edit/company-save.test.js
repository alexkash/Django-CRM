import { it, expect, vi } from 'vitest';
const saveLegalEntity = vi.fn();
vi.mock('$lib/server/v2/legal-entities.js', () => ({
  saveLegalEntity: (...args) => saveLegalEntity(...args),
  getLegalEntity: vi.fn(),
  saveBankAccount: vi.fn(),
  uploadScan: vi.fn(),
  deleteScan: vi.fn()
}));
it('returns submitted company particulars after API validation failure', async () => {
  const { actions } = await import('./+page.server.js');
  const form = new FormData();
  form.set('legal_name', 'KEEP-COMPANY');
  form.set('registration_code', 'bad');
  form.set('active', 'true');
  saveLegalEntity.mockRejectedValue({ status: 400, body: { registration_code: ['Invalid code'] } });
  const event = /** @type {any} */ ({
    params: { id: 'seller' },
    cookies: { get: () => 'session' },
    request: { formData: async () => form }
  });
  const result = await actions.save(event);
  if (!('status' in result)) throw Error('Expected a validation failure');
  expect(result.status).toBe(400);
  expect(result.data.values).toMatchObject({
    legal_name: 'KEEP-COMPANY',
    registration_code: 'bad',
    active: true
  });
});
