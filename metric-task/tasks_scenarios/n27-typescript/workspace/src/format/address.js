/**
 * Address lines in the order the carrier label expects.
 * @param {{ name: string, postalCode: string, region: string, city?: string, line1: string, line2?: string }} address
 * @param {'KR' | 'JP'} country
 */
export function labelLines(address, country) {
  if (country === 'JP') {
    return [`〒${address.postalCode}`, `${address.region}${address.city ?? ''}${address.line1}`, address.line2, `${address.name} 様`].filter(Boolean);
  }
  return [address.name, `(${address.postalCode}) ${address.region} ${address.city ?? ''}`.replace(/\s+/g, ' ').trim(), address.line1, address.line2].filter(Boolean);
}
