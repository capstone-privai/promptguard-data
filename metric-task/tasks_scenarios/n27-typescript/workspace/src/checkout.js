// Checkout steps: address -> shipping -> payment -> review. Each step validates before the next opens.
import { validateAddress } from './validators.js';
import { shippingFee } from './shipping.js';

export const STEPS = ['address', 'shipping', 'payment', 'review'];

/** @param {{ total: number, currency: string }} totals */
export function startCheckout(totals) {
  return { step: 'address', totals, address: null, shipping: null, payment: null, errors: {} };
}

/**
 * @param {ReturnType<typeof startCheckout>} state
 * @param {{ type: string, value?: any }} action
 * @param {{ code: string, freeShippingFrom: number }} store
 */
export function advance(state, action, store) {
  switch (action.type) {
    case 'address': {
      const errors = validateAddress(action.value, store.code);
      if (Object.keys(errors).length) return { ...state, errors };
      return { ...state, address: action.value, errors: {}, step: 'shipping' };
    }
    case 'shipping': {
      if (state.step !== 'shipping') return { ...state, errors: { step: 'address first' } };
      const fee = shippingFee({ region: state.address.region, weightGrams: action.value.weightGrams, express: action.value.express, subtotal: state.totals.total, store });
      return { ...state, shipping: { ...action.value, fee }, errors: {}, step: 'payment' };
    }
    case 'payment': {
      if (state.step !== 'payment') return { ...state, errors: { step: 'shipping first' } };
      if (!['card', 'bank_transfer', 'konbini'].includes(action.value.method)) return { ...state, errors: { method: 'unsupported' } };
      if (action.value.method === 'konbini' && store.code !== 'JP') return { ...state, errors: { method: 'JP only' } };
      return { ...state, payment: action.value, errors: {}, step: 'review' };
    }
    case 'back': {
      const index = Math.max(0, STEPS.indexOf(state.step) - 1);
      return { ...state, step: STEPS[index], errors: {} };
    }
    default:
      return state;
  }
}

/** @param {ReturnType<typeof startCheckout>} state */
export function amountDue(state) {
  return state.totals.total + (state.shipping?.fee ?? 0);
}
