const MINOR_UNITS = { KRW: 0, JPY: 0, USD: 2 };

/** @param {number} amount @param {string} currency */
export function roundMoney(amount, currency) {
  const factor = 10 ** (MINOR_UNITS[currency] ?? 2);
  return Math.round(amount * factor) / factor;
}

/**
 * @param {number} amount
 * @param {string} currency
 * @param {string} locale
 */
export function formatMoney(amount, currency, locale) {
  const digits = MINOR_UNITS[currency] ?? 2;
  const fixed = roundMoney(Math.abs(amount), currency).toFixed(digits);
  const [whole, fraction] = fixed.split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const number = fraction ? `${grouped}.${fraction}` : grouped;
  const sign = amount < 0 ? '-' : '';
  if (currency === 'KRW') return locale === 'ko' ? `${sign}${number}원` : `${sign}₩${number}`;
  if (currency === 'JPY') return locale === 'ja' ? `${sign}${number}円` : `${sign}¥${number}`;
  return `${sign}$${number}`;
}
