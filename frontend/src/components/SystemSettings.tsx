import React, { useState, useEffect } from 'react';
import { 
  Settings, Save, RefreshCw, AlertCircle, Check, X,
  Cpu, Mic, Bot, Database, Shield, Network, HardDrive,
  Volume2, Zap, Brain, Server, Key, Lock
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface SystemSettings {
  ai: {
    ollama: {
      provider: string;
      url: string;
      apiKey?: string;
      model: string;
      enabled: boolean;
    };
    openai?: {
      provider: string;
      url: string;
      apiKey?: string;
      model: string;
      enabled: boolean;
    };
    transcription: {
      provider: string;
      model: string;
      useNPU: boolean;
      device: string;
    };
  };
  audio: {
    sampleRate: number;
    channels: number;
    format: string;
    device: string;
    bufferSize: number;
  };
  storage: {
    basePath: string;
    maxSize: number;
    compression: boolean;
    autoCleanup: boolean;
    retentionDays: number;
  };
  security: {
    sessionTimeout: number;
    requireAuth: boolean;
    allowRegistration: boolean;
    passwordMinLength: number;
  };
}

export const SystemSettings: React.FC = () => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [originalSettings, setOriginalSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'ai' | 'audio' | 'storage' | 'security'>('ai');
  const [hasChanges, setHasChanges] = useState(false);
  const [testingConnection, setTestingConnection] = useState<string | null>(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  useEffect(() => {
    if (settings && originalSettings) {
      setHasChanges(JSON.stringify(settings) !== JSON.stringify(originalSettings));
    }
  }, [settings, originalSettings]);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      
      // Fetch AI settings
      const aiResponse = await fetch(`${API_BASE_URL}/api/settings/ai`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      let aiSettings = {};
      if (aiResponse.ok) {
        aiSettings = await aiResponse.json();
      } else {
        // Default AI settings
        aiSettings = {
          ollama: {
            provider: 'ollama',
            url: 'http://localhost:11434',
            model: 'gemma3n:e4b',
            enabled: true
          },
          transcription: {
            provider: 'whisperx',
            model: 'large-v3',
            useNPU: true,
            device: '/dev/accel/accel0'
          }
        };
      }

      // Mock other settings for now (would come from backend)
      const fullSettings: SystemSettings = {
        ai: aiSettings as any,
        audio: {
          sampleRate: 44100,
          channels: 1,
          format: 'WAV',
          device: 'hw:0,0',
          bufferSize: 1024
        },
        storage: {
          basePath: '/home/ucadmin/Meeting-Ops/data',
          maxSize: 100,
          compression: true,
          autoCleanup: true,
          retentionDays: 90
        },
        security: {
          sessionTimeout: 24,
          requireAuth: true,
          allowRegistration: false,
          passwordMinLength: 8
        }
      };

      setSettings(fullSettings);
      setOriginalSettings(JSON.parse(JSON.stringify(fullSettings)));
    } catch (error) {
      console.error('Failed to fetch settings:', error);
      toast.error('Failed to load system settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!settings) return;

    setSaving(true);
    try {
      const token = localStorage.getItem('access_token');
      
      // Save AI settings
      const aiResponse = await fetch(`${API_BASE_URL}/api/settings/ai`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(settings.ai)
      });

      if (aiResponse.ok) {
        setOriginalSettings(JSON.parse(JSON.stringify(settings)));
        setHasChanges(false);
        toast.success('Settings saved successfully');
      } else {
        throw new Error('Failed to save AI settings');
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async (service: string) => {
    if (!settings) return;

    setTestingConnection(service);
    try {
      let url = '';
      if (service === 'ollama') {
        url = `${settings.ai.ollama.url}/api/tags`;
      }

      const response = await fetch(url);
      if (response.ok) {
        toast.success(`${service} connection successful`);
      } else {
        throw new Error(`${service} connection failed`);
      }
    } catch (error) {
      toast.error(`Failed to connect to ${service}`);
    } finally {
      setTestingConnection(null);
    }
  };

  const handleReset = () => {
    if (originalSettings) {
      setSettings(JSON.parse(JSON.stringify(originalSettings)));
    }
  };

  const updateSetting = (path: string[], value: any) => {
    if (!settings) return;

    const newSettings = JSON.parse(JSON.stringify(settings));
    let current = newSettings;
    
    for (let i = 0; i < path.length - 1; i++) {
      current = current[path[i]];
    }
    current[path[path.length - 1]] = value;
    
    setSettings(newSettings);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="text-center py-12 text-gray-400">
        <AlertCircle className="w-16 h-16 mx-auto mb-4 opacity-50" />
        <p>Failed to load system settings</p>
      </div>
    );
  }

  const tabs = [
    { id: 'ai', label: 'AI & Models', icon: Brain },
    { id: 'audio', label: 'Audio', icon: Mic },
    { id: 'storage', label: 'Storage', icon: HardDrive },
    { id: 'security', label: 'Security', icon: Shield }
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">System Settings</h2>
        <div className="flex items-center space-x-4">
          {hasChanges && (
            <>
              <button
                onClick={handleReset}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                Reset
              </button>
              <button
                onClick={handleSaveSettings}
                disabled={saving}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center"
              >
                {saving ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Save className="w-4 h-4 mr-2" />
                )}
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-gray-800 rounded-lg p-1 border border-gray-700">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center px-4 py-3 rounded-md transition-colors ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              <tab.icon className="w-4 h-4 mr-2" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Settings Content */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        {activeTab === 'ai' && (
          <div className="space-y-6">
            <h3 className="text-xl font-semibold mb-4">AI & Language Models</h3>
            
            {/* Ollama Settings */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center">
                  <Bot className="w-6 h-6 mr-3 text-blue-400" />
                  <h4 className="text-lg font-semibold">Ollama (Local LLM)</h4>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleTestConnection('ollama')}
                    disabled={testingConnection === 'ollama'}
                    className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm"
                  >
                    {testingConnection === 'ollama' ? 'Testing...' : 'Test'}
                  </button>
                  <label className="flex items-center">
                    <input
                      type="checkbox"
                      checked={settings.ai.ollama.enabled}
                      onChange={(e) => updateSetting(['ai', 'ollama', 'enabled'], e.target.checked)}
                      className="mr-2 rounded border-gray-600 bg-gray-700 text-purple-600"
                    />
                    <span className="text-sm">Enabled</span>
                  </label>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Server URL</label>
                  <input
                    type="url"
                    value={settings.ai.ollama.url}
                    onChange={(e) => updateSetting(['ai', 'ollama', 'url'], e.target.value)}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Model</label>
                  <select
                    value={settings.ai.ollama.model}
                    onChange={(e) => updateSetting(['ai', 'ollama', 'model'], e.target.value)}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="gemma3n:e4b">Gemma3n:e4b</option>
                    <option value="llama3.2">Llama 3.2</option>
                    <option value="llama3.1">Llama 3.1</option>
                    <option value="mistral">Mistral</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Transcription Settings */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center mb-4">
                <Zap className="w-6 h-6 mr-3 text-green-400" />
                <h4 className="text-lg font-semibold">Speech-to-Text</h4>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Model</label>
                  <select
                    value={settings.ai.transcription.model}
                    onChange={(e) => updateSetting(['ai', 'transcription', 'model'], e.target.value)}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="large-v3">Whisper Large-v3 (Best)</option>
                    <option value="large-v2">Whisper Large-v2</option>
                    <option value="large">Whisper Large</option>
                    <option value="medium">Whisper Medium</option>
                    <option value="small">Whisper Small</option>
                    <option value="base">Whisper Base (Fastest)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Device</label>
                  <select
                    value={settings.ai.transcription.device}
                    onChange={(e) => updateSetting(['ai', 'transcription', 'device'], e.target.value)}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="/dev/accel/accel0">AMD NPU (/dev/accel/accel0)</option>
                    <option value="cpu">CPU</option>
                    <option value="cuda">NVIDIA GPU (CUDA)</option>
                  </select>
                </div>
              </div>
              
              <div className="mt-4">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.ai.transcription.useNPU}
                    onChange={(e) => updateSetting(['ai', 'transcription', 'useNPU'], e.target.checked)}
                    className="mr-3 rounded border-gray-600 bg-gray-700 text-purple-600"
                  />
                  <span>Use NPU acceleration (220x faster)</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'audio' && (
          <div className="space-y-6">
            <h3 className="text-xl font-semibold mb-4">Audio Configuration</h3>
            
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Sample Rate</label>
                <select
                  value={settings.audio.sampleRate}
                  onChange={(e) => updateSetting(['audio', 'sampleRate'], parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                >
                  <option value={8000}>8 kHz</option>
                  <option value={16000}>16 kHz</option>
                  <option value={22050}>22.05 kHz</option>
                  <option value={44100}>44.1 kHz (CD Quality)</option>
                  <option value={48000}>48 kHz</option>
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Channels</label>
                <select
                  value={settings.audio.channels}
                  onChange={(e) => updateSetting(['audio', 'channels'], parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                >
                  <option value={1}>Mono</option>
                  <option value={2}>Stereo</option>
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Audio Device</label>
                <input
                  type="text"
                  value={settings.audio.device}
                  onChange={(e) => updateSetting(['audio', 'device'], e.target.value)}
                  placeholder="hw:0,0"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Buffer Size</label>
                <select
                  value={settings.audio.bufferSize}
                  onChange={(e) => updateSetting(['audio', 'bufferSize'], parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                >
                  <option value={512}>512 samples</option>
                  <option value={1024}>1024 samples</option>
                  <option value={2048}>2048 samples</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'storage' && (
          <div className="space-y-6">
            <h3 className="text-xl font-semibold mb-4">Storage Management</h3>
            
            <div className="grid grid-cols-1 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Base Storage Path</label>
                <input
                  type="text"
                  value={settings.storage.basePath}
                  onChange={(e) => updateSetting(['storage', 'basePath'], e.target.value)}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Max Storage (GB)</label>
                  <input
                    type="number"
                    value={settings.storage.maxSize}
                    onChange={(e) => updateSetting(['storage', 'maxSize'], parseInt(e.target.value))}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Retention (Days)</label>
                  <input
                    type="number"
                    value={settings.storage.retentionDays}
                    onChange={(e) => updateSetting(['storage', 'retentionDays'], parseInt(e.target.value))}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
              
              <div className="space-y-3">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.storage.compression}
                    onChange={(e) => updateSetting(['storage', 'compression'], e.target.checked)}
                    className="mr-3 rounded border-gray-600 bg-gray-700 text-purple-600"
                  />
                  <span>Enable audio compression (saves ~90% space)</span>
                </label>
                
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.storage.autoCleanup}
                    onChange={(e) => updateSetting(['storage', 'autoCleanup'], e.target.checked)}
                    className="mr-3 rounded border-gray-600 bg-gray-700 text-purple-600"
                  />
                  <span>Automatic cleanup of old recordings</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'security' && (
          <div className="space-y-6">
            <h3 className="text-xl font-semibold mb-4">Security Settings</h3>
            
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Session Timeout (Hours)</label>
                <input
                  type="number"
                  value={settings.security.sessionTimeout}
                  onChange={(e) => updateSetting(['security', 'sessionTimeout'], parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Password Min Length</label>
                <input
                  type="number"
                  value={settings.security.passwordMinLength}
                  onChange={(e) => updateSetting(['security', 'passwordMinLength'], parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>
            
            <div className="space-y-3">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={settings.security.requireAuth}
                  onChange={(e) => updateSetting(['security', 'requireAuth'], e.target.checked)}
                  className="mr-3 rounded border-gray-600 bg-gray-700 text-purple-600"
                />
                <span>Require authentication for all access</span>
              </label>
              
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={settings.security.allowRegistration}
                  onChange={(e) => updateSetting(['security', 'allowRegistration'], e.target.checked)}
                  className="mr-3 rounded border-gray-600 bg-gray-700 text-purple-600"
                />
                <span>Allow user self-registration</span>
              </label>
            </div>
          </div>
        )}
      </div>

      {hasChanges && (
        <div className="bg-yellow-900/50 border border-yellow-600 rounded-lg p-4 flex items-center">
          <AlertCircle className="w-5 h-5 text-yellow-400 mr-3" />
          <span className="text-yellow-200">You have unsaved changes. Don't forget to save!</span>
        </div>
      )}
    </div>
  );
};