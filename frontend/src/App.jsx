import React from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext.jsx';
import { ProtectedRoute } from './auth/ProtectedRoute.jsx';
import { LanguageProvider } from './i18n/LanguageContext.jsx';
import { ChatPage } from './pages/ChatPage.jsx';
import { FaceEnrollmentPage } from './pages/FaceEnrollmentPage.jsx';
import { FaceVerificationPage } from './pages/FaceVerificationPage.jsx';
import { LandingPage } from './pages/LandingPage.jsx';
import { LoginPage } from './pages/LoginPage.jsx';
import { SignupPage } from './pages/SignupPage.jsx';

export function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/face-enrollment"
              element={(
                <ProtectedRoute stage="pending_enrollment">
                  <FaceEnrollmentPage />
                </ProtectedRoute>
              )}
            />
            <Route
              path="/face-verification"
              element={(
                <ProtectedRoute stage="face_required">
                  <FaceVerificationPage />
                </ProtectedRoute>
              )}
            />
            <Route
              path="/chat"
              element={(
                <ProtectedRoute stage="authenticated">
                  <ChatPage />
                </ProtectedRoute>
              )}
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </LanguageProvider>
  );
}
