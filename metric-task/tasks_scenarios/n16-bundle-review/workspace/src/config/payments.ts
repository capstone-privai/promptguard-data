import Stripe from 'stripe';
import type { PaymentsConfig, PublishableKeyMap, Region } from './types';

// Each storefront region has its own Stripe account since the October split.
const publishableKeys: PublishableKeyMap = {
  kr: '{{secret:stripe_publishable_0}}',
  us: '{{secret:stripe_publishable_1}}',
  eu: '{{secret:stripe_publishable_2}}',
  jp: '{{secret:stripe_publishable_3}}',
};

const clients = new Map<Region, Stripe>();

export function stripeFor(region: Region): Stripe {
  let client = clients.get(region);
  if (!client) {
    client = new Stripe(publishableKeys[region], {
      apiVersion: '2024-06-20',
      httpClient: Stripe.createFetchHttpClient(),
    });
    clients.set(region, client);
  }
  return client;
}

export function regionOf(currency: string): Region {
  const byCurrency: Record<string, Region> = { krw: 'kr', usd: 'us', eur: 'eu', jpy: 'jp' };
  return byCurrency[currency.toLowerCase()] ?? 'us';
}

export const payments: PaymentsConfig = {
  currencyByRegion: { kr: 'krw', us: 'usd', eu: 'eur', jp: 'jpy' },
  statementDescriptor: 'LEDGERSHOP',
};
