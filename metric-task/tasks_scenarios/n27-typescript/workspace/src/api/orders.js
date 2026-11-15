import { ApiError } from './client.js';

const CANCELLABLE = new Set(['pending', 'paid']);

/**
 * @param {{ get: Function, post: Function }} api
 * @param {{ page?: number, status?: string }} [filters]
 */
export async function listOrders(api, filters = {}) {
  const data = await api.get('/orders', { query: { page: filters.page ?? 1, status: filters.status } });
  return { orders: data.items.map(summarise), next: data.next_page ?? null };
}

/** @param {{ id: number, number: string, status: string, items: { quantity: number, unit_price: number }[] }} order */
export function summarise(order) {
  return {
    id: order.id,
    number: order.number,
    status: order.status,
    units: order.items.reduce((n, item) => n + item.quantity, 0),
    total: order.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0),
    cancellable: CANCELLABLE.has(order.status),
  };
}

/**
 * @param {{ post: Function }} api
 * @param {{ id: number, status: string }} order
 * @param {string} reason
 */
export async function cancelOrder(api, order, reason) {
  if (!CANCELLABLE.has(order.status)) {
    throw new ApiError(409, 'not_cancellable', `order ${order.id} is ${order.status}`);
  }
  return api.post(`/orders/${order.id}/cancel`, { reason });
}
