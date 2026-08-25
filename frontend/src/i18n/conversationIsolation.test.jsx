import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanguageProvider, useLanguage } from './LanguageContext.jsx';

// Mirrors the real ChatPage.jsx shape: conversation state (`turns`) is
// ordinary React state set once from the user's own message or the
// backend's own per-turn response, never derived from useLanguage()'s `t`.
// UI chrome (the composer hint below) is the only thing that reads `t`.
function ChatLikeHarness() {
  const { t, setLanguage } = useLanguage();
  const [turns] = React.useState([
    { role: 'assistant', body: 'Welcome. Ask about tax records...' },
    { role: 'user', body: 'مرحبا, عايز أعرف الضرايب بتاعتي' },
  ]);
  return (
    <div>
      <ul>
        {turns.map((turn, i) => (
          <li key={i} data-testid={`turn-${i}`}>{turn.body}</li>
        ))}
      </ul>
      <span data-testid="composer-hint">{t('chat.hintDefault')}</span>
      <button onClick={() => setLanguage('ar')}>switch-to-arabic</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe('UI language switch does not touch conversation content', () => {
  it('leaves existing conversation turns exactly as they were after switching the UI language', async () => {
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <ChatLikeHarness />
      </LanguageProvider>,
    );

    const turn0Before = screen.getByTestId('turn-0').textContent;
    const turn1Before = screen.getByTestId('turn-1').textContent;
    expect(screen.getByTestId('composer-hint')).toHaveTextContent(
      'Answers cover records you are authorized to access. Every retrieval is logged against your session.',
    );

    await user.click(screen.getByText('switch-to-arabic'));

    // UI chrome (composer hint) DID switch language...
    expect(screen.getByTestId('composer-hint')).toHaveTextContent(
      'الإجابات تغطي السجلات المصرح لك بالاطلاع عليها. كل عملية استرجاع تُسجَّل على جلستك.',
    );
    // ...but the conversation content is byte-for-byte unchanged, including
    // the Arabic user message that was already there before the UI toggle
    // (proving the toggle doesn't "helpfully" retranslate anything).
    expect(screen.getByTestId('turn-0')).toHaveTextContent(turn0Before);
    expect(screen.getByTestId('turn-1')).toHaveTextContent(turn1Before);
  });
});
