import { error, fail, redirect } from '@sveltejs/kit';
import { getAct, issueAct, cancelAct, deleteAct } from '$lib/server/v2/service-acts.js';
import { readableError } from '$lib/server/v2/form-errors.js';
export async function load(event) {
  try {
    return { act: await getAct(event, event.params.id) };
  } catch (err) {
    if (err.status === 404) error(404, 'Акт недоступний.');
    throw err;
  }
}
const failure = (err) =>
  fail(err.status ?? 400, { error: readableError(err, 'Не вдалося виконати дію.') });
export const actions = {
  issue: async (event) => {
    try {
      await issueAct(event, event.params.id);
      return { issued: true };
    } catch (err) {
      return failure(err);
    }
  },
  cancel: async (event) => {
    try {
      await cancelAct(
        event,
        event.params.id,
        String((await event.request.formData()).get('reason') ?? '')
      );
      return { cancelled: true };
    } catch (err) {
      return failure(err);
    }
  },
  delete: async (event) => {
    try {
      await deleteAct(event, event.params.id);
    } catch (err) {
      return failure(err);
    }
    redirect(303, '/invoices/acts');
  }
};
