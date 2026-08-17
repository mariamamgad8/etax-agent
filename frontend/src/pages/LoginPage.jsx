import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { AuthShell } from '../components/auth/AuthShell.jsx';
import { Button } from '../components/core/Button.jsx';
import { Icon } from '../components/core/Icon.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { Checkbox } from '../components/forms/Checkbox.jsx';
import { TextField } from '../components/forms/TextField.jsx';

export function LoginPage() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
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
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Log in"
      description="Face verification follows once your credentials are accepted."
      footer={<>No account yet? <Link to="/signup">Create one</Link></>}
    >
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {error && <Alert tone="danger" title="Sign-in failed">{error}</Alert>}
        <TextField label="Email or username" required value={username} onChange={(e) => setUsername(e.target.value)} />
        <TextField label="Password" type="password" revealable required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Checkbox label="Remember this device" />
          <a href="#" style={{ fontSize: 'var(--text-body-sm)' }}>Forgot password?</a>
        </div>
        <Button type="submit" size="lg" fullWidth disabled={submitting}>{submitting ? 'Signing in…' : 'Log in'}</Button>
        <p style={{ fontSize: 'var(--text-caption)', color: 'var(--text-muted)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <Icon name="lock" size={13} /> Do not share your credentials. eTax staff will never ask for your password.
        </p>
      </form>
    </AuthShell>
  );
}
