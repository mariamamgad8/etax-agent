import React from 'react';
import { Icon } from './Icon.jsx';

const tones = {
  neutral: { background: 'var(--white)', color: 'var(--etax-navy)', borderColor: 'var(--border-default)' },
  navy: { background: 'var(--etax-navy)', color: 'var(--text-inverse)', borderColor: 'var(--etax-navy)' },
  accent: { background: 'var(--action-accent)', color: 'var(--text-inverse)', borderColor: 'var(--action-accent)' },
  ghost: { background: 'transparent', color: 'var(--gray-600)', borderColor: 'transparent' },
};
const sizes = { sm: 32, md: 40, lg: 48 };

/** Square icon-only control: composer mic/send, playback, header actions. */
export function IconButton({ icon, label, tone = 'neutral', size = 'md', active, disabled, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const px = sizes[size];
  const t = tones[tone];
  return (
    <button
      type="button" aria-label={label} title={label} disabled={disabled}
      {...rest}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        width: px, height: px, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        border: '1px solid', borderRadius: 'var(--radius-sm)', cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background-color var(--dur-fast) var(--ease-standard),border-color var(--dur-fast) var(--ease-standard)',
        ...t,
        ...(active ? { background: 'var(--etax-red-100)', color: 'var(--etax-red-700)', borderColor: 'var(--etax-red)' } : null),
        ...(hover && !disabled && !active ? { background: tone === 'neutral' || tone === 'ghost' ? 'var(--gray-100)' : tone === 'navy' ? 'var(--etax-navy-800)' : 'var(--action-accent-hover)' } : null),
        opacity: disabled ? 0.4 : 1,
        ...style,
      }}
    >
      <Icon name={icon} size={size === 'sm' ? 16 : size === 'lg' ? 22 : 18} />
    </button>
  );
}
