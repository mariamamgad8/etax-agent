import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { AppHeader } from '../components/navigation/AppHeader.jsx';
import { ChatComposer } from '../components/chat/ChatComposer.jsx';
import { ChatMessage } from '../components/chat/ChatMessage.jsx';
import { FraudForm } from '../components/chat/FraudForm.jsx';
import { DataTable } from '../components/data/DataTable.jsx';
import { Alert } from '../components/feedback/Alert.jsx';
import { Spinner } from '../components/feedback/Spinner.jsx';
import { IconButton } from '../components/core/IconButton.jsx';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder.js';
import { LOGO_SRC } from '../constants.js';

const WELCOME =
  'Welcome. Ask about tax records you are authorized to access, or ask for a fraud-risk assessment on a taxpayer or business.';

const VOICE_REPLIES_KEY = 'etax_voice_replies';

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function ChatPage() {
  const { auth, signOut } = useAuth();
  const navigate = useNavigate();
  const [sessionValid, setSessionValid] = React.useState(true);
  const [turns, setTurns] = React.useState([{ role: 'assistant', body: WELCOME, time: '' }]);
  const [pendingForm, setPendingForm] = React.useState(null); // {threadId, fields, errors, schemaInfo}
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [composerText, setComposerText] = React.useState('');
  const [transcribing, setTranscribing] = React.useState(false);
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = React.useState(
    () => typeof localStorage !== 'undefined' && localStorage.getItem(VOICE_REPLIES_KEY) === '1',
  );
  const scroller = React.useRef(null);
  const audioPlayerRef = React.useRef(null);
  const voiceRecorder = useVoiceRecorder();

  React.useEffect(() => {
    localStorage.setItem(VOICE_REPLIES_KEY, voiceRepliesEnabled ? '1' : '0');
  }, [voiceRepliesEnabled]);

  React.useEffect(() => {
    let cancelled = false;
    // Backend-side confirmation that the "authenticated" stage on this token
    // is still valid — the frontend route guard alone isn't trusted for this.
    api.me(auth.token).catch(() => {
      if (!cancelled) setSessionValid(false);
    });
    return () => {
      cancelled = true;
    };
  }, [auth.token]);

  React.useEffect(() => {
    if (!sessionValid) {
      signOut();
      navigate('/login', { replace: true });
    }
  }, [sessionValid, signOut, navigate]);

  React.useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [turns, pendingForm, busy]);

  const handleSignOut = () => {
    signOut();
    navigate('/', { replace: true });
  };

  const pushAssistantTurn = (response) => {
    setTurns((prev) =>
      prev.concat({
        role: 'assistant',
        body: response.reply || '',
        table: response.table || null,
        time: nowLabel(),
      }),
    );
    if (voiceRepliesEnabled && response.reply) speakReply(response.reply);
  };

  // TTS is a separate, on-demand step, never part of /chat/message itself —
  // the text reply above always stands on its own, so a voice failure here
  // is surfaced softly and never retracts or blocks the text already shown.
  const speakReply = async (text) => {
    try {
      const blob = await api.speakText(auth.token, text);
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        URL.revokeObjectURL(audioPlayerRef.current.src);
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not play the voice reply.');
    }
  };

  const applyResponse = (response) => {
    if (response.awaiting) {
      setPendingForm({
        threadId: response.thread_id,
        fields: response.awaiting.fields || {},
        errors: response.awaiting.errors || [],
        schemaInfo: response.awaiting.schema,
      });
    } else {
      setPendingForm(null);
      pushAssistantTurn(response);
    }
  };

  const ask = async (text) => {
    setError('');
    setTurns((prev) => prev.concat({ role: 'user', body: text, time: nowLabel() }));
    setBusy(true);
    try {
      const response = await api.sendChatMessage(auth.token, text);
      applyResponse(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const submitForm = async (values) => {
    if (!pendingForm) return;
    setError('');
    setBusy(true);
    try {
      const response = await api.resumeChatForm(auth.token, pendingForm.threadId, values);
      applyResponse(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const handleMicToggle = () => {
    if (voiceRecorder.status === 'recording') {
      voiceRecorder.stop();
      return;
    }
    setError('');
    voiceRecorder.start(async (blob, filename) => {
      setTranscribing(true);
      try {
        const { text } = await api.transcribeAudio(auth.token, blob, filename);
        if (text && text.trim()) {
          setComposerText((prev) => (prev ? `${prev} ${text.trim()}` : text.trim()));
        } else {
          setError('Did not catch that — try again or type your message.');
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Could not transcribe your voice message.');
      } finally {
        setTranscribing(false);
      }
    });
  };

  React.useEffect(() => {
    if (voiceRecorder.error) setError(voiceRecorder.error);
  }, [voiceRecorder.error]);

  const listening = voiceRecorder.status === 'recording';
  const composerHint = pendingForm
    ? 'Complete the form above to continue.'
    : transcribing
      ? 'Transcribing your voice…'
      : listening
        ? 'Listening — click the mic again to stop.'
        : 'Answers cover records you are authorized to access. Every retrieval is logged against your session.';

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--surface-page)' }}>
      <AppHeader
        logoSrc={LOGO_SRC}
        user={auth.user?.full_name}
        verified
        onSignOut={handleSignOut}
        nav={
          <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <span style={{ fontSize: 'var(--text-body-sm)', borderBottom: '2px solid var(--etax-red)', paddingBottom: 2, color: 'var(--text-strong)', fontWeight: 'var(--fw-semibold)' }}>
              Assistant
            </span>
            <IconButton
              icon="volume-2"
              label={voiceRepliesEnabled ? 'Voice replies on — click to switch to text-only' : 'Voice replies off — click to hear replies spoken aloud'}
              tone="ghost"
              size="sm"
              active={voiceRepliesEnabled}
              onClick={() => setVoiceRepliesEnabled((v) => !v)}
            />
          </span>
        }
      />
      <div ref={scroller} style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-6) var(--space-8) var(--space-8)' }}>
        <div style={{ maxWidth: 820, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          {turns.map((t, i) => (
            <ChatMessage key={i} role={t.role} time={t.time}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {t.body}
                {t.table && <DataTable columns={t.table.columns} rows={t.table.rows} />}
              </div>
            </ChatMessage>
          ))}

          {pendingForm && (
            <ChatMessage role="assistant" time={nowLabel()}>
              <FraudForm
                fields={pendingForm.fields}
                errors={pendingForm.errors}
                schemaInfo={pendingForm.schemaInfo}
                onSubmit={submitForm}
                submitting={busy}
              />
            </ChatMessage>
          )}

          {busy && !pendingForm && (
            <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', paddingLeft: 44 }}>
              <Spinner label="Thinking…" />
            </div>
          )}
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--white)', padding: 'var(--space-4) var(--space-8) var(--space-6)' }}>
        <div style={{ maxWidth: 820, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {error && <Alert tone="danger" title="Something went wrong">{error}</Alert>}
          <ChatComposer
            value={composerText}
            onChange={setComposerText}
            onSend={ask}
            onMicToggle={handleMicToggle}
            listening={listening}
            disabled={busy || !!pendingForm || transcribing}
            hint={composerHint}
          />
        </div>
      </div>
    </div>
  );
}
