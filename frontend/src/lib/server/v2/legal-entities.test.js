import { describe, it, expect, vi, beforeEach } from 'vitest';
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));
const event = { cookies: { get: () => 'session' } };

describe('issuing company API', () => {
  beforeEach(() => apiRequest.mockReset());
  it('returns company settings without converting rate strings or leaking scan bytes', async () => {
    const { listLegalEntities } = await import('./legal-entities.js');
    apiRequest.mockResolvedValue({
      results: [
        {
          id: 'company',
          legal_name: 'Тест',
          default_vat_rate: '20.00',
          signature_png: 'secret',
          stamp_png: 'secret'
        }
      ]
    });
    const result = await listLegalEntities(event);
    expect(result[0].default_vat_rate).toBe('20.00');
    expect(result[0]).not.toHaveProperty('signature_png');
    expect(result[0]).not.toHaveProperty('stamp_png');
  });
  it('writes only editable company fields and uses its own nested bank path', async () => {
    const { saveLegalEntity, saveBankAccount } = await import('./legal-entities.js');
    apiRequest.mockResolvedValue({ id: 'company' });
    await saveLegalEntity(event, null, {
      legal_name: 'Тест',
      vat_status: 'NON_PAYER',
      org: 'forged',
      signature_png: 'forged'
    });
    expect(apiRequest.mock.calls[0][1].body).toEqual({
      legal_name: 'Тест',
      vat_status: 'NON_PAYER'
    });
    await saveBankAccount(event, 'company', null, {
      iban: 'UA27',
      bank_name: 'Bank',
      entity: 'forged'
    });
    expect(apiRequest.mock.calls[1][0]).toBe(
      '/invoices/billing/legal-entities/company/bank-accounts/'
    );
    expect(apiRequest.mock.calls[1][1].body).toEqual({ iban: 'UA27', bank_name: 'Bank' });
  });
});
