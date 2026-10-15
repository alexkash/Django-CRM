import { error, fail } from '@sveltejs/kit';
import {
  getLegalEntity,
  saveLegalEntity,
  saveBankAccount,
  uploadScan,
  deleteScan
} from '$lib/server/v2/legal-entities.js';
import { viewerIsAdmin } from '$lib/server/v2/organization.js';
import { COMPANY_FIELDS } from '$lib/v2/billing.js';
import { readableError } from '$lib/server/v2/form-errors.js';
export async function load(event) {
  if (!viewerIsAdmin(event.cookies)) error(403, 'Лише адміністратор може змінювати компанії.');
  try {
    return await getLegalEntity(event, event.params.id);
  } catch (err) {
    if (err.status === 404) error(404, 'Компанія недоступна.');
    throw err;
  }
}
const failure = (err) =>
  fail([400, 403, 404, 409].includes(err.status) ? err.status : 400, {
    error: readableError(err, 'Не вдалося зберегти зміни.')
  });
export const actions = {
  save: async (event) => {
    const form = await event.request.formData();
    const values = Object.fromEntries(
      COMPANY_FIELDS.map((key) => [
        key,
        key === 'active' ? form.get(key) === 'true' : String(form.get(key) ?? '').trim()
      ])
    );
    try {
      await saveLegalEntity(event, event.params.id, values);
      return { saved: true };
    } catch (err) {
      return failure(err);
    }
  },
  bank: async (event) => {
    const form = await event.request.formData();
    try {
      await saveBankAccount(event, event.params.id, String(form.get('bank_id') ?? '') || null, {
        iban: String(form.get('iban') ?? ''),
        bank_name: String(form.get('bank_name') ?? ''),
        mfo: String(form.get('mfo') ?? ''),
        active: form.get('active') !== 'false'
      });
      return { saved: true };
    } catch (err) {
      return failure(err);
    }
  },
  scan: async (event) => {
    const form = await event.request.formData();
    try {
      await uploadScan(event, event.params.id, String(form.get('kind')), form);
      return { saved: true };
    } catch (err) {
      return failure(err);
    }
  },
  deleteScan: async (event) => {
    const form = await event.request.formData();
    try {
      await deleteScan(event, event.params.id, String(form.get('kind')));
      return { saved: true };
    } catch (err) {
      return failure(err);
    }
  }
};
