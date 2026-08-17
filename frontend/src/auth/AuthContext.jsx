import React from 'react';

const STORAGE_KEY = 'etax_auth';
const AuthContext = React.createContext(null);

function loadStored() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = React.useState(loadStored);

  const persist = (next) => {
    setAuth(next);
    if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(STORAGE_KEY);
  };

  // Accepts an auth-stage response ({access_token, stage, user?}); keeps the
  // previously known user if this response didn't include one (face
  // enroll/verify responses only return a new token + stage).
  const setSession = (response) => {
    persist({
      token: response.access_token,
      stage: response.stage,
      user: response.user ?? auth?.user ?? null,
    });
  };

  const signOut = () => persist(null);

  const value = { auth, setSession, signOut };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
