import React, { useState, useEffect } from 'react';
import { 
  Bot, 
  Brain, 
  Settings, 
  Save, 
  RotateCcw, 
  TestTube,
  Zap,
  CheckCircle,
  AlertCircle,
  Loader
} from 'lucide-react';
import { config } from '../../config';

interface UnifiedAgent {
  id: string;
  name: string;
  description: string;
  personality: string;
  system_prompt: string;
  provider_type: string;
  model_name: string;
  model_config: {
    temperature: number;
    max_tokens: number;
    top_p: number;
  };
  progressive_config: {
    initial_interval: number;
    multiplier: number;
    max_interval: number;
    enabled: boolean;
  };
  output_template: any;
  is_active: boolean;
  is_default: boolean;
}

interface ModelInfo {
  name: string;
  size: number;
  recommended: boolean;
}

interface ProviderInfo {
  type: string;
  name: string;
  description: string;
  recommended: boolean;
  available: boolean;
}

export default function UnifiedAgent() {
  const [agent, setAgent] = useState<UnifiedAgent | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [availableProviders, setAvailableProviders] = useState<ProviderInfo[]>([]);
  const [testResult, setTestResult] = useState<any>(null);

  useEffect(() => {
    loadAgent();
    loadAvailableModels();
    loadAvailableProviders();
  }, []);

  const loadAgent = async () => {
    try {
      setError(null);
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agent`);
      if (response.ok) {
        const data = await response.json();
        setAgent(data);
      } else {
        throw new Error('Failed to load agent configuration');
      }
    } catch (error) {
      console.error('Failed to load agent:', error);
      setError('Failed to load agent configuration. Please check that the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableModels = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/models`);
      if (response.ok) {
        const data = await response.json();
        setAvailableModels(data.models || []);
      }
    } catch (error) {
      console.error('Failed to load models:', error);
    }
  };

  const loadAvailableProviders = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/providers`);
      if (response.ok) {
        const data = await response.json();
        setAvailableProviders(data.providers || []);
      }
    } catch (error) {
      console.error('Failed to load providers:', error);
    }
  };

  const saveAgent = async () => {
    if (!agent) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agent`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agent)
      });

      if (response.ok) {
        const data = await response.json();
        setAgent(data.agent);
        setSuccess('Agent configuration saved successfully!');
        setTimeout(() => setSuccess(null), 3000);
      } else {
        throw new Error('Failed to save agent configuration');
      }
    } catch (error) {
      console.error('Failed to save agent:', error);
      setError('Failed to save agent configuration');
    } finally {
      setSaving(false);
    }
  };

  const resetAgent = async () => {
    if (!confirm('Are you sure you want to reset the agent to default configuration? This cannot be undone.')) {
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/agent/reset`, {
        method: 'POST'
      });

      if (response.ok) {
        const data = await response.json();
        setAgent(data.agent);
        setSuccess('Agent reset to default configuration');
        setTimeout(() => setSuccess(null), 3000);
      } else {
        throw new Error('Failed to reset agent');
      }
    } catch (error) {
      console.error('Failed to reset agent:', error);
      setError('Failed to reset agent configuration');
    } finally {
      setSaving(false);
    }
  };

  const testAgent = async () => {
    setTesting(true);
    setTestResult(null);
    setError(null);

    try {
      const response = await fetch(`${config.apiUrl}/api/unified-agent/test`, {
        method: 'POST'
      });

      if (response.ok) {
        const data = await response.json();
        setTestResult(data);
      } else {
        throw new Error('Failed to test agent');
      }
    } catch (error) {
      console.error('Failed to test agent:', error);
      setError('Failed to test agent configuration');
    } finally {
      setTesting(false);
    }
  };

  const updateAgent = (field: string, value: any) => {
    if (!agent) return;
    setAgent({ ...agent, [field]: value });
  };

  const updateNestedField = (parent: string, field: string, value: any) => {
    if (!agent) return;
    setAgent({
      ...agent,
      [parent]: {
        ...agent[parent as keyof UnifiedAgent],
        [field]: value
      }
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
        <div className="max-w-6xl mx-auto p-6">
          <div className="flex items-center justify-center h-64">
            <Loader className="w-8 h-8 animate-spin text-purple-400" />
            <span className="ml-3 text-lg">Loading agent configuration...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
        <div className="max-w-6xl mx-auto p-6">
          <div className="text-center">
            <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">Failed to Load Agent</h2>
            {error && <p className="text-red-300">{error}</p>}
            <button
              onClick={loadAgent}
              className="mt-4 px-6 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto p-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Bot className="w-8 h-8 text-purple-400" />
            Unified Meeting Agent
          </h1>
          <p className="text-zinc-400 mt-2">
            Configure your AI meeting assistant powered by granite3.3:8b
          </p>
        </div>

        {/* Status Messages */}
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-red-900/20 border border-red-500/30">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-red-300">{error}</span>
            </div>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 rounded-xl bg-green-900/20 border border-green-500/30">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-300">{success}</span>
            </div>
          </div>
        )}

        {/* Main Configuration */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Basic Configuration */}
          <div className="lg:col-span-2 space-y-6">
            {/* Basic Info */}
            <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <Settings className="w-5 h-5 text-blue-400" />
                Basic Configuration
              </h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Agent Name</label>
                  <input
                    type="text"
                    value={agent.name}
                    onChange={(e) => updateAgent('name', e.target.value)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    placeholder="Meeting Assistant"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Description</label>
                  <input
                    type="text"
                    value={agent.description}
                    onChange={(e) => updateAgent('description', e.target.value)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    placeholder="AI assistant for meeting transcription and analysis"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Personality</label>
                  <input
                    type="text"
                    value={agent.personality}
                    onChange={(e) => updateAgent('personality', e.target.value)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    placeholder="Professional, concise, and actionable"
                  />
                </div>
              </div>
            </div>

            {/* AI Provider & Model */}
            <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <Brain className="w-5 h-5 text-green-400" />
                AI Provider & Model
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Provider</label>
                  <select
                    value={agent.provider_type}
                    onChange={(e) => updateAgent('provider_type', e.target.value)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  >
                    {availableProviders.map(provider => (
                      <option key={provider.type} value={provider.type}>
                        {provider.name} {provider.recommended && '(Recommended)'}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Model</label>
                  <select
                    value={agent.model_name}
                    onChange={(e) => updateAgent('model_name', e.target.value)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  >
                    {availableModels.length > 0 ? (
                      availableModels.map(model => (
                        <option key={model.name} value={model.name}>
                          {model.name} {model.recommended && '(Recommended)'}
                        </option>
                      ))
                    ) : (
                      <option value={agent.model_name}>{agent.model_name}</option>
                    )}
                  </select>
                </div>
              </div>

              {/* Model Configuration */}
              <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Temperature</label>
                  <input
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={agent.model_config.temperature}
                    onChange={(e) => updateNestedField('model_config', 'temperature', parseFloat(e.target.value))}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Max Tokens</label>
                  <input
                    type="number"
                    min="100"
                    max="4000"
                    step="100"
                    value={agent.model_config.max_tokens}
                    onChange={(e) => updateNestedField('model_config', 'max_tokens', parseInt(e.target.value))}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Top P</label>
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={agent.model_config.top_p}
                    onChange={(e) => updateNestedField('model_config', 'top_p', parseFloat(e.target.value))}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* System Prompt */}
            <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
              <h3 className="text-xl font-semibold mb-4">System Prompt</h3>
              <p className="text-sm text-zinc-400 mb-4">
                This prompt defines how the agent behaves and what it generates. Edit freely like Open WebUI custom models.
              </p>
              <textarea
                value={agent.system_prompt}
                onChange={(e) => updateAgent('system_prompt', e.target.value)}
                rows={12}
                className="w-full p-4 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none font-mono text-sm"
                placeholder="You are a professional meeting assistant..."
              />
            </div>

            {/* Progressive Settings */}
            <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <Zap className="w-5 h-5 text-yellow-400" />
                Progressive Analysis Settings
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Initial Interval (words)</label>
                  <input
                    type="number"
                    min="25"
                    max="200"
                    value={agent.progressive_config.initial_interval}
                    onChange={(e) => updateNestedField('progressive_config', 'initial_interval', parseInt(e.target.value))}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Multiplier</label>
                  <input
                    type="number"
                    min="1.1"
                    max="3.0"
                    step="0.1"
                    value={agent.progressive_config.multiplier}
                    onChange={(e) => updateNestedField('progressive_config', 'multiplier', parseFloat(e.target.value))}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Max Interval (words)</label>
                  <input
                    type="number"
                    min="200"
                    max="1000"
                    value={agent.progressive_config.max_interval}
                    onChange={(e) => updateNestedField('progressive_config', 'max_interval', parseInt(e.target.value))}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="mt-4">
                <label className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={agent.progressive_config.enabled}
                    onChange={(e) => updateNestedField('progressive_config', 'enabled', e.target.checked)}
                    className="w-4 h-4 text-purple-600 bg-zinc-800 border-zinc-700 rounded focus:ring-purple-500"
                  />
                  <span className="text-sm">Enable progressive analysis</span>
                </label>
              </div>
            </div>
          </div>

          {/* Right Column: Actions & Testing */}
          <div className="space-y-6">
            {/* Action Buttons */}
            <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
              <h3 className="text-lg font-semibold mb-4">Actions</h3>
              <div className="space-y-3">
                <button
                  onClick={saveAgent}
                  disabled={saving}
                  className="w-full px-4 py-3 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {saving ? <Loader className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {saving ? 'Saving...' : 'Save Configuration'}
                </button>

                <button
                  onClick={testAgent}
                  disabled={testing || saving}
                  className="w-full px-4 py-3 bg-green-600 hover:bg-green-700 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {testing ? <Loader className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
                  {testing ? 'Testing...' : 'Test Agent'}
                </button>

                <button
                  onClick={resetAgent}
                  disabled={saving}
                  className="w-full px-4 py-3 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <RotateCcw className="w-4 h-4" />
                  Reset to Default
                </button>
              </div>
            </div>

            {/* Test Results */}
            {testResult && (
              <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
                <h3 className="text-lg font-semibold mb-4">Test Results</h3>
                {testResult.success ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-green-400">
                      <CheckCircle className="w-4 h-4" />
                      <span className="text-sm">Test successful!</span>
                    </div>
                    <div className="p-3 bg-zinc-800 rounded-lg">
                      <div className="text-xs text-zinc-400 mb-2">Executive Summary:</div>
                      <div className="text-sm">{testResult.test_result?.executive}</div>
                    </div>
                    <div className="text-xs text-zinc-500">
                      Model: {testResult.model_used}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-red-400">
                      <AlertCircle className="w-4 h-4" />
                      <span className="text-sm">Test failed</span>
                    </div>
                    <div className="p-3 bg-red-900/20 rounded-lg text-sm text-red-300">
                      {testResult.error}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Current Status */}
            <div className="p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
              <h3 className="text-lg font-semibold mb-4">Current Status</h3>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-zinc-400">Provider:</span>
                  <span>{agent.provider_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Model:</span>
                  <span>{agent.model_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Status:</span>
                  <span className={agent.is_active ? 'text-green-400' : 'text-red-400'}>
                    {agent.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Progressive:</span>
                  <span className={agent.progressive_config.enabled ? 'text-green-400' : 'text-zinc-400'}>
                    {agent.progressive_config.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}