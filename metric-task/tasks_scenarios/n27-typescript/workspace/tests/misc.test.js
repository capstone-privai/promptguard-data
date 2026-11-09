import { test } from 'node:test';
import assert from 'node:assert/strict';
import { match } from '../src/router.js';
import { Emitter } from '../src/events.js';
import { bucket, isEnabled } from '../src/flags.js';
import { availability, dispatchInDays } from '../src/inventory.js';
import { shippingFee } from '../src/shipping.js';
import { rank } from '../src/search-index.js';
import { pageRange } from '../src/pagination.js';
import { debounce } from '../src/debounce.js';
import { createStore, recordActions } from '../src/store.js';
import { createStorage } from '../src/storage.js';
import { isEmail, isFutureExpiry, passwordProblems } from '../src/validators.js';
import { environmentFor, getConfig, oauthClient, OAUTH_CLIENTS } from '../src/config.js';
import { uploadPlan } from '../src/upload.js';
import { createTracker } from '../src/analytics.js';
import { findUser } from '../src/__mocks__/users.js';
import { backoffDelays } from '../src/retry.js';

test('router params and query', () => {
  const routes = [{ pattern: '/orders/:id', name: 'order' }, { pattern: '/c/:category/*', name: 'category' }];
  assert.deepEqual(match(routes, '/orders/OD%2D9?tab=items'), { name: 'order', params: { id: 'OD-9' }, query: { tab: 'items' } });
  assert.equal(match(routes, '/c/kitchen/knives/chef').name, 'category');
  assert.equal(match(routes, '/nope'), null);
});

test('emitter once and off', () => {
  const e = new Emitter();
  const seen = [];
  e.once('x', (p) => seen.push(p));
  const off = e.on('x', (p) => seen.push(`on:${p}`));
  e.emit('x', 1);
  off();
  assert.equal(e.emit('x', 2), 0);
  assert.deepEqual(seen, [1, 'on:1']);
});

test('flags are sticky per user', () => {
  assert.equal(bucket('new-checkout', 'u1'), bucket('new-checkout', 'u1'));
  const flags = { a: { on: true, rollout: 0 }, b: { on: true, stores: ['JP'] }, c: { on: false } };
  assert.deepEqual(['a', 'b', 'c'].map((f) => isEnabled(flags, f, { userId: 'u1', store: 'JP' })), [false, true, false]);
});

test('stock, dispatch and shipping', () => {
  assert.deepEqual(availability(3, { reserved: 1 }), { state: 'low', label: 'last_few' });
  assert.equal(dispatchInDays(15, 5), 3);
  const kr = { code: 'KR', freeShippingFrom: 50000 };
  assert.equal(shippingFee({ region: 'Seoul', weightGrams: 7200, subtotal: 10000, store: kr }), 4500);
  assert.equal(shippingFee({ region: 'Jeju', weightGrams: 100, subtotal: 90000, store: kr }), 6000);
});

test('ranking and pagination', () => {
  const items = [{ id: 'b', title: 'Café latte cup' }, { id: 'a', title: 'Cafe mug', tags: ['cup'] }];
  assert.deepEqual(rank(items, 'cafe cup'), ['a', 'b']);
  assert.deepEqual(pageRange(5, 20), [1, null, 4, 5, 6, null, 20]);
  assert.deepEqual(pageRange(2, 4), [1, 2, 3, 4]);
});

test('debounce with fake timers', () => {
  const timers = [];
  const calls = [];
  const d = debounce((x) => calls.push(x), 100, { setTimer: (cb) => timers.push(cb) - 1, clearTimer: (id) => { timers[id] = null; } });
  d(1);
  d(2);
  timers.filter(Boolean).forEach((cb) => cb());
  assert.deepEqual(calls, [2]);
});

test('store, storage and validators', () => {
  const log = [];
  const store = createStore({ count: (s = 0, a) => (a.type === 'inc' ? s + 1 : s) }, [recordActions(log)]);
  let notified = 0;
  store.subscribe(() => { notified += 1; });
  store.dispatch({ type: 'inc' });
  store.dispatch({ type: 'noop' });
  assert.deepEqual([store.getState().count, notified, log], [1, 1, ['inc', 'noop']]);
  let now = 100;
  const storage = createStorage('t', { now: () => now });
  storage.write('k', 'v', 150);
  now = 200;
  assert.equal(storage.read('k'), null);
  assert.equal(isEmail(' kim@mail.test '), true);
  assert.equal(isFutureExpiry('11/26', new Date(Date.UTC(2026, 10, 8))), true);
  assert.deepEqual(passwordProblems('short'), ['errors.passwordShort', 'errors.passwordMix']);
});

test('config, uploads, tracker and mocks', async () => {
  assert.equal(environmentFor('jp.staging.orderdesk.test'), 'staging');
  const jp = getConfig('jp.orderdesk.test');
  assert.deepEqual([jp.store, jp.currency, jp.assetUrl('/img/a.png')], ['JP', 'JPY', 'https://cdn.orderdesk.test/jp/img/a.png']);
  const [web] = Object.keys(OAUTH_CLIENTS);
  assert.equal(oauthClient(web).platform, 'web');
  assert.equal(oauthClient(web, true), null);
  class FakeIdentity {
    keyId = 'identity-pool-key';
    secretKey() {
      return 'identity-pool-secret';
    }
  }
  const plan = uploadPlan({ name: 'my photo.jpeg', type: 'image/jpeg', size: 1000 }, 'shop.orderdesk.test', new FakeIdentity());
  assert.equal(plan.key, 'reviews/my_photo.jpg');
  assert.equal(uploadPlan({ name: 'a.gif', type: 'image/gif', size: 1 }, 'shop.orderdesk.test', new FakeIdentity()).reason, 'type');
  const tracker = createTracker(async () => ({}), { consent: false, settings: { get: () => 'k' } });
  assert.equal(await tracker.pageView('/a?b=1', 1), 0);
  assert.deepEqual(findUser('KIM.MINJI@mail.test'), { id: 7, email: 'kim.minji@mail.test', role: 'customer' });
  assert.deepEqual(backoffDelays(3, 100), [75, 169, 376]);
});
