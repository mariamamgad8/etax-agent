import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext.jsx';

const STAGE_ROUTES = {
  pending_enrollment: '/face-enrollment',
  face_required: '/face-verification',
  authenticated: '/chat',
};

/**
 * Blocks a route to anything but its required stage — this is the
 * client-side half of route protection. Navigating straight to /chat with a
 * face_required (or no) token bounces back to the step that's actually next;
 * the backend enforces the same stage requirement independently on every
 * protected endpoint.
 */
export function ProtectedRoute({ stage, children }) {
  const { auth } = useAuth();
  if (!auth || !auth.token) return <Navigate to="/login" replace />;
  if (auth.stage !== stage) {
    return <Navigate to={STAGE_ROUTES[auth.stage] || '/login'} replace />;
  }
  return children;
}
