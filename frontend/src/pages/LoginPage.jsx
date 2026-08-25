import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import { AuthShell } from '../components/auth/AuthShell.jsx';
import { Button } from '../components/core/Button.jsx';
import { Icon } from '../components/core/Icon.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { Checkbox } from '../components/forms/Checkbox.jsx';
import { TextField } from '../components/forms/TextField.jsx';

export function LoginPage() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const { t } = useLanguage();
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const res = await api.login({ username, password });
      setSession(res);
      navigate(res.stage === 'pending_enrollment' ? '/face-enrollment' : '/face-verification');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('auth.genericError'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title={t('auth.loginTitle')}
      description={t('auth.loginDescription')}
      footer={<>{t('auth.noAccountYet')} <Link to="/signup">{t('auth.createOne')}</Link></>}
    >
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && <Alert tone="danger" title={t('auth.signInFailed')}>{error}</Alert>}
        <TextField label={t('auth.usernameLabel')} required value={username} onChange={(e) => setUsername(e.target.value)} />
        <TextField label={t('auth.passwordLabel')} type="password" revealable required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Checkbox label={t('auth.rememberDevice')} />
          <a href="#" style={{ fontSize: 'var(--text-body-sm)' }}>{t('auth.forgotPassword')}</a>
        </div>
        <Button type="submit" size="lg" fullWidth disabled={submitting}>{submitting ? t('auth.loginSubmitting') : t('auth.loginSubmit')}</Button>
        <p style={{ fontSize: 'var(--text-caption)', color: 'var(--text-muted)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <Icon name="lock" size={13} /> {t('auth.credentialsNotice')}
        </p>
      </form>
    </AuthShell>
  );
}
