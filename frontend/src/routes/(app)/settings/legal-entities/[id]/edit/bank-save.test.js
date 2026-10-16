import { it, expect, vi } from 'vitest';
const saveBankAccount = vi.fn();
vi.mock('$lib/server/v2/legal-entities.js', () => ({
  saveBankAccount: (...args) => saveBankAccount(...args),
  getLegalEntity: vi.fn(),
  saveLegalEntity: vi.fn(),
  uploadScan: vi.fn(),
  deleteScan: vi.fn()
}));
it.each(['', 'existing-bank'])('retains rejected bank fields for bank id %s', async (bankId) => {
  const { actions } = await import('./+page.server.js');
  const form = new FormData();
  form.set('bank_id', bankId);
  form.set('iban', 'BAD');
  form.set('bank_name', 'KEEP-BANK');
  form.set('mfo', '300001');
  form.set('active', 'false');
  saveBankAccount.mockRejectedValue({ status: 400, body: { iban: ['Invalid IBAN'] } });
  const result = await actions.bank(
    /** @type{any} */ ({ params: { id: 'seller' }, request: { formData: async () => form } })
  );
  if (!('status' in result)) throw Error('Expected validation failure');
  expect(result.status).toBe(400);
  expect(result.data.bank_id).toBe(bankId || null);
  expect(result.data.bank_values).toMatchObject({
    iban: 'BAD',
    bank_name: 'KEEP-BANK',
    mfo: '300001',
    active: false
  });
  expect(result.data.values).toBeUndefined();
});
