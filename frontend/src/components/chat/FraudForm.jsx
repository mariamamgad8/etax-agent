import React from 'react';
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

/**
 * The fraud-assessment review form — always shown before a prediction runs,
 * prefilled with whatever the assistant extracted from the message, with
 * every field still editable. schemaInfo comes straight from the backend
 * interrupt payload (categorical options + which fields are integer-only),
 * so the option lists never drift out of sync with the trained model.
 */
export function FraudForm({ fields, errors, schemaInfo, onSubmit, submitting }) {
  const [values, setValues] = React.useState(() => ({ ...fields }));

  const update = (name) => (e) => {
    const raw = e.target.value;
    setValues((v) => ({ ...v, [name]: raw }));
  };

  const submit = (e) => {
    e.preventDefault();
    const payload = {};
    for (const [key, raw] of Object.entries(values)) {
      if (raw === '' || raw === undefined || raw === null) continue;
      payload[key] = schemaInfo.numeric_fields.includes(key) ? Number(raw) : raw;
    }
    onSubmit(payload);
  };

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', width: '100%' }}>
      {errors && errors.length > 0 && (
        <Alert tone="danger" title="Check these fields">
          <ul style={{ margin: 0, paddingLeft: 'var(--space-4)' }}>
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Alert>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3) var(--space-4)' }}>
        {Object.entries(schemaInfo.categorical_fields).map(([name, options]) => (
          <Select
            key={name}
            label={CATEGORICAL_LABELS[name] || fieldLabel(name)}
            required
            value={values[name] ?? ''}
            onChange={update(name)}
            options={[{ value: '', label: 'Select…' }, ...options]}
          />
        ))}
        {schemaInfo.numeric_fields.map((name) => (
          <TextField
            key={name}
            label={fieldLabel(name)}
            required
            type="number"
            step={schemaInfo.integer_fields.includes(name) ? '1' : 'any'}
            value={values[name] ?? ''}
            onChange={update(name)}
          />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Checking…' : 'Run fraud assessment'}
        </Button>
      </div>
    </form>
  );
}
