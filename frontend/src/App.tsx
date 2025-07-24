import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import { AuthProvider } from './contexts/AuthContext';
import { LoginRegister } from './components/LoginRegister';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AccountManagement } from './components/AccountManagement';
import ModelPerformanceDashboard from './components/ModelPerformanceDashboard';
import { DashboardRouter } from './components/DashboardRouter';
import Dashboard from './Dashboard';
import { getErrorMessage } from './utils/errorHandling';

function App() {
  // Global error handler for unhandled promise rejections
  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      console.error('Unhandled promise rejection:', event.reason);
      // Prevent the default behavior which might show "[object Object]"
      event.preventDefault();
      
      // Only show alert for non-network errors to avoid spamming
      if (event.reason && typeof event.reason === 'object' && 'message' in event.reason) {
        const message = getErrorMessage(event.reason);
        if (!message.includes('fetch') && !message.includes('Network')) {
          console.error('Unhandled error:', message);
        }
      }
    };

    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    
    return () => {
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, []);

  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginRegister />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<DashboardRouter />} />
            <Route path="/user" element={<DashboardRouter defaultView="user" />} />
            <Route path="/admin" element={<DashboardRouter defaultView="admin" />} />
            <Route path="/legacy" element={<DashboardRouter defaultView="legacy" />} />
            <Route path="/account" element={<AccountManagement />} />
            <Route path="/performance" element={<ModelPerformanceDashboard />} />
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;