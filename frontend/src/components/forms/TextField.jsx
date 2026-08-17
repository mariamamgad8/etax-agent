import React from 'react';
import { Icon } from '../core/Icon.jsx';

/** Labelled text input with optional hint, error and password reveal. */
export function TextField({ label, type = 'text', hint, error, required, id, revealable, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const [shown, setShown] = React.useState(false);
  const fid = id || `f-${label ? label.toLowerCase().replace(/[^a-z]+/g, '-') : 'field'}`;
  const inputType = revealable && shown ? 'text' : type;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', ...style }}>
      {label && (
        <label htmlFor={fid} style={{ fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-strong)' }}>
          {label}{required && <span style={{ color: 'var(--etax-red)' }}> *</span>}
        </label>
      )}
      <div style={{ position: 'relative', display: 'flex' }}>
        <input
          id={fid} type={inputType} {...rest}
          onFocus={(e) => { setFocus(true); rest.onFocus && rest.onFocus(e); }}
          onBlur={(e) => { setFocus(false); rest.onBlur && rest.onBlur(e); }}
          style={{
            width: '100%', height: 'var(--control-h-md)', padding: `0 ${revealable ? '40px' : 'var(--space-3)'} 0 var(--space-3)`,
            fontFamily: 'var(--font-body)', fontSize: 'var(--text-body-md)', color: 'var(--text-strong)',
            background: 'var(--white)', borderRadius: 'var(--radius-sm)',
            border: `1px solid ${error ? 'var(--danger)' : focus ? 'var(--border-focus)' : 'var(--border-default)'}`,
            boxShadow: focus ? 'var(--focus-ring)' : 'none', outline: 'none',
            transition: 'border-color var(--dur-fast) var(--ease-standard),box-shadow var(--dur-fast) var(--ease-standard)',
          }}
        />
        {revealable && (
          <button type="button" onClick={() => setShown((s) => !s)} aria-label={shown ? 'Hide password' : 'Show password'}
            style={{ position: 'absolute', right: 0, top: 0, height: '100%', width: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-500)' }}>
            <Icon name={shown ? 'eye-off' : 'eye'} size={17} />
          </button>
        )}
      </div>
      {(error || hint) && (
        <span style={{ fontSize: 'var(--text-caption)', color: error ? 'var(--danger)' : 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)' }}>
          {error && <Icon name="circle-alert" size={13} />}{error || hint}
        </span>
      )}
    </div>
  );
}
