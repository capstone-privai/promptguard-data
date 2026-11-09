import { format } from 'date-fns';
import { getLocale } from '../config/i18n';

export function formatDate(date: Date, localeTag = navigator.language): string {
  return format(date, 'PP', { locale: getLocale(localeTag) });
}

export function formatMoney(minorUnits: number, currency: string): string {
  const zeroDecimal = ['krw', 'jpy'].includes(currency.toLowerCase());
  const amount = zeroDecimal ? minorUnits : minorUnits / 100;
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount);
}
