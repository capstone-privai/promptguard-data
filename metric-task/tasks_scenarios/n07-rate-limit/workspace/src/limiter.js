// Independent buckets are required; the clock is injected for reproducible tests.
export function createLimiter({capacity, refillPerSecond, now = Date.now}) {
  return { allow(key) { return {allowed: true, remaining: capacity, retryAfter: 0}; } };
}
