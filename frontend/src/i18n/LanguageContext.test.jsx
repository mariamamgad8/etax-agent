import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanguageProvider, useLanguage } from './LanguageContext.jsx';

function Probe() {
  const { language, setLanguage, t, isRtl } = useLanguage();
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="isRtl">{String(isRtl)}</span>
      <span data-testid="greeting">{t('nav.login')}</span>
      <button onClick={() => setLanguage('ar')}>go-ar</button>
      <button onClick={() => setLanguage('en')}>go-en</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.lang = '';
  document.documentElement.dir = '';
});

describe('LanguageProvider / useLanguage', () => {
  it('defaults to English on first render (initial switch renders correctly)', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    expect(screen.getByTestId('language')).toHaveTextContent('en');
    expect(screen.getByTestId('greeting')).toHaveTextContent('Log in');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('renders English UI strings', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    expect(screen.getByTestId('greeting')).toHaveTextContent('Log in');
  });

  it('renders Arabic UI strings and switches lang/dir (RTL/LTR switching)', async () => {
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );

    await user.click(screen.getByText('go-ar'));

    expect(screen.getByTestId('language')).toHaveTextContent('ar');
    expect(screen.getByTestId('greeting')).toHaveTextContent('تسجيل الدخول');
    expect(screen.getByTestId('isRtl')).toHaveTextContent('true');
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');

    await user.click(screen.getByText('go-en'));
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('persists the selected language across a simulated refresh (remount)', async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    await user.click(screen.getByText('go-ar'));
    expect(localStorage.getItem('etax_ui_language')).toBe('ar');
    unmount();

    // A fresh mount reads from localStorage, simulating a page refresh.
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    expect(screen.getByTestId('language')).toHaveTextContent('ar');
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('falls back to English for an invalid stored value', () => {
    localStorage.setItem('etax_ui_language', 'fr');
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    expect(screen.getByTestId('language')).toHaveTextContent('en');
  });
});
