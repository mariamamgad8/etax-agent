import React from 'react';

/** Plain records table: 1px rules, tabular numerals, no zebra striping. */
export function DataTable({ columns = [], rows = [], caption, style, ...rest }) {
  const align = (c) => (typeof c === 'object' && c.numeric ? 'right' : 'left');
  const label = (c) => (typeof c === 'string' ? c : c.label);
  return (
    <div {...rest} style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', ...style }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-body-sm)' }}>
        {caption && <caption style={{ captionSide: 'top', textAlign: 'left', padding: 'var(--space-3) var(--space-4)', background: 'var(--gray-25)', borderBottom: '1px solid var(--border-subtle)', fontSize: 'var(--text-caption)', color: 'var(--text-muted)' }}>{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i} style={{ textAlign: align(c), padding: 'var(--space-3) var(--space-4)', background: 'var(--gray-50)', borderBottom: '1px solid var(--border-default)', color: 'var(--gray-600)', fontSize: 'var(--text-overline)', letterSpacing: 'var(--ls-overline)', textTransform: 'uppercase', fontWeight: 'var(--fw-semibold)' }}>{label(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((cell, ci) => (
                <td key={ci} style={{
                  padding: 'var(--space-3) var(--space-4)', borderBottom: ri === rows.length - 1 ? 'none' : '1px solid var(--border-subtle)',
                  textAlign: align(columns[ci]), color: 'var(--gray-800)',
                  fontFamily: align(columns[ci]) === 'right' ? 'var(--font-mono)' : 'var(--font-body)',
                  fontVariantNumeric: 'tabular-nums',
                }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
