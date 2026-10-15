import { error } from '@sveltejs/kit';
import { getEntityHistory, listLegacy, listLegacyFiles } from '$lib/server/v2/legacy.js';
/** @type {import('./$types').PageServerLoad} */
export async function load(event) {
  const params = event.url.searchParams;
  const entity = params.get('entity');
  const id = params.get('id');
  try {
    const history =
      params.get('view') === 'files'
        ? await listLegacyFiles(event, params)
        : entity && id
          ? await getEntityHistory(event, entity, id, params)
          : await listLegacy(event, params);
    return {
      history,
      query: Object.fromEntries(params),
      filesView: params.get('view') === 'files'
    };
  } catch (/** @type {any} */ err) {
    error(
      err?.status >= 400 && err.status <= 599 ? err.status : 502,
      'Не удалось загрузить историю SuiteCRM.'
    );
  }
}
