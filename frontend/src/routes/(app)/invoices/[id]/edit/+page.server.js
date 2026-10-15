import { error, fail, redirect } from '@sveltejs/kit';
import { getInvoice, updateInvoice } from '$lib/server/v2/invoices.js';
import { billingOptions } from '$lib/server/v2/billing-options.js';
import { readableError } from '$lib/server/v2/form-errors.js';
export async function load(event) {
  const [detail, options] = await Promise.all([
    getInvoice(event, event.params.id),
    billingOptions(event)
  ]);
  if (!detail.billing?.issuer_id || detail.billing.issued_at)
    error(400, 'Редагувати можна лише чернетку українського рахунку.');
  return { ...options, initial: detail.billing };
}
export const actions = {
  save: async (event) => {
    let body;
    try {
      body = JSON.parse(String((await event.request.formData()).get('payload') ?? '{}'));
      await updateInvoice(event, event.params.id, body);
    } catch (err) {
      return fail(err.status ?? 400, {
        values: body,
        error: readableError(err, 'Не вдалося зберегти рахунок.')
      });
    }
    redirect(303, `/invoices/${event.params.id}`);
  }
};
