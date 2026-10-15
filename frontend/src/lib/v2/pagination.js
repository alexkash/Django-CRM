/** Paging is separate from filters; only these two validated numbers reach the API. */
/** @param {string|null|undefined} value @param {number} fallback @param {number} minimum */
function integer(value, fallback, minimum) {
  const n = /^\d+$/.test(value ?? '') ? Number(value) : NaN;
  return Number.isSafeInteger(n) && n >= minimum && n <= 2147483647 ? n : fallback;
}
/** @param {URLSearchParams} params @param {number} [defaultLimit] */
export function pageQuery(params, defaultLimit = 25) {
  const query = new URLSearchParams(params);
  query.set('limit', String(integer(query.get('limit'), defaultLimit, 1)));
  const offset = integer(query.get('offset'), 0, 0);
  if (offset) query.set('offset', String(offset));
  else query.delete('offset');
  return query;
}
/** @param {URLSearchParams} params @param {URL} url */
export function copyPaging(params, url) {
  for (const key of ['limit', 'offset']) {
    const value = url.searchParams.get(key);
    if (value !== null) params.set(key, value);
  }
  return params;
}
/** @param {URLSearchParams} query @param {number} count @param {number} shown */
export function pageState(query, count, shown) {
  const limit = integer(query.get('limit'), 25, 1);
  const offset = integer(query.get('offset'), 0, 0);
  const last = Math.max(0, (Math.ceil(count / limit) - 1) * limit);
  return {
    count,
    shown,
    limit,
    offset,
    start: shown ? offset + 1 : 0,
    end: shown ? Math.min(count, offset + shown) : 0,
    current: Math.floor(offset / limit) + 1,
    pages: Math.max(1, Math.ceil(count / limit)),
    previous: offset ? Math.min(last, Math.max(0, offset - limit)) : null,
    next: offset + limit < count ? offset + limit : null
  };
}
/** @param {URL} url @param {number} offset @param {number} limit */
export function pageHref(url, offset, limit) {
  const query = new URLSearchParams(url.search);
  query.set('limit', String(limit));
  if (offset) query.set('offset', String(offset));
  else query.delete('offset');
  return `${url.pathname}?${query}`;
}
