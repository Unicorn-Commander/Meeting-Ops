import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Key, RefreshCw, CheckCircle, XCircle } from 'lucide-react';

export const AuthDebug: React.FC = () => {
  const { token, user } = useAuth();
  const [authStatus, setAuthStatus] = useState<any>({});
  const [loading, setLoading] = useState(false);

  const testAuth = async () => {
    setLoading(true);
    const results: any = {};

    // Check localStorage
    const localToken = localStorage.getItem('access_token');
    results.localStorage = {
      hasToken: !!localToken,
      tokenLength: localToken?.length || 0,
      tokenPreview: localToken ? `${localToken.substring(0, 20)}...` : 'none'
    };

    // Check context token
    results.contextToken = {
      hasToken: !!token,
      tokenLength: token?.length || 0,
      tokenPreview: token ? `${token.substring(0, 20)}...` : 'none'
    };

    // Test /api/auth/me
    try {
      const meRes = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${localToken || token}`
        }
      });
      results.authMe = {
        status: meRes.status,
        statusText: meRes.statusText,
        ok: meRes.ok,
        data: meRes.ok ? await meRes.json() : await meRes.text()
      };
    } catch (err) {
      results.authMe = { error: err.toString() };
    }

    // Test /api/status (no auth)
    try {
      const statusRes = await fetch('/api/status');
      results.apiStatus = {
        status: statusRes.status,
        ok: statusRes.ok,
        data: statusRes.ok ? await statusRes.json() : null
      };
    } catch (err) {
      results.apiStatus = { error: err.toString() };
    }

    setAuthStatus(results);
    setLoading(false);
  };

  useEffect(() => {
    testAuth();
  }, []);

  return (
    <div className="fixed bottom-4 right-4 w-96 max-h-96 overflow-y-auto bg-gray-900 border border-gray-700 rounded-lg p-4 text-xs font-mono">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Key className="w-4 h-4" />
          Auth Debug
        </h3>
        <button
          onClick={testAuth}
          disabled={loading}
          className="p-1 hover:bg-gray-800 rounded"
        >
          <RefreshCw className={`w-4 h-4 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="space-y-3">
        {/* User Info */}
        <div className="border-t border-gray-800 pt-2">
          <div className="text-gray-400">Current User:</div>
          <div className="text-gray-300">
            {user ? `${user.username} (${user.role})` : 'Not logged in'}
          </div>
        </div>

        {/* Token Status */}
        <div className="border-t border-gray-800 pt-2">
          <div className="text-gray-400">Token Status:</div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              {authStatus.localStorage?.hasToken ? 
                <CheckCircle className="w-3 h-3 text-green-400" /> : 
                <XCircle className="w-3 h-3 text-red-400" />
              }
              <span className="text-gray-300">
                LocalStorage: {authStatus.localStorage?.tokenPreview || 'none'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {authStatus.contextToken?.hasToken ? 
                <CheckCircle className="w-3 h-3 text-green-400" /> : 
                <XCircle className="w-3 h-3 text-red-400" />
              }
              <span className="text-gray-300">
                Context: {authStatus.contextToken?.tokenPreview || 'none'}
              </span>
            </div>
          </div>
        </div>

        {/* API Test Results */}
        <div className="border-t border-gray-800 pt-2">
          <div className="text-gray-400">API Tests:</div>
          <div className="space-y-2">
            <div>
              <div className="flex items-center gap-2">
                {authStatus.authMe?.ok ? 
                  <CheckCircle className="w-3 h-3 text-green-400" /> : 
                  <XCircle className="w-3 h-3 text-red-400" />
                }
                <span className="text-gray-300">/api/auth/me: {authStatus.authMe?.status || 'not tested'}</span>
              </div>
              {authStatus.authMe?.data && (
                <pre className="text-gray-400 ml-5 text-xs">
                  {JSON.stringify(authStatus.authMe.data, null, 2)}
                </pre>
              )}
            </div>

            <div>
              <div className="flex items-center gap-2">
                {authStatus.apiStatus?.ok ? 
                  <CheckCircle className="w-3 h-3 text-green-400" /> : 
                  <XCircle className="w-3 h-3 text-red-400" />
                }
                <span className="text-gray-300">/api/status: {authStatus.apiStatus?.status || 'not tested'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};