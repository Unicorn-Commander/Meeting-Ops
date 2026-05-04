import React from 'react';
import { HashRouter as Router } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import { AuthProvider } from './contexts/AuthContext';
import { OrgProvider } from './contexts/OrgContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { RecordingProvider } from './contexts/RecordingContext';
import { UploadsProvider } from './contexts/UploadsContext';
import { AppRouterSimplified } from './AppRouterSimplified';
import { RecordingIndicator } from './components/RecordingIndicator';
import { DragDropOverlay } from './components/DragDropOverlay';
import { UploadTray } from './components/UploadTray';
import { useMeetingOpsShortcuts } from './hooks/useKeyboardShortcuts';
import 'react-toastify/dist/ReactToastify.css';
import './index.css';

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
  return (
    <Router>
      <ThemeProvider>
        <AuthProvider>
          <OrgProvider>
            <RecordingProvider>
              <UploadsProvider>
                <div className="min-h-screen bg-gray-950 dark:bg-gray-950 light:bg-gray-50">
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
          </OrgProvider>
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
