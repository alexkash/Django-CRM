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
          logo_sha256: 'logo-hash',
          logo_png: 'private-logo',
          stamp_png: 'secret'
        }
      ]
    });
    const result = await listLegalEntities(event);
    expect(result[0].default_vat_rate).toBe('20.00');
    expect(result[0]).not.toHaveProperty('signature_png');
    expect(result[0]).not.toHaveProperty('stamp_png');
    expect(result[0].logo_sha256).toBe('logo-hash');
    expect(result[0]).not.toHaveProperty('logo_png');
  });
  it('uploads and removes the company logo through the private asset route', async () => {
    const { uploadScan, deleteScan } = await import('./legal-entities.js');
    const form = new FormData();
    apiRequest.mockResolvedValue({ sha256: 'logo-hash' });
    await uploadScan(event, 'company', 'logo', form);
    expect(apiRequest.mock.calls[0][0]).toBe(
      '/invoices/billing/legal-entities/company/scans/logo/'
    );
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'PUT', body: form });
    await deleteScan(event, 'company', 'logo');
    expect(apiRequest.mock.calls[1][1].method).toBe('DELETE');
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
