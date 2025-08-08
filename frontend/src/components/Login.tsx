import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Shield, Download } from 'lucide-react';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login(username, password);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Sign in to Unicorn Commander
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Meeting Ops Control Panel
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <input type="hidden" name="remember" value="true" />
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="username" className="sr-only">
                Username or Email
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
                placeholder="Username or Email"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
              />
            </div>
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-4">
              <div className="flex">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="ml-3">
                  <p className="text-sm text-red-800">{error}</p>
                </div>
              </div>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <span className="flex items-center">
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </div>

          <div className="text-sm text-center">
            <div className="bg-gradient-to-r from-blue-50 to-purple-50 p-4 rounded-lg border border-blue-200 mb-2">
              <p className="text-gray-800 font-bold mb-3 text-base">
                🔐 Default Login Credentials
              </p>
              <div className="space-y-2">
                <div className="bg-white p-2 rounded-md border border-blue-300">
                  <p className="text-gray-700">
                    <span className="font-bold text-blue-700">Administrator Account:</span>
                  </p>
                  <div className="flex items-center justify-center gap-2 mt-1">
                    <span className="font-mono text-lg bg-blue-600 text-white px-3 py-1 rounded">admin</span>
                    <span className="text-gray-500">/</span>
                    <span className="font-mono text-lg bg-blue-600 text-white px-3 py-1 rounded">admin123</span>
                  </div>
                  <span className="text-xs text-gray-600 mt-1 block">Full system access, all features enabled</span>
                </div>
                <div className="bg-white p-2 rounded-md border border-green-300">
                  <p className="text-gray-700">
                    <span className="font-bold text-green-700">Standard User Account:</span>
                  </p>
                  <div className="flex items-center justify-center gap-2 mt-1">
                    <span className="font-mono text-lg bg-green-600 text-white px-3 py-1 rounded">user</span>
                    <span className="text-gray-500">/</span>
                    <span className="font-mono text-lg bg-green-600 text-white px-3 py-1 rounded">user123</span>
                  </div>
                  <span className="text-xs text-gray-600 mt-1 block">Limited access, basic recording features</span>
                </div>
              </div>
              <div className="mt-3 p-2 bg-yellow-50 rounded-md">
                <p className="text-xs text-yellow-800">
                  ⚠️ Please change these default passwords after first login for security
                </p>
              </div>
            </div>
            <p className="text-purple-600 text-xs font-medium">
              💡 Login with either account to explore different dashboard features
            </p>
          </div>

          {/* Certificate Download for HTTPS */}
          {location.protocol === 'http:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1' && (
            <div className="mt-6 p-4 bg-purple-900/20 border border-purple-700 rounded-lg">
              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-purple-400 flex-shrink-0 mt-1" />
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-purple-300 mb-1">
                    🦄 Secure Access Available
                  </h4>
                  <p className="text-xs text-gray-400 mb-3">
                    For enhanced security, install our certificate and use HTTPS.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <a
                      href={`http://${location.hostname}:8888`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center gap-2 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium rounded transition-colors"
                    >
                      <Download className="w-3 h-3" />
                      Get Certificate
                    </a>
                    <a
                      href={`https://${location.hostname}:7777`}
                      className="inline-flex items-center justify-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-medium rounded transition-colors"
                    >
                      <Shield className="w-3 h-3" />
                      Switch to HTTPS
                    </a>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Issued by: Magic Unicorn Unconventional Technology & Stuff Inc.
                  </p>
                </div>
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  );
};