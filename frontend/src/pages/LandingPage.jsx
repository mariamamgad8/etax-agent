import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import { Button } from '../components/core/Button.jsx';
import { Icon } from '../components/core/Icon.jsx';
import { Logo } from '../components/core/Logo.jsx';
import { LanguageSwitcher } from '../components/navigation/LanguageSwitcher.jsx';
import { LOGO_SRC } from '../constants.js';

function LandingHeader({ onLogin, onSignUp }) {
  const { t } = useLanguage();
  return (
    <header style={{ display: 'flex', alignItems: 'center', height: 72, padding: '0 var(--space-8)', background: 'var(--white)', borderBottom: '1px solid var(--border-subtle)' }}>
      <Logo height={30} src={LOGO_SRC} subtitle={t('common.tagline')} />
      <div style={{ marginInlineStart: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-5)' }}>
        <LanguageSwitcher />
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <Button variant="ghost" onClick={onLogin}>{t('nav.login')}</Button>
          <Button onClick={onSignUp}>{t('nav.createAccount')}</Button>
        </div>
      </div>
    </header>
  );
}

export function LandingPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const onLogin = () => navigate('/login');
  const onSignUp = () => navigate('/signup');

  const capabilities = [
    { icon: 'messages-square', title: t('landing.capability1Title'), body: t('landing.capability1Body') },
    { icon: 'shield-alert', title: t('landing.capability2Title'), body: t('landing.capability2Body') },
    { icon: 'database', title: t('landing.capability3Title'), body: t('landing.capability3Body') },
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-page)' }}>
      <LandingHeader onLogin={onLogin} onSignUp={onSignUp} />
      <main style={{ maxWidth: 'var(--container-lg)', margin: '0 auto', padding: 'var(--space-16) var(--space-8) var(--space-12)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,.85fr)', gap: 'var(--space-16)', alignItems: 'start' }}>
          <div>
            <p className="etax-overline" style={{ marginBottom: 'var(--space-4)' }}>{t('landing.eyebrow')}</p>
            <h1 style={{ fontSize: 'var(--text-display-lg)', letterSpacing: 'var(--ls-display)', lineHeight: 'var(--lh-tight)', marginBottom: 'var(--space-5)' }}>
              {t('landing.heading')}
            </h1>
            <p style={{ fontSize: 'var(--text-body-lg)', color: 'var(--text-body)', maxWidth: 560, marginBottom: 'var(--space-8)', textWrap: 'pretty' }}>
              {t('landing.body')}
            </p>
            <div style={{ display: 'flex', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
              <Button variant="accent" size="lg" onClick={onSignUp}>{t('nav.createAccount')}</Button>
              <Button variant="secondary" size="lg" onClick={onLogin}>{t('nav.login')}</Button>
            </div>
            <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <Icon name="lock" size={14} /> {t('landing.sessionsNotice')}
            </p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {capabilities.map((c) => (
              <div key={c.title} style={{ display: 'flex', gap: 'var(--space-4)', padding: 'var(--space-5)', background: 'var(--white)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)' }}>
                <Icon name={c.icon} size={20} color="var(--etax-navy)" style={{ marginTop: 2 }} />
                <div>
                  <h3 style={{ fontSize: 'var(--text-body-md)', marginBottom: 'var(--space-1)' }}>{c.title}</h3>
                  <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-body)' }}>{c.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
      <footer style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--white)' }}>
        <div style={{ maxWidth: 'var(--container-lg)', margin: '0 auto', padding: 'var(--space-6) var(--space-8)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)', alignItems: 'center', fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>
          <Logo height={22} src={LOGO_SRC} />
          <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 'var(--space-6)' }}>
            <a href="#">{t('landing.privacyNotice')}</a><a href="#">{t('landing.termsOfUse')}</a><a href="#">{t('landing.reportProblem')}</a>
          </span>
        </div>
      </footer>
    </div>
  );
}
