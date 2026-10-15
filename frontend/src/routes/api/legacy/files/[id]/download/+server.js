import { streamDownload } from '$lib/server/v2/files.js';
/** @type {import('./$types').RequestHandler} */
export async function GET(event) {
  const response = await streamDownload(
    event,
    `/legacy/files/${encodeURIComponent(event.params.id)}/download/`
  );
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}
