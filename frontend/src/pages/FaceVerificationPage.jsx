import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { Badge } from '../components/core/Badge.jsx';
import { Button } from '../components/core/Button.jsx';
import { Icon } from '../components/core/Icon.jsx';
import { Logo } from '../components/core/Logo.jsx';
import { LiveCameraFrame } from '../components/face/LiveCameraFrame.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { StatusSteps } from '../components/feedback/StatusSteps.jsx';
import { LOGO_SRC } from '../constants.js';
import { useCamera } from '../hooks/useCamera.js';

const STEPS = ['Camera ready', 'Face detected', 'Liveness check', 'Identity verified'];

function errorMessage(err) {
  if (!(err instanceof ApiError)) return 'Verification failed. Try again.';
  if (err.status === 422) return 'No face detected. Position your face inside the frame and try again.';
  if (err.status === 403) return 'Liveness check failed. This looks like a photo, screen, or other spoof rather than a live face.';
  if (err.status === 401) return 'Face does not match this account.';
  if (err.status === 409) return 'No enrolled face found for this account.';
  return err.message || 'Verification failed. Try again.';
}

export function FaceVerificationPage() {
  const navigate = useNavigate();
  const { auth, setSession, signOut } = useAuth();
  const { videoRef, status: cameraStatus, start, captureFrame } = useCamera();
  const [stepIndex, setStepIndex] = React.useState(0);
  const [submitting, setSubmitting] = React.useState(false);
  const [failure, setFailure] = React.useState('');
  const [done, setDone] = React.useState(false);
  const pacingTimer = React.useRef(null);

  React.useEffect(() => {
    start();
    return () => clearTimeout(pacingTimer.current);
  }, [start]);

  const verify = async () => {
    setFailure('');
    setSubmitting(true);
    setStepIndex(1);
    pacingTimer.current = setTimeout(() => setStepIndex(2), 700);
    try {
      const blob = await captureFrame();
      if (!blob) throw new ApiError('Camera is not ready yet.', 0);
      const res = await api.verifyFace(auth.token, blob);
      clearTimeout(pacingTimer.current);
      setStepIndex(4);
      setDone(true);
      setSession({ access_token: res.access_token, stage: res.stage, user: auth.user });
      setTimeout(() => navigate('/chat', { replace: true }), 900);
    } catch (err) {
      clearTimeout(pacingTimer.current);
      setFailure(errorMessage(err));
      setStepIndex(err instanceof ApiError && err.status === 403 ? 2 : err instanceof ApiError && err.status === 401 ? 3 : 0);
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = () => {
    signOut();
    navigate('/login', { replace: true });
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-page)', display: 'flex', flexDirection: 'column' }}>
      <header style={{ display: 'flex', alignItems: 'center', height: 72, padding: '0 var(--space-8)', background: 'var(--white)', borderBottom: '1px solid var(--border-subtle)' }}>
        <Logo height={30} src={LOGO_SRC} subtitle="Identity check" />
        <Badge tone="navy" style={{ marginLeft: 'auto' }}>Step 2 of 2</Badge>
      </header>
      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: 'var(--space-10) var(--space-4)' }}>
        <div style={{ width: '100%', maxWidth: 860 }}>
          <h1 style={{ fontSize: 'var(--text-h1)', marginBottom: 'var(--space-2)' }}>Verify your identity</h1>
          <p style={{ fontSize: 'var(--text-body-md)', color: 'var(--text-body)', marginBottom: 'var(--space-6)' }}>
            {auth.user ? `${auth.user.full_name}, ` : ''}look straight at the camera in even lighting. Nothing is recorded — the check runs and is discarded.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 'var(--space-6)', background: 'var(--white)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sm)', padding: 'var(--space-6)' }}>
            <LiveCameraFrame videoRef={videoRef} stage={done ? 'verified' : 'active'} failed={!!failure} cameraStatus={cameraStatus} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
              <div>
                <p className="etax-overline" style={{ marginBottom: 'var(--space-3)' }}>Security check</p>
                <StatusSteps steps={STEPS} current={stepIndex} failed={!!failure} />
              </div>
              {failure ? (
                <Alert tone="danger" title="Verification failed">{failure}</Alert>
              ) : done ? (
                <Alert tone="success" title="Identity verified">Opening your assistant.</Alert>
              ) : cameraStatus === 'denied' ? (
                <Alert tone="danger" title="Camera permission denied">Allow camera access in your browser to continue.</Alert>
              ) : (
                <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'flex-start', padding: 'var(--space-4)', background: 'var(--gray-50)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <Icon name="scan-face" size={18} color="var(--etax-navy)" style={{ marginTop: 1 }} />
                  <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--gray-800)' }}>
                    {cameraStatus === 'ready' ? 'Position your face inside the frame, then verify.' : 'Starting camera…'}
                  </p>
                </div>
              )}
              <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {!done && (
                  <Button fullWidth disabled={cameraStatus !== 'ready' || submitting} onClick={verify}>
                    {submitting ? 'Verifying…' : failure ? 'Try again' : 'Verify my identity'}
                  </Button>
                )}
                <Button variant="ghost" fullWidth onClick={cancel}>Cancel and return to login</Button>
              </div>
            </div>
          </div>
          <p style={{ fontSize: 'var(--text-caption)', color: 'var(--text-muted)', marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <Icon name="lock" size={13} /> Face data stays on the verification service and is never shown to other users.
          </p>
        </div>
      </main>
    </div>
  );
}
