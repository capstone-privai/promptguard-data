import { useEffect, useState } from 'react';
import { PriceTag } from '../components/PriceTag';
import { Spinner } from '../components/Spinner';
import { regionOf, stripeFor } from '../config/payments';
import { postJson } from '../lib/http';

interface Quote {
  amount: number;
  currency: string;
  expiresAt: string;
}

export function CheckoutPage() {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    postJson<Quote>('/api/checkout/quote', { cart: 'current' })
      .then(setQuote)
      .catch((err: Error) => setError(err.message));
  }, []);

  async function pay() {
    if (!quote) return;
    const stripe = stripeFor(regionOf(quote.currency));
    const session = await postJson<{ id: string }>('/api/checkout/session', { quote });
    const checkout = await stripe.checkout.sessions.retrieve(session.id);
    if (checkout.url) window.location.assign(checkout.url);
  }

  if (error) return <p role="alert">{error}</p>;
  if (!quote) return <Spinner label="Preparing your quote" />;
  return (
    <section>
      <h1>Checkout</h1>
      <PriceTag amount={quote.amount} currency={quote.currency} />
      <button type="button" onClick={pay}>Pay now</button>
    </section>
  );
}
