import React from 'react';
import { Icon } from '../core/Icon.jsx';

/** Vertical checklist of sequential security stages (camera → detection → liveness → identity). */
export function StatusSteps({ steps = [], current = 0, failed, style, ...rest }) {
  return (
    <ol {...rest} style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', ...style }}>
      {steps.map((label, i) => {
        const done = i < current;
        const active = i === current;
        const isFailed = failed && active;
        const fg = isFailed ? 'var(--danger)' : done ? 'var(--success)' : active ? 'var(--etax-navy)' : 'var(--gray-400)';
        return (
          <li key={label} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <span style={{
              width: 20, height: 20, flex: 'none', borderRadius: 'var(--radius-pill)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              border: `1px solid ${done || isFailed ? fg : active ? 'var(--etax-navy)' : 'var(--border-default)'}`,
              background: done ? 'var(--success)' : isFailed ? 'var(--danger)' : 'var(--white)',
            }}>
              {done && <Icon name="check" size={12} color="var(--white)" />}
              {isFailed && <Icon name="x" size={12} color="var(--white)" />}
              {active && !isFailed && <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--etax-navy)', animation: 'etaxPulse var(--dur-pulse) var(--ease-in-out) infinite' }} />}
            </span>
            <span style={{ fontSize: 'var(--text-body-sm)', fontWeight: active ? 'var(--fw-semibold)' : 'var(--fw-regular)', color: active || done ? 'var(--text-strong)' : 'var(--text-muted)' }}>{label}</span>
          </li>
        );
      })}
      <style>{'@keyframes etaxPulse{0%,100%{opacity:1}50%{opacity:.25}}'}</style>
    </ol>
  );
}
