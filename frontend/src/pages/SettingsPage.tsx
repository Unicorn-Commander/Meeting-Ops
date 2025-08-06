import React, { useState, useEffect } from 'react';
import { 
  Save, Server, Key, Brain, Mic, AlertCircle, CheckCircle,
  ChevronDown, ChevronUp, TestTube, Loader
} from 'lucide-react';

interface LLMConfig {
  provider: 'ollama' | 'openai' | 'anthropic' | 'llama.cpp';
  url: string;
  apiKey?: string;
  model: string;
  enabled: boolean;
}

interface TranscriptionConfig {
  provider: 'whisper' | 'whisperx';
  model: 'tiny' | 'base' | 'small' | 'medium' | 'large';
  useNPU: boolean;
  device: string;
}

export const SettingsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'llm' | 'transcription' | 'general'>('llm');
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<{[key: string]: {success: boolean, message: string}}>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);
  const [availableOllamaModels, setAvailableOllamaModels] = useState<string[]>([]);

  // LLM Settings
  const [ollamaConfig, setOllamaConfig] = useState<LLMConfig>({
    provider: 'ollama',
    url: 'http://localhost:11434',
    model: 'gemma3n:latest',
    enabled: true
  });

  const [openaiConfig, setOpenaiConfig] = useState<LLMConfig>({
    provider: 'openai',
    url: 'https://api.openai.com/v1',
    apiKey: '',
    model: 'gpt-3.5-turbo',
    enabled: false
  });

  const [anthropicConfig, setAnthropicConfig] = useState<LLMConfig>({
    provider: 'anthropic',
    url: 'https://api.anthropic.com',
    apiKey: '',
    model: 'claude-3-opus-20240229',
    enabled: false
  });

  // Transcription Settings
  const [transcriptionConfig, setTranscriptionConfig] = useState<TranscriptionConfig>({
    provider: 'whisper',
    model: 'base',
    useNPU: true,
    device: '/dev/accel/accel0'
  });

  useEffect(() => {
    loadSettings();
    fetchOllamaModels();
  }, []);

  const fetchOllamaModels = async () => {
    try {
      const response = await fetch('/api/ollama/models', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAvailableOllamaModels(data.models || []);
      }
    } catch (error) {
      console.log('Could not fetch Ollama models');
    }
  };

  const loadSettings = async () => {
    try {
      const response = await fetch('/api/settings/ai', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const settings = await response.json();
        
        // Load Ollama settings
        if (settings.ollama) {
          setOllamaConfig({
            provider: 'ollama',
            url: settings.ollama.url || 'http://localhost:11434',
            model: settings.ollama.model || 'gemma3n:latest',
            enabled: settings.ollama.enabled !== false
          });
        }
        
        // Load OpenAI settings
        if (settings.openai) {
          setOpenaiConfig({
            provider: 'openai',
            url: settings.openai.url || 'https://api.openai.com/v1',
            apiKey: settings.openai.apiKey || '',
            model: settings.openai.model || 'gpt-3.5-turbo',
            enabled: settings.openai.enabled === true
          });
        }
        
        // Load Anthropic settings
        if (settings.anthropic) {
          setAnthropicConfig({
            provider: 'anthropic',
            url: settings.anthropic.url || 'https://api.anthropic.com',
            apiKey: settings.anthropic.apiKey || '',
            model: settings.anthropic.model || 'claude-3-opus-20240229',
            enabled: settings.anthropic.enabled === true
          });
        }
        
        // Load transcription settings
        if (settings.transcription) {
          setTranscriptionConfig(settings.transcription);
        }
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage(null);
    
    try {
      const settings = {
        ollama: ollamaConfig,
        openai: openaiConfig,
        anthropic: anthropicConfig,
        transcription: transcriptionConfig
      };
      
      const response = await fetch('/api/settings/ai', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(settings)
      });
      
      if (response.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' });
      } else {
        throw new Error('Failed to save settings');
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to save settings' });
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async (provider: string) => {
    setTestingProvider(provider);
    
    try {
      let testUrl = '';
      let testBody = {};
      
      switch (provider) {
        case 'ollama':
          testUrl = '/api/test/ollama';
          testBody = { url: ollamaConfig.url, model: ollamaConfig.model };
          break;
        case 'openai':
          testUrl = '/api/test/openai';
          testBody = { apiKey: openaiConfig.apiKey, model: openaiConfig.model };
          break;
        case 'anthropic':
          testUrl = '/api/test/anthropic';
          testBody = { apiKey: anthropicConfig.apiKey, model: anthropicConfig.model };
          break;
      }
      
      const response = await fetch(testUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(testBody)
      });
      
      const result = await response.json();
      
      setTestResults({
        ...testResults,
        [provider]: {
          success: result.success,
          message: result.message || (result.success ? 'Connection successful!' : 'Connection failed')
        }
      });
    } catch (error) {
      setTestResults({
        ...testResults,
        [provider]: {
          success: false,
          message: 'Connection test failed'
        }
      });
    } finally {
      setTestingProvider(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-gray-800 rounded-lg p-6">
        <h1 className="text-2xl font-bold text-white mb-6">AI Settings</h1>
        
        {/* Tabs */}
        <div className="flex gap-4 mb-6 border-b border-gray-700">
          <button
            onClick={() => setActiveTab('llm')}
            className={`pb-2 px-4 font-medium transition-colors ${
              activeTab === 'llm' 
                ? 'text-purple-400 border-b-2 border-purple-400' 
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            LLM Providers
          </button>
          <button
            onClick={() => setActiveTab('transcription')}
            className={`pb-2 px-4 font-medium transition-colors ${
              activeTab === 'transcription' 
                ? 'text-purple-400 border-b-2 border-purple-400' 
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            Transcription
          </button>
        </div>

        {/* Message */}
        {message && (
          <div className={`mb-4 p-4 rounded-lg flex items-center gap-2 ${
            message.type === 'success' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
          }`}>
            {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
            {message.text}
          </div>
        )}

        {/* LLM Tab */}
        {activeTab === 'llm' && (
          <div className="space-y-6">
            {/* Ollama Configuration (Local - Priority) */}
            <div className="bg-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Server className="w-5 h-5 text-green-400" />
                  <h3 className="text-lg font-semibold text-white">Ollama (Local - Recommended)</h3>
                  <span className="px-2 py-1 bg-green-900/50 text-green-400 text-xs rounded-full">
                    Priority
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-gray-300">
                    <input
                      type="checkbox"
                      checked={ollamaConfig.enabled}
                      onChange={(e) => setOllamaConfig({...ollamaConfig, enabled: e.target.checked})}
                      className="rounded"
                    />
                    Enabled
                  </label>
                  <button
                    onClick={() => testConnection('ollama')}
                    disabled={testingProvider === 'ollama'}
                    className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm flex items-center gap-2"
                  >
                    {testingProvider === 'ollama' ? (
                      <Loader className="w-4 h-4 animate-spin" />
                    ) : (
                      <TestTube className="w-4 h-4" />
                    )}
                    Test
                  </button>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">URL</label>
                  <input
                    type="text"
                    value={ollamaConfig.url}
                    onChange={(e) => setOllamaConfig({...ollamaConfig, url: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                    placeholder="http://localhost:11434"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Model
                    {availableOllamaModels.length > 0 && (
                      <span className="ml-2 text-xs text-green-400">
                        ({availableOllamaModels.length} available)
                      </span>
                    )}
                  </label>
                  <div className="flex gap-2">
                    <select
                      value={ollamaConfig.model}
                      onChange={(e) => setOllamaConfig({...ollamaConfig, model: e.target.value})}
                      className="flex-1 px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                    >
                      {availableOllamaModels.length > 0 ? (
                        availableOllamaModels.map(model => (
                          <option key={model} value={model}>{model}</option>
                        ))
                      ) : (
                        <>
                          <option value="gemma3n:latest">Gemma 3N Latest</option>
                          <option value="gemma3:27b">Gemma 3 27B</option>
                          <option value="llama3.2:3b">LLaMA 3.2 3B</option>
                          <option value="qwen2.5:14b">Qwen 2.5 14B</option>
                          <option value="deepseek-r1:7b">DeepSeek R1 7B</option>
                        </>
                      )}
                    </select>
                    <button
                      onClick={fetchOllamaModels}
                      className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm"
                      title="Refresh available models"
                    >
                      🔄
                    </button>
                  </div>
                </div>
              </div>
              
              {testResults['ollama'] && (
                <div className={`mt-3 p-3 rounded-lg ${
                  testResults['ollama'].success ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                }`}>
                  {testResults['ollama'].message}
                </div>
              )}
            </div>

            {/* OpenAI Configuration */}
            <div className="bg-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Brain className="w-5 h-5 text-blue-400" />
                  <h3 className="text-lg font-semibold text-white">OpenAI (Optional)</h3>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-gray-300">
                    <input
                      type="checkbox"
                      checked={openaiConfig.enabled}
                      onChange={(e) => setOpenaiConfig({...openaiConfig, enabled: e.target.checked})}
                      className="rounded"
                    />
                    Enabled
                  </label>
                  <button
                    onClick={() => testConnection('openai')}
                    disabled={testingProvider === 'openai' || !openaiConfig.apiKey}
                    className="px-3 py-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm flex items-center gap-2"
                  >
                    {testingProvider === 'openai' ? (
                      <Loader className="w-4 h-4 animate-spin" />
                    ) : (
                      <TestTube className="w-4 h-4" />
                    )}
                    Test
                  </button>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">API Key</label>
                  <input
                    type="password"
                    value={openaiConfig.apiKey}
                    onChange={(e) => setOpenaiConfig({...openaiConfig, apiKey: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                    placeholder="sk-..."
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Model</label>
                  <select
                    value={openaiConfig.model}
                    onChange={(e) => setOpenaiConfig({...openaiConfig, model: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                  >
                    <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                    <option value="gpt-4">GPT-4</option>
                    <option value="gpt-4-turbo-preview">GPT-4 Turbo</option>
                  </select>
                </div>
              </div>
              
              {testResults['openai'] && (
                <div className={`mt-3 p-3 rounded-lg ${
                  testResults['openai'].success ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                }`}>
                  {testResults['openai'].message}
                </div>
              )}
            </div>

            {/* Anthropic Configuration */}
            <div className="bg-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Brain className="w-5 h-5 text-purple-400" />
                  <h3 className="text-lg font-semibold text-white">Anthropic (Optional)</h3>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-gray-300">
                    <input
                      type="checkbox"
                      checked={anthropicConfig.enabled}
                      onChange={(e) => setAnthropicConfig({...anthropicConfig, enabled: e.target.checked})}
                      className="rounded"
                    />
                    Enabled
                  </label>
                  <button
                    onClick={() => testConnection('anthropic')}
                    disabled={testingProvider === 'anthropic' || !anthropicConfig.apiKey}
                    className="px-3 py-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm flex items-center gap-2"
                  >
                    {testingProvider === 'anthropic' ? (
                      <Loader className="w-4 h-4 animate-spin" />
                    ) : (
                      <TestTube className="w-4 h-4" />
                    )}
                    Test
                  </button>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">API Key</label>
                  <input
                    type="password"
                    value={anthropicConfig.apiKey}
                    onChange={(e) => setAnthropicConfig({...anthropicConfig, apiKey: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                    placeholder="sk-ant-..."
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Model</label>
                  <select
                    value={anthropicConfig.model}
                    onChange={(e) => setAnthropicConfig({...anthropicConfig, model: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                  >
                    <option value="claude-3-opus-20240229">Claude 3 Opus</option>
                    <option value="claude-3-sonnet-20240229">Claude 3 Sonnet</option>
                    <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
                  </select>
                </div>
              </div>
              
              {testResults['anthropic'] && (
                <div className={`mt-3 p-3 rounded-lg ${
                  testResults['anthropic'].success ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                }`}>
                  {testResults['anthropic'].message}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transcription Tab */}
        {activeTab === 'transcription' && (
          <div className="space-y-6">
            <div className="bg-gray-700 rounded-lg p-4">
              <div className="flex items-center gap-3 mb-4">
                <Mic className="w-5 h-5 text-purple-400" />
                <h3 className="text-lg font-semibold text-white">Transcription Settings</h3>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Provider</label>
                  <select
                    value={transcriptionConfig.provider}
                    onChange={(e) => setTranscriptionConfig({...transcriptionConfig, provider: e.target.value as any})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                  >
                    <option value="whisper">Whisper</option>
                    <option value="whisperx">WhisperX (with diarization)</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Model Size</label>
                  <select
                    value={transcriptionConfig.model}
                    onChange={(e) => setTranscriptionConfig({...transcriptionConfig, model: e.target.value as any})}
                    className="w-full px-4 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                  >
                    <option value="tiny">Tiny (39M params)</option>
                    <option value="base">Base (74M params)</option>
                    <option value="small">Small (244M params)</option>
                    <option value="medium">Medium (769M params)</option>
                    <option value="large">Large (1550M params)</option>
                  </select>
                </div>
              </div>
              
              <div className="mt-4">
                <label className="flex items-center gap-2 text-gray-300">
                  <input
                    type="checkbox"
                    checked={transcriptionConfig.useNPU}
                    onChange={(e) => setTranscriptionConfig({...transcriptionConfig, useNPU: e.target.checked})}
                    className="rounded"
                  />
                  Use NPU Acceleration (AMD Phoenix)
                </label>
                {transcriptionConfig.useNPU && (
                  <div className="mt-2 ml-6 text-sm text-green-400">
                    NPU device: {transcriptionConfig.device}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Save Button */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={saveSettings}
            disabled={saving}
            className="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg flex items-center gap-2"
          >
            {saving ? (
              <Loader className="w-5 h-5 animate-spin" />
            ) : (
              <Save className="w-5 h-5" />
            )}
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};