import { listLegalEntities } from '$lib/server/v2/legal-entities.js';
import { viewerIsAdmin } from '$lib/server/v2/organization.js';
export async function load(event) {
  return { entities: await listLegalEntities(event), can_edit: viewerIsAdmin(event.cookies) };
}
