// Prices are tax-inclusive. Discounts apply to the subtotal; VAT is reported as the included share.
import { roundMoney } from './format/money.js';

/**
 * @param {{ quantity: number, unitPrice: number }[]} lines
 * @param {{ currency: string, vatRate: number, coupon: { percent?: number, amount?: number, minimum?: number } | null }} options
 */
export function priceLines(lines, { currency, vatRate, coupon }) {
  const subtotal = lines.reduce((sum, line) => sum + line.quantity * line.unitPrice, 0);
  const discount = couponDiscount(subtotal, coupon, currency);
  const total = Math.max(0, subtotal - discount);
  const vat = roundMoney(total - total / (1 + vatRate), currency);
  return { subtotal, discount, total, vat };
}

/**
 * @param {number} subtotal
 * @param {{ percent?: number, amount?: number, minimum?: number } | null} coupon
 * @param {string} currency
 */
export function couponDiscount(subtotal, coupon, currency) {
  if (!coupon || subtotal < (coupon.minimum ?? 0)) return 0;
  if (coupon.percent) return Math.min(subtotal, roundMoney((subtotal * coupon.percent) / 100, currency));
  return Math.min(subtotal, coupon.amount ?? 0);
}

/**
 * Tiered price for wholesale accounts: the tier with the largest minimum not above the quantity.
 * @param {number} unitPrice
 * @param {number} quantity
 * @param {{ minimum: number, percentOff: number }[]} tiers
 */
export function tieredUnitPrice(unitPrice, quantity, tiers) {
  const tier = [...tiers].sort((a, b) => b.minimum - a.minimum).find((t) => quantity >= t.minimum);
  return tier ? Math.round(unitPrice * (1 - tier.percentOff / 100)) : unitPrice;
}
