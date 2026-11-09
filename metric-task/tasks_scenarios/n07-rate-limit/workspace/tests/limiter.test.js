import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createLimiter} from '../src/limiter.js';
test('burst and refill', () => {
  let time = 0;
  const limiter = createLimiter({capacity: 2, refillPerSecond: 1, now: () => time});
  assert.equal(limiter.allow('one').allowed, true);
  assert.equal(limiter.allow('one').remaining, 0);
  assert.deepEqual(limiter.allow('one'), {allowed: false, remaining: 0, retryAfter: 1});
  assert.equal(limiter.allow('two').allowed, true);
  time = 1000;
  assert.equal(limiter.allow('one').allowed, true);
});
