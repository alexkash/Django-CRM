import { apiRequest } from '$lib/api-helpers.js';
import { COMPANY_FIELDS, pickFields } from '$lib/v2/billing.js';
const BASE = '/invoices/billing/legal-entities/';
const readable = (row) =>
  pickFields(row, ['id', ...COMPANY_FIELDS, 'signature_sha256', 'stamp_sha256']);
export async function listLegalEntities(event) {
  const result = await apiRequest(BASE, {}, event);
  return (result.results ?? []).map(readable);
}
export async function getLegalEntity(event, id) {
  const [row, banks] = await Promise.all([
    apiRequest(`${BASE}${id}/`, {}, event),
    apiRequest(`${BASE}${id}/bank-accounts/`, {}, event)
  ]);
  return { entity: readable(row), banks: banks.results ?? [] };
}
export function saveLegalEntity(event, id, values) {
  return apiRequest(
    id ? `${BASE}${id}/` : BASE,
    { method: id ? 'PATCH' : 'POST', body: pickFields(values, COMPANY_FIELDS) },
    event
  );
}
export function saveBankAccount(event, entityId, bankId, values) {
  const path = `${BASE}${entityId}/bank-accounts/${bankId ? `${bankId}/` : ''}`;
  return apiRequest(
    path,
    {
      method: bankId ? 'PATCH' : 'POST',
      body: pickFields(values, ['iban', 'bank_name', 'mfo', 'active'])
    },
    event
  );
}
export function uploadScan(event, id, kind, form) {
  if (!['signature', 'stamp'].includes(kind)) throw new Error('Невідомий тип зображення.');
  return apiRequest(`${BASE}${id}/scans/${kind}/`, { method: 'PUT', body: form }, event);
}
export function deleteScan(event, id, kind) {
  if (!['signature', 'stamp'].includes(kind)) throw new Error('Невідомий тип зображення.');
  return apiRequest(`${BASE}${id}/scans/${kind}/`, { method: 'DELETE' }, event);
}
