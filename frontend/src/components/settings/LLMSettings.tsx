import React, { useState, useEffect } from 'react';
import {
  Server, Plus, Trash2, Edit2, Check, X, TestTube, 
  Wifi, WifiOff, Zap, AlertCircle, Settings
} from 'lucide-react';
import { config } from '../../config';

interface LLMEndpoint {
  name: string;
  provider: string;
  url: string;
  api_key?: string;
  model: string;
  context_window: number;
  max_tokens: number;
  temperature: number;
  enabled: boolean;
  priority: number;
  description?: string;
}

interface LLMConfig {
  endpoints: LLMEndpoint[];
  active_endpoint: string | null;
  fallback_enabled: boolean;
  timeout_seconds: number;
  retry_attempts: number;
}

export const LLMSettings: React.FC = () => {
  const [llmConfig, setLLMConfig] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingEndpoint, setEditingEndpoint] = useState<string | null>(null);
  const [newEndpoint, setNewEndpoint] = useState<Partial<LLMEndpoint> | null>(null);
  const [testResults, setTestResults] = useState<Record<string, any>>({});
  const [testing, setTesting] = useState<string | null>(null);

  // Fetch LLM configuration
  const fetchConfig = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/llm-settings/endpoints`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setLLMConfig(data);
      }
    } catch (error) {
      console.error('Failed to fetch LLM config:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // Test endpoint connection
  const testEndpoint = async (name: string) => {
    setTesting(name);
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/llm-settings/endpoints/${name}/test`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      const result = await response.json();
      setTestResults(prev => ({
        ...prev,
        [name]: result
      }));
    } catch (error) {
      setTestResults(prev => ({
        ...prev,
        [name]: { success: false, error: 'Connection failed' }
      }));
    } finally {
      setTesting(null);
    }
  };

  // Activate endpoint
  const activateEndpoint = async (name: string) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/llm-settings/endpoints/${name}/activate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        await fetchConfig();
      }
    } catch (error) {
      console.error('Failed to activate endpoint:', error);
    }
  };

  // Toggle fallback
  const toggleFallback = async () => {
    if (!llmConfig) return;

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/llm-settings/config/fallback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ enabled: !llmConfig.fallback_enabled })
      });

      if (response.ok) {
        await fetchConfig();
      }
    } catch (error) {
      console.error('Failed to toggle fallback:', error);
    }
  };

  // Delete endpoint
  const deleteEndpoint = async (name: string) => {
    if (!confirm(`Delete endpoint "${name}"?`)) return;

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/llm-settings/endpoints/${name}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        await fetchConfig();
      }
    } catch (error) {
      console.error('Failed to delete endpoint:', error);
    }
  };

  // Save new endpoint
  const saveNewEndpoint = async () => {
    if (!newEndpoint || !newEndpoint.name || !newEndpoint.url || !newEndpoint.model) return;

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/llm-settings/endpoints`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          ...newEndpoint,
          provider: newEndpoint.provider || 'custom',
          context_window: newEndpoint.context_window || 8192,
          max_tokens: newEndpoint.max_tokens || 4096,
          temperature: newEndpoint.temperature || 0.7,
          enabled: true,
          priority: (llmConfig?.endpoints.length || 0) + 1
        })
      });

      if (response.ok) {
        setNewEndpoint(null);
        await fetchConfig();
      }
    } catch (error) {
      console.error('Failed to save endpoint:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="bg-gray-950 rounded-xl border border-gray-800 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Server className="w-6 h-6 text-purple-400" />
          <h2 className="text-xl font-bold text-white">LLM Endpoint Configuration</h2>
        </div>

        <div className="flex items-center gap-4">
          {/* Fallback Toggle */}
          <button
            onClick={toggleFallback}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
              llmConfig?.fallback_enabled
                ? 'bg-green-500/20 text-green-400'
                : 'bg-gray-800 text-gray-400'
            }`}
          >
            {llmConfig?.fallback_enabled ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
            Fallback {llmConfig?.fallback_enabled ? 'On' : 'Off'}
          </button>

          {/* Add Endpoint Button */}
          <button
            onClick={() => setNewEndpoint({
              name: '',
              provider: 'remote_ollama',
              url: '',
              model: '',
              context_window: 8192,
              max_tokens: 4096,
              temperature: 0.7
            })}
            className="flex items-center gap-2 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 rounded-lg text-white text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Endpoint
          </button>
        </div>
      </div>

      {/* Quick Switch */}
      <div className="mb-6 p-4 bg-gray-900/50 rounded-lg border border-gray-800">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Quick Switch</h3>
        <div className="flex gap-2 flex-wrap">
          {llmConfig?.endpoints
            .filter(e => e.enabled)
            .sort((a, b) => a.priority - b.priority)
            .map(endpoint => (
              <button
                key={endpoint.name}
                onClick={() => activateEndpoint(endpoint.name)}
                className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  endpoint.name === llmConfig.active_endpoint
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {endpoint.name === 'remote_gemma3_27b' ? '🌐 Remote Gemma3' :
                 endpoint.name === 'local_gemma3n' ? '💻 Local Gemma3n' :
                 endpoint.name}
                {endpoint.name === llmConfig.active_endpoint && (
                  <span className="ml-2 text-xs">✓</span>
                )}
              </button>
            ))}
        </div>
      </div>

      {/* Endpoints List */}
      <div className="space-y-4">
        {llmConfig?.endpoints.map(endpoint => {
          const testResult = testResults[endpoint.name];
          const isActive = endpoint.name === llmConfig.active_endpoint;

          return (
            <div
              key={endpoint.name}
              className={`p-4 rounded-lg border transition-all ${
                isActive
                  ? 'bg-purple-900/20 border-purple-700'
                  : 'bg-gray-900/50 border-gray-800'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="font-semibold text-white">{endpoint.name}</h3>
                    {isActive && (
                      <span className="px-2 py-0.5 bg-purple-600 text-white text-xs rounded-full">
                        Active
                      </span>
                    )}
                    {!endpoint.enabled && (
                      <span className="px-2 py-0.5 bg-gray-700 text-gray-400 text-xs rounded-full">
                        Disabled
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-500">Provider:</span>
                      <span className="ml-2 text-gray-300">{endpoint.provider}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Model:</span>
                      <span className="ml-2 text-gray-300">{endpoint.model}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">URL:</span>
                      <span className="ml-2 text-gray-300 font-mono text-xs">{endpoint.url}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Context:</span>
                      <span className="ml-2 text-gray-300">{endpoint.context_window.toLocaleString()} tokens</span>
                    </div>
                  </div>

                  {endpoint.description && (
                    <p className="mt-2 text-sm text-gray-400">{endpoint.description}</p>
                  )}

                  {/* Test Result */}
                  {testResult && (
                    <div className={`mt-3 p-2 rounded text-sm ${
                      testResult.success
                        ? 'bg-green-900/30 text-green-400'
                        : 'bg-red-900/30 text-red-400'
                    }`}>
                      {testResult.success ? (
                        <div>
                          ✓ Connected - Model {testResult.has_configured_model ? 'found' : 'not found'}
                          {testResult.models && (
                            <div className="mt-1 text-xs text-gray-400">
                              Available: {testResult.models.join(', ')}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div>✗ {testResult.error || 'Connection failed'}</div>
                      )}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 ml-4">
                  {!isActive && endpoint.enabled && (
                    <button
                      onClick={() => activateEndpoint(endpoint.name)}
                      className="p-2 text-gray-400 hover:text-purple-400 transition-colors"
                      title="Activate"
                    >
                      <Zap className="w-4 h-4" />
                    </button>
                  )}

                  <button
                    onClick={() => testEndpoint(endpoint.name)}
                    disabled={testing === endpoint.name}
                    className="p-2 text-gray-400 hover:text-blue-400 transition-colors"
                    title="Test Connection"
                  >
                    {testing === endpoint.name ? (
                      <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <TestTube className="w-4 h-4" />
                    )}
                  </button>

                  <button
                    onClick={() => deleteEndpoint(endpoint.name)}
                    className="p-2 text-gray-400 hover:text-red-400 transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {/* New Endpoint Form */}
        {newEndpoint && (
          <div className="p-4 bg-gray-900/50 rounded-lg border border-purple-700">
            <h3 className="font-semibold text-white mb-4">Add New Endpoint</h3>
            
            <div className="grid grid-cols-2 gap-4">
              <input
                type="text"
                placeholder="Endpoint Name"
                value={newEndpoint.name || ''}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, name: e.target.value })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />

              <select
                value={newEndpoint.provider || 'remote_ollama'}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, provider: e.target.value })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
              >
                <option value="local_ollama">Local Ollama</option>
                <option value="remote_ollama">Remote Ollama</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="custom">Custom</option>
              </select>

              <input
                type="text"
                placeholder="API URL (e.g., http://192.168.1.135:11434)"
                value={newEndpoint.url || ''}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, url: e.target.value })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />

              <input
                type="text"
                placeholder="Model Name (e.g., gemma3:27b)"
                value={newEndpoint.model || ''}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, model: e.target.value })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />

              <input
                type="number"
                placeholder="Context Window"
                value={newEndpoint.context_window || 8192}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, context_window: parseInt(e.target.value) })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />

              <input
                type="text"
                placeholder="API Key (optional)"
                value={newEndpoint.api_key || ''}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, api_key: e.target.value })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />

              <input
                type="text"
                placeholder="Description (optional)"
                value={newEndpoint.description || ''}
                onChange={(e) => setNewEndpoint({ ...newEndpoint, description: e.target.value })}
                className="col-span-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>

            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setNewEndpoint(null)}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveNewEndpoint}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-white transition-colors"
              >
                Save Endpoint
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Info Section */}
      <div className="mt-6 p-4 bg-blue-900/20 rounded-lg border border-blue-800">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-blue-400 mt-0.5" />
          <div className="text-sm text-blue-300">
            <p className="font-semibold mb-1">Configuration Tips:</p>
            <ul className="list-disc list-inside space-y-1 text-blue-200">
              <li>The active endpoint will be used for all AI features</li>
              <li>Enable fallback to automatically switch to backup endpoints if the primary fails</li>
              <li>Test endpoints after adding to ensure connectivity</li>
              <li>For testing, use Gemma3 27B from 192.168.1.135:11434</li>
              <li>Local Gemma3n E4B is optimized for AMD 8945HS with HSA 11.0.3</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};