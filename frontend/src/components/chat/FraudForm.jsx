import React from 'react';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { Button } from '../core/Button.jsx';
import { Alert } from '../feedback/Alert.jsx';
import { Checkbox } from '../forms/Checkbox.jsx';

function fieldLabel(name) {
  return name.replace(/_/g, ' ');
}

/**
 * The fraud-assessment review card — read-only. Every value comes straight
 * from the user's linked tax.fraud_records row (see app.chat.fraud.records),
 * never typed/pasted into the chat. The user either confirms it as-is (runs
 * the risk assessment) or flags specific values as wrong (submits them for
 * the tax authority to review — this app never lets the user edit the
 * stored values directly).
 */
export function FraudForm({ record, reviewStatus, onConfirm, onRequestReview, submitting }) {
  const { t } = useLanguage();
  const [flagged, setFlagged] = React.useState(() => new Set());

  const toggleFlag = (name) => {
    setFlagged((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const entries = Object.entries(record || {});

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', width: '100%' }}>
      <div>
        <h4 style={{ margin: '0 0 var(--space-1)', fontSize: 'var(--text-body-md)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-strong)' }}>
          {t('fraud.reviewTitle')}
        </h4>
        <p style={{ margin: '0 0 var(--space-1)', fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>
          {t('fraud.reviewSubtitle')}
        </p>
        <p style={{ margin: 0, fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>
          {t('fraud.reviewStatusLabel')} {t(`fraud.status.${reviewStatus}`)}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2) var(--space-4)' }}>
        {entries.map(([name, value]) => (
          <div key={name}>
            <Checkbox
              id={`flag-${name}`}
              checked={flagged.has(name)}
              onChange={() => toggleFlag(name)}
              label={`${fieldLabel(name)}: ${value}`}
            />
          </div>
        ))}
      </div>

      {flagged.size > 0 && (
        <Alert tone="info" title={t('fraud.flaggedNoticeTitle')}>
          {t('fraud.flaggedNoticeBody', { count: flagged.size })}
        </Alert>
      )}

      <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
        <Button type="button" disabled={submitting} onClick={() => onConfirm()}>
          {submitting ? t('fraud.submitting') : t('fraud.showRiskScore')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={submitting || flagged.size === 0}
          onClick={() => onRequestReview(Array.from(flagged))}
        >
          {t('fraud.requestReview')}
        </Button>
      </div>
    </div>
  );
}
