import React from 'react';
import { HashRouter as Router } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { AppRouter } from './AppRouter';
import { useMeetingOpsShortcuts } from './hooks/useKeyboardShortcuts';
import 'react-toastify/dist/ReactToastify.css';
import './index.css';

function AppWithShortcuts() {
  useMeetingOpsShortcuts();
  return <AppRouter />;
}

function App() {
  return (
    <Router>
      <ThemeProvider>
        <AuthProvider>
          <div className="min-h-screen bg-gray-950 dark:bg-gray-950 light:bg-gray-50">
            <AppWithShortcuts />
            <ToastContainer 
              position="bottom-right"
              theme="dark"
              autoClose={5000}
              hideProgressBar={false}
              newestOnTop
              closeOnClick
              rtl={false}
              pauseOnFocusLoss
              draggable
              pauseOnHover
            />
          </div>
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;