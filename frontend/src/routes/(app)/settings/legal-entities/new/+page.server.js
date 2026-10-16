import { error, fail, redirect } from '@sveltejs/kit';
import { saveLegalEntity } from '$lib/server/v2/legal-entities.js';
import { viewerIsAdmin } from '$lib/server/v2/organization.js';
import { COMPANY_FIELDS } from '$lib/v2/billing.js';
import { readableError } from '$lib/server/v2/form-errors.js';
export function load({ cookies }) {
  if (!viewerIsAdmin(cookies)) error(403, 'Лише адміністратор може додавати компанії.');
  return {};
}
export const actions = {
  save: async (event) => {
    const form = await event.request.formData();
    const values = Object.fromEntries(
      COMPANY_FIELDS.map((key) => [
        key,
        key === 'active' ? form.get(key) === 'true' : String(form.get(key) ?? '').trim()
      ])
    );
    let entity;
    try {
      entity = await saveLegalEntity(event, null, values);
    } catch (err) {
      return fail(err.status ?? 400, {
        values,
        error: readableError(err, 'Не вдалося зберегти компанію.')
      });
    }
    redirect(303, `/settings/legal-entities/${entity.id}/edit`);
  }
};
