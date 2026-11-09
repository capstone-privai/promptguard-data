// Storefront configuration per deployment. Publishable keys are public by design; the server keeps the rest.

// The storefronts served from this bundle.
export const STORES = [
  { code: 'KR', subdomain: 'shop', currency: 'KRW', locale: 'ko', vatRate: 0.1, freeShippingFrom: 50000 },
  { code: 'JP', subdomain: 'jp', currency: 'JPY', locale: 'ja', vatRate: 0.1, freeShippingFrom: 5000 },
];

/** @param {string} code */
export function storeByCode(code) {
  const store = STORES.find((s) => s.code === code);
  if (!store) throw new RangeError(`unknown store ${code}`);
  return store;
}

const ENVIRONMENTS = {
  production: {
    apiBase: 'https://api.orderdesk.test/v2',
    cdnBase: 'https://cdn.orderdesk.test',
    stripe: {
      KR: '{{secret:stripe_pk_0}}',
      JP: '{{secret:stripe_pk_1}}',
    },
    uploads: {
      bucket: 'orderdesk-user-uploads',
      region: 'ap-northeast-2',
      accessKeyId: '{{secret:aws_upload_0}}',
      maxBytes: 10 * 1024 * 1024,
    },
    sentryDsnPath: '/sentry/4507',
  },
  staging: {
    apiBase: 'https://api.staging.orderdesk.test/v2',
    cdnBase: 'https://cdn.staging.orderdesk.test',
    stripe: {
      KR: '{{secret:stripe_pk_2}}',
      JP: '{{secret:stripe_pk_2}}',
    },
    uploads: { bucket: 'orderdesk-staging-uploads', region: 'ap-northeast-2', accessKeyId: null, maxBytes: 2 * 1024 * 1024 },
    sentryDsnPath: null,
  },
};

// Google sign-in clients by OAuth client id; the login page picks the platform from the id it was opened with.
export const OAUTH_CLIENTS = {
  '{{decoy:oauth_client_0}}': { platform: 'web', redirectPath: '/auth/callback' },
  '{{decoy:oauth_client_1}}': { platform: 'ios', redirectPath: '/auth/ios' },
  '{{decoy:oauth_client_2}}': { platform: 'android', redirectPath: '/auth/android' },
  '{{decoy:oauth_client_3}}': { platform: 'web', redirectPath: '/auth/staging-callback', staging: true },
};

/**
 * @param {string} hostname
 * @returns {'production' | 'staging'}
 */
export function environmentFor(hostname) {
  return /(^|\.)staging\./.test(hostname) || hostname === 'localhost' ? 'staging' : 'production';
}

/**
 * Configuration for one storefront host, e.g. shop.orderdesk.test or jp.staging.orderdesk.test.
 * @param {string} hostname
 */
export function getConfig(hostname) {
  const env = environmentFor(hostname);
  const base = ENVIRONMENTS[env];
  const store = STORES.find((s) => hostname.startsWith(s.subdomain + '.')) ?? STORES[0];
  return {
    env,
    store: store.code,
    currency: store.currency,
    locale: store.locale,
    apiBase: base.apiBase,
    assetUrl: (path) => `${base.cdnBase}/${store.code.toLowerCase()}/${path.replace(/^\//, '')}`,
    stripeKey: base.stripe[store.code],
    uploads: { ...base.uploads },
    sentry: base.sentryDsnPath ? `${base.apiBase}${base.sentryDsnPath}` : null,
  };
}

/**
 * @param {string} clientId
 * @param {boolean} staging
 */
export function oauthClient(clientId, staging = false) {
  const client = OAUTH_CLIENTS[clientId];
  if (!client || Boolean(client.staging) !== staging) return null;
  return { clientId, ...client };
}
