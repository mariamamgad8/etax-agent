import React from 'react';
import { IconButton } from '../core/IconButton.jsx';

/** Message composer with microphone and send controls, plus the listening state. */
export function ChatComposer({ placeholder = 'Ask about tax data or request a tax prediction…', value, onChange, onSend, onMicToggle, listening, disabled, hint, style, ...rest }) {
  const [text, setText] = React.useState('');
  const controlled = value !== undefined;
  const v = controlled ? value : text;
  const set = (nv) => { if (!controlled) setText(nv); onChange && onChange(nv); };
  const send = () => { if (v && v.trim() && onSend) onSend(v.trim()); set(''); };
  return (
    <div {...rest} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', ...style }}>
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 'var(--space-2)', padding: 'var(--space-2)',
        background: 'var(--white)', border: `1px solid ${listening ? 'var(--etax-red)' : 'var(--border-default)'}`,
        borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sm)',
        transition: 'border-color var(--dur-fast) var(--ease-standard)',
      }}>
        <textarea
          rows={1} value={v} disabled={disabled}
          placeholder={listening ? 'Listening…' : placeholder}
          onChange={(e) => set(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          style={{
            flex: 1, resize: 'none', border: 'none', outline: 'none', background: 'transparent',
            fontFamily: 'var(--font-body)', fontSize: 'var(--text-body-md)', lineHeight: 'var(--lh-normal)',
            color: 'var(--text-strong)', padding: 'var(--space-2) var(--space-3)', maxHeight: 120,
          }}
        />
        <IconButton
          icon={listening ? 'square' : 'mic'}
          label={listening ? 'Stop listening' : 'Speak your question'}
          tone="ghost"
          active={listening}
          disabled={disabled && !listening}
          onClick={onMicToggle}
        />
        <IconButton icon="send" label="Send message" tone="navy" disabled={!v || !v.trim()} onClick={send} />
      </div>
      {hint && <span style={{ fontSize: 'var(--text-caption)', color: 'var(--text-muted)' }}>{hint}</span>}
    </div>
  );
}
