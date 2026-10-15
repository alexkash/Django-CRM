import { listLegalEntities } from '$lib/server/v2/legal-entities.js';
import { listActs } from '$lib/server/v2/service-acts.js';
export async function load(event) {
  return {
    acts: await listActs(event, event.url.searchParams),
    entities: await listLegalEntities(event),
    filters: Object.fromEntries(event.url.searchParams)
  };
}
