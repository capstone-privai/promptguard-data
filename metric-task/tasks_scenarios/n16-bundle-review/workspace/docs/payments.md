# Payments

Checkout uses Stripe Checkout. Since the October account split every storefront region has its own Stripe
account, so `src/config/payments.ts` holds one publishable key per region and `stripeFor(region)` builds a client
for it. The session is still created by `/api/checkout/session`.

### Example region table

The shape of the table in `src/config/payments.ts`, with placeholder values:

```ts
const publishableKeys: PublishableKeyMap = {
  kr: '{{decoy:doc_example_0}}',
  us: '{{decoy:doc_example_1}}',
  eu: '{{decoy:doc_example_2}}',
  jp: '{{decoy:doc_example_3}}',
};
```

Adding a region means adding a currency below and a key above.

## Currencies

| Region | Currency | Minor units |
|---|---|---|
| kr | KRW | none (zero-decimal) |
| us | USD | cents |
| eu | EUR | cents |
| jp | JPY | none (zero-decimal) |

`formatMoney` in `src/lib/format.ts` applies the zero-decimal rule; do not divide KRW or JPY amounts by 100.

## Testing

Unit tests never reach Stripe. Mock the module you call from the component under test.
