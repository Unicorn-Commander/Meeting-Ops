import React, { useEffect } from 'react';
import { HashRouter as Router } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import { AuthProvider } from './contexts/AuthContext';
import { OrgProvider } from './contexts/OrgContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { RecordingProvider } from './contexts/RecordingContext';
import { UploadsProvider } from './contexts/UploadsContext';
import { AlwaysOnProvider } from './contexts/AlwaysOnContext';
import { AppRouterSimplified } from './AppRouterSimplified';
import { RecordingIndicator } from './components/RecordingIndicator';
import { DragDropOverlay } from './components/DragDropOverlay';
import { UploadTray } from './components/UploadTray';
import { ReconnectingOverlay } from './components/ReconnectingOverlay';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PWAUpdate } from './components/PWAUpdate';
import { useMeetingOpsShortcuts } from './hooks/useKeyboardShortcuts';
import { initPostHog, track, PENDING_CHECKOUT_KEY } from './utils/posthog';
import { resetSsoAttemptGuard } from './utils/loginRedirect';
import 'react-toastify/dist/ReactToastify.css';
import './index.css';

// Bureau CX L6: the one-attempt SSO-down marker is per document load: a
// fresh load is a fresh chance (a later manual retry must work), so clear
// it here at module load, before React renders anything. The marker is then
// re-set only when a redirect attempt is actually made (see
// utils/loginRedirect redirectToLogin).
resetSsoAttemptGuard();

function AppWithShortcuts() {
  useMeetingOpsShortcuts();
  return (
    <>
      <RecordingIndicator />
      <AppRouterSimplified />
    </>
  );
}

function App() {
  // Lazy-safe: returns immediately if already initialized OR if no key.
  initPostHog();

  // Stripe success redirect lands at `#/sessions?upgrade=success&...`.
  // Fire `subscription_started` once, reading the plan + cycle stashed
  // by the Pricing page before the checkout redirect. No stash = we
  // can't attribute plan/cycle (bookmark, cross-device), so we skip.
  useEffect(() => {
    try {
      const hash = window.location.hash || '';
      const qIndex = hash.indexOf('?');
      if (qIndex === -1) return;
      const params = new URLSearchParams(hash.slice(qIndex + 1));
      if (params.get('upgrade') !== 'success') return;
      const raw = window.sessionStorage.getItem(PENDING_CHECKOUT_KEY);
      if (!raw) return;
      window.sessionStorage.removeItem(PENDING_CHECKOUT_KEY);
      const parsed = JSON.parse(raw) as { plan?: string; billing_cycle?: string };
      track('subscription_started', {
        plan: parsed.plan,
        billing_cycle: parsed.billing_cycle,
      });
    } catch {
      /* analytics must never break app boot */
    }
  }, []);

  // Bureau CX L6: the SSO start bounces failures back here as
  // #/login?sso_error=<reason> (native-OIDC path). Strip the parameter so a
  // later reload of the same URL does not re-trigger a redirect attempt, and
  // so the Login page's own ?verify= handling is not confused by it. The
  // one-attempt marker (set by the redirect that produced this URL) is what
  // actually prevents the loop; this is belt-and-suspenders for the URL
  // itself.
  useEffect(() => {
    try {
      const hash = window.location.hash || '';
      if (!hash.includes('sso_error=')) return;
      const qIndex = hash.indexOf('?');
      if (qIndex === -1) return;
      const path = hash.slice(0, qIndex);
      const params = new URLSearchParams(hash.slice(qIndex + 1));
      params.delete('sso_error');
      const qs = params.toString();
      window.location.replace(`${path}${qs ? `?${qs}` : ''}`);
    } catch {
      /* URL cleanup must never break app boot */
    }
  }, []);

  return (
    <ErrorBoundary scope="app">
      <Router>
        <ThemeProvider>
          <AuthProvider>
            <OrgProvider>
              <AlwaysOnProvider>
                <RecordingProvider>
                  <UploadsProvider>
                  <div className="min-h-screen bg-gray-950 dark:bg-gray-950 light:bg-gray-50">
                    <ReconnectingOverlay />
                    <PWAUpdate />
                    <AppWithShortcuts />
                    <DragDropOverlay />
                    <UploadTray />
                    <ToastContainer
                      position="bottom-right"
                      theme="dark"
                      autoClose={3000}
                      hideProgressBar={false}
                      newestOnTop
                      closeOnClick
                      rtl={false}
                      pauseOnFocusLoss
                      draggable
                      pauseOnHover
                    />
                  </div>
                  </UploadsProvider>
                </RecordingProvider>
              </AlwaysOnProvider>
            </OrgProvider>
          </AuthProvider>
        </ThemeProvider>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
