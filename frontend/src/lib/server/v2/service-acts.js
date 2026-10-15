import { apiRequest } from '$lib/api-helpers.js';
import { actPayload } from '$lib/v2/billing.js';
const BASE = '/invoices/billing/acts/';
export function listActs(event, params = new URLSearchParams()) {
  const query = new URLSearchParams();
  for (const key of [
    'invoice',
    'account',
    'issuer',
    'status',
    'period_start',
    'period_end',
    'limit',
    'offset'
  ])
    if (params.get(key)) query.set(key, params.get(key));
  return apiRequest(BASE + (query.size ? '?' + query : ''), {}, event);
}
export function getAct(event, id) {
  return apiRequest(`${BASE}${id}/`, {}, event);
}
export function createAct(event, body) {
  return apiRequest(BASE, { method: 'POST', body: actPayload(body) }, event);
}
export function updateAct(event, id, body) {
  return apiRequest(`${BASE}${id}/`, { method: 'PUT', body: actPayload(body) }, event);
}
export function issueAct(event, id) {
  return apiRequest(`${BASE}${id}/issue/`, { method: 'POST', body: {} }, event);
}
export function cancelAct(event, id, reason) {
  return apiRequest(`${BASE}${id}/cancel/`, { method: 'POST', body: { reason } }, event);
}
export function deleteAct(event, id) {
  return apiRequest(`${BASE}${id}/`, { method: 'DELETE' }, event);
}
