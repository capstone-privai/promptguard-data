// Client-side filter for the order history page: tokenised, accent-insensitive, ranked.
/** @param {string} text */
export function tokens(text) {
  return text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

/**
 * @param {{ id: string, title: string, tags?: string[] }[]} items
 * @param {string} query
 */
export function rank(items, query) {
  const wanted = tokens(query);
  if (!wanted.length) return items.map((item) => item.id);
  return items
    .map((item) => {
      const words = tokens([item.title, ...(item.tags ?? [])].join(' '));
      const score = wanted.reduce((s, w) => s + (words.includes(w) ? 3 : words.some((x) => x.startsWith(w)) ? 1 : 0), 0);
      return { id: item.id, score };
    })
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
    .map((r) => r.id);
}
