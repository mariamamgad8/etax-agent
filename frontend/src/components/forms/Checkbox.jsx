import React from 'react';
import { Icon } from '../core/Icon.jsx';

/** Square checkbox with inline label — used for consent and "remember this device". */
export function Checkbox({ label, checked, defaultChecked, onChange, id, disabled, style, ...rest }) {
  const controlled = checked !== undefined;
  const [on, setOn] = React.useState(!!defaultChecked);
  const isOn = controlled ? checked : on;
  const fid = id || `c-${label ? label.toLowerCase().replace(/[^a-z]+/g, '-').slice(0, 24) : 'check'}`;
  return (
    <label htmlFor={fid} style={{ display: 'inline-flex', gap: 'var(--space-3)', alignItems: 'flex-start', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1, ...style }}>
      <input
        id={fid} type="checkbox" checked={isOn} disabled={disabled} {...rest}
        onChange={(e) => { if (!controlled) setOn(e.target.checked); onChange && onChange(e); }}
        style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
      />
      <span style={{
        width: 18, height: 18, flex: 'none', marginTop: 2, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        borderRadius: 'var(--radius-xs)', border: `1px solid ${isOn ? 'var(--etax-navy)' : 'var(--border-default)'}`,
        background: isOn ? 'var(--etax-navy)' : 'var(--white)', transition: 'background-color var(--dur-fast) var(--ease-standard)',
      }}>
        {isOn && <Icon name="check" size={13} color="var(--white)" />}
      </span>
      <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-body)' }}>{label}</span>
    </label>
  );
}
