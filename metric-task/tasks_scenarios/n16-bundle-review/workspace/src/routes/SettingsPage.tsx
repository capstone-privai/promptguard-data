import { useState } from 'react';
import { supportedLocaleTags } from '../config/i18n';
import { formatDate } from '../lib/format';

export function SettingsPage() {
  const [locale, setLocale] = useState(() => localStorage.getItem('locale') ?? navigator.language);

  function choose(tag: string) {
    localStorage.setItem('locale', tag);
    setLocale(tag);
  }

  return (
    <section>
      <h1>Settings</h1>
      <label>
        Language
        <select value={locale} onChange={(e) => choose(e.target.value)}>
          {supportedLocaleTags.map((tag) => (
            <option key={tag} value={tag}>{tag}</option>
          ))}
        </select>
      </label>
      <p>Preview: {formatDate(new Date(), locale)}</p>
    </section>
  );
}
