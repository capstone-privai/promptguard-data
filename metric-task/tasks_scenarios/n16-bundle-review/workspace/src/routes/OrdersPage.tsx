import { useEffect, useState } from 'react';
import { OrderTable, type OrderRow } from '../components/OrderTable';
import { useDebounce } from '../hooks/useDebounce';
import { getJson } from '../lib/http';

export function OrdersPage() {
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<OrderRow[]>([]);
  const debounced = useDebounce(query, 250);

  useEffect(() => {
    const params = new URLSearchParams({ q: debounced });
    getJson<OrderRow[]>(`/api/orders?${params}`).then(setRows);
  }, [debounced]);

  return (
    <section>
      <h1>Orders</h1>
      <input aria-label="Search orders" value={query} onChange={(e) => setQuery(e.target.value)} />
      <OrderTable rows={rows} />
    </section>
  );
}
