import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { FraudForm } from './FraudForm.jsx';

const RECORD = { Business_Type: 'Retail', Net_Profit: 1052937.1, Industry_Risk: 'Medium' };

beforeEach(() => {
  localStorage.clear();
});

describe('FraudForm (read-only review card)', () => {
  it('renders English chrome, the linked record values, and both actions by default', () => {
    render(
      <LanguageProvider>
        <FraudForm record={RECORD} reviewStatus="pending" onConfirm={vi.fn()} onRequestReview={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    expect(screen.getByText('Your Tax Record')).toBeInTheDocument();
    expect(screen.getByText(/Net Profit: 1052937.1/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show Risk Score' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request Review' })).toBeInTheDocument();
  });

  it('renders Arabic chrome when the UI language is Arabic', () => {
    localStorage.setItem('etax_ui_language', 'ar');
    render(
      <LanguageProvider>
        <FraudForm record={RECORD} reviewStatus="pending" onConfirm={vi.fn()} onRequestReview={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    expect(screen.getByText('سجلك الضريبي')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'عرض درجة المخاطر' })).toBeInTheDocument();
  });

  it('keeps the backend-supplied field identifier as-is in both languages (never translated)', () => {
    localStorage.setItem('etax_ui_language', 'ar');
    render(
      <LanguageProvider>
        <FraudForm record={RECORD} reviewStatus="pending" onConfirm={vi.fn()} onRequestReview={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    expect(screen.getByText(/Net Profit/)).toBeInTheDocument();
  });

  it('disables Request Review until at least one value is flagged', () => {
    render(
      <LanguageProvider>
        <FraudForm record={RECORD} reviewStatus="pending" onConfirm={vi.fn()} onRequestReview={vi.fn()} submitting={false} />
      </LanguageProvider>,
    );
    expect(screen.getByRole('button', { name: 'Request Review' })).toBeDisabled();
  });
});
