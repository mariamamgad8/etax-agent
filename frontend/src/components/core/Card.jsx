import React from 'react';

/** Flat white panel: 1px gray border, 6px radius, optional navy header rule. */
export function Card({ title, action, padding = 'var(--space-6)', accentTop, children, style, ...rest }) {
  return (
    <section
      {...rest}
      style={{
        background: 'var(--surface-card)', border: '1px solid var(--border-subtle)',
        borderTop: accentTop ? '3px solid var(--action-accent)' : '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sm)', ...style,
      }}
    >
      {title && (
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-4)', padding: `var(--space-4) ${padding}`, borderBottom: '1px solid var(--border-subtle)' }}>
          <h3 style={{ fontSize: 'var(--text-h3)' }}>{title}</h3>
          {action}
        </header>
      )}
      <div style={{ padding }}>{children}</div>
    </section>
  );
}
