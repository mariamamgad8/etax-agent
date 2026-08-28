import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import { Badge } from '../components/core/Badge.jsx';
import { Button } from '../components/core/Button.jsx';
import { Icon } from '../components/core/Icon.jsx';
import { Logo } from '../components/core/Logo.jsx';
import { LiveCameraFrame } from '../components/face/LiveCameraFrame.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { StatusSteps } from '../components/feedback/StatusSteps.jsx';
import { LanguageSwitcher } from '../components/navigation/LanguageSwitcher.jsx';
import { LOGO_SRC } from '../constants.js';
import { useCamera } from '../hooks/useCamera.js';

function useErrorMessage() {
  const { t } = useLanguage();
  return (err) => {
    if (!(err instanceof ApiError)) return t('face.errorEnrollFailed');
    if (err.status === 422) return t('face.errorNoFaceDetected');
    if (err.status === 403) return t('face.errorEnrollLivenessFailed');
    if (err.status === 409) return t('face.errorAlreadyEnrolled');
    return err.message || t('face.errorEnrollFailed');
  };
}

export function FaceEnrollmentPage() {
  const navigate = useNavigate();
  const { auth, setSession, signOut } = useAuth();
  const { t } = useLanguage();
  const errorMessage = useErrorMessage();
  const { videoRef, status: cameraStatus, start, stop, captureFrame } = useCamera();
  const [stepIndex, setStepIndex] = React.useState(0);
  const [submitting, setSubmitting] = React.useState(false);
  const [failure, setFailure] = React.useState('');
  const [done, setDone] = React.useState(false);
  const pacingTimer = React.useRef(null);

  const STEPS = [t('face.stepCameraReady'), t('face.stepFaceCaptured'), t('face.stepLivenessCheck'), t('face.stepFaceEnrolled')];

  React.useEffect(() => {
    start();
    return () => {
      clearTimeout(pacingTimer.current);
      stop();
    };
  }, [start, stop]);

  const capture = async () => {
    setFailure('');
    setSubmitting(true);
    setStepIndex(1);
    pacingTimer.current = setTimeout(() => setStepIndex(2), 700);
    try {
      const blob = await captureFrame();
      if (!blob) throw new ApiError(t('face.cameraNotReady'), 0);
      const res = await api.enrollFace(auth.token, blob);
      clearTimeout(pacingTimer.current);
      setStepIndex(4);
      setDone(true);
      // Release the camera the moment it's no longer needed — see the same
      // fix in FaceVerificationPage.jsx for why this can't just wait for
      // unmount.
      stop();
      setSession({ access_token: res.access_token, stage: res.stage, user: auth.user });
      setTimeout(() => navigate('/chat', { replace: true }), 900);
    } catch (err) {
      clearTimeout(pacingTimer.current);
      setFailure(errorMessage(err));
      setStepIndex(err instanceof ApiError && err.status === 403 ? 2 : 0);
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
        <Logo height={30} src={LOGO_SRC} subtitle={t('face.enrollTagline')} />
        <div style={{ marginInlineStart: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
          <LanguageSwitcher />
          <Badge tone="navy">{t('face.enrollStepBadge')}</Badge>
        </div>
      </header>
      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: 'var(--space-10) var(--space-4)' }}>
        <div style={{ width: '100%', maxWidth: 860 }}>
          <h1 style={{ fontSize: 'var(--text-h1)', marginBottom: 'var(--space-2)' }}>{t('face.enrollHeading')}</h1>
          <p style={{ fontSize: 'var(--text-body-md)', color: 'var(--text-body)', marginBottom: 'var(--space-6)' }}>
            {t('face.enrollBody')}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 'var(--space-6)', background: 'var(--white)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sm)', padding: 'var(--space-6)' }}>
            <LiveCameraFrame videoRef={videoRef} stage={done ? 'verified' : 'active'} failed={!!failure} cameraStatus={cameraStatus} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
              <div>
                <p className="etax-overline" style={{ marginBottom: 'var(--space-3)' }}>{t('face.securityCheck')}</p>
                <StatusSteps steps={STEPS} current={stepIndex} failed={!!failure} />
              </div>
              {failure ? (
                <Alert tone="danger" title={t('face.enrollFailedTitle')}>{failure}</Alert>
              ) : done ? (
                <Alert tone="success" title={t('face.enrolledTitle')}>{t('face.openingAssistant')}</Alert>
              ) : cameraStatus === 'denied' ? (
                <Alert tone="danger" title={t('face.cameraDenied')}>{t('face.cameraDeniedBody')}</Alert>
              ) : (
                <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'flex-start', padding: 'var(--space-4)', background: 'var(--gray-50)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <Icon name="scan-face" size={18} color="var(--etax-navy)" style={{ marginTop: 1 }} />
                  <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--gray-800)' }}>
                    {cameraStatus === 'ready' ? t('face.positionFace') : t('face.startingCamera')}
                  </p>
                </div>
              )}
              <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {!done && (
                  <Button fullWidth disabled={cameraStatus !== 'ready' || submitting} onClick={capture}>
                    {submitting ? t('face.enrollChecking') : failure ? t('common.tryAgain') : t('face.enrollCapture')}
                  </Button>
                )}
                <Button variant="ghost" fullWidth onClick={cancel}>{t('face.cancelAndReturn')}</Button>
              </div>
            </div>
          </div>
          <p style={{ fontSize: 'var(--text-caption)', color: 'var(--text-muted)', marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <Icon name="lock" size={13} /> {t('face.privacyFootnote')}
          </p>
        </div>
      </main>
    </div>
  );
}
