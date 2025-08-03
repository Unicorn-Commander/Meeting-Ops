import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { LogIn, CheckCircle, XCircle } from 'lucide-react';

export const QuickLogin: React.FC = () => {
  const { login } = useAuth();
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState('');

  const handleQuickLogin = async () => {
    setStatus('loading');
    setError('');
    
    try {
      await login('admin', 'admin'); // Default admin password
      setStatus('success');
      setTimeout(() => {
        window.location.reload(); // Refresh to apply auth
      }, 1000);
    } catch (err: any) {
      // Try alternate password
      try {
        await login('admin', 'admin');
        setStatus('success');
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      } catch (err2: any) {
        setStatus('error');
        setError(err2.message || 'Login failed');
      }
    }
  };

  if (status === 'success') {
    return (
      <div className="fixed top-4 left-1/2 transform -translate-x-1/2 bg-green-900/90 border border-green-700 rounded-lg px-4 py-3 flex items-center gap-2">
        <CheckCircle className="w-5 h-5 text-green-400" />
        <span className="text-green-300">Login successful! Refreshing...</span>
      </div>
    );
  }

  return (
    <div className="fixed top-4 left-1/2 transform -translate-x-1/2 z-50">
      {status === 'idle' && (
        <button
          onClick={handleQuickLogin}
          className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 shadow-lg transition-all"
        >
          <LogIn className="w-4 h-4" />
          Quick Admin Login
        </button>
      )}
      
      {status === 'loading' && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
          <span className="text-gray-300">Logging in...</span>
        </div>
      )}
      
      {status === 'error' && (
        <div className="bg-red-900/90 border border-red-700 rounded-lg px-4 py-3 flex items-center gap-2">
          <XCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-300">{error}</span>
          <button
            onClick={handleQuickLogin}
            className="ml-2 text-xs underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
};