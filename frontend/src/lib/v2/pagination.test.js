import { expect, it } from 'vitest';
import { pageQuery, pageState, pageHref } from './pagination.js';
it('normalizes malformed paging before making an API request', () => {
  const query = pageQuery(new URLSearchParams('search=Acme&offset=-5&limit=wrong'), 25);
  expect(query.toString()).toBe('search=Acme&limit=25');
  expect(pageQuery(new URLSearchParams('offset=99999999999999999&limit=0'), 50).toString()).toBe(
    'limit=50'
  );
});
it('derives correct middle and final ranges from the matched count', () => {
  expect(pageState(new URLSearchParams('offset=25&limit=25'), 51, 25)).toEqual({
    count: 51,
    shown: 25,
    limit: 25,
    offset: 25,
    start: 26,
    end: 50,
    current: 2,
    pages: 3,
    previous: 0,
    next: 50
  });
  expect(pageState(new URLSearchParams('offset=50&limit=25'), 51, 1)).toMatchObject({
    start: 51,
    end: 51,
    current: 3,
    pages: 3,
    previous: 25,
    next: null
  });
});
it('can recover from an empty out-of-range page', () => {
  expect(pageState(new URLSearchParams('offset=75&limit=25'), 26, 0)).toMatchObject({
    start: 0,
    end: 0,
    previous: 25,
    next: null
  });
  expect(pageState(new URLSearchParams('limit=25'), 0, 0)).toMatchObject({
    previous: null,
    next: null,
    start: 0,
    end: 0,
    pages: 1
  });
});
it('preserves repeated filters and query text in same-origin navigation', () => {
  const url = new URL('https://crm.test/contacts?tags=one&tags=two&search=A%26B&inactive=1');
  expect(pageHref(url, 25, 25)).toBe(
    '/contacts?tags=one&tags=two&search=A%26B&inactive=1&limit=25&offset=25'
  );
  expect(pageHref(new URL('https://crm.test/tasks?all=1&offset=25'), 0, 50)).toBe(
    '/tasks?all=1&limit=50'
  );
});
