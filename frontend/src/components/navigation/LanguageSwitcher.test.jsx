import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';
import { LanguageSwitcher } from './LanguageSwitcher.jsx';

beforeEach(() => {
  localStorage.clear();
});

describe('LanguageSwitcher', () => {
  it('renders the visible العربية | English control', () => {
    render(
      <LanguageProvider>
        <LanguageSwitcher />
      </LanguageProvider>,
    );
    expect(screen.getByText('العربية')).toBeInTheDocument();
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('switches the document to RTL/Arabic when العربية is clicked', async () => {
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <LanguageSwitcher />
      </LanguageProvider>,
    );
    await user.click(screen.getByText('العربية'));
    expect(document.documentElement.dir).toBe('rtl');
    expect(document.documentElement.lang).toBe('ar');
  });

  it('switches back to LTR/English when English is clicked', async () => {
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <LanguageSwitcher />
      </LanguageProvider>,
    );
    await user.click(screen.getByText('العربية'));
    await user.click(screen.getByText('English'));
    expect(document.documentElement.dir).toBe('ltr');
    expect(document.documentElement.lang).toBe('en');
  });
});
