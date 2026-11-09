// Product search through the hosted search engine (read-only search token).
const SEARCH_HOST = 'https://search.orderdesk.test';
const SEARCH_TOKEN = '{{secret:service_token_0}}';

/**
 * @param {string} text
 * @param {{ category?: string, inStock?: boolean, page?: number }} [filters]
 */
export function buildQuery(text, filters = {}) {
  const clauses = [];
  if (filters.category) clauses.push(`category = "${filters.category.replace(/"/g, '')}"`);
  if (filters.inStock) clauses.push('stock > 0');
  return { q: text.trim().slice(0, 120), filter: clauses.join(' AND ') || undefined, offset: ((filters.page ?? 1) - 1) * 24, limit: 24 };
}

/**
 * @param {typeof fetch} fetchImpl
 * @param {string} text
 * @param {object} [filters]
 */
export async function search(fetchImpl, text, filters = {}) {
  const headers = { 'content-type': 'application/json' };
  headers['authorization'] = 'Bearer ' + SEARCH_TOKEN;
  const response = await fetchImpl(`${SEARCH_HOST}/indexes/products/search`, {
    method: 'POST',
    headers,
    body: JSON.stringify(buildQuery(text, filters)),
  });
  const data = await response.json();
  return { hits: data.hits.map((h) => h.sku), total: data.estimatedTotalHits ?? data.hits.length };
}
