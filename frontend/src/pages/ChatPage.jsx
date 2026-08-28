import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { useLanguage } from '../i18n/LanguageContext.jsx';
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

const CHAT_HISTORY_KEY_PREFIX = 'etax_chat_history_';

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Scoped per account so one user's conversation never leaks into another's
// view on a shared browser, and so it can be cleared on sign-out.
function chatHistoryKey(userId) {
  return `${CHAT_HISTORY_KEY_PREFIX}${userId}`;
}

function loadStoredHistory(userId) {
  try {
    const raw = localStorage.getItem(chatHistoryKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.turns) || parsed.turns.length === 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

function clearStoredHistory(userId) {
  try {
    localStorage.removeItem(chatHistoryKey(userId));
  } catch {
    // ignore
  }
}

export function ChatPage() {
  const { auth, signOut } = useAuth();
  const navigate = useNavigate();
  // UI-chrome-only localization (this hook) — the conversation itself
  // (turns below) is never re-translated when the UI language changes: the
  // welcome bubble is written once, at mount, in whatever language was
  // active then, and every other turn is either the user's own words or the
  // backend's own per-turn response-language choice. Toggling the UI
  // language later must not rewrite any of that. See i18n/LanguageContext.jsx.
  const { t, language } = useLanguage();
  const [sessionValid, setSessionValid] = React.useState(true);
  const [turns, setTurns] = React.useState([]);
  // Reused across the WHOLE session (not just interrupt resumes) once the
  // first response hands one back — this is what makes the backend's
  // cross-turn memory (graph.py's prepare_db_question) actually apply.
  const [threadId, setThreadId] = React.useState(null);
  // The backend's per-process boot_id (see chat/routes.py) — a fresh value
  // every time the backend restarts (a `docker compose down && up`, or even
  // just uvicorn's own --reload), since the graph's InMemorySaver
  // checkpointer is wiped either way. Saved alongside the persisted
  // conversation so a stale one (from before a restart) is never restored.
  const bootIdRef = React.useRef(null);
  const [pendingReview, setPendingReview] = React.useState(null); // {threadId, recordId, record, reviewStatus}
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [composerText, setComposerText] = React.useState('');
  const [transcribing, setTranscribing] = React.useState(false);
  // Always ON at the start of every session, in-memory only — deliberately
  // NOT persisted anywhere (no localStorage). Turning it off only lasts for
  // as long as this one chat session is active; sign-out+sign-in (same or a
  // different user), a page reload, or the backend restarting all mean a
  // fresh mount of this component, which resets it back to on.
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = React.useState(true);
  const scroller = React.useRef(null);
  const audioPlayerRef = React.useRef(null);
  const voiceRecorder = useVoiceRecorder();

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
  }, [turns, pendingReview, busy]);

  // Persists the conversation so reloading the SAME page doesn't wipe it back
  // to just the welcome bubble — this is purely a frontend replay of what's
  // shown, keyed alongside the backend's boot_id (see the welcome-fetch
  // effect below) so a since-restarted backend's now-meaningless thread_id
  // never gets silently restored either. Deliberately narrower than "survive
  // anything": cleared on sign-out, on navigating away from this page (see
  // the unmount effect below), and discarded once the boot_id no longer
  // matches — a plain reload of /chat is the only thing meant to survive.
  React.useEffect(() => {
    if (!auth.user?.id || turns.length === 0) return;
    try {
      localStorage.setItem(chatHistoryKey(auth.user.id), JSON.stringify({ turns, threadId, bootId: bootIdRef.current }));
    } catch {
      // Storage full/unavailable (private mode, etc.) — the conversation
      // just won't survive a reload this time; not worth surfacing an error for.
    }
  }, [turns, threadId, auth.user?.id]);

  // Navigating away from the chat page entirely (not just reloading it)
  // clears the saved conversation — only a same-page reload is meant to
  // restore it. The clear is deliberately delayed a tick and cancellable:
  // this app renders under <React.StrictMode> (see main.jsx), which
  // deliberately double-invokes effects once in dev (mount -> cleanup ->
  // mount again, synchronously) to surface exactly this kind of missing-
  // cleanup bug — a naive unmount-clear would wipe a real, valid
  // conversation on every dev-mode mount, before ever getting a chance to
  // display it. A REAL navigation-away unmount has no follow-up setup to
  // cancel the scheduled clear, so it still goes through.
  const pendingClearRef = React.useRef(null);
  React.useEffect(() => {
    const userId = auth.user?.id;
    if (pendingClearRef.current) {
      clearTimeout(pendingClearRef.current);
      pendingClearRef.current = null;
    }
    return () => {
      pendingClearRef.current = setTimeout(() => {
        if (userId) clearStoredHistory(userId);
        pendingClearRef.current = null;
      }, 0);
    };
  }, [auth.user?.id]);

  const handleSignOut = () => {
    if (auth.user?.id) clearStoredHistory(auth.user.id);
    signOut();
    navigate('/', { replace: true });
  };

  // A session can now expire mid-chat (sliding inactivity timeout — see
  // app.auth.dependencies.require_stage), not just at the initial /auth/me
  // check on mount. Any 401 from any backend call means the same thing: the
  // session is gone, so sign out and send them back to login rather than
  // just showing "Session expired" as an inert chat error bubble.
  const handleApiError = (err, fallbackMessage) => {
    if (err instanceof ApiError) {
      if (err.status === 401) {
        signOut();
        navigate('/login', { replace: true });
        return;
      }
      setError(err.message);
      return;
    }
    setError(fallbackMessage);
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
      handleApiError(err, t('chat.couldNotPlayVoice'));
    }
  };

  const applyResponse = (response) => {
    setThreadId(response.thread_id);
    if (response.awaiting) {
      setPendingReview({
        threadId: response.thread_id,
        recordId: response.awaiting.record_id,
        record: response.awaiting.record || {},
        reviewStatus: response.awaiting.review_status,
      });
    } else {
      setPendingReview(null);
      pushAssistantTurn(response);
    }
  };

  const ask = async (text) => {
    setError('');
    setTurns((prev) => prev.concat({ role: 'user', body: text, time: nowLabel() }));
    setBusy(true);
    try {
      const response = await api.sendChatMessage(auth.token, text, threadId);
      applyResponse(response);
    } catch (err) {
      handleApiError(err, t('chat.genericError'));
    } finally {
      setBusy(false);
    }
  };

  // Restores a persisted conversation on mount if one exists for this
  // account (see the save-effect above) — reloading the SAME page must not
  // wipe the chat back to just the welcome bubble. Shown optimistically,
  // synchronously, before the network round-trip below, so there's no flash
  // of an empty conversation — but only actually kept once the backend's
  // current boot_id confirms this history was saved since the LAST backend
  // restart; a `docker compose down && up` (or a dev --reload) wipes the
  // graph's InMemorySaver checkpointer, so a thread_id from before that is
  // meaningless now and the stale history is discarded in favor of a fresh
  // welcome instead. The spoken (by account name) greeting is a SEPARATE
  // concern from the text history, though, and always speaks on every mount
  // regardless of which branch above ran — it's only shown as a NEW bubble
  // when there's no (still-valid) history to restore, so reopening an
  // ongoing conversation doesn't insert a duplicate "Hi Ahmed..." line above
  // what's already there, but you still hear it every time you enter the
  // chatbot. Speaks it too, but only if voice replies are already enabled —
  // same on-demand-only rule every other reply follows, and sidesteps
  // browsers silently blocking unprompted autoplay audio.
  React.useEffect(() => {
    let cancelled = false;

    const stored = auth.user?.id ? loadStoredHistory(auth.user.id) : null;
    if (stored) {
      setTurns(stored.turns);
      setThreadId(stored.threadId || null);
    }

    (async () => {
      let text = t('chat.welcome');
      let bootId = null;
      try {
        const res = await api.getWelcome(auth.token, language);
        if (res && res.text) text = res.text;
        bootId = (res && res.boot_id) || null;
      } catch {
        // Non-critical personalization — fall back to the generic
        // UI-language welcome below rather than surfacing an error banner
        // before the conversation has even started.
      }
      if (cancelled) return;

      bootIdRef.current = bootId;
      const stillValid = stored && bootId && stored.bootId === bootId;
      if (stored && !stillValid) {
        // The backend has restarted since this was saved — its thread_id no
        // longer means anything server-side, so don't keep showing it as if
        // it were still a live conversation.
        clearStoredHistory(auth.user.id);
        setTurns([]);
        setThreadId(null);
      }
      if (!stillValid) setTurns([{ role: 'assistant', body: text, time: nowLabel() }]);
      if (voiceRepliesEnabled) speakReply(text);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const confirmReview = async () => {
    if (!pendingReview) return;
    setError('');
    setBusy(true);
    try {
      const response = await api.resumeChatForm(auth.token, pendingReview.threadId, { action: 'confirm' });
      applyResponse(response);
    } catch (err) {
      handleApiError(err, t('chat.genericError'));
    } finally {
      setBusy(false);
    }
  };

  const requestReviewFields = async (fields) => {
    if (!pendingReview) return;
    setError('');
    setBusy(true);
    try {
      const response = await api.resumeChatForm(auth.token, pendingReview.threadId, { action: 'flag', fields });
      applyResponse(response);
    } catch (err) {
      handleApiError(err, t('chat.genericError'));
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
          setError(t('chat.didNotCatchThat'));
        }
      } catch (err) {
        handleApiError(err, t('chat.couldNotTranscribe'));
      } finally {
        setTranscribing(false);
      }
    });
  };

  React.useEffect(() => {
    if (voiceRecorder.error) setError(voiceRecorder.error);
  }, [voiceRecorder.error]);

  const listening = voiceRecorder.status === 'recording';
  const composerHint = pendingReview
    ? t('chat.hintPendingReview')
    : transcribing
      ? t('chat.hintTranscribing')
      : listening
        ? t('chat.hintListening')
        : t('chat.hintDefault');

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
              {t('nav.assistant')}
            </span>
            <IconButton
              icon="volume-2"
              label={voiceRepliesEnabled ? t('chat.voiceRepliesOn') : t('chat.voiceRepliesOff')}
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
          {turns.map((turn, i) => (
            <ChatMessage key={i} role={turn.role} time={turn.time}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {turn.body}
                {turn.table && <DataTable columns={turn.table.columns} rows={turn.table.rows} />}
              </div>
            </ChatMessage>
          ))}

          {pendingReview && (
            <ChatMessage role="assistant" time={nowLabel()}>
              <FraudForm
                record={pendingReview.record}
                reviewStatus={pendingReview.reviewStatus}
                onConfirm={confirmReview}
                onRequestReview={requestReviewFields}
                submitting={busy}
              />
            </ChatMessage>
          )}

          {busy && !pendingReview && (
            <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', paddingLeft: 44 }}>
              <Spinner label={t('chat.thinking')} />
            </div>
          )}
        </div>
      </div>
      <div style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--white)', padding: 'var(--space-4) var(--space-8) var(--space-6)' }}>
        <div style={{ maxWidth: 820, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {error && <Alert tone="danger" title={t('chat.errorTitle')}>{error}</Alert>}
          <ChatComposer
            value={composerText}
            onChange={setComposerText}
            onSend={ask}
            onMicToggle={handleMicToggle}
            listening={listening}
            disabled={busy || transcribing || !!pendingReview}
            hint={composerHint}
          />
        </div>
      </div>
    </div>
  );
}
