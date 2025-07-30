import React, { useState, useEffect } from 'react';
import { Lock, RefreshCcw, Info, AlertCircle, CheckCircle } from 'lucide-react';

export const SSLManager: React.FC = () => {
  const [domain, setDomain] = useState('');
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const API_BASE_URL = import.meta.env.VITE_API_URL || '';

  const fetchSSLStatus = async () => {
    if (!domain) {
      setError("Please enter a domain name to check SSL status.");
      setStatus(null);
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/ssl/status?domain=${domain}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setStatus(data);
    } catch (e: any) {
      setError(`Failed to fetch SSL status: ${e.message}`);
      console.error("Error fetching SSL status:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerRenewal = async () => {
    if (window.confirm("Are you sure you want to trigger a manual SSL certificate renewal? This requires Certbot to be installed and configured on the server.")) {
      setLoading(true);
      setMessage(null);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/ssl/renew`, {
          method: 'POST',
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setMessage(data.message);
        // Re-fetch status after renewal attempt
        setTimeout(() => fetchSSLStatus(), 2000); 
      } catch (e: any) {
        setError(`Failed to trigger renewal: ${e.message}`);
        console.error("Error triggering renewal:", e);
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 flex flex-col h-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <Lock className="w-6 h-6 text-yellow-400" />
          <h3 className="text-xl font-bold">SSL/HTTPS Configuration</h3>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/50 text-red-300 border border-red-700 p-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}
      {message && (
        <div className="bg-blue-900/50 text-blue-300 border border-blue-700 p-3 rounded-lg mb-4 text-sm">
          {message}
        </div>
      )}

      <div className="space-y-4 mb-6">
        <div>
          <label className="block text-sm font-medium mb-1">Domain Name</label>
          <input
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="e.g., yourdomain.com"
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
          />
        </div>
        <button
          onClick={fetchSSLStatus}
          className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm flex items-center space-x-2"
          disabled={loading}
        >
          <Info className="w-4 h-4" />
          <span>{loading ? 'Checking...' : 'Check SSL Status'}</span>
        </button>
      </div>

      {status && (
        <div className="bg-gray-700 p-4 rounded-lg space-y-3">
          <h4 className="font-medium text-gray-300">Certificate Details</h4>
          <div className="flex items-center space-x-2">
            {status.valid ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-500" />
            )}
            <p className="text-sm">
              Status: <span className={`font-bold ${status.valid ? 'text-green-400' : 'text-red-400'}`}>
                {status.valid ? 'Valid' : 'Invalid'}
              </span>
            </p>
          </div>
          <p className="text-sm">Configured: {status.configured ? 'Yes' : 'No'}</p>
          {status.expiration_date && (
            <p className="text-sm">Expiration Date: {new Date(status.expiration_date).toLocaleString()}</p>
          )}
          {status.expires_in_days !== null && (
            <p className="text-sm">
              Expires In: <span className={`font-bold ${status.expires_in_days < 30 ? 'text-red-400' : 'text-green-400'}`}>
                {status.expires_in_days} days
              </span>
            </p>
          )}
          <p className="text-sm">Auto-renewal Enabled: {status.auto_renewal_enabled ? 'Yes' : 'No'}</p>
          {status.message && <p className="text-xs text-gray-400">Message: {status.message}</p>}

          <button
            onClick={handleTriggerRenewal}
            className="bg-yellow-600 hover:bg-yellow-700 px-4 py-2 rounded-lg text-sm flex items-center space-x-2 mt-4"
            disabled={loading}
          >
            <RefreshCcw className="w-4 h-4" />
            <span>Trigger Manual Renewal</span>
          </button>
        </div>
      )}

      <div className="mt-6 border-t border-gray-700 pt-6">
        <h4 className="font-medium text-gray-300 mb-3">Setup Instructions</h4>
        <p className="text-sm text-gray-400 mb-2">
          To initially set up SSL/HTTPS for your domain, run the provided script on your server:
        </p>
        <pre className="bg-gray-900 text-gray-200 p-3 rounded-lg text-xs overflow-auto font-mono">
          <code>sudo /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/setup-ssl.sh</code>
        </pre>
        <p className="text-xs text-gray-500 mt-2">
          Remember to edit the `DOMAIN` and `EMAIL` variables inside `setup-ssl.sh` before running it.
        </p>
      </div>
    </div>
  );
};