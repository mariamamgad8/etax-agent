import React from 'react';
import { Icon } from '../core/Icon.jsx';

const tones = {
  info: { bg: 'var(--info-100)', border: '#c9d7ec', fg: 'var(--info)', icon: 'info' },
  success: { bg: 'var(--success-100)', border: '#bfe3ce', fg: 'var(--success)', icon: 'circle-check' },
  warning: { bg: 'var(--warning-100)', border: '#f0d9a8', fg: 'var(--warning)', icon: 'triangle-alert' },
  danger: { bg: 'var(--danger-100)', border: '#f6c9c8', fg: 'var(--danger)', icon: 'circle-alert' },
};

/** Inline message block for form errors, security notices and verification failures. */
export function Alert({ tone = 'info', title, children, action, style, ...rest }) {
  const t = tones[tone];
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} {...rest}
      style={{ display: 'flex', gap: 'var(--space-3)', padding: 'var(--space-3) var(--space-4)', background: t.bg, border: `1px solid ${t.border}`, borderRadius: 'var(--radius-sm)', ...style }}>
      <Icon name={t.icon} size={18} color={t.fg} style={{ marginTop: 1 }} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        {title && <strong style={{ fontSize: 'var(--text-body-sm)', color: t.fg, fontWeight: 'var(--fw-semibold)' }}>{title}</strong>}
        {children && <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--gray-700)' }}>{children}</div>}
      </div>
      {action}
    </div>
  );
}
