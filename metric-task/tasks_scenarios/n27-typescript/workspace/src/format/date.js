/**
 * "3분 전", "2 hours ago": relative time for order timelines.
 * @param {number} thenSeconds
 * @param {number} nowSeconds
 * @param {'ko' | 'en' | 'ja'} locale
 */
export function relativeTime(thenSeconds, nowSeconds, locale) {
  const diff = Math.max(0, Math.floor(nowSeconds - thenSeconds));
  const units = [['day', 86400], ['hour', 3600], ['minute', 60]];
  const words = {
    ko: { day: '일', hour: '시간', minute: '분', ago: ' 전', now: '방금' },
    ja: { day: '日', hour: '時間', minute: '分', ago: '前', now: 'たった今' },
    en: { day: ' day', hour: ' hour', minute: ' minute', ago: ' ago', now: 'just now' },
  }[locale];
  for (const [unit, size] of units) {
    const n = Math.floor(diff / size);
    if (n >= 1) return `${n}${words[unit]}${locale === 'en' && n > 1 ? 's' : ''}${words.ago}`;
  }
  return words.now;
}

/** @param {number} seconds @param {string} timeZoneOffset e.g. '+09:00' */
export function isoDate(seconds, timeZoneOffset = '+09:00') {
  const [h, m] = timeZoneOffset.slice(1).split(':').map(Number);
  const offset = (timeZoneOffset[0] === '-' ? -1 : 1) * (h * 60 + m) * 60;
  return new Date((seconds + offset) * 1000).toISOString().slice(0, 10);
}
