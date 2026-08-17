import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/core/Button.jsx';
import { Icon } from '../components/core/Icon.jsx';
import { Logo } from '../components/core/Logo.jsx';
import { LOGO_SRC } from '../constants.js';

function LandingHeader({ onLogin, onSignUp }) {
  return (
    <header style={{ display: 'flex', alignItems: 'center', height: 72, padding: '0 var(--space-8)', background: 'var(--white)', borderBottom: '1px solid var(--border-subtle)' }}>
      <Logo height={30} src={LOGO_SRC} subtitle="Tax Assistant" />
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-3)' }}>
        <Button variant="ghost" onClick={onLogin}>Log in</Button>
        <Button onClick={onSignUp}>Create account</Button>
      </div>
    </header>
  );
}

const CAPABILITIES = [
  { icon: 'messages-square', title: 'Ask in writing or by voice', body: 'Type a question or use the microphone. Answers can be read back aloud when you need them hands-free.' },
  { icon: 'shield-alert', title: 'Fraud risk assessment', body: 'Run the assessment model on a taxpayer record and see the predicted risk level with the factors behind it.' },
  { icon: 'database', title: 'Authorized data only', body: 'Queries are limited to the records your account is cleared to see. Every retrieval is logged against your session.' },
];

export function LandingPage() {
  const navigate = useNavigate();
  const onLogin = () => navigate('/login');
  const onSignUp = () => navigate('/signup');

  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-page)' }}>
      <LandingHeader onLogin={onLogin} onSignUp={onSignUp} />
      <main style={{ maxWidth: 'var(--container-lg)', margin: '0 auto', padding: 'var(--space-16) var(--space-8) var(--space-12)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,.85fr)', gap: 'var(--space-16)', alignItems: 'start' }}>
          <div>
            <p className="etax-overline" style={{ marginBottom: 'var(--space-4)' }}>Revenue service · secure portal</p>
            <h1 style={{ fontSize: 'var(--text-display-lg)', letterSpacing: 'var(--ls-display)', lineHeight: 'var(--lh-tight)', marginBottom: 'var(--space-5)' }}>
              A tax assistant for authorized enquiries and risk assessment
            </h1>
            <p style={{ fontSize: 'var(--text-body-lg)', color: 'var(--text-body)', maxWidth: 560, marginBottom: 'var(--space-8)', textWrap: 'pretty' }}>
              eTax answers questions about taxpayer records you are cleared to access and runs the fraud risk model on request. Access requires an account and face verification at every sign-in.
            </p>
            <div style={{ display: 'flex', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
              <Button variant="accent" size="lg" onClick={onSignUp}>Create account</Button>
              <Button variant="secondary" size="lg" onClick={onLogin}>Log in</Button>
            </div>
            <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <Icon name="lock" size={14} /> Sessions are encrypted and expire after inactivity.
            </p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {CAPABILITIES.map((c) => (
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
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-6)' }}>
            <a href="#">Privacy notice</a><a href="#">Terms of use</a><a href="#">Report a problem</a>
          </span>
        </div>
      </footer>
    </div>
  );
}
