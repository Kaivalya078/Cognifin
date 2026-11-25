/**
 * FinSight AI - Main App
 * =======================
 * Multi-page application with routing, authentication, and page transitions
 */

import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { AuthProvider } from './context/AuthContext';
import { lazy, Suspense } from 'react';
import LandingPage from './pages/LandingPage';

// Only the landing page ships in the first bundle; the chat (PDF viewer, charts,
// markdown) and the other pages load when visited.
const LoginPage = lazy(() => import('./pages/LoginPage'));
const RegisterPage = lazy(() => import('./pages/RegisterPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const AuthCallbackPage = lazy(() => import('./pages/AuthCallbackPage'));
const EngineeringPage = lazy(() => import('./pages/EngineeringPage'));

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Suspense fallback={null}>
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={
          <PageTransition>
            <LandingPage />
          </PageTransition>
        } />
        <Route path="/login" element={
          <PageTransition>
            <LoginPage />
          </PageTransition>
        } />
        <Route path="/register" element={
          <PageTransition>
            <RegisterPage />
          </PageTransition>
        } />
        <Route path="/engineering" element={
          <PageTransition>
            <EngineeringPage />
          </PageTransition>
        } />
        <Route path="/auth/callback" element={
          <AuthCallbackPage />
        } />
        {/* Open without login: anonymous visitors get a free trial (backend-capped) */}
        <Route path="/chat" element={<ChatPage />} />
      </Routes>
      </Suspense>
    </AnimatePresence>
  );
}

function PageTransition({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
    >
      {children}
    </motion.div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <AnimatedRoutes />
      </Router>
    </AuthProvider>
  );
}
