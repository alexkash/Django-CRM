import { error } from '@sveltejs/kit';
import { getLegacy } from '$lib/server/v2/legacy.js';
/** @type {import('./$types').PageServerLoad} */
export async function load(event) {
  try {
    return { record: await getLegacy(event, event.params.id) };
  } catch (/** @type {any} */ err) {
    error(
      err?.status >= 400 && err.status <= 599 ? err.status : 502,
      'История SuiteCRM недоступна.'
    );
  }
}
