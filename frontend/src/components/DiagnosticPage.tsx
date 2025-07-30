import React, { useEffect, useState } from 'react';

export const DiagnosticPage: React.FC = () => {
  const [diagnostics, setDiagnostics] = useState<any>({
    loading: true,
    apiReachable: null,
    authCheckResult: null,
    localStorage: null,
    errors: []
  });

  useEffect(() => {
    const runDiagnostics = async () => {
      const results: any = {
        loading: false,
        timestamp: new Date().toISOString(),
        location: window.location.href,
        userAgent: navigator.userAgent,
        errors: []
      };

      // Check localStorage
      try {
        results.localStorage = {
          hasAccessToken: !!localStorage.getItem('access_token'),
          hasRefreshToken: !!localStorage.getItem('refresh_token'),
          dashboardView: localStorage.getItem('dashboard-view')
        };
      } catch (e) {
        results.errors.push(`localStorage error: ${e}`);
      }

      // Check API reachability
      try {
        const response = await fetch('/api/status', { 
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        results.apiReachable = {
          status: response.status,
          ok: response.ok,
          statusText: response.statusText
        };
      } catch (e) {
        results.apiReachable = false;
        results.errors.push(`API fetch error: ${e}`);
      }

      // Check auth endpoint
      try {
        const token = localStorage.getItem('access_token');
        if (token) {
          const response = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          results.authCheckResult = {
            status: response.status,
            ok: response.ok
          };
        } else {
          results.authCheckResult = 'No token';
        }
      } catch (e) {
        results.errors.push(`Auth check error: ${e}`);
      }

      setDiagnostics(results);
    };

    runDiagnostics();
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Diagnostic Information</h1>
        
        <div className="bg-gray-800 rounded-lg p-6 space-y-4">
          <div>
            <h2 className="text-xl font-semibold mb-2">Environment</h2>
            <pre className="bg-gray-700 p-4 rounded overflow-auto text-sm">
              {JSON.stringify({
                location: diagnostics.location,
                userAgent: diagnostics.userAgent,
                timestamp: diagnostics.timestamp
              }, null, 2)}
            </pre>
          </div>

          <div>
            <h2 className="text-xl font-semibold mb-2">API Status</h2>
            <pre className="bg-gray-700 p-4 rounded overflow-auto text-sm">
              {JSON.stringify(diagnostics.apiReachable, null, 2)}
            </pre>
          </div>

          <div>
            <h2 className="text-xl font-semibold mb-2">Auth Status</h2>
            <pre className="bg-gray-700 p-4 rounded overflow-auto text-sm">
              {JSON.stringify({
                authCheck: diagnostics.authCheckResult,
                localStorage: diagnostics.localStorage
              }, null, 2)}
            </pre>
          </div>

          {diagnostics.errors.length > 0 && (
            <div>
              <h2 className="text-xl font-semibold mb-2 text-red-400">Errors</h2>
              <pre className="bg-gray-700 p-4 rounded overflow-auto text-sm text-red-300">
                {JSON.stringify(diagnostics.errors, null, 2)}
              </pre>
            </div>
          )}
        </div>

        <div className="mt-6 space-x-4">
          <button 
            onClick={() => window.location.href = '/login'}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded"
          >
            Go to Login
          </button>
          <button 
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded"
          >
            Reload Page
          </button>
        </div>
      </div>
    </div>
  );
};