import { sortBy } from 'lodash-es';
import { formatDate, formatMoney } from '../lib/format';

export interface OrderRow {
  id: string;
  placedAt: string;
  amount: number;
  currency: string;
  status: 'paid' | 'refunded' | 'pending';
}

export function OrderTable({ rows }: { rows: OrderRow[] }) {
  const ordered = sortBy(rows, [(row) => -Date.parse(row.placedAt), 'id']);
  return (
    <table>
      <thead>
        <tr><th>Order</th><th>Placed</th><th>Amount</th><th>Status</th></tr>
      </thead>
      <tbody>
        {ordered.map((row) => (
          <tr key={row.id}>
            <td>{row.id}</td>
            <td>{formatDate(new Date(row.placedAt))}</td>
            <td>{formatMoney(row.amount, row.currency)}</td>
            <td>{row.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
