import React from 'react';

/** Determinate-looking activity indicator: a 2px navy arc. */
export function Spinner({ size = 18, color = 'var(--etax-navy)', label, style, ...rest }) {
  return (
    <span {...rest} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)', ...style }}>
      <span style={{
        width: size, height: size, flex: 'none', borderRadius: '50%',
        border: `2px solid ${color}`, borderTopColor: 'transparent', borderRightColor: 'transparent',
        animation: 'etaxSpin 700ms linear infinite',
      }} />
      {label && <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>{label}</span>}
      <style>{'@keyframes etaxSpin{to{transform:rotate(360deg)}}'}</style>
    </span>
  );
}
