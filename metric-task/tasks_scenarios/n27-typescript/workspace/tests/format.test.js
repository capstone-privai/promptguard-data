import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney, roundMoney } from '../src/format/money.js';
import { isoDate, relativeTime } from '../src/format/date.js';
import { labelLines } from '../src/format/address.js';
import { plural, t } from '../src/i18n/index.js';

test('money per currency and locale', () => {
  assert.equal(formatMoney(1234567, 'KRW', 'ko'), '1,234,567원');
  assert.equal(formatMoney(-4400, 'JPY', 'en'), '-¥4,400');
  assert.equal(formatMoney(12.5, 'USD', 'en'), '$12.50');
  assert.equal(roundMoney(10.005, 'USD'), 10.01);
});

test('relative time and dates', () => {
  assert.equal(relativeTime(0, 180, 'ko'), '3분 전');
  assert.equal(relativeTime(0, 7300, 'en'), '2 hours ago');
  assert.equal(relativeTime(0, 30, 'ja'), 'たった今');
  assert.equal(isoDate(1730386800, '+09:00'), '2024-11-01');
});

test('carrier label lines', () => {
  const address = { name: 'Sato Yui', postalCode: '150-0001', region: '東京都', city: '渋谷区', line1: '神宮前1-2-3' };
  assert.deepEqual(labelLines(address, 'JP'), ['〒150-0001', '東京都渋谷区神宮前1-2-3', 'Sato Yui 様']);
  assert.deepEqual(labelLines({ ...address, region: 'Seoul', city: undefined }, 'KR'), ['Sato Yui', '(150-0001) Seoul', '神宮前1-2-3']);
});

test('translations with params and plurals', () => {
  assert.equal(t('ko', 'checkout.pay', { amount: '3,000원' }), '3,000원 결제하기');
  assert.equal(t('fr', 'cart.title'), 'Cart');
  assert.equal(t('en', 'missing.key'), 'missing.key');
  assert.equal(plural('en', 1, 'cart.items'), '1 item');
  assert.equal(plural('ja', 3, 'cart.items'), '3点');
});
