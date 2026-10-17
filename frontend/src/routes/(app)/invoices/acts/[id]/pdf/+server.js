import { streamDownload } from '$lib/server/v2/files.js';
export function GET(event) {
  const variant = event.url.searchParams.get('variant') ?? 'clean';
  if (!['clean', 'stamped'].includes(variant))
    return new Response('Invalid variant', { status: 400 });
  return streamDownload(event, `/invoices/billing/acts/${event.params.id}/pdf/?variant=${variant}`);
}
