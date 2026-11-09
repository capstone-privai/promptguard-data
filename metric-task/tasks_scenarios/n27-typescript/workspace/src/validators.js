// Form validation for the storefront. Messages are i18n keys.
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PHONES = { KR: /^01[016789]-?\d{3,4}-?\d{4}$/, JP: /^0[789]0-?\d{4}-?\d{4}$/ };
const POSTAL = { KR: /^\d{5}$/, JP: /^\d{3}-?\d{4}$/ };

/** @param {string} value */
export function isEmail(value) {
  return EMAIL.test(value.trim());
}

/** @param {string} value @param {'KR' | 'JP'} country */
export function isPhone(value, country) {
  return PHONES[country]?.test(value.replace(/\s/g, '')) ?? false;
}

/**
 * Card expiry as MM/YY; valid through the end of that month.
 * @param {string} value
 * @param {Date} now
 */
export function isFutureExpiry(value, now) {
  const match = /^(0[1-9]|1[0-2])\/(\d{2})$/.exec(value.trim());
  if (!match) return false;
  const end = new Date(Date.UTC(2000 + Number(match[2]), Number(match[1]), 1));
  return end.getTime() > now.getTime();
}

/**
 * @param {{ name?: string, phone?: string, postalCode?: string, line1?: string, region?: string }} address
 * @param {'KR' | 'JP'} country
 * @returns {Record<string, string>}
 */
export function validateAddress(address, country) {
  const errors = {};
  if (!address?.name?.trim()) errors.name = 'errors.required';
  if (!address?.line1?.trim()) errors.line1 = 'errors.required';
  if (!address?.region) errors.region = 'errors.required';
  if (!POSTAL[country].test(address?.postalCode ?? '')) errors.postalCode = 'errors.postal';
  if (!isPhone(address?.phone ?? '', country)) errors.phone = 'errors.phone';
  return errors;
}

/**
 * @param {string} value
 * @param {{ minLength?: number }} [rules]
 */
export function passwordProblems(value, rules = {}) {
  const problems = [];
  if (value.length < (rules.minLength ?? 10)) problems.push('errors.passwordShort');
  if (!/\d/.test(value) || !/[A-Za-z]/.test(value)) problems.push('errors.passwordMix');
  return problems;
}
