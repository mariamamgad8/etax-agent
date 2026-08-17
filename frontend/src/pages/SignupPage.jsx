import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { AuthShell } from '../components/auth/AuthShell.jsx';
import { Button } from '../components/core/Button.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { Checkbox } from '../components/forms/Checkbox.jsx';
import { TextField } from '../components/forms/TextField.jsx';

const INITIAL = { full_name: '', username: '', email: '', password: '', confirm_password: '' };

export function SignupPage() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [values, setValues] = React.useState(INITIAL);
  const [agree, setAgree] = React.useState(false);
  const [error, setError] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);

  const update = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (values.password !== values.confirm_password) {
      setError('Passwords do not match.');
      return;
    }
    if (values.password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (!agree) {
      setError('You must agree to the terms of use and privacy notice.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.signup(values);
      setSession(res);
      navigate('/face-enrollment');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      description="You will enrol your face on the next step. It is used only to confirm it is you at sign-in."
      footer={<>Already registered? <Link to="/login">Log in</Link></>}
    >
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && <Alert tone="danger" title="Could not create your account">{error}</Alert>}
        <TextField label="Full name" required placeholder="As shown on your tax ID" value={values.full_name} onChange={update('full_name')} />
        <TextField label="Email address" type="email" required value={values.email} onChange={update('email')} hint="Used for security notices and account recovery" />
        <TextField label="Username" required value={values.username} onChange={update('username')} hint="Letters, numbers, dots, underscores and hyphens only" />
        <TextField label="Password" type="password" revealable required value={values.password} onChange={update('password')} hint="At least 8 characters" />
        <TextField label="Confirm password" type="password" revealable required value={values.confirm_password} onChange={update('confirm_password')} />
        <Checkbox checked={agree} onChange={(e) => setAgree(e.target.checked)} label="I agree to the terms of use and the privacy notice." />
        <Button type="submit" size="lg" fullWidth disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account and continue'}
        </Button>
      </form>
    </AuthShell>
  );
}
