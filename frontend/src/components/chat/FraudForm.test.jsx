import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { FraudForm } from './FraudForm.jsx';

const SCHEMA_INFO = {
  numeric_fields: ['Net_Profit', 'Taxable_Income', 'Years_in_Business'],
  integer_fields: ['Years_in_Business'],
  categorical_fields: { Industry_Risk: ['Low', 'Medium', 'High'] },
  required_fields: ['Net_Profit', 'Taxable_Income', 'Industry_Risk'],
  optional_fields: ['Years_in_Business'],
};

beforeEach(() => {
  localStorage.clear();
});

describe('FraudForm localization', () => {
  it('renders English section labels and submit button by default', () => {
    render(
      <LanguageProvider>
        <FraudForm fields={{}} errors={[]} schemaInfo={SCHEMA_INFO} onSubmit={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    expect(screen.getByText('Required Assessment Fields')).toBeInTheDocument();
    expect(screen.getByText(/Advanced Optional Fields/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run fraud assessment' })).toBeInTheDocument();
  });

  it('renders Arabic section labels and submit button when the UI language is Arabic', () => {
    localStorage.setItem('etax_ui_language', 'ar');
    render(
      <LanguageProvider>
        <FraudForm fields={{}} errors={[]} schemaInfo={SCHEMA_INFO} onSubmit={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    expect(screen.getByText('حقول التقييم المطلوبة')).toBeInTheDocument();
    expect(screen.getByText(/حقول اختيارية متقدمة/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'تشغيل تقييم الاحتيال' })).toBeInTheDocument();
  });

  it('keeps the backend-supplied field identifier as-is in both languages (never translated)', () => {
    localStorage.setItem('etax_ui_language', 'ar');
    render(
      <LanguageProvider>
        <FraudForm fields={{}} errors={[]} schemaInfo={SCHEMA_INFO} onSubmit={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    // "Net Profit" (from Net_Profit) is a technical field identifier, not UI chrome.
    expect(screen.getByText(/Net Profit/)).toBeInTheDocument();
  });
});
