import React, { useState, useEffect } from 'react';
import {
  Settings,
  Mic,
  Brain,
  Mail,
  Webhook,
  Calendar,
  Save,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Zap,
  Database,
  Speaker,
  FileText,
  Clock,
  Globe
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface SettingsData {
  [key: string]: any;
  audio?: {
    input_source?: { value: string };
    sample_rate?: { value: number };
    channels?: { value: number };
  };
  ai?: {
    whisper_model?: { value: string };
    enable_speaker_diarization?: { value: boolean };
    confidence_threshold?: { value: number };
  };
  email?: {
    smtp_host?: { value: string };
    smtp_port?: { value: number };
    smtp_user?: { value: string };
    from_email?: { value: string };
    smtp_use_tls?: { value: boolean };
  };
  storage?: {
    auto_cleanup?: { value: boolean };
    retention_days?: { value: number };
    max_storage_gb?: { value: number };
  };
  webhooks?: {
    enabled?: { value: boolean };
    retry_attempts?: { value: number };
    timeout_seconds?: { value: number };
  };
}

export const ApplicationAdminPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState('audio');
  const [settings, setSettings] = useState<SettingsData>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [audioDevices, setAudioDevices] = useState<any[]>([]);

  useEffect(() => {
    fetchSettings();
    fetchAudioDevices();
  }, []);

  const fetchSettings = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/settings`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSettings(data.settings || {});
      } else {
        setError('Failed to fetch settings');
      }
    } catch (err) {
      setError('Network error while fetching settings');
    } finally {
      setLoading(false);
    }
  };

  const fetchAudioDevices = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/audio-devices`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAudioDevices(data.devices || []);
      }
    } catch (err) {
      console.error('Failed to fetch audio devices:', err);
    }
  };

  const saveSettings = async (category: string, categorySettings: any) => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/settings/${category}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(categorySettings)
      });
      
      if (response.ok) {
        setSuccess(`${category} settings saved successfully`);
        // Refresh settings
        fetchSettings();
      } else {
        setError(`Failed to save ${category} settings`);
      }
    } catch (err) {
      setError('Network error while saving settings');
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (category: string, key: string, value: any) => {
    setSettings(prev => ({
      ...prev,
      [category]: {
        ...(prev[category] || {}),
        [key]: { value }
      }
    }));
  };

  const tabs = [
    { id: 'audio', label: 'Audio Settings', icon: <Mic className="w-4 h-4" /> },
    { id: 'ai', label: 'AI Models', icon: <Brain className="w-4 h-4" /> },
    { id: 'email', label: 'Email Config', icon: <Mail className="w-4 h-4" /> },
    { id: 'storage', label: 'Storage', icon: <Database className="w-4 h-4" /> },
    { id: 'webhooks', label: 'Webhooks', icon: <Webhook className="w-4 h-4" /> }
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
        <span className="ml-2 text-gray-400">Loading application settings...</span>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Quick Actions Bar */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">Application Configuration</h2>
        <button
          onClick={fetchSettings}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

        {/* Status Messages */}
        {error && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-red-400">{error}</span>
            </div>
          </div>
        )}

        {success && (
          <div className="bg-green-900/50 border border-green-700 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-400">{success}</span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex space-x-1 bg-gray-800 rounded-lg p-1 mb-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          {activeTab === 'audio' && (
            <div className="space-y-6">
              <h3 className="text-xl font-semibold flex items-center gap-2">
                <Mic className="w-6 h-6 text-purple-400" />
                Audio Configuration
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">Input Device</label>
                  <select
                    value={settings.audio?.input_source?.value || 'default'}
                    onChange={(e) => updateSetting('audio', 'input_source', e.target.value)}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  >
                    <option value="default">Default Device</option>
                    {audioDevices.map((device, index) => (
                      <option key={index} value={device.name}>
                        {device.name} ({device.channels} channels)
                      </option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Sample Rate (Hz)</label>
                  <select
                    value={settings.audio?.sample_rate?.value || 16000}
                    onChange={(e) => updateSetting('audio', 'sample_rate', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  >
                    <option value={8000}>8,000 Hz</option>
                    <option value={16000}>16,000 Hz (Recommended)</option>
                    <option value={22050}>22,050 Hz</option>
                    <option value={44100}>44,100 Hz</option>
                    <option value={48000}>48,000 Hz</option>
                  </select>
                </div>
              </div>
              
              <button
                onClick={() => saveSettings('audio', settings.audio)}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded transition-colors"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Audio Settings'}
              </button>
            </div>
          )}

          {activeTab === 'ai' && (
            <div className="space-y-6">
              <h3 className="text-xl font-semibold flex items-center gap-2">
                <Brain className="w-6 h-6 text-purple-400" />
                AI Model Configuration
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">Whisper Model</label>
                  <select
                    value={settings.ai?.whisper_model?.value || 'whisper-base'}
                    onChange={(e) => updateSetting('ai', 'whisper_model', e.target.value)}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  >
                    <option value="whisper-tiny">Tiny (Fast, Lower Quality)</option>
                    <option value="whisper-base">Base (Recommended)</option>
                    <option value="whisper-small">Small (Better Quality)</option>
                    <option value="whisper-medium">Medium (High Quality)</option>
                    <option value="whisper-large">Large (Best Quality)</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Confidence Threshold</label>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.1"
                    value={settings.ai?.confidence_threshold?.value || 0.8}
                    onChange={(e) => updateSetting('ai', 'confidence_threshold', parseFloat(e.target.value))}
                    className="w-full"
                  />
                  <div className="text-sm text-gray-400 mt-1">
                    Current: {settings.ai?.confidence_threshold?.value || 0.8}
                  </div>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={settings.ai?.enable_speaker_diarization?.value || false}
                  onChange={(e) => updateSetting('ai', 'enable_speaker_diarization', e.target.checked)}
                  className="rounded"
                />
                <label className="text-sm">Enable Speaker Diarization</label>
              </div>
              
              <button
                onClick={() => saveSettings('ai', settings.ai)}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded transition-colors"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save AI Settings'}
              </button>
            </div>
          )}

          {activeTab === 'email' && (
            <div className="space-y-6">
              <h3 className="text-xl font-semibold flex items-center gap-2">
                <Mail className="w-6 h-6 text-purple-400" />
                Email Configuration
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">SMTP Host</label>
                  <input
                    type="text"
                    value={settings.email?.smtp_host?.value || ''}
                    onChange={(e) => updateSetting('email', 'smtp_host', e.target.value)}
                    placeholder="smtp.gmail.com"
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">SMTP Port</label>
                  <input
                    type="number"
                    value={settings.email?.smtp_port?.value || 587}
                    onChange={(e) => updateSetting('email', 'smtp_port', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">SMTP Username</label>
                  <input
                    type="text"
                    value={settings.email?.smtp_user?.value || ''}
                    onChange={(e) => updateSetting('email', 'smtp_user', e.target.value)}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">From Email</label>
                  <input
                    type="email"
                    value={settings.email?.from_email?.value || ''}
                    onChange={(e) => updateSetting('email', 'from_email', e.target.value)}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={settings.email?.smtp_use_tls?.value !== false}
                  onChange={(e) => updateSetting('email', 'smtp_use_tls', e.target.checked)}
                  className="rounded"
                />
                <label className="text-sm">Use TLS Encryption</label>
              </div>
              
              <button
                onClick={() => saveSettings('email', settings.email)}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded transition-colors"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Email Settings'}
              </button>
            </div>
          )}

          {activeTab === 'storage' && (
            <div className="space-y-6">
              <h3 className="text-xl font-semibold flex items-center gap-2">
                <Database className="w-6 h-6 text-purple-400" />
                Storage Management
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">Retention Period (Days)</label>
                  <input
                    type="number"
                    value={settings.storage?.retention_days?.value || 30}
                    onChange={(e) => updateSetting('storage', 'retention_days', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Max Storage (GB)</label>
                  <input
                    type="number"
                    value={settings.storage?.max_storage_gb?.value || 100}
                    onChange={(e) => updateSetting('storage', 'max_storage_gb', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={settings.storage?.auto_cleanup?.value || false}
                  onChange={(e) => updateSetting('storage', 'auto_cleanup', e.target.checked)}
                  className="rounded"
                />
                <label className="text-sm">Enable Automatic Cleanup</label>
              </div>
              
              <button
                onClick={() => saveSettings('storage', settings.storage)}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded transition-colors"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Storage Settings'}
              </button>
            </div>
          )}

          {activeTab === 'webhooks' && (
            <div className="space-y-6">
              <h3 className="text-xl font-semibold flex items-center gap-2">
                <Webhook className="w-6 h-6 text-purple-400" />
                Webhook Configuration
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">Retry Attempts</label>
                  <input
                    type="number"
                    value={settings.webhooks?.retry_attempts?.value || 3}
                    onChange={(e) => updateSetting('webhooks', 'retry_attempts', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Timeout (Seconds)</label>
                  <input
                    type="number"
                    value={settings.webhooks?.timeout_seconds?.value || 30}
                    onChange={(e) => updateSetting('webhooks', 'timeout_seconds', parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  />
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={settings.webhooks?.enabled?.value !== false}
                  onChange={(e) => updateSetting('webhooks', 'enabled', e.target.checked)}
                  className="rounded"
                />
                <label className="text-sm">Enable Webhook Notifications</label>
              </div>
              
              <button
                onClick={() => saveSettings('webhooks', settings.webhooks)}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded transition-colors"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Webhook Settings'}
              </button>
            </div>
          )}
        </div>
    </div>
  );
};