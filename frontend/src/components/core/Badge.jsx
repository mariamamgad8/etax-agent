import React from 'react';

const tones = {
  neutral: { background: 'var(--gray-100)', color: 'var(--gray-700)', border: 'var(--gray-200)' },
  navy: { background: 'var(--etax-navy-50)', color: 'var(--etax-navy)', border: 'var(--etax-navy-100)' },
  success: { background: 'var(--success-100)', color: 'var(--success)', border: '#bfe3ce' },
  warning: { background: 'var(--warning-100)', color: 'var(--warning)', border: '#f0d9a8' },
  danger: { background: 'var(--danger-100)', color: 'var(--danger)', border: '#f6c9c8' },
};

/** Small status label. Square-ish (2px radius) — pills are reserved for filter chips. */
export function Badge({ tone = 'neutral', children, style, ...rest }) {
  const t = tones[tone];
  return (
    <span
      {...rest}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)',
        padding: '2px var(--space-2)', borderRadius: 'var(--radius-xs)',
        background: t.background, color: t.color, border: `1px solid ${t.border}`,
        fontSize: 'var(--text-caption)', fontWeight: 'var(--fw-semibold)', letterSpacing: '0.02em', whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  );
}
