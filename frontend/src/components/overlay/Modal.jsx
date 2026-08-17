import React from 'react';
import { IconButton } from '../core/IconButton.jsx';

/** Centered dialog on a navy scrim. */
export function Modal({ open = true, title, description, footer, width = 560, onClose, children, style, ...rest }) {
  if (!open) return null;
  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'var(--overlay-scrim)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: 'var(--space-12) var(--space-4)', overflowY: 'auto', zIndex: 40 }}
      onClick={(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}
    >
      <div role="dialog" aria-modal="true" aria-label={title} {...rest}
        style={{ width: '100%', maxWidth: width, background: 'var(--white)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-modal)', ...style }}>
        <header style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-4)', padding: 'var(--space-5) var(--space-6)', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <h2 style={{ fontSize: 'var(--text-h2)' }}>{title}</h2>
            {description && <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>{description}</p>}
          </div>
          {onClose && <IconButton icon="x" label="Close" tone="ghost" size="sm" onClick={onClose} />}
        </header>
        <div style={{ padding: 'var(--space-6)' }}>{children}</div>
        {footer && (
          <footer style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', padding: 'var(--space-4) var(--space-6)', borderTop: '1px solid var(--border-subtle)', background: 'var(--gray-25)', borderRadius: '0 0 var(--radius-md) var(--radius-md)' }}>{footer}</footer>
        )}
      </div>
    </div>
  );
}
