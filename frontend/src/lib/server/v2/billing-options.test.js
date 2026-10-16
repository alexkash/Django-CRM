import { it, expect, vi } from 'vitest';

vi.mock('./legal-entities.js', () => ({
  listLegalEntities: vi.fn().mockResolvedValue([]),
  getLegalEntity: vi.fn()
}));
vi.mock('./accounts.js', () => ({ listAccounts: vi.fn().mockResolvedValue({ results: [] }) }));
vi.mock('./contacts.js', () => ({ listContacts: vi.fn().mockResolvedValue({ results: [] }) }));
vi.mock('./products.js', () => ({
  listProducts: vi.fn().mockResolvedValue({
    results: [
      { id: 'uah', currency: 'UAH', is_active: true, price: 1000 },
      { id: 'usd', currency: 'USD', is_active: true, price: 1000 },
      { id: 'unknown', currency: null, is_active: true, price: 1000 },
      { id: 'inactive', currency: 'UAH', is_active: false, price: 1000 }
    ]
  })
}));

it('offers only active UAH catalogue prices in the UAH invoice builder', async () => {
  const { billingOptions } = await import('./billing-options.js');
  const result = await billingOptions({ cookies: { get: () => 'session' } });
  expect(result.products.map((p) => p.id)).toEqual(['uah']);
});
