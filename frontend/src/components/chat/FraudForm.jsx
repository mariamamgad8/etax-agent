import React from 'react';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { Button } from '../core/Button.jsx';
import { Alert } from '../feedback/Alert.jsx';
import { Select } from '../forms/Select.jsx';
import { TextField } from '../forms/TextField.jsx';

const CATEGORICAL_LABELS = {
  Business_Type: 'Business type',
  Region: 'Region',
  Industry_Risk: 'Industry risk',
};

function fieldLabel(name) {
  return name.replace(/_/g, ' ');
}

function isEmpty(value) {
  return value === undefined || value === null || value === '';
}

/**
 * The fraud-assessment review form — always shown before a prediction runs,
 * prefilled with whatever the assistant extracted from the message, with
 * every field still editable. schemaInfo comes straight from the backend
 * interrupt payload (categorical options, which fields are integer-only,
 * and the required/optional split), so none of this ever drifts out of sync
 * with the trained model or hand-duplicates its rules.
 *
 * Interface chrome (section titles, the Required badge, buttons) is
 * localized via useLanguage(); the individual field names themselves
 * (Net_Profit, Industry_Risk, ...) are the backend schema's own technical
 * identifiers and stay as-is in both languages — same convention as
 * taxpayer IDs/business terms elsewhere in this app.
 *
 * Two visible sections, never described to the user as anything to do with
 * models: the 8 required fields are enough to run an assessment on their
 * own; the rest are optional and unlock a more complete one.
 */
export function FraudForm({ fields, errors, schemaInfo, onSubmit, submitting }) {
  const { t } = useLanguage();
  const [values, setValues] = React.useState(() => ({ ...fields }));
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [touched, setTouched] = React.useState(false);

  // A prefill/merge from the chat (see ChatPage.jsx) replaces `fields` in
  // place — pick that up without clobbering what the user has since typed
  // directly into the form.
  const prevFieldsRef = React.useRef(fields);
  React.useEffect(() => {
    if (fields !== prevFieldsRef.current) {
      setValues((v) => ({ ...fields, ...v }));
      prevFieldsRef.current = fields;
    }
  }, [fields]);

  const requiredFields = schemaInfo.required_fields || [];
  const optionalFields = schemaInfo.optional_fields || [];
  const isRequired = (name) => requiredFields.includes(name);
  const isCategorical = (name) => name in schemaInfo.categorical_fields;

  const update = (name) => (e) => {
    const raw = e.target.value;
    setValues((v) => ({ ...v, [name]: raw }));
  };

  const missingRequired = requiredFields.filter((name) => isEmpty(values[name]));

  const submit = (e) => {
    e.preventDefault();
    setTouched(true);
    if (missingRequired.length > 0) return;
    const payload = {};
    for (const [key, raw] of Object.entries(values)) {
      if (raw === '' || raw === undefined || raw === null) continue;
      payload[key] = schemaInfo.numeric_fields.includes(key) ? Number(raw) : raw;
    }
    onSubmit(payload);
  };

  const renderField = (name) => {
    const required = isRequired(name);
    // Shown as soon as a required field is empty, not just after a failed
    // submit — the point is an at-a-glance "what's still missing" signal
    // while reviewing the prefilled form, especially since more values can
    // arrive by typing into the chat (see ChatPage.jsx) rather than typing
    // directly into the field.
    const missing = required && isEmpty(values[name]);
    const fieldError = missing ? t('fraud.required') : undefined;
    if (isCategorical(name)) {
      return (
        <Select
          key={name}
          label={CATEGORICAL_LABELS[name] || fieldLabel(name)}
          required={required}
          error={fieldError}
          value={values[name] ?? ''}
          onChange={update(name)}
          options={[{ value: '', label: t('fraud.selectPlaceholder') }, ...schemaInfo.categorical_fields[name]]}
        />
      );
    }
    return (
      <TextField
        key={name}
        label={fieldLabel(name)}
        required={required}
        error={fieldError}
        type="number"
        step={schemaInfo.integer_fields.includes(name) ? '1' : 'any'}
        value={values[name] ?? ''}
        onChange={update(name)}
      />
    );
  };

  // Field order within each section: categorical fields from schemaInfo
  // first, then numeric — matches how the backend lists them.
  const orderFields = (names) => [
    ...Object.keys(schemaInfo.categorical_fields).filter((n) => names.includes(n)),
    ...schemaInfo.numeric_fields.filter((n) => names.includes(n)),
  ];

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', width: '100%' }}>
      {errors && errors.length > 0 && (
        <Alert tone="danger" title={t('fraud.checkTheseFields')}>
          <ul style={{ margin: 0, paddingInlineStart: 'var(--space-4)' }}>
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Alert>
      )}
      {touched && missingRequired.length > 0 && (
        <Alert tone="danger" title={t('fraud.completeRequiredTitle')}>
          {missingRequired.length === 1
            ? t('fraud.completeRequiredBodyOne')
            : t('fraud.completeRequiredBodyMany', { count: missingRequired.length })}
        </Alert>
      )}

      <div>
        <h4 style={{ margin: '0 0 var(--space-1)', fontSize: 'var(--text-body-md)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-strong)' }}>
          {t('fraud.requiredFieldsTitle')}
        </h4>
        <p style={{ margin: '0 0 var(--space-3)', fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>
          {t('fraud.requiredFieldsSubtitle')}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3) var(--space-4)' }}>
          {orderFields(requiredFields).map(renderField)}
        </div>
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced((s) => !s)}
          style={{
            display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'none', border: 'none',
            cursor: 'pointer', padding: 0, fontSize: 'var(--text-body-sm)', fontWeight: 'var(--fw-semibold)',
            color: 'var(--etax-navy)',
          }}
        >
          {showAdvanced ? '▾' : '▸'} {t('fraud.advancedFieldsToggle')}
        </button>
        <p style={{ margin: 'var(--space-1) 0 var(--space-3)', fontSize: 'var(--text-body-sm)', color: 'var(--text-muted)' }}>
          {t('fraud.advancedFieldsSubtitle')}
        </p>
        {showAdvanced && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3) var(--space-4)' }}>
            {orderFields(optionalFields).map(renderField)}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
        <Button type="submit" disabled={submitting}>
          {submitting ? t('fraud.submitting') : t('fraud.submit')}
        </Button>
      </div>
    </form>
  );
}
