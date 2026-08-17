import React from 'react';

/** Suggested question the user can send with one click. */
export function SuggestionChip({ children, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button type="button" onClick={onClick} {...rest}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        textAlign: 'left', padding: 'var(--space-3) var(--space-4)', cursor: 'pointer',
        background: hover ? 'var(--etax-navy-50)' : 'var(--white)',
        border: `1px solid ${hover ? 'var(--etax-navy-100)' : 'var(--border-subtle)'}`,
        borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 'var(--text-body-sm)',
        color: 'var(--text-strong)', transition: 'background-color var(--dur-fast) var(--ease-standard),border-color var(--dur-fast) var(--ease-standard)',
        ...style,
      }}
    >
      {children}
    </button>
  );
}
