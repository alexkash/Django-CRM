import { streamDownload } from '$lib/server/v2/files.js';
export function GET(event) {
  if (!['signature', 'stamp'].includes(event.params.kind))
    return new Response('Not found', { status: 404 });
  return streamDownload(
    event,
    `/invoices/billing/legal-entities/${event.params.id}/scans/${event.params.kind}/`
  );
}
