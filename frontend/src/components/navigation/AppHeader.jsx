import React from 'react';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { Badge } from '../core/Badge.jsx';
import { Icon } from '../core/Icon.jsx';
import { Logo } from '../core/Logo.jsx';
import { LanguageSwitcher } from './LanguageSwitcher.jsx';

/** Application header: logo lockup left, session state and account controls right. */
export function AppHeader({ logoSrc = '/assets/etax-logo.png', subtitle, user, verified, nav, onSignOut, style, ...rest }) {
  const { t } = useLanguage();
  return (
    <header {...rest} style={{
      display: 'flex', alignItems: 'center', gap: 'var(--space-6)', height: 64, padding: '0 var(--space-6)',
      background: 'var(--white)', borderBottom: '1px solid var(--border-subtle)', ...style,
    }}>
      <Logo height={28} src={logoSrc} subtitle={subtitle ?? t('common.tagline')} />
      {nav && <nav style={{ display: 'flex', gap: 'var(--space-5)', flex: 1 }}>{nav}</nav>}
      <div style={{ marginInlineStart: nav ? 0 : 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
        <LanguageSwitcher />
        {verified && <Badge tone="success" style={{ whiteSpace: 'nowrap' }}><Icon name="shield-check" size={12} /> {t('nav.identityVerified')}</Badge>}
        {user && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', paddingInlineStart: 'var(--space-4)', borderInlineStart: '1px solid var(--border-subtle)' }}>
            <span style={{ width: 28, height: 28, borderRadius: 'var(--radius-sm)', background: 'var(--etax-navy-50)', color: 'var(--etax-navy)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-semibold)' }}>
              {user.split(' ').map((w) => w[0]).slice(0, 2).join('')}
            </span>
            <span style={{ fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-medium)', color: 'var(--text-strong)', whiteSpace: 'nowrap' }}>{user}</span>
          </span>
        )}
        {onSignOut && (
          <button type="button" onClick={onSignOut}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 'var(--text-body-sm)', color: 'var(--gray-600)', whiteSpace: 'nowrap' }}>
            <Icon name="log-out" size={16} /> {t('common.logout')}
          </button>
        )}
      </div>
    </header>
  );
}
