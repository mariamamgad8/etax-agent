import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { DataTable } from './DataTable.jsx';

beforeEach(() => {
  localStorage.clear();
});

describe('DataTable chrome localization', () => {
  it('shows an English empty state by default', () => {
    render(
      <LanguageProvider>
        <DataTable columns={['Taxpayer', 'Amount']} rows={[]} />
      </LanguageProvider>,
    );
    expect(screen.getByText('No records to show.')).toBeInTheDocument();
  });

  it('shows an Arabic empty state when the UI language is Arabic', () => {
    localStorage.setItem('etax_ui_language', 'ar');
    render(
      <LanguageProvider>
        <DataTable columns={['Taxpayer', 'Amount']} rows={[]} />
      </LanguageProvider>,
    );
    expect(screen.getByText('لا توجد سجلات لعرضها.')).toBeInTheDocument();
  });

  it('renders the caller-supplied data (columns/rows) unchanged regardless of UI language', () => {
    localStorage.setItem('etax_ui_language', 'ar');
    render(
      <LanguageProvider>
        <DataTable columns={['Taxpayer']} rows={[['Ahmed Ali']]} />
      </LanguageProvider>,
    );
    // Column headers and row data are caller-supplied real data, never translated.
    expect(screen.getByText('Taxpayer')).toBeInTheDocument();
    expect(screen.getByText('Ahmed Ali')).toBeInTheDocument();
  });
});
