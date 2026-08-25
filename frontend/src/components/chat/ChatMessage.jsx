import React from 'react';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { Icon } from '../core/Icon.jsx';
import { IconButton } from '../core/IconButton.jsx';

/** One turn in the conversation. Assistant turns are white panels; user turns are navy-tinted blocks. */
export function ChatMessage({ role = 'assistant', name, time, speakable, playing, onPlay, children, style, ...rest }) {
  const { t } = useLanguage();
  const isUser = role === 'user';
  return (
    <article {...rest} style={{ display: 'flex', gap: 'var(--space-3)', flexDirection: isUser ? 'row-reverse' : 'row', ...style }}>
      <span style={{
        width: 32, height: 32, flex: 'none', borderRadius: 'var(--radius-sm)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: isUser ? 'var(--gray-200)' : 'var(--etax-navy)', color: isUser ? 'var(--gray-600)' : 'var(--white)',
      }}>
        <Icon name={isUser ? 'user' : 'landmark'} size={16} />
      </span>
      <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'baseline' }}>
          <span style={{ fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-strong)' }}>{name || (isUser ? t('chat.senderYou') : t('chat.senderAssistant'))}</span>
          {time && <span style={{ fontSize: 'var(--text-caption)', color: 'var(--text-muted)' }} className="etax-mono">{time}</span>}
        </div>
        <div style={{
          padding: 'var(--space-4)', borderRadius: 'var(--radius-md)', fontSize: 'var(--text-body-md)', lineHeight: 'var(--lh-normal)', color: 'var(--gray-800)',
          background: isUser ? 'var(--etax-navy-50)' : 'var(--white)',
          border: `1px solid ${isUser ? 'var(--etax-navy-100)' : 'var(--border-subtle)'}`,
        }}>
          {children}
        </div>
        {speakable && !isUser && (
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <IconButton icon={playing ? 'pause' : 'volume-2'} label={playing ? t('chat.stopPlayback') : t('chat.readAloud')} size="sm" tone="ghost" active={playing} onClick={onPlay} />
          </div>
        )}
      </div>
    </article>
  );
}
