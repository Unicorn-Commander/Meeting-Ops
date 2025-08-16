import React, { useState, useEffect } from 'react';
import { 
  Brain, 
  Settings, 
  Plus, 
  Check, 
  X, 
  Eye, 
  EyeOff,
  Server,
  Key,
  Zap
} from 'lucide-react';
import { config } from '../../config';

interface AIProvider {
  id: string;
  name: string;
  type: 'openai' | 'anthropic' | 'ollama' | 'custom';
  apiUrl: string;
  apiKey?: string;
  models: string[];
  isActive: boolean;
}

const PROVIDER_PRESETS = {
  openai: { 
    name: "OpenAI",
    apiUrl: "https://api.openai.com/v1", 
    models: ["gpt-4o", "gpt-4", "gpt-3.5-turbo"] 
  },
  anthropic: { 
    name: "Anthropic",
    apiUrl: "https://api.anthropic.com", 
    models: ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"] 
  },
  ollama: { 
    name: "Ollama (Local)",
    apiUrl: "http://localhost:11434", 
    models: [] // Auto-detect from /api/tags
  },
  custom: { 
    name: "Custom Provider",
    apiUrl: "", 
    models: [] 
  }
};

export default function AISettings() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [showApiKey, setShowApiKey] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [editingProvider, setEditingProvider] = useState<AIProvider | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    try {
      setBackendError(null);
      const response = await fetch(`${config.apiUrl}/api/advanced/ai-providers`);
      if (response.ok) {
        const data = await response.json();
        setProviders(data);
        return;
      } else {
        throw new Error(`Backend returned ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to load providers from backend:', error);
      setBackendError('Cannot connect to Meeting-Ops backend. Please check that the backend service is running.');
      setProviders([]);
    }
  };

  const addProvider = (type: keyof typeof PROVIDER_PRESETS) => {
    const preset = PROVIDER_PRESETS[type];
    const newProvider: AIProvider = {
      id: Date.now().toString(),
      ...preset,
      type,
      isActive: false
    };
    setEditingProvider(newProvider);
  };

  const saveProvider = async (provider: AIProvider) => {
    setLoading(true);
    try {
      // Test connection first
      if (provider.type === 'ollama') {
        try {
          const testResponse = await fetch(`${provider.apiUrl}/api/tags`);
          if (testResponse.ok) {
            const data = await testResponse.json();
            provider.models = data.models?.map((m: any) => m.name) || [];
          }
        } catch (error) {
          console.log('Could not test Ollama connection, proceeding with save');
        }
      }

      // Save to backend
      const response = await fetch(`${config.apiUrl}/api/advanced/ai-providers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(provider)
      });

      if (response.ok) {
        updateProvidersList(provider);
        setEditingProvider(null);
      } else {
        alert('Failed to save provider. Backend returned error.');
      }
    } catch (error) {
      console.error('Failed to save provider:', error);
      alert('Failed to save provider. Please check the configuration.');
    } finally {
      setLoading(false);
    }
  };

  const updateProvidersList = (provider: AIProvider) => {
    const existing = providers.find(p => p.id === provider.id);
    if (existing) {
      setProviders(prev => prev.map(p => p.id === provider.id ? provider : p));
    } else {
      setProviders(prev => [...prev, provider]);
    }
  };

  const setActiveProvider = async (providerId: string) => {
    // Update all providers to set only the selected one as active
    const updatedProviders = providers.map(p => ({
      ...p,
      isActive: p.id === providerId
    }));
    setProviders(updatedProviders);

    try {
      // Update the selected provider to be active in backend
      const response = await fetch(`${config.apiUrl}/api/advanced/ai-providers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...updatedProviders.find(p => p.id === providerId),
          isActive: true
        })
      });
      
      // Also update other providers to be inactive
      const inactiveProviders = updatedProviders.filter(p => p.id !== providerId);
      for (const provider of inactiveProviders) {
        await fetch(`${config.apiUrl}/api/advanced/ai-providers`, {
          method: 'POST', 
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...provider,
            isActive: false
          })
        });
      }
      
      if (!response.ok) {
        alert('Failed to set active provider. Backend returned error.');
      }
    } catch (error) {
      console.error('Failed to set active provider:', error);
      alert('Failed to set active provider. Please check backend connection.');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Brain className="w-8 h-8 text-purple-400" />
            AI Settings
          </h1>
          <p className="text-zinc-400 mt-2">
            Configure AI providers and inference settings for Meeting-Ops
          </p>
        </div>

        {/* Backend Error */}
        {backendError && (
          <div className="mb-8 p-6 rounded-2xl bg-red-900/20 border border-red-500/30">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
              <h2 className="text-xl font-semibold text-red-300">Backend Connection Error</h2>
            </div>
            <p className="text-red-200 mb-4">{backendError}</p>
            <button
              onClick={loadProviders}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Current Active Provider */}
        <div className="mb-8 p-6 rounded-2xl bg-zinc-900/70 border border-zinc-800">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Zap className="w-5 h-5 text-green-400" />
            Active Provider
          </h2>
          {providers.find(p => p.isActive) ? (
            <div className="flex items-center justify-between p-4 rounded-xl bg-green-500/10 border border-green-500/30">
              <div>
                <div className="font-medium text-green-300">
                  {providers.find(p => p.isActive)?.name}
                </div>
                <div className="text-sm text-zinc-400">
                  {providers.find(p => p.isActive)?.apiUrl}
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  Models: {providers.find(p => p.isActive)?.models.join(', ') || 'Loading...'}
                </div>
              </div>
              <Check className="w-6 h-6 text-green-400" />
            </div>
          ) : (
            <div className="text-center py-8 text-zinc-500">
              No active provider configured
            </div>
          )}
        </div>

        {/* Provider List */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Server className="w-5 h-5 text-blue-400" />
              Configured Providers
            </h2>
            <div className="flex gap-2">
              {Object.entries(PROVIDER_PRESETS).map(([key, preset]) => (
                <button
                  key={key}
                  onClick={() => addProvider(key as keyof typeof PROVIDER_PRESETS)}
                  className="px-3 py-2 text-sm bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Add {preset.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4">
            {providers.map((provider) => (
              <div
                key={provider.id}
                className={`p-6 rounded-2xl border transition-all ${
                  provider.isActive
                    ? 'bg-green-500/5 border-green-500/30'
                    : 'bg-zinc-900/70 border-zinc-800 hover:border-zinc-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold">{provider.name}</h3>
                      {provider.isActive && (
                        <span className="px-2 py-1 text-xs bg-green-500/20 text-green-300 rounded-full">
                          Active
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-zinc-400">
                      <div>URL: {provider.apiUrl}</div>
                      {provider.apiKey && (
                        <div className="flex items-center gap-2 mt-1">
                          <Key className="w-3 h-3" />
                          API Key: {showApiKey[provider.id] ? provider.apiKey : '••••••••••••'}
                          <button
                            onClick={() => setShowApiKey(prev => ({
                              ...prev,
                              [provider.id]: !prev[provider.id]
                            }))}
                            className="text-purple-400 hover:text-purple-300"
                          >
                            {showApiKey[provider.id] ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                          </button>
                        </div>
                      )}
                      <div className="mt-1">
                        Models: {provider.models.length > 0 ? provider.models.join(', ') : 'None detected'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setEditingProvider(provider)}
                      className="p-2 text-zinc-400 hover:text-white transition-colors"
                    >
                      <Settings className="w-4 h-4" />
                    </button>
                    {!provider.isActive && (
                      <button
                        onClick={() => setActiveProvider(provider.id)}
                        className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 rounded transition-colors"
                      >
                        Activate
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Edit Provider Modal */}
        {editingProvider && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-zinc-900 rounded-2xl p-6 max-w-lg w-full">
              <h3 className="text-xl font-semibold mb-4">
                {providers.find(p => p.id === editingProvider.id) ? 'Edit' : 'Add'} Provider
              </h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Name</label>
                  <input
                    type="text"
                    value={editingProvider.name}
                    onChange={(e) => setEditingProvider(prev => prev ? {...prev, name: e.target.value} : null)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">API URL</label>
                  <input
                    type="text"
                    value={editingProvider.apiUrl}
                    onChange={(e) => setEditingProvider(prev => prev ? {...prev, apiUrl: e.target.value} : null)}
                    className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                    placeholder="https://api.example.com/v1"
                  />
                </div>

                {editingProvider.type !== 'ollama' && (
                  <div>
                    <label className="block text-sm font-medium mb-2">API Key</label>
                    <input
                      type="password"
                      value={editingProvider.apiKey || ''}
                      onChange={(e) => setEditingProvider(prev => prev ? {...prev, apiKey: e.target.value} : null)}
                      className="w-full p-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:border-purple-500 focus:outline-none"
                      placeholder="Enter API key..."
                    />
                  </div>
                )}

                <div className="flex justify-end gap-3">
                  <button
                    onClick={() => setEditingProvider(null)}
                    className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => saveProvider(editingProvider)}
                    disabled={loading}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {loading ? 'Testing...' : 'Save'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}