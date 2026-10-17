import { error, fail, redirect } from '@sveltejs/kit';
import { getInvoice } from '$lib/server/v2/invoices.js';
import { getAct, updateAct } from '$lib/server/v2/service-acts.js';
import { readableError } from '$lib/server/v2/form-errors.js';
export async function load(event) {
  const initial = await getAct(event, event.params.id);
  if (initial.status !== 'Draft') error(400, 'Редагувати можна лише чернетку.');
  const detail = await getInvoice(event, initial.invoice_id);
  return { initial, invoice: detail.billing };
}
export const actions = {
  save: async (event) => {
    let body;
    try {
      body = JSON.parse(String((await event.request.formData()).get('payload') ?? '{}'));
      await updateAct(event, event.params.id, body);
    } catch (err) {
      return fail(err.status ?? 400, {
        values: body,
        error: readableError(err, 'Не вдалося зберегти акт.')
      });
    }
    redirect(303, `/invoices/acts/${event.params.id}`);
  }
};
