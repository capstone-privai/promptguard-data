import { formatMoney } from '../lib/format';

export function PriceTag({ amount, currency }: { amount: number; currency: string }) {
  return <strong className="price">{formatMoney(amount, currency)}</strong>;
}
