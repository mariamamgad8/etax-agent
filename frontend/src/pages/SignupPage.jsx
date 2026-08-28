import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import { AuthShell } from '../components/auth/AuthShell.jsx';
import { Button } from '../components/core/Button.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { Checkbox } from '../components/forms/Checkbox.jsx';
import { TextField } from '../components/forms/TextField.jsx';

const INITIAL = { full_name: '', username: '', email: '', password: '', confirm_password: '', tax_record_code: '' };

export function SignupPage() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const { t } = useLanguage();
  const [values, setValues] = React.useState(INITIAL);
  const [agree, setAgree] = React.useState(false);
  const [error, setError] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);

  const update = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (values.password !== values.confirm_password) {
      setError(t('auth.passwordsDoNotMatch'));
      return;
    }
    if (values.password.length < 8) {
      setError(t('auth.passwordTooShort'));
      return;
    }
    if (!/^\d{9}$/.test(values.tax_record_code)) {
      setError(t('auth.taxRecordCodeInvalid'));
      return;
    }
    if (!agree) {
      setError(t('auth.mustAgreeToTerms'));
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.signup(values);
      setSession(res);
      navigate('/face-enrollment');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('auth.genericError'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title={t('auth.signupTitle')}
      description={t('auth.signupDescription')}
      footer={<>{t('auth.alreadyRegistered')} <Link to="/login">{t('auth.loginSubmit')}</Link></>}
    >
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && <Alert tone="danger" title={t('auth.couldNotCreateAccount')}>{error}</Alert>}
        <TextField label={t('auth.fullNameLabel')} required placeholder={t('auth.fullNamePlaceholder')} value={values.full_name} onChange={update('full_name')} />
        <TextField label={t('auth.emailLabel')} type="email" required value={values.email} onChange={update('email')} hint={t('auth.emailHint')} />
        <TextField label={t('auth.usernameFieldLabel')} required value={values.username} onChange={update('username')} hint={t('auth.usernameHint')} />
        <TextField
          label={t('auth.taxRecordCodeLabel')}
          required
          value={values.tax_record_code}
          onChange={update('tax_record_code')}
          hint={t('auth.taxRecordCodeHint')}
          maxLength={9}
        />
        <TextField label={t('auth.passwordLabel')} type="password" revealable required value={values.password} onChange={update('password')} hint={t('auth.passwordHint')} />
        <TextField label={t('auth.confirmPasswordLabel')} type="password" revealable required value={values.confirm_password} onChange={update('confirm_password')} />
        <Checkbox checked={agree} onChange={(e) => setAgree(e.target.checked)} label={t('auth.agreeToTerms')} />
        <Button type="submit" size="lg" fullWidth disabled={submitting}>
          {submitting ? t('auth.signupSubmitting') : t('auth.signupSubmit')}
        </Button>
      </form>
    </AuthShell>
  );
}
