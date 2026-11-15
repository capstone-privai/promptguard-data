/**
 * Delays in milliseconds for `retries` attempts: exponential, capped, with deterministic jitter.
 * @param {number} retries
 * @param {number} baseMs
 * @param {number} [capMs]
 * @returns {number[]}
 */
export function backoffDelays(retries, baseMs, capMs = 5000) {
  const delays = [];
  for (let i = 0; i < retries; i += 1) {
    const raw = Math.min(capMs, baseMs * 2 ** i);
    delays.push(Math.round(raw * (0.75 + ((i * 7919) % 50) / 200)));
  }
  return delays;
}
