import React from 'react';
import { useLanguage } from '../../i18n/LanguageContext.jsx';

/** Visible "العربية | English" control — UI localization only, see LanguageContext.jsx. */
export function LanguageSwitcher({ style }) {
  const { language, setLanguage, t } = useLanguage();
  const optionStyle = (lang) => ({
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontFamily: 'var(--font-body)',
    fontSize: 'var(--text-body-sm)',
    padding: 0,
    color: language === lang ? 'var(--text-strong)' : 'var(--text-muted)',
    fontWeight: language === lang ? 'var(--fw-semibold)' : 'var(--fw-regular)',
    textDecoration: language === lang ? 'underline' : 'none',
  });

  return (
    <div
      role="group"
      aria-label={t('languageSwitcher.label')}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--text-body-sm)', ...style }}
    >
      <button type="button" style={optionStyle('ar')} onClick={() => setLanguage('ar')} lang="ar" dir="rtl">
        العربية
      </button>
      <span style={{ color: 'var(--border-default)' }}>|</span>
      <button type="button" style={optionStyle('en')} onClick={() => setLanguage('en')} lang="en" dir="ltr">
        English
      </button>
    </div>
  );
}
