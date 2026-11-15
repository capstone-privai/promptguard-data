/**
 * @param {{ get: Function }} api
 * @param {string} category
 * @param {number} [limit]
 */
export async function allInCategory(api, category, limit = 200) {
  const products = [];
  let cursor = null;
  do {
    const page = await api.get('/products', { query: { category, cursor, limit: Math.min(limit - products.length, 50) } });
    products.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && products.length < limit);
  return products.slice(0, limit);
}

/** @param {{ sku: string, stock: number, price: number, sale_price?: number | null }} product */
export function displayPrice(product) {
  const onSale = product.sale_price != null && product.sale_price < product.price;
  return { amount: onSale ? product.sale_price : product.price, was: onSale ? product.price : null, soldOut: product.stock <= 0 };
}
