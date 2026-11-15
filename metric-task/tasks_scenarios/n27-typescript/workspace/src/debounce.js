/**
 * Debounce with an injectable timer so tests need no real clock.
 * @param {(...args: any[]) => void} fn
 * @param {number} waitMs
 * @param {{ setTimer?: (cb: () => void, ms: number) => unknown, clearTimer?: (id: unknown) => void }} [timers]
 */
export function debounce(fn, waitMs, timers = {}) {
  const setTimer = timers.setTimer ?? setTimeout;
  const clearTimer = timers.clearTimer ?? clearTimeout;
  let id = null;
  const debounced = (...args) => {
    if (id !== null) clearTimer(id);
    id = setTimer(() => {
      id = null;
      fn(...args);
    }, waitMs);
  };
  debounced.cancel = () => {
    if (id !== null) clearTimer(id);
    id = null;
  };
  return debounced;
}
