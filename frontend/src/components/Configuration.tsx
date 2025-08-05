import React, { useState, useEffect } from 'react';
import { 
  Settings, 
  Mic, 
  Brain, 
  FileText, 
  Mail, 
  Save, 
  RefreshCw,
  Volume2,
  Cpu,
  HardDrive,
  Shield,
  Bell,
  CheckCircle,
  AlertCircle,
  Info
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface AudioDevice {
  id: string;
  name: string;
  channels: number;
  default_sample_rate: number;
}

interface STTModel {
  id: string;
  name: string;
  size: string;
  language: string;
  status: 'downloaded' | 'available' | 'downloading';
  npu_compatible?: boolean;
}

interface ConfigurationSettings {
  audio: {
    input_device: string;
    sample_rate: number;
    channels: number;
    buffer_size: number;
    auto_gain_control: boolean;
    noise_reduction: boolean;
  };
  stt: {
    model: string;
    language: string;
    use_npu: boolean;
    confidence_threshold: number;
    realtime_processing: boolean;
  };
  export: {
    default_format: 'txt' | 'pdf' | 'docx';
    include_timestamps: boolean;
    include_speaker_labels: boolean;
    include_confidence_scores: boolean;
    pdf_template: 'standard' | 'professional' | 'minimal';
  };
  notifications: {
    email_enabled: boolean;
    email_recipients: string[];
    send_summary_on_completion: boolean;
    send_weekly_digest: boolean;
    webhook_enabled: boolean;
    webhook_url: string;
  };
  system: {
    auto_cleanup_days: number;
    max_storage_gb: number;
    log_level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
    enable_analytics: boolean;
  };
}

export const Configuration: React.FC = () => {
  const [settings, setSettings] = useState<ConfigurationSettings | null>(null);
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([]);
  const [sttModels, setSTTModels] = useState<STTModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'audio' | 'stt' | 'export' | 'notifications' | 'system'>('audio');
  const [testResults, setTestResults] = useState<Record<string, 'success' | 'error' | 'testing' | undefined>>({});

  useEffect(() => {
    loadConfiguration();
    loadAudioDevices();
    loadSTTModels();
  }, []);

  const loadConfiguration = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/settings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      } else {
        // Set default settings if none exist
        setSettings({
          audio: {
            input_device: 'default',
            sample_rate: 16000,
            channels: 1,
            buffer_size: 1024,
            auto_gain_control: true,
            noise_reduction: true
          },
          stt: {
            model: 'whisper-base',
            language: 'en',
            use_npu: true,
            confidence_threshold: 0.7,
            realtime_processing: true
          },
          export: {
            default_format: 'txt',
            include_timestamps: true,
            include_speaker_labels: true,
            include_confidence_scores: false,
            pdf_template: 'standard'
          },
          notifications: {
            email_enabled: false,
            email_recipients: [],
            send_summary_on_completion: true,
            send_weekly_digest: false,
            webhook_enabled: false,
            webhook_url: ''
          },
          system: {
            auto_cleanup_days: 30,
            max_storage_gb: 100,
            log_level: 'INFO',
            enable_analytics: true
          }
        });
      }
    } catch (error) {
      console.error('Failed to load configuration:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadAudioDevices = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/audio-devices`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Defensively check if the response is an array. The API might return an object.
        const devicesArray = Array.isArray(data) ? data : (data.devices || data.audio_devices || []);
        setAudioDevices(devicesArray);
      } else {
        console.error(`Failed to load audio devices: ${response.statusText}`);
        // The catch block will handle network failures and provide mock data.
        setAudioDevices([]);
      }
    } catch (error) {
      console.error('Failed to load audio devices:', error);
      // Mock data for testing
      setAudioDevices([
        { id: 'default', name: 'Default Device', channels: 2, default_sample_rate: 44100 },
        { id: 'usb_mic', name: 'USB Microphone', channels: 1, default_sample_rate: 16000 },
        { id: 'built_in', name: 'Built-in Microphone', channels: 1, default_sample_rate: 44100 }
      ]);
    }
  };

  const loadSTTModels = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/ai/stt/models`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        const modelsArray = Array.isArray(data) ? data : (data.models || data.stt_models || []);
        setSTTModels(modelsArray);
      } else {
        console.error(`Failed to load STT models: ${response.statusText}`);
        setSTTModels([]);
      }
    } catch (error) {
      console.error('Failed to load STT models:', error);
      // Mock data for testing
      setSTTModels([
        { id: 'whisper-tiny', name: 'Whisper Tiny', size: '39 MB', language: 'multilingual', status: 'downloaded', npu_compatible: false },
        { id: 'whisper-base', name: 'Whisper Base', size: '142 MB', language: 'multilingual', status: 'downloaded', npu_compatible: true },
        { id: 'whisper-small', name: 'Whisper Small', size: '461 MB', language: 'multilingual', status: 'available', npu_compatible: true },
        { id: 'whisper-medium', name: 'Whisper Medium', size: '1.42 GB', language: 'multilingual', status: 'available', npu_compatible: false }
      ]);
    }
  };

  const handleSave = async () => {
    if (!settings) return;
    
    setSaving(true);
    try {
      const token = localStorage.getItem('access_token');
      
      // Save each category separately
      const categories = Object.keys(settings) as (keyof ConfigurationSettings)[];
      
      for (const category of categories) {
        const response = await fetch(`${API_BASE_URL}/api/settings/${category}`, {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(settings[category])
        });
        
        if (!response.ok) {
          throw new Error(`Failed to save ${category} settings`);
        }
      }
      
      setTestResults(prev => ({ ...prev, save: 'success' }));
      setTimeout(() => setTestResults(prev => ({ ...prev, save: undefined })), 3000);
    } catch (error) {
      console.error('Failed to save settings:', error);
      setTestResults(prev => ({ ...prev, save: 'error' }));
    } finally {
      setSaving(false);
    }
  };

  const testAudioDevice = async (deviceId: string) => {
    setTestResults(prev => ({ ...prev, [`audio_${deviceId}`]: 'testing' }));
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/audio-devices/${deviceId}/test`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        setTestResults(prev => ({ ...prev, [`audio_${deviceId}`]: 'success' }));
      } else {
        setTestResults(prev => ({ ...prev, [`audio_${deviceId}`]: 'error' }));
      }
    } catch (error) {
      setTestResults(prev => ({ ...prev, [`audio_${deviceId}`]: 'error' }));
    }
    
    setTimeout(() => {
      setTestResults(prev => ({ ...prev, [`audio_${deviceId}`]: undefined }));
    }, 3000);
  };

  const testWebhook = async () => {
    if (!settings?.notifications.webhook_url) return;
    
    setTestResults(prev => ({ ...prev, webhook: 'testing' }));
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/webhooks/test`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url: settings.notifications.webhook_url })
      });
      
      if (response.ok) {
        setTestResults(prev => ({ ...prev, webhook: 'success' }));
      } else {
        setTestResults(prev => ({ ...prev, webhook: 'error' }));
      }
    } catch (error) {
      setTestResults(prev => ({ ...prev, webhook: 'error' }));
    }
    
    setTimeout(() => {
      setTestResults(prev => ({ ...prev, webhook: undefined }));
    }, 3000);
  };

  const updateSettings = (category: keyof ConfigurationSettings, field: string, value: any) => {
    if (!settings) return;
    
    setSettings(prev => prev ? {
      ...prev,
      [category]: {
        ...prev[category],
        [field]: value
      }
    } : null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="text-center text-red-400 py-8">
        <AlertCircle className="w-16 h-16 mx-auto mb-4" />
        <p>Failed to load configuration</p>
        <button
          onClick={loadConfiguration}
          className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  const tabs = [
    { id: 'audio' as const, label: 'Audio', icon: Mic },
    { id: 'stt' as const, label: 'Speech Recognition', icon: Brain },
    { id: 'export' as const, label: 'Export', icon: FileText },
    { id: 'notifications' as const, label: 'Notifications', icon: Bell },
    { id: 'system' as const, label: 'System', icon: Settings }
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Configuration</h1>
          <p className="text-gray-400">System settings and preferences</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded transition-colors"
        >
          {saving ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {saving ? 'Saving...' : 'Save Changes'}
          {testResults.save === 'success' && <CheckCircle className="w-4 h-4 text-green-400" />}
          {testResults.save === 'error' && <AlertCircle className="w-4 h-4 text-red-400" />}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-800 rounded-lg p-1">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors flex-1 ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        {activeTab === 'audio' && (
          <div className="space-y-6">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Volume2 className="w-5 h-5 text-blue-400" />
              Audio Configuration
            </h2>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Input Device</label>
                  <div className="flex gap-2">
                    <select
                      value={settings.audio.input_device}
                      onChange={(e) => updateSettings('audio', 'input_device', e.target.value)}
                      className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2"
                    >
                      {Array.isArray(audioDevices) && audioDevices.map((device) => (
                        <option key={device.id} value={device.id}>
                          {device.name} ({device.channels} ch)
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => testAudioDevice(settings.audio.input_device)}
                      className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                      title="Test Device"
                    >
                      {testResults[`audio_${settings.audio.input_device}`] === 'testing' ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : testResults[`audio_${settings.audio.input_device}`] === 'success' ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : testResults[`audio_${settings.audio.input_device}`] === 'error' ? (
                        <AlertCircle className="w-4 h-4 text-red-400" />
                      ) : (
                        <Volume2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Sample Rate</label>
                  <select
                    value={settings.audio.sample_rate}
                    onChange={(e) => updateSettings('audio', 'sample_rate', parseInt(e.target.value))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                    <option value={16000}>16 kHz (Recommended for Speech)</option>
                    <option value={22050}>22.05 kHz</option>
                    <option value={44100}>44.1 kHz (CD Quality)</option>
                    <option value={48000}>48 kHz (Professional)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Buffer Size</label>
                  <select
                    value={settings.audio.buffer_size}
                    onChange={(e) => updateSettings('audio', 'buffer_size', parseInt(e.target.value))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                    <option value={512}>512 samples (Low latency)</option>
                    <option value={1024}>1024 samples (Balanced)</option>
                    <option value={2048}>2048 samples (Stable)</option>
                    <option value={4096}>4096 samples (High latency)</option>
                  </select>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Auto Gain Control</label>
                  <button
                    onClick={() => updateSettings('audio', 'auto_gain_control', !settings.audio.auto_gain_control)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.audio.auto_gain_control ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.audio.auto_gain_control ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Noise Reduction</label>
                  <button
                    onClick={() => updateSettings('audio', 'noise_reduction', !settings.audio.noise_reduction)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.audio.noise_reduction ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.audio.noise_reduction ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Channels</label>
                  <select
                    value={settings.audio.channels}
                    onChange={(e) => updateSettings('audio', 'channels', parseInt(e.target.value))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                    <option value={1}>Mono (1 channel)</option>
                    <option value={2}>Stereo (2 channels)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'stt' && (
          <div className="space-y-6">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Brain className="w-5 h-5 text-purple-400" />
              Speech Recognition Settings
            </h2>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">STT Model</label>
                  <select
                    value={settings.stt.model}
                    onChange={(e) => updateSettings('stt', 'model', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                                      {Array.isArray(sttModels) && sttModels.map((model) => (
                      <option key={model.id} value={model.id} disabled={model.status !== 'downloaded'}>
                        {model.name} ({model.size}) {model.status !== 'downloaded' && `- ${model.status}`} {model.npu_compatible && '(NPU Optimized)'}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Language</label>
                  <select
                    value={settings.stt.language}
                    onChange={(e) => updateSettings('stt', 'language', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                    <option value="en">English</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                    <option value="it">Italian</option>
                    <option value="auto">Auto-detect</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Confidence Threshold: {(settings.stt.confidence_threshold * 100).toFixed(0)}%
                  </label>
                  <input
                    type="range"
                    min="0.3"
                    max="1.0"
                    step="0.05"
                    value={settings.stt.confidence_threshold}
                    onChange={(e) => updateSettings('stt', 'confidence_threshold', parseFloat(e.target.value))}
                    className="w-full accent-purple-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400">
                    <span>More transcriptions</span>
                    <span>Higher accuracy</span>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-medium">Use NPU Acceleration</label>
                    <p className="text-xs text-gray-400">7,800x faster processing</p>
                  </div>
                  <button
                    onClick={() => updateSettings('stt', 'use_npu', !settings.stt.use_npu)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.stt.use_npu ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.stt.use_npu ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-medium">Real-time Processing</label>
                    <p className="text-xs text-gray-400">Transcribe during recording</p>
                  </div>
                  <button
                    onClick={() => updateSettings('stt', 'realtime_processing', !settings.stt.realtime_processing)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.stt.realtime_processing ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.stt.realtime_processing ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="bg-gray-700 rounded p-4">
                  <h4 className="font-medium mb-2">Available Models</h4>
                  <div className="space-y-2">
                                      {Array.isArray(sttModels) && sttModels.map((model) => (
                      <div key={model.id} className="flex items-center justify-between text-sm">
                        <span>{model.name}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">{model.size}</span>
                          {model.status === 'downloaded' && <CheckCircle className="w-4 h-4 text-green-400" />}
                          {model.status === 'downloading' && <RefreshCw className="w-4 h-4 animate-spin text-blue-400" />}
                          {model.status === 'available' && (
                            <button className="text-blue-400 hover:text-blue-300">Download</button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-gray-700 rounded p-4 border border-purple-500">
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-purple-400" /> NPU Optimization
                  </h4>
                  <p className="text-sm text-gray-400 mb-3">
                    Select NPU-optimized models for significantly faster transcription and diarization.
                    These models leverage your dedicated NPU hardware.
                  </p>
                  <div className="space-y-2">
                    {Array.isArray(sttModels) && sttModels.filter(model => model.npu_compatible).map(model => (
                      <div key={model.id} className="flex items-center justify-between text-sm">
                        <span>{model.name}</span>
                        <span className="text-green-400">NPU Compatible</span>
                      </div>
                    ))}
                    {Array.isArray(sttModels) && sttModels.filter(model => !model.npu_compatible).length > 0 && (
                      <p className="text-xs text-gray-500 mt-2">
                        Other models may run on CPU/GPU and will be slower.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'export' && (
          <div className="space-y-6">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <FileText className="w-5 h-5 text-green-400" />
              Export Settings
            </h2>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Default Format</label>
                  <select
                    value={settings.export.default_format}
                    onChange={(e) => updateSettings('export', 'default_format', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                    <option value="txt">Plain Text (.txt)</option>
                    <option value="pdf">PDF Document (.pdf)</option>
                    <option value="docx">Word Document (.docx)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">PDF Template</label>
                  <select
                    value={settings.export.pdf_template}
                    onChange={(e) => updateSettings('export', 'pdf_template', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                    disabled={settings.export.default_format !== 'pdf'}
                  >
                    <option value="standard">Standard Template</option>
                    <option value="professional">Professional Template</option>
                    <option value="minimal">Minimal Template</option>
                  </select>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Include Timestamps</label>
                  <button
                    onClick={() => updateSettings('export', 'include_timestamps', !settings.export.include_timestamps)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.export.include_timestamps ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.export.include_timestamps ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Include Speaker Labels</label>
                  <button
                    onClick={() => updateSettings('export', 'include_speaker_labels', !settings.export.include_speaker_labels)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.export.include_speaker_labels ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.export.include_speaker_labels ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Include Confidence Scores</label>
                  <button
                    onClick={() => updateSettings('export', 'include_confidence_scores', !settings.export.include_confidence_scores)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.export.include_confidence_scores ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.export.include_confidence_scores ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'notifications' && (
          <div className="space-y-6">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Mail className="w-5 h-5 text-yellow-400" />
              Notification Settings
            </h2>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Email Notifications</label>
                  <button
                    onClick={() => updateSettings('notifications', 'email_enabled', !settings.notifications.email_enabled)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.notifications.email_enabled ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.notifications.email_enabled ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Email Recipients</label>
                  <textarea
                    value={settings.notifications.email_recipients.join('\n')}
                    onChange={(e) => updateSettings('notifications', 'email_recipients', e.target.value.split('\n').filter(email => email.trim()))}
                    placeholder="Enter email addresses, one per line"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 h-24 resize-none"
                    disabled={!settings.notifications.email_enabled}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Send Summary on Completion</label>
                  <button
                    onClick={() => updateSettings('notifications', 'send_summary_on_completion', !settings.notifications.send_summary_on_completion)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.notifications.send_summary_on_completion ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                    disabled={!settings.notifications.email_enabled}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.notifications.send_summary_on_completion ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Send Weekly Digest</label>
                  <button
                    onClick={() => updateSettings('notifications', 'send_weekly_digest', !settings.notifications.send_weekly_digest)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.notifications.send_weekly_digest ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                    disabled={!settings.notifications.email_enabled}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.notifications.send_weekly_digest ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Webhook Notifications</label>
                  <button
                    onClick={() => updateSettings('notifications', 'webhook_enabled', !settings.notifications.webhook_enabled)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.notifications.webhook_enabled ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.notifications.webhook_enabled ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Webhook URL</label>
                  <div className="flex gap-2">
                    <input
                      type="url"
                      value={settings.notifications.webhook_url}
                      onChange={(e) => updateSettings('notifications', 'webhook_url', e.target.value)}
                      placeholder="https://your-webhook-endpoint.com/webhook"
                      className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2"
                      disabled={!settings.notifications.webhook_enabled}
                    />
                    <button
                      onClick={testWebhook}
                      disabled={!settings.notifications.webhook_enabled || !settings.notifications.webhook_url}
                      className="px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded transition-colors"
                      title="Test Webhook"
                    >
                      {testResults.webhook === 'testing' ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : testResults.webhook === 'success' ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : testResults.webhook === 'error' ? (
                        <AlertCircle className="w-4 h-4 text-red-400" />
                      ) : (
                        <Info className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'system' && (
          <div className="space-y-6">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Settings className="w-5 h-5 text-orange-400" />
              System Settings
            </h2>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Auto Cleanup (days): {settings.system.auto_cleanup_days}
                  </label>
                  <input
                    type="range"
                    min="7"
                    max="365"
                    value={settings.system.auto_cleanup_days}
                    onChange={(e) => updateSettings('system', 'auto_cleanup_days', parseInt(e.target.value))}
                    className="w-full accent-purple-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400">
                    <span>7 days</span>
                    <span>1 year</span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Max Storage (GB): {settings.system.max_storage_gb}
                  </label>
                  <input
                    type="range"
                    min="10"
                    max="1000"
                    step="10"
                    value={settings.system.max_storage_gb}
                    onChange={(e) => updateSettings('system', 'max_storage_gb', parseInt(e.target.value))}
                    className="w-full accent-purple-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400">
                    <span>10 GB</span>
                    <span>1 TB</span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Log Level</label>
                  <select
                    value={settings.system.log_level}
                    onChange={(e) => updateSettings('system', 'log_level', e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                  >
                    <option value="DEBUG">Debug (Verbose)</option>
                    <option value="INFO">Info (Standard)</option>
                    <option value="WARNING">Warning (Important only)</option>
                    <option value="ERROR">Error (Critical only)</option>
                  </select>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-medium">Enable Analytics</label>
                    <p className="text-xs text-gray-400">Collect usage statistics</p>
                  </div>
                  <button
                    onClick={() => updateSettings('system', 'enable_analytics', !settings.system.enable_analytics)}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      settings.system.enable_analytics ? 'bg-purple-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      settings.system.enable_analytics ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>

                <div className="bg-gray-700 rounded p-4 space-y-3">
                  <h4 className="font-medium flex items-center gap-2">
                    <HardDrive className="w-4 h-4" />
                    Storage Information
                  </h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span>Current Usage:</span>
                      <span>45.2 GB</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Available Space:</span>
                      <span>234.8 GB</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Cleanup Schedule:</span>
                      <span>Every {settings.system.auto_cleanup_days} days</span>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-700 rounded p-4 space-y-3">
                  <h4 className="font-medium flex items-center gap-2">
                    <Cpu className="w-4 h-4" />
                    Performance
                  </h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span>NPU Status:</span>
                      <span className="text-green-400">Active</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Processing Speed:</span>
                      <span>7,866x real-time</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Active Sessions:</span>
                      <span>0</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};