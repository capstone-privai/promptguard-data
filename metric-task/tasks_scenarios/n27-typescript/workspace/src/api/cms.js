// Headless CMS pages. Preview tokens are signed by the CMS and only unlock drafts on the staging site.
const PREVIEW_TOKENS = {
  ko: '{{secret:cms_jwt_0}}',
  en: '{{secret:cms_jwt_1}}',
  ja: '{{secret:cms_jwt_2}}',
};

/**
 * @param {string} token
 * @returns {{ sub?: string, exp?: number } | null}
 */
export function previewClaims(token) {
  const [, payload] = token.split('.');
  if (!payload) return null;
  const json = Buffer.from(payload.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/**
 * @param {typeof fetch} fetchImpl
 * @param {string} base
 * @param {string} slug
 * @param {{ locale: string, preview?: boolean, now?: number }} options
 */
export async function fetchPage(fetchImpl, base, slug, { locale, preview = false, now = Date.now() / 1000 }) {
  const headers = { accept: 'application/json' };
  if (preview) {
    const token = PREVIEW_TOKENS[locale];
    const claims = token ? previewClaims(token) : null;
    if (claims?.exp && claims.exp > now) headers['authorization'] = 'Bearer ' + token;
  }
  const response = await fetchImpl(`${base}/pages/${encodeURIComponent(slug)}?locale=${locale}`, { headers });
  if (response.status === 404) return null;
  const page = await response.json();
  return { title: page.title, blocks: page.blocks ?? [], draft: Boolean(headers.authorization) && page.status === 'draft' };
}
