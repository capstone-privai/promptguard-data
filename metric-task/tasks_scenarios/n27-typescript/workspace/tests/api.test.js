import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, createClient, queryString } from '../src/api/client.js';
import { cancelOrder, listOrders } from '../src/api/orders.js';
import { allInCategory, displayPrice } from '../src/api/products.js';
import { buildQuery, search } from '../src/api/search.js';
import { EventQueue } from '../src/api/analytics.js';
import { previewClaims } from '../src/api/cms.js';
import { mockResponse } from '../src/__mocks__/login.js';
import { session } from '../src/session.js';

function fakeFetch(replies) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url, ...init });
    const [status, body, headers = {}] = replies.shift();
    return mockResponse(status, headers, body);
  };
  return { fetchImpl, calls };
}

test('query strings skip empty values', () => {
  assert.equal(queryString({ page: 2, status: undefined, q: 'mug & cup', empty: '' }), '?page=2&q=mug%20%26%20cup');
  assert.equal(queryString({}), '');
});

test('client retries 503 and sends the session token', async () => {
  session.store('opaque-access-1', 'opaque-refresh-1', 4102444800);
  const { fetchImpl, calls } = fakeFetch([[503, undefined, { 'retry-after': '1' }], [200, { items: [], next_page: null }]]);
  const slept = [];
  const api = createClient({ baseUrl: 'https://api.test/v2', fetchImpl, sleep: async (ms) => slept.push(ms) });
  assert.deepEqual(await listOrders(api, { status: 'paid' }), { orders: [], next: null });
  assert.deepEqual(slept, [1000]);
  assert.equal(calls[1].url, 'https://api.test/v2/orders?page=1&status=paid');
  assert.equal(calls[1].headers.authorization, 'Bearer opaque-access-1');
  session.clear();
});

test('API errors carry status and code', async () => {
  const { fetchImpl } = fakeFetch([[422, { error: { code: 'invalid_reason', message: 'reason required' } }]]);
  const api = createClient({ baseUrl: 'https://api.test', fetchImpl, retries: 0 });
  await assert.rejects(cancelOrder(api, { id: 4, status: 'paid' }, ''), (e) => e instanceof ApiError && e.code === 'invalid_reason');
  await assert.rejects(cancelOrder(api, { id: 5, status: 'shipped' }, 'late'), (e) => e.status === 409);
});

test('category listing follows cursors', async () => {
  const { fetchImpl, calls } = fakeFetch([[200, { items: [{ sku: 'a' }, { sku: 'b' }], next_cursor: 'c2' }], [200, { items: [{ sku: 'c' }], next_cursor: null }]]);
  const api = createClient({ baseUrl: '', fetchImpl });
  assert.deepEqual((await allInCategory(api, 'kitchen')).map((p) => p.sku), ['a', 'b', 'c']);
  assert.match(calls[1].url, /cursor=c2/);
  assert.deepEqual(displayPrice({ sku: 'x', stock: 0, price: 1000, sale_price: 800 }), { amount: 800, was: 1000, soldOut: true });
});

test('search query and request', async () => {
  assert.deepEqual(buildQuery('  mug ', { category: 'kitchen"', inStock: true, page: 3 }),
    { q: 'mug', filter: 'category = "kitchen" AND stock > 0', offset: 48, limit: 24 });
  const { fetchImpl, calls } = fakeFetch([[200, { hits: [{ sku: 'KIT-1' }], estimatedTotalHits: 9 }]]);
  assert.deepEqual(await search(fetchImpl, 'mug'), { hits: ['KIT-1'], total: 9 });
  assert.match(calls[0].headers.authorization, /^Bearer /);
});

test('analytics batches by maxBatch', async () => {
  const { fetchImpl, calls } = fakeFetch([[202, {}], [202, {}]]);
  const queue = new EventQueue(fetchImpl, { maxBatch: 3 });
  for (let i = 0; i < 4; i += 1) await queue.push({ name: 'view', at: 1730000000.7 + i });
  assert.equal(await queue.flush(), 1);
  assert.deepEqual(calls.map((c) => JSON.parse(c.body).events.length), [3, 1]);
  assert.equal(queue.sent, 4);
});

test('preview claims decode a JWT payload', () => {
  const payload = Buffer.from(JSON.stringify({ sub: 'preview', exp: 2000000000 })).toString('base64url');
  assert.deepEqual(previewClaims(`e30.${payload}.sig`), { sub: 'preview', exp: 2000000000 });
  assert.equal(previewClaims('not-a-jwt'), null);
});
