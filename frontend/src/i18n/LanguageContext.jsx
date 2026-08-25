import React from 'react';
import { DEFAULT_LANGUAGE, LANGUAGES, translate } from './translations.js';

// FRONTEND UI localization only — English/Arabic labels, buttons, direction.
// This is completely separate from the backend's per-turn assistant
// response-language feature (app.chat.state.AgentState.response_language),
// which decides what language the CHATBOT replies in based on what the user
// typed/said, independent of this toggle. Never derive one from the other:
// a user may leave the UI in Arabic and ask the assistant a question in
// English, and the assistant must still answer in English.
const STORAGE_KEY = 'etax_ui_language';
const LanguageContext = React.createContext(null);

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return LANGUAGES.includes(raw) ? raw : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = React.useState(loadStored);

  React.useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
    try {
      localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // localStorage unavailable (private mode, etc.) — the toggle still
      // works for the current page load, it just won't persist.
    }
  }, [language]);

  const setLanguage = (next) => {
    if (LANGUAGES.includes(next)) setLanguageState(next);
  };

  const t = React.useCallback((key, vars) => translate(language, key, vars), [language]);

  const value = { language, setLanguage, t, isRtl: language === 'ar' };
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const ctx = React.useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
}
