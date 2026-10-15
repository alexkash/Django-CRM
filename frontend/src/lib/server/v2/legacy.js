/** Private history requests use the caller's HttpOnly session, never browser tokens. */
import { apiRequest } from '$lib/api-helpers.js';

const FILTERS = ['q', 'table', 'kind', 'from', 'to', 'deleted', 'limit', 'offset'];
/** @param {URLSearchParams | Record<string,string>} [params] */
function query(params = {}) {
  const source = new URLSearchParams(params);
  const result = new URLSearchParams();
  for (const key of FILTERS) if (source.has(key)) result.set(key, source.get(key) ?? '');
  if (!result.has('deleted')) result.set('deleted', 'false');
  if (!result.has('limit')) result.set('limit', '50');
  return result;
}
/** @param {any} event @param {URLSearchParams | Record<string,string>} [params] */
export function listLegacy(event, params) {
  return apiRequest(`/legacy/records/?${query(params)}`, {}, event);
}
/** @param {any} event @param {string} id */
export function getLegacy(event, id) {
  return apiRequest(`/legacy/records/${encodeURIComponent(id)}/`, {}, event);
}
/** @param {any} event @param {string} model @param {string} id @param {URLSearchParams | Record<string,string>} [params] */
export function getEntityHistory(event, model, id, params) {
  return apiRequest(
    `/legacy/entities/${encodeURIComponent(model)}/${encodeURIComponent(id)}/history/?${query(params)}`,
    {},
    event
  );
}
/** An unavailable history panel must not masquerade as an empty history.
 * @param {any} event @param {string} model @param {string} id */
export async function entityHistorySection(event, model, id) {
  try {
    return await getEntityHistory(event, model, id, { limit: '5' });
  } catch {
    return { results: [], count: null, error: 'Не удалось загрузить историю SuiteCRM.' };
  }
}
/** @param {any} event @param {URLSearchParams | Record<string,string>} [params] */
export function listLegacyFiles(event, params) {
  return apiRequest(`/legacy/files/?${query(params)}`, {}, event);
}
