import * as locales from 'date-fns/locale';
import type { Locale } from 'date-fns';

const table = locales as Record<string, Locale>;

// Accept whatever tag the browser reports (ja-JP -> ja, de-AT -> de) instead of a fixed list.
export function getLocale(tag: string): Locale {
  return table[tag.replace('-', '')] ?? table[tag.split('-')[0]] ?? locales.enUS;
}

export const supportedLocaleTags = Object.keys(table);
