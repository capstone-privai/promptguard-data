import { test } from 'node:test';
import assert from 'node:assert/strict';
import { advance, amountDue, startCheckout } from '../src/checkout.js';
import { storeByCode } from '../src/config.js';

const address = { name: 'Kim Minji', phone: '010-2345-6789', postalCode: '06236', line1: 'Teheran-ro 152', region: 'Seoul' };

test('steps open in order and the fee is added', () => {
  const kr = storeByCode('KR');
  let state = startCheckout({ total: 42000, currency: 'KRW' });
  state = advance(state, { type: 'payment', value: { method: 'card' } }, kr);
  assert.equal(state.errors.step, 'shipping first');
  state = advance(state, { type: 'address', value: address }, kr);
  state = advance(state, { type: 'shipping', value: { weightGrams: 1200, express: false } }, kr);
  assert.equal(state.shipping.fee, 3000);
  state = advance(state, { type: 'payment', value: { method: 'card' } }, kr);
  assert.equal(state.step, 'review');
  assert.equal(amountDue(state), 45000);
});

test('invalid address and JP-only methods are rejected', () => {
  const kr = storeByCode('KR');
  const state = advance(startCheckout({ total: 1000, currency: 'KRW' }), { type: 'address', value: { ...address, postalCode: '1234' } }, kr);
  assert.deepEqual(state.errors, { postalCode: 'errors.postal' });
  let jp = advance(startCheckout({ total: 1000, currency: 'KRW' }), { type: 'address', value: address }, kr);
  jp = advance(jp, { type: 'shipping', value: { weightGrams: 100 } }, kr);
  assert.equal(advance(jp, { type: 'payment', value: { method: 'konbini' } }, kr).errors.method, 'JP only');
  assert.equal(advance(jp, { type: 'back' }, kr).step, 'shipping');
});
