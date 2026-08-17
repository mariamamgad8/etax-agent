import React from 'react';

const base = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-2)',
  fontFamily: 'var(--font-body)', fontWeight: 'var(--fw-semibold)', letterSpacing: '0.01em',
  border: '1px solid transparent', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
  transition: 'background-color var(--dur-fast) var(--ease-standard),border-color var(--dur-fast) var(--ease-standard),color var(--dur-fast) var(--ease-standard)',
  textDecoration: 'none', whiteSpace: 'nowrap',
};
const sizes = {
  sm: { height: 'var(--control-h-sm)', padding: '0 var(--space-3)', fontSize: 'var(--text-body-sm)' },
  md: { height: 'var(--control-h-md)', padding: '0 var(--space-5)', fontSize: 'var(--text-body-md)' },
  lg: { height: 'var(--control-h-lg)', padding: '0 var(--space-6)', fontSize: 'var(--text-body-lg)' },
};
const variants = {
  primary: { background: 'var(--action-primary)', color: 'var(--text-inverse)' },
  accent: { background: 'var(--action-accent)', color: 'var(--text-inverse)' },
  secondary: { background: 'var(--white)', color: 'var(--etax-navy)', borderColor: 'var(--border-default)' },
  ghost: { background: 'transparent', color: 'var(--etax-navy-600)' },
  danger: { background: 'var(--white)', color: 'var(--danger)', borderColor: 'var(--danger)' },
};
const hovers = {
  primary: { background: 'var(--action-primary-hover)' },
  accent: { background: 'var(--action-accent-hover)' },
  secondary: { background: 'var(--gray-50)', borderColor: 'var(--border-strong)' },
  ghost: { background: 'var(--etax-navy-50)' },
  danger: { background: 'var(--danger-100)' },
};

/** Primary text action. Navy = default commit action, red = single highest-stakes action per screen. */
export function Button({ variant = 'primary', size = 'md', fullWidth, disabled, as = 'button', children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const Tag = as;
  return (
    <Tag
      {...rest}
      disabled={Tag === 'button' ? disabled : undefined}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        ...base, ...sizes[size], ...variants[variant],
        ...(hover && !disabled ? hovers[variant] : null),
        width: fullWidth ? '100%' : undefined,
        opacity: disabled ? 0.45 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}
