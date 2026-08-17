import React from 'react';

/** The eTax lockup. Uses the supplied PNG mark; on navy, set inverse to add the white wordmark treatment. */
export function Logo({ height = 32, src = '/assets/etax-logo.png', inverse, subtitle, style, ...rest }) {
  return (
    <span {...rest} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-3)', ...style }}>
      <img
        src={src} alt="eTax"
        style={{ height, width: 'auto', display: 'block', filter: inverse ? 'brightness(0) invert(1)' : undefined }}
      />
      {subtitle && (
        <>
          <span style={{ width: 1, height: height * 0.62, background: inverse ? 'rgba(255,255,255,.32)' : 'var(--border-default)' }} />
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-medium)', letterSpacing: '0.04em', textTransform: 'uppercase', color: inverse ? 'rgba(255,255,255,.86)' : 'var(--gray-600)' }}>{subtitle}</span>
        </>
      )}
    </span>
  );
}
