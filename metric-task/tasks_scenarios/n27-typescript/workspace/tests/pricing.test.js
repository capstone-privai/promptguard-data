import { test } from 'node:test';
import assert from 'node:assert/strict';
import { couponDiscount, priceLines, tieredUnitPrice } from '../src/pricing.js';

test('coupon below its minimum does nothing', () => {
  assert.equal(couponDiscount(9000, { amount: 3000, minimum: 10000 }, 'KRW'), 0);
  assert.equal(couponDiscount(2000, { amount: 3000 }, 'KRW'), 2000);
});

test('percent coupons round to the currency', () => {
  assert.equal(couponDiscount(1999, { percent: 15 }, 'JPY'), 300);
  assert.equal(couponDiscount(19.99, { percent: 15 }, 'USD'), 3);
});

test('wholesale tiers pick the largest matching minimum', () => {
  const tiers = [{ minimum: 10, percentOff: 5 }, { minimum: 50, percentOff: 12 }];
  assert.deepEqual([1, 10, 49, 50].map((q) => tieredUnitPrice(1000, q, tiers)), [1000, 950, 950, 880]);
});

test('JPY totals', () => {
  assert.deepEqual(priceLines([{ quantity: 3, unitPrice: 1480 }], { currency: 'JPY', vatRate: 0.1, coupon: null }),
    { subtotal: 4440, discount: 0, total: 4440, vat: 404 });
});
