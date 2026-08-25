import React from 'react';
import { Link } from 'react-router-dom';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { LOGO_SRC } from '../../constants.js';
import { LanguageSwitcher } from '../navigation/LanguageSwitcher.jsx';
import { Logo } from '../core/Logo.jsx';

export function AuthShell({ title, description, children, footer }) {
  const { t } = useLanguage();
  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-page)', display: 'flex', flexDirection: 'column' }}>
      <header style={{ display: 'flex', alignItems: 'center', height: 72, padding: '0 var(--space-8)', background: 'var(--white)', borderBottom: '1px solid var(--border-subtle)' }}>
        <Link to="/" style={{ border: 'none', display: 'inline-flex' }}>
          <Logo height={30} src={LOGO_SRC} subtitle={t('common.tagline')} />
        </Link>
        <LanguageSwitcher style={{ marginInlineStart: 'auto' }} />
      </header>
      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: 'var(--space-12) var(--space-4)' }}>
        <div style={{ width: '100%', maxWidth: 480 }}>
          <div style={{ background: 'var(--white)', border: '1px solid var(--border-subtle)', borderTop: '3px solid var(--action-accent)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sm)', padding: 'var(--space-8)' }}>
            <h1 style={{ fontSize: 'var(--text-h1)', marginBottom: 'var(--space-2)' }}>{title}</h1>
            <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)', marginBottom: 'var(--space-6)' }}>{description}</p>
            {children}
          </div>
          <p style={{ textAlign: 'center', marginTop: 'var(--space-5)', fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>{footer}</p>
        </div>
      </main>
    </div>
  );
}
