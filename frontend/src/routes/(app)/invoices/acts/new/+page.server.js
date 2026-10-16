import { fail, redirect } from '@sveltejs/kit';
import { getInvoice, listInvoices } from '$lib/server/v2/invoices.js';
import { createAct } from '$lib/server/v2/service-acts.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { hasRemainingServices } from '$lib/v2/billing.js';
export async function load(event) {
  const id = event.url.searchParams.get('invoice');
  if (id) {
    const detail = await getInvoice(event, id);
    const invoice = detail.billing;
    if (
      !invoice?.issuer_id ||
      !invoice.issued_at ||
      invoice.status === 'Cancelled' ||
      !hasRemainingServices(invoice)
    )
      redirect(303, '/invoices/acts/new');
    return { invoice };
  }
  const rows = await listInvoices(event, new URLSearchParams({ limit: '1000' }));
  return {
    invoice: null,
    invoices: rows.invoices.filter(
      (row) =>
        row.issuer && row.issued_at && row.status !== 'Cancelled' && hasRemainingServices(row)
    )
  };
}
export const actions = {
  save: async (event) => {
    let body, act;
    try {
      body = JSON.parse(String((await event.request.formData()).get('payload') ?? '{}'));
      act = await createAct(event, body);
    } catch (err) {
      return fail(err.status ?? 400, {
        values: body,
        error: readableError(err, 'Не вдалося створити акт.')
      });
    }
    redirect(303, `/invoices/acts/${act.id}`);
  }
};
