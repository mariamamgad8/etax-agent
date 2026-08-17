import React from 'react';
import { Icon } from '../core/Icon.jsx';

/** Labelled native select with the eTax chevron affordance. */
export function Select({ label, options = [], hint, error, required, id, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const fid = id || `s-${label ? label.toLowerCase().replace(/[^a-z]+/g, '-') : 'select'}`;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', ...style }}>
      {label && (
        <label htmlFor={fid} style={{ fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-strong)' }}>
          {label}{required && <span style={{ color: 'var(--etax-red)' }}> *</span>}
        </label>
      )}
      <div style={{ position: 'relative', display: 'flex' }}>
        <select
          id={fid} {...rest}
          onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
          style={{
            width: '100%', height: 'var(--control-h-md)', padding: '0 36px 0 var(--space-3)', appearance: 'none',
            fontFamily: 'var(--font-body)', fontSize: 'var(--text-body-md)', color: 'var(--text-strong)',
            background: 'var(--white)', borderRadius: 'var(--radius-sm)',
            border: `1px solid ${error ? 'var(--danger)' : focus ? 'var(--border-focus)' : 'var(--border-default)'}`,
            boxShadow: focus ? 'var(--focus-ring)' : 'none', outline: 'none', cursor: 'pointer',
          }}
        >
          {options.map((o) => {
            const value = typeof o === 'string' ? o : o.value;
            const text = typeof o === 'string' ? o : o.label;
            return <option key={value} value={value}>{text}</option>;
          })}
        </select>
        <Icon name="chevron-down" size={16} color="var(--gray-500)" style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
      </div>
      {(error || hint) && <span style={{ fontSize: 'var(--text-caption)', color: error ? 'var(--danger)' : 'var(--text-muted)' }}>{error || hint}</span>}
    </div>
  );
}
