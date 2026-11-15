/**
 * Page numbers to show around the current page, with null for an ellipsis: [1, null, 4, 5, 6, null, 20].
 * @param {number} current
 * @param {number} total
 * @param {number} [around]
 * @returns {(number | null)[]}
 */
export function pageRange(current, total, around = 1) {
  if (total <= 0) return [];
  const pages = new Set([1, total]);
  for (let p = current - around; p <= current + around; p += 1) if (p >= 1 && p <= total) pages.add(p);
  const sorted = [...pages].sort((a, b) => a - b);
  const out = [];
  for (const [i, p] of sorted.entries()) {
    if (i && p - sorted[i - 1] > 1) out.push(p - sorted[i - 1] === 2 ? p - 1 : null);
    out.push(p);
  }
  return out;
}
