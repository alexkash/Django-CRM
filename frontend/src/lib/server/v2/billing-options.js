import { listLegalEntities, getLegalEntity } from './legal-entities.js';
import { listAccounts } from './accounts.js';
import { listContacts } from './contacts.js';
import { listProducts } from './products.js';
export async function billingOptions(event) {
  const [entities, accounts, contacts, products] = await Promise.all([
    listLegalEntities(event),
    listAccounts(event, new URLSearchParams({ limit: '1000' })),
    listContacts(event, new URLSearchParams({ limit: '1000' })),
    listProducts(event)
  ]);
  const details = await Promise.all(entities.map((row) => getLegalEntity(event, row.id)));
  return {
    entities,
    banks_by_entity: Object.fromEntries(details.map((row) => [row.entity.id, row.banks])),
    accounts: accounts.results.map((row) => ({ id: row.id, name: row.name })),
    contacts: contacts.results.map((row) => ({
      id: row.id,
      name: row.name || row.email,
      account_id: row.account?.id ?? null
    })),
    products: products.results.filter((row) => row.is_active && row.currency === 'UAH')
  };
}
