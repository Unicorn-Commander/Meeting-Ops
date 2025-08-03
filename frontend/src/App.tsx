import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import { AuthProvider } from './contexts/AuthContext';
import { LoginRegister } from './components/LoginRegister';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AccountManagement } from './components/AccountManagement';
import ModelPerformanceDashboard from './components/ModelPerformanceDashboard';
import { ProductionDashboard } from './components/ProductionDashboard';
import { QuickLogin } from './components/QuickLogin';
import { RecordingDashboard } from './components/RecordingDashboard';
import { AdminDashboard } from './components/AdminDashboard';
import { SystemAdminDashboard } from './components/SystemAdminDashboard';
import { getErrorMessage } from './utils/errorHandling';
import { fixUrlRedirect } from './utils/fixUrlRedirect';

function App() {
  // Fix URL redirect issues
  useEffect(() => {
    // Check and fix www. prefix on IP addresses
    if (fixUrlRedirect()) {
      // Page will redirect, no need to continue
      return;
    }
  }, []);

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
        <QuickLogin />
        <Routes>
          <Route path="/login" element={<LoginRegister />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<ProductionDashboard />} />
            <Route path="/account" element={<AccountManagement />} />
            <Route path="/performance" element={<ModelPerformanceDashboard />} />
            <Route path="/recording" element={<RecordingDashboard />} />
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/system-admin" element={<SystemAdminDashboard />} />
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;