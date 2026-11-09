// Stock badges on product pages. Warehouses report stock every few minutes, so low counts are shown as ranges.
/**
 * @param {number} stock
 * @param {{ reserved?: number, lowThreshold?: number }} [options]
 */
export function availability(stock, options = {}) {
  const available = Math.max(0, stock - (options.reserved ?? 0));
  if (available === 0) return { state: 'sold_out', label: null };
  if (available <= (options.lowThreshold ?? 5)) return { state: 'low', label: available <= 2 ? 'last_few' : 'few_left' };
  return { state: 'in_stock', label: null };
}

/**
 * Earliest dispatch day given the warehouse cut-off hour (local time).
 * @param {number} localHour
 * @param {number} weekday 0 = Sunday
 * @param {number} [cutoffHour]
 */
export function dispatchInDays(localHour, weekday, cutoffHour = 14) {
  let days = localHour < cutoffHour ? 0 : 1;
  let day = (weekday + days) % 7;
  while (day === 0 || day === 6) {
    days += 1;
    day = (day + 1) % 7;
  }
  return days;
}
