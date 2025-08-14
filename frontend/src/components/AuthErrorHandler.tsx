import React, { useEffect, useState } from 'react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { AlertTriangle, RefreshCw, LogOut } from 'lucide-react';

interface AuthError {
  type: 'token_expired' | 'session_failed' | 'network_error';
  message: string;
  timestamp: Date;
}

export const AuthErrorHandler: React.FC = () => {
  const { refreshToken, logout } = useAuthentikAuth();
  const [error, setError] = useState<AuthError | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    // Intercept all API responses
    const interceptor = (response: Response) => {
      if (response.status === 401) {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          response.json().then(data => {
            if (data.code === 'TOKEN_EXPIRED') {
              handleTokenExpired();
            } else if (data.code === 'INVALID_TOKEN') {
              handleInvalidToken();
            }
          });
        }
      } else if (response.status >= 500) {
        handleServerError();
      }
    };

    // Override fetch to add interceptor
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      try {
        const response = await originalFetch(...args);
        interceptor(response.clone());
        return response;
      } catch (error) {
        handleNetworkError();
        throw error;
      }
    };

    // Cleanup
    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  const handleTokenExpired = async () => {
    if (isRefreshing || retryCount >= 3) {
      setError({
        type: 'token_expired',
        message: 'Your session has expired. Please log in again.',
        timestamp: new Date()
      });
      return;
    }

    setIsRefreshing(true);
    setRetryCount(prev => prev + 1);

    try {
      await refreshToken();
      setError(null);
      setRetryCount(0);
      
      // Retry failed requests
      window.location.reload();
    } catch (error) {
      setError({
        type: 'token_expired',
        message: 'Failed to refresh session. Please log in again.',
        timestamp: new Date()
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleInvalidToken = () => {
    setError({
      type: 'session_failed',
      message: 'Invalid authentication. Please log in again.',
      timestamp: new Date()
    });
  };

  const handleServerError = () => {
    // Don't show error for every 500, only if it persists
    if (retryCount < 3) {
      setRetryCount(prev => prev + 1);
      return;
    }

    setError({
      type: 'session_failed',
      message: 'Server error. Your work has been saved. Please try again.',
      timestamp: new Date()
    });
  };

  const handleNetworkError = () => {
    setError({
      type: 'network_error',
      message: 'Network connection lost. Please check your internet connection.',
      timestamp: new Date()
    });
  };

  const handleRetry = async () => {
    setError(null);
    setRetryCount(0);
    
    if (error?.type === 'token_expired') {
      await handleTokenExpired();
    } else {
      window.location.reload();
    }
  };

  const handleLogout = () => {
    logout();
    setError(null);
  };

  if (!error) return null;

  return (
    <div className="fixed top-4 right-4 max-w-md bg-gray-800 border border-gray-700 rounded-lg shadow-lg p-4 z-50">
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-full ${
          error.type === 'network_error' ? 'bg-yellow-900/30' : 'bg-red-900/30'
        }`}>
          <AlertTriangle className={`h-5 w-5 ${
            error.type === 'network_error' ? 'text-yellow-400' : 'text-red-400'
          }`} />
        </div>
        
        <div className="flex-1">
          <h3 className="font-medium text-white mb-1">
            {error.type === 'token_expired' ? 'Session Expired' :
             error.type === 'network_error' ? 'Connection Error' :
             'Authentication Error'}
          </h3>
          <p className="text-sm text-gray-300 mb-3">{error.message}</p>
          
          <div className="flex items-center gap-2">
            {error.type !== 'network_error' && (
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
              >
                <LogOut className="h-3 w-3" />
                Log Out
              </button>
            )}
            
            <button
              onClick={handleRetry}
              disabled={isRefreshing}
              className="flex items-center gap-2 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Retry'}
            </button>
            
            <button
              onClick={() => setError(null)}
              className="px-3 py-1 text-sm text-gray-400 hover:text-white transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};