// Shopping cart: lines keyed by SKU, quantity limits and merging the guest cart into the account cart.
import { priceLines } from './pricing.js';

export const MAX_QUANTITY = 20;

/** @typedef {{ sku: string, quantity: number, unitPrice: number, title: string }} CartLine */

/** @returns {{ lines: CartLine[], coupon: string | null }} */
export function emptyCart() {
  return { lines: [], coupon: null };
}

/**
 * @param {{ lines: CartLine[], coupon: string | null }} cart
 * @param {{ sku: string, unitPrice: number, title: string }} product
 * @param {number} [quantity]
 */
export function addItem(cart, product, quantity = 1) {
  if (!Number.isInteger(quantity) || quantity < 1) throw new RangeError('quantity must be a positive integer');
  const existing = cart.lines.find((line) => line.sku === product.sku);
  const lines = existing
    ? cart.lines.map((line) => (line.sku === product.sku ? { ...line, quantity: Math.min(MAX_QUANTITY, line.quantity + quantity) } : line))
    : [...cart.lines, { sku: product.sku, title: product.title, unitPrice: product.unitPrice, quantity: Math.min(MAX_QUANTITY, quantity) }];
  return { ...cart, lines };
}

/**
 * @param {{ lines: CartLine[], coupon: string | null }} cart
 * @param {string} sku
 * @param {number} quantity
 */
export function setQuantity(cart, sku, quantity) {
  if (quantity <= 0) return { ...cart, lines: cart.lines.filter((line) => line.sku !== sku) };
  return { ...cart, lines: cart.lines.map((line) => (line.sku === sku ? { ...line, quantity: Math.min(MAX_QUANTITY, quantity) } : line)) };
}

/**
 * Guest lines are added to the account cart; the account keeps its coupon unless it has none.
 * @param {{ lines: CartLine[], coupon: string | null }} account
 * @param {{ lines: CartLine[], coupon: string | null }} guest
 */
export function mergeCarts(account, guest) {
  let merged = { ...account, coupon: account.coupon ?? guest.coupon };
  for (const line of guest.lines) merged = addItem(merged, line, line.quantity);
  return merged;
}

/**
 * @param {{ lines: CartLine[], coupon: string | null }} cart
 * @param {{ currency: string, vatRate: number }} store
 * @param {Record<string, { percent?: number, amount?: number, minimum?: number }>} coupons
 */
export function cartTotals(cart, store, coupons) {
  const coupon = cart.coupon ? coupons[cart.coupon] ?? null : null;
  return priceLines(cart.lines, { currency: store.currency, vatRate: store.vatRate, coupon });
}

/** @param {{ lines: CartLine[] }} cart */
export function itemCount(cart) {
  return cart.lines.reduce((n, line) => n + line.quantity, 0);
}
