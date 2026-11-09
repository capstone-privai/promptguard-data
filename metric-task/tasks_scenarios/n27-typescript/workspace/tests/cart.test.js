import { test } from 'node:test';
import assert from 'node:assert/strict';
import { addItem, cartTotals, emptyCart, itemCount, mergeCarts, setQuantity, MAX_QUANTITY } from '../src/cart.js';
import { storeByCode } from '../src/config.js';

const mug = { sku: 'KIT-2001', title: 'Stoneware mug', unitPrice: 12900 };
const towel = { sku: 'BAT-3302', title: 'Cotton towel', unitPrice: 8900 };

test('adding the same SKU raises the quantity up to the limit', () => {
  let cart = addItem(emptyCart(), mug, 3);
  cart = addItem(cart, mug, 30);
  assert.equal(cart.lines.length, 1);
  assert.equal(cart.lines[0].quantity, MAX_QUANTITY);
  assert.throws(() => addItem(cart, mug, 0), RangeError);
});

test('setting quantity to zero removes the line', () => {
  const cart = setQuantity(addItem(addItem(emptyCart(), mug), towel, 2), mug.sku, 0);
  assert.deepEqual(cart.lines.map((l) => l.sku), [towel.sku]);
  assert.equal(itemCount(cart), 2);
});

test('guest cart merges into the account cart', () => {
  const account = { ...addItem(emptyCart(), mug, 1), coupon: null };
  const guest = { ...addItem(addItem(emptyCart(), mug, 2), towel), coupon: 'WELCOME10' };
  const merged = mergeCarts(account, guest);
  assert.deepEqual(merged.lines.map((l) => [l.sku, l.quantity]), [[mug.sku, 3], [towel.sku, 1]]);
  assert.equal(merged.coupon, 'WELCOME10');
});

test('totals include the VAT share and the coupon', () => {
  const cart = { ...addItem(addItem(emptyCart(), mug, 2), towel), coupon: 'WELCOME10' };
  const totals = cartTotals(cart, storeByCode('KR'), { WELCOME10: { percent: 10, minimum: 30000 } });
  assert.deepEqual(totals, { subtotal: 34700, discount: 3470, total: 31230, vat: 2839 });
});
