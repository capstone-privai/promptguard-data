// Shipping fees. Islands and remote areas pay a surcharge; free shipping above the store threshold.
const REMOTE = { KR: ['jeju', 'ulleung'], JP: ['okinawa', 'hokkaido'] };
const BASE = { KR: 3000, JP: 600 };
const EXPRESS = { KR: 4000, JP: 900 };

/**
 * @param {{ region: string, weightGrams: number, express?: boolean, subtotal: number, store: { code: string, freeShippingFrom: number } }} order
 * @returns {number}
 */
export function shippingFee({ region, weightGrams, express = false, subtotal, store }) {
  const remote = REMOTE[store.code].includes(region.toLowerCase());
  const heavy = Math.max(0, Math.ceil((weightGrams - 5000) / 1000));
  if (subtotal >= store.freeShippingFrom && !remote && !express) return 0;
  let fee = express ? EXPRESS[store.code] : BASE[store.code];
  fee += heavy * (store.code === 'KR' ? 500 : 50);
  if (remote) fee += store.code === 'KR' ? 3000 : 800;
  return fee;
}
