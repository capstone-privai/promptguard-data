import en from './en.js';
import ja from './ja.js';
import ko from './ko.js';

const CATALOGUES = { en, ja, ko };

/**
 * @param {string} locale
 * @param {string} key
 * @param {Record<string, string | number>} [params]
 */
export function t(locale, key, params = {}) {
  const catalogue = CATALOGUES[locale] ?? en;
  const template = key.split('.').reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), catalogue);
  if (typeof template !== 'string') return key;
  return template.replace(/\{(\w+)\}/g, (_, name) => (name in params ? String(params[name]) : `{${name}}`));
}

/**
 * English needs one/other; Korean and Japanese use one form.
 * @param {string} locale
 * @param {number} count
 * @param {string} key
 */
export function plural(locale, count, key) {
  const suffix = locale === 'en' && count === 1 ? 'one' : 'other';
  return t(locale, `${key}.${suffix}`, { count });
}
