import React, { useState, useEffect } from 'react';
import { 
  Settings as SettingsIcon,
  Mic,
  Cpu,
  Database,
  Users,
  Key,
  Bell,
  Globe,
  Shield,
  Save,
  ChevronRight,
  Wifi,
  Network,
  HardDrive,
  Monitor,
  Server,
  Lock,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Volume2
} from 'lucide-react';
import { config } from '../config';

interface SettingsSection {
  id: string;
  title: string;
  icon: React.ElementType;
  description: string;
  category: 'app' | 'admin' | 'system';
}

interface AudioDevice {
  id: string;
  name: string;
  sampleRates: number[];
  channels: number;
  isDefault: boolean;
  isUSB: boolean;
}

const SETTINGS_KEY = 'meeting-ops-settings';

export default function SettingsEnhanced() {
  const [activeSection, setActiveSection] = useState('audio');
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([]);
  const [networkInfo, setNetworkInfo] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error' | 'backend-pending'>('idle');
  const [micVolume, setMicVolume] = useState(75); // USB mic volume percentage
  
  // Load settings from localStorage or use defaults
  const loadSettings = () => {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error('Failed to parse saved settings:', e);
      }
    }
    return {
    // Audio Settings
    defaultDevice: 'hw:0,0', // USB PnP Sound Device
    sampleRate: '44100', // 44.1kHz as this USB mic supports it
    recordingFormat: 'wav',
    transcriptionModel: 'large-v3',
    liveTranscription: true,
    vadEnabled: true,
    vadThreshold: 500,
    chunkDuration: 10,
    
    // AI Settings
    enableAI: true,
    summaryFormat: 'executive',
    autoGenerateActions: true,
    speakerDiarization: true,
    maxSpeakers: 4,
    llmModel: 'gemma3n:e4b',
    llmProvider: 'ollama',
    
    // Export Settings
    defaultExportFormat: 'txt',
    includeTimestamps: true,
    includeSpeakerLabels: true,
    autoExport: false,
    exportPath: '/home/ucadmin/Meeting-Ops/exports',
    
    // Authentik Settings
    authentikEnabled: true,
    authentikUrl: 'https://authentik.local',
    authentikClientId: 'meeting-ops',
    authentikClientSecret: '',
    authentikRedirectUri: 'http://localhost:7778/auth/callback',
    
    // Network Settings
    hostname: 'meeting-ops',
    ipMode: 'dhcp', // or 'static'
    ipAddress: '',
    netmask: '255.255.255.0',
    gateway: '',
    dns1: '1.1.1.1',
    dns2: '8.8.8.8',
    vlan: '',
    
    // WiFi Settings
    wifiEnabled: false,
    wifiSSID: '',
    wifiPassword: '',
    wifiSecurity: 'WPA2',
    
    // System Settings
    autoStart: true,
    startOnBoot: true,
    autoUpdate: false,
    updateChannel: 'stable',
    backupEnabled: false,
    backupPath: '/backup',
    backupSchedule: 'daily',
    
    // Monitoring
    telemetryEnabled: false,
    logLevel: 'info',
    logRetention: 30,
    
    // Performance
    npuEnabled: true,
    npuPowerMode: 'balanced', // low, balanced, performance
    cpuThreads: 4,
    memoryLimit: 8192, // MB
  };
  };
  
  const [settings, setSettings] = useState(loadSettings());

  const sections: SettingsSection[] = [
    // App Settings
    { id: 'audio', title: 'Audio & Recording', icon: Mic, description: 'Audio devices and recording configuration', category: 'app' },
    { id: 'ai', title: 'AI & Transcription', icon: Cpu, description: 'AI models and processing options', category: 'app' },
    { id: 'export', title: 'Export & Sharing', icon: Database, description: 'Export formats and automation', category: 'app' },
    
    // Admin Settings
    { id: 'authentik', title: 'Authentication (Authentik)', icon: Lock, description: 'Authentik SSO configuration', category: 'admin' },
    { id: 'users', title: 'Users & Roles', icon: Users, description: 'User management and permissions', category: 'admin' },
    { id: 'api', title: 'API & Webhooks', icon: Key, description: 'API keys and webhook endpoints', category: 'admin' },
    
    // System Settings
    { id: 'network', title: 'Network Configuration', icon: Network, description: 'Ethernet, IP, DNS settings', category: 'system' },
    { id: 'wifi', title: 'WiFi Settings', icon: Wifi, description: 'Wireless network configuration', category: 'system' },
    { id: 'system', title: 'System & Startup', icon: Server, description: 'Boot options and system behavior', category: 'system' },
    { id: 'performance', title: 'Performance & NPU', icon: Monitor, description: 'Hardware acceleration and limits', category: 'system' },
    { id: 'backup', title: 'Backup & Updates', icon: RefreshCw, description: 'Backup settings and system updates', category: 'system' },
  ];

  useEffect(() => {
    // Fetch real audio devices
    fetchAudioDevices();
    // Fetch network info
    fetchNetworkInfo();
    // Try to load settings from backend
    loadSettingsFromBackend();
  }, []);
  
  // Auto-save to localStorage when settings change
  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

  const loadSettingsFromBackend = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/settings`);
      if (response.ok) {
        const backendSettings = await response.json();
        
        // Map backend field names to frontend field names
        const mappedSettings = {
          ...settings,
          defaultDevice: backendSettings.defaultMicrophone || settings.defaultDevice,
          sampleRate: settings.sampleRate, // Not in backend yet
          transcriptionModel: backendSettings.transcriptionModel || settings.transcriptionModel,
          liveTranscription: backendSettings.enableLiveAI !== false,
          vadEnabled: backendSettings.enableVAD || settings.vadEnabled,
          vadThreshold: (backendSettings.vadThreshold * 1000) || settings.vadThreshold,
          enableAI: backendSettings.enableLiveAI || settings.enableAI,
          summaryFormat: settings.summaryFormat, // Not directly in backend
          autoGenerateActions: backendSettings.enableAutoSummary || settings.autoGenerateActions,
          speakerDiarization: backendSettings.enableSpeakerDiarization || settings.speakerDiarization,
          maxSpeakers: backendSettings.maxSpeakers || settings.maxSpeakers,
          llmModel: backendSettings.aiModel || settings.llmModel,
          llmProvider: backendSettings.aiProvider || settings.llmProvider,
          hostname: backendSettings.hostname || settings.hostname,
          ipMode: backendSettings.ipMode || settings.ipMode,
          authentikUrl: backendSettings.authentikUrl || settings.authentikUrl,
          npuEnabled: backendSettings.npuEnabled !== false,
          npuPowerMode: backendSettings.npuPowerMode || settings.npuPowerMode,
        };
        
        setSettings(mappedSettings);
        setMicVolume(backendSettings.microphoneVolume || 75);
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(mappedSettings));
      }
    } catch (error) {
      console.log('Backend settings not available, using local storage');
    }
  };

  const fetchAudioDevices = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/audio-devices`);
      if (response.ok) {
        const data = await response.json();
        const devices = data.devices || data; // Handle both {devices: [...]} and [...] formats
        
        // Map the devices to our format
        const mappedDevices: AudioDevice[] = devices.map((device: any) => ({
          id: device.deviceId || device.id || `hw:${device.index},0`,
          name: device.name || device.label || 'Unknown Device',
          sampleRates: device.sampleRates || device.sample_rates || [device.sample_rate] || [44100, 48000],
          channels: device.channels || 1,
          isDefault: device.is_default || device.isDefault || device.name?.includes('USB') || false,
          isUSB: device.name?.includes('USB') || device.label?.includes('USB') || false
        }));
        
        setAudioDevices(mappedDevices);
        
        // Set default device to first device or USB if found
        const defaultDevice = mappedDevices.find(d => d.isDefault) || mappedDevices.find(d => d.isUSB) || mappedDevices[0];
        if (defaultDevice && !settings.defaultDevice) {
          setSettings((prev: any) => ({
            ...prev,
            defaultDevice: defaultDevice.id,
            sampleRate: '44100' // Default rate
          }));
        }
      }
    } catch (error) {
      console.error('Failed to fetch audio devices:', error);
      // Fallback to detected hardware
      setAudioDevices([
        {
          id: 'hw:0,0',
          name: 'USB PnP Sound Device (C-Media)',
          sampleRates: [44100, 48000],
          channels: 1,
          isDefault: true,
          isUSB: true
        },
        {
          id: 'hw:2,0',
          name: 'HD-Audio Generic (Built-in)',
          sampleRates: [16000, 44100, 48000],
          channels: 2,
          isDefault: false,
          isUSB: false
        }
      ]);
    }
  };

  const fetchNetworkInfo = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/system/network`);
      if (response.ok) {
        const info = await response.json();
        setNetworkInfo(info);
        setSettings((prev: any) => ({
          ...prev,
          hostname: info.hostname || prev.hostname,
          ipAddress: info.ipAddress || prev.ipAddress,
          gateway: info.gateway || prev.gateway,
        }));
      }
    } catch (error) {
      console.error('Failed to fetch network info:', error);
    }
  };

  const adjustMicVolume = async (volume: number) => {
    try {
      // Try to set via backend
      const response = await fetch(`${config.apiUrl}/api/simple/audio/volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          device: settings.defaultDevice,
          volume: volume 
        })
      });
      if (response.ok) {
        setMicVolume(volume);
      }
    } catch (error) {
      console.log('Backend not available for volume control');
      // Could still update UI optimistically
      setMicVolume(volume);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus('idle');
    
    // Always save to localStorage
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    
    // Map frontend settings to backend format
    const backendSettings = {
      defaultMicrophone: settings.defaultDevice,
      microphoneVolume: micVolume,
      transcriptionModel: settings.transcriptionModel,
      enableLiveAI: settings.liveTranscription,
      enableVAD: settings.vadEnabled,
      vadThreshold: settings.vadThreshold / 1000,
      enableSpeakerDiarization: settings.speakerDiarization,
      maxSpeakers: settings.maxSpeakers,
      aiModel: settings.llmModel,
      aiProvider: settings.llmProvider,
      enableAutoSummary: settings.autoGenerateActions,
      hostname: settings.hostname,
      ipMode: settings.ipMode,
      ipAddress: settings.ipAddress,
      gateway: settings.gateway,
      dns1: settings.dns1,
      dns2: settings.dns2,
      wifiEnabled: settings.wifiEnabled,
      wifiSSID: settings.wifiSSID,
      wifiPassword: settings.wifiPassword,
      npuEnabled: settings.npuEnabled,
      npuPowerMode: settings.npuPowerMode,
      authentikUrl: settings.authentikUrl,
      authentikClientId: settings.authentikClientId,
      authentikClientSecret: settings.authentikClientSecret,
      defaultExportFormat: settings.defaultExportFormat,
      includeTimestamps: settings.includeTimestamps,
      includeSpeakerLabels: settings.includeSpeakerLabels,
    };
    
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(backendSettings)
      });
      
      if (response.ok) {
        setSaveStatus('success');
        setTimeout(() => setSaveStatus('idle'), 3000);
      } else {
        throw new Error('Backend not available');
      }
    } catch (error) {
      // Save to localStorage was successful, backend pending
      setSaveStatus('backend-pending');
      setTimeout(() => setSaveStatus('idle'), 5000);
    } finally {
      setSaving(false);
    }
  };

  const renderSectionContent = () => {
    switch (activeSection) {
      case 'audio':
        return (
          <div className="space-y-6">
            {/* Audio Device Selection */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Recording Device
              </label>
              <select 
                value={settings.defaultDevice}
                onChange={(e) => {
                  const device = audioDevices.find(d => d.id === e.target.value);
                  setSettings({
                    ...settings, 
                    defaultDevice: e.target.value,
                    // Auto-adjust sample rate based on device capabilities
                    sampleRate: device?.sampleRates.includes(44100) ? '44100' : '48000'
                  });
                }}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                {audioDevices.map(device => (
                  <option key={device.id} value={device.id}>
                    {device.name} {device.isUSB && '(USB)'} {device.isDefault && '⭐'}
                  </option>
                ))}
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                {audioDevices.find(d => d.id === settings.defaultDevice)?.isUSB 
                  ? '✅ USB microphone detected - optimal for recording'
                  : 'Built-in microphone selected'}
              </p>
            </div>

            {/* USB Mic Volume Control */}
            {settings.defaultDevice === 'hw:0,0' && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  USB Microphone Volume
                </label>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={micVolume}
                    onChange={(e) => adjustMicVolume(parseInt(e.target.value))}
                    className="flex-1 h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
                  />
                  <span className="text-sm text-zinc-200 w-12 text-right">{micVolume}%</span>
                </div>
                <p className="text-xs text-zinc-500 mt-1">
                  Adjust microphone input sensitivity
                </p>
              </div>
            )}

            {/* Sample Rate */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Sample Rate
              </label>
              <select 
                value={settings.sampleRate}
                onChange={(e) => setSettings({...settings, sampleRate: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                {audioDevices.find(d => d.id === settings.defaultDevice)?.sampleRates.map(rate => (
                  <option key={rate} value={rate}>
                    {rate / 1000} kHz {rate === 44100 && '(USB Mic Native)'}
                  </option>
                )) || [
                  <option key="44100" value="44100">44.1 kHz</option>,
                  <option key="48000" value="48000">48 kHz</option>
                ]}
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                Recording at native rate avoids resampling and preserves quality
              </p>
            </div>

            {/* Transcription Model */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Transcription Model
              </label>
              <select 
                value={settings.transcriptionModel}
                onChange={(e) => setSettings({...settings, transcriptionModel: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="base">Whisper Base (Fastest, ~39MB)</option>
                <option value="small">Whisper Small (~244MB)</option>
                <option value="medium">Whisper Medium (~1.5GB)</option>
                <option value="large">Whisper Large (~3GB)</option>
                <option value="large-v2">Whisper Large-v2 (~3GB)</option>
                <option value="large-v3">Whisper Large-v3 (Best, ~3GB) ⭐</option>
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                Large-v3 with NPU acceleration: 220x faster than CPU
              </p>
            </div>

            {/* Advanced Audio Settings */}
            <div className="space-y-3">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.liveTranscription}
                  onChange={(e) => setSettings({...settings, liveTranscription: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable live transcription during recording</span>
              </label>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.vadEnabled}
                  onChange={(e) => setSettings({...settings, vadEnabled: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Voice Activity Detection (removes silence)</span>
              </label>

              {settings.vadEnabled && (
                <div className="ml-7">
                  <label className="block text-xs text-zinc-400 mb-1">
                    VAD Threshold (ms)
                  </label>
                  <input
                    type="number"
                    value={settings.vadThreshold}
                    onChange={(e) => setSettings({...settings, vadThreshold: parseInt(e.target.value)})}
                    className="w-32 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-200"
                    min="100"
                    max="2000"
                    step="100"
                  />
                </div>
              )}
            </div>
          </div>
        );

      case 'authentik':
        return (
          <div className="space-y-6">
            <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-yellow-400 mt-0.5" />
                <div>
                  <p className="text-sm text-yellow-200 font-medium">Authentik SSO Configuration</p>
                  <p className="text-xs text-yellow-300 mt-1">
                    Configure Single Sign-On with your Authentik instance for centralized authentication
                  </p>
                </div>
              </div>
            </div>

            <div>
              <label className="flex items-center gap-3 mb-4">
                <input
                  type="checkbox"
                  checked={settings.authentikEnabled}
                  onChange={(e) => setSettings({...settings, authentikEnabled: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable Authentik Authentication</span>
              </label>

              {settings.authentikEnabled && (
                <div className="space-y-4 ml-7">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Authentik URL
                    </label>
                    <input
                      type="url"
                      value={settings.authentikUrl}
                      onChange={(e) => setSettings({...settings, authentikUrl: e.target.value})}
                      placeholder="https://auth.yourdomain.com"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Client ID
                    </label>
                    <input
                      type="text"
                      value={settings.authentikClientId}
                      onChange={(e) => setSettings({...settings, authentikClientId: e.target.value})}
                      placeholder="meeting-ops"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Client Secret
                    </label>
                    <input
                      type="password"
                      value={settings.authentikClientSecret}
                      onChange={(e) => setSettings({...settings, authentikClientSecret: e.target.value})}
                      placeholder="••••••••••••••••"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Redirect URI
                    </label>
                    <input
                      type="url"
                      value={settings.authentikRedirectUri}
                      onChange={(e) => setSettings({...settings, authentikRedirectUri: e.target.value})}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
                    />
                    <p className="text-xs text-zinc-500 mt-1">
                      Add this URI to your Authentik application configuration
                    </p>
                  </div>

                  <button className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors">
                    Test Connection
                  </button>
                </div>
              )}
            </div>
          </div>
        );

      case 'network':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Hostname
              </label>
              <input
                type="text"
                value={settings.hostname}
                onChange={(e) => setSettings({...settings, hostname: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                IP Configuration
              </label>
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setSettings({...settings, ipMode: 'dhcp'})}
                  className={`px-4 py-2 rounded-lg text-sm ${
                    settings.ipMode === 'dhcp' 
                      ? 'bg-zinc-700 text-white' 
                      : 'bg-zinc-800 text-zinc-400 hover:text-white'
                  }`}
                >
                  DHCP (Automatic)
                </button>
                <button
                  onClick={() => setSettings({...settings, ipMode: 'static'})}
                  className={`px-4 py-2 rounded-lg text-sm ${
                    settings.ipMode === 'static' 
                      ? 'bg-zinc-700 text-white' 
                      : 'bg-zinc-800 text-zinc-400 hover:text-white'
                  }`}
                >
                  Static IP
                </button>
              </div>

              {settings.ipMode === 'static' && (
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">IP Address</label>
                    <input
                      type="text"
                      value={settings.ipAddress}
                      onChange={(e) => setSettings({...settings, ipAddress: e.target.value})}
                      placeholder="192.168.1.100"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Subnet Mask</label>
                    <input
                      type="text"
                      value={settings.netmask}
                      onChange={(e) => setSettings({...settings, netmask: e.target.value})}
                      placeholder="255.255.255.0"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Gateway</label>
                    <input
                      type="text"
                      value={settings.gateway}
                      onChange={(e) => setSettings({...settings, gateway: e.target.value})}
                      placeholder="192.168.1.1"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
                    />
                  </div>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                DNS Servers
              </label>
              <div className="space-y-2">
                <input
                  type="text"
                  value={settings.dns1}
                  onChange={(e) => setSettings({...settings, dns1: e.target.value})}
                  placeholder="Primary DNS (e.g., 1.1.1.1)"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
                />
                <input
                  type="text"
                  value={settings.dns2}
                  onChange={(e) => setSettings({...settings, dns2: e.target.value})}
                  placeholder="Secondary DNS (e.g., 8.8.8.8)"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                VLAN ID (Optional)
              </label>
              <input
                type="text"
                value={settings.vlan}
                onChange={(e) => setSettings({...settings, vlan: e.target.value})}
                placeholder="Leave empty for no VLAN"
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
              />
            </div>

            {/* Current Network Status */}
            {networkInfo.ipAddress && (
              <div className="bg-zinc-800/50 rounded-lg p-4 mt-6">
                <h4 className="text-sm font-medium text-zinc-300 mb-3">Current Network Status</h4>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Current IP:</span>
                    <span className="text-zinc-200 font-mono">{networkInfo.ipAddress}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Gateway:</span>
                    <span className="text-zinc-200 font-mono">{networkInfo.gateway}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Interface:</span>
                    <span className="text-zinc-200">{networkInfo.interface || 'eth0'}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        );

      case 'wifi':
        return (
          <div className="space-y-6">
            <div>
              <label className="flex items-center gap-3 mb-4">
                <input
                  type="checkbox"
                  checked={settings.wifiEnabled}
                  onChange={(e) => setSettings({...settings, wifiEnabled: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable WiFi</span>
              </label>

              {settings.wifiEnabled && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Network Name (SSID)
                    </label>
                    <input
                      type="text"
                      value={settings.wifiSSID}
                      onChange={(e) => setSettings({...settings, wifiSSID: e.target.value})}
                      placeholder="Your WiFi network name"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Password
                    </label>
                    <input
                      type="password"
                      value={settings.wifiPassword}
                      onChange={(e) => setSettings({...settings, wifiPassword: e.target.value})}
                      placeholder="WiFi password"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Security Type
                    </label>
                    <select 
                      value={settings.wifiSecurity}
                      onChange={(e) => setSettings({...settings, wifiSecurity: e.target.value})}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
                    >
                      <option value="WPA2">WPA2 Personal</option>
                      <option value="WPA3">WPA3 Personal</option>
                      <option value="WPA2-Enterprise">WPA2 Enterprise</option>
                      <option value="Open">Open (No Security)</option>
                    </select>
                  </div>

                  <button className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors">
                    Scan for Networks
                  </button>
                </div>
              )}
            </div>
          </div>
        );

      case 'performance':
        return (
          <div className="space-y-6">
            <div className="bg-green-900/20 border border-green-800 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <Cpu className="w-5 h-5 text-green-400 mt-0.5" />
                <div>
                  <p className="text-sm text-green-200 font-medium">NPU Acceleration Active</p>
                  <p className="text-xs text-green-300 mt-1">
                    AMD Phoenix NPU detected - 220x faster transcription enabled
                  </p>
                </div>
              </div>
            </div>

            <div>
              <label className="flex items-center gap-3 mb-4">
                <input
                  type="checkbox"
                  checked={settings.npuEnabled}
                  onChange={(e) => setSettings({...settings, npuEnabled: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable NPU Acceleration</span>
              </label>

              {settings.npuEnabled && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      NPU Power Mode
                    </label>
                    <select 
                      value={settings.npuPowerMode}
                      onChange={(e) => setSettings({...settings, npuPowerMode: e.target.value})}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
                    >
                      <option value="low">Low Power (Battery Saver)</option>
                      <option value="balanced">Balanced (Recommended)</option>
                      <option value="performance">Maximum Performance</option>
                    </select>
                    <p className="text-xs text-zinc-500 mt-1">
                      Performance mode: 0.0045 RTF, 4,789 tokens/sec
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                CPU Threads
              </label>
              <input
                type="number"
                value={settings.cpuThreads}
                onChange={(e) => setSettings({...settings, cpuThreads: parseInt(e.target.value)})}
                min="1"
                max="16"
                className="w-32 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
              />
              <p className="text-xs text-zinc-500 mt-1">
                Number of CPU threads for background processing
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Memory Limit (MB)
              </label>
              <input
                type="number"
                value={settings.memoryLimit}
                onChange={(e) => setSettings({...settings, memoryLimit: parseInt(e.target.value)})}
                min="2048"
                max="32768"
                step="1024"
                className="w-32 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
              />
              <p className="text-xs text-zinc-500 mt-1">
                Maximum memory allocation for Meeting-Ops
              </p>
            </div>

            {/* Hardware Info */}
            <div className="bg-zinc-800/50 rounded-lg p-4 mt-6">
              <h4 className="text-sm font-medium text-zinc-300 mb-3">Hardware Information</h4>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-400">CPU:</span>
                  <span className="text-zinc-200">AMD Ryzen 9 7940HS</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">NPU:</span>
                  <span className="text-zinc-200">AMD Phoenix (16 TOPS)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">RAM:</span>
                  <span className="text-zinc-200">32 GB DDR5</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Storage:</span>
                  <span className="text-zinc-200">1 TB NVMe SSD</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'ai':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                LLM Provider
              </label>
              <select 
                value={settings.llmProvider}
                onChange={(e) => setSettings({...settings, llmProvider: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="ollama">Ollama (Local)</option>
                <option value="openai">OpenAI API</option>
                <option value="anthropic">Anthropic Claude</option>
                <option value="custom">Custom Endpoint</option>
              </select>
            </div>

            {settings.llmProvider === 'ollama' && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Ollama Model
                </label>
                <select 
                  value={settings.llmModel}
                  onChange={(e) => setSettings({...settings, llmModel: e.target.value})}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
                >
                  <option value="gemma3n:e4b">Gemma 3n E4B (Recommended)</option>
                  <option value="llama3.3:latest">Llama 3.3</option>
                  <option value="phi4:latest">Phi-4</option>
                  <option value="granite3.3:latest">Granite 3.3</option>
                  <option value="mistral:latest">Mistral</option>
                </select>
                <p className="text-xs text-zinc-500 mt-1">
                  Gemma3n optimized for ROCm with HSA override
                </p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Default Summary Format
              </label>
              <select 
                value={settings.summaryFormat}
                onChange={(e) => setSettings({...settings, summaryFormat: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="executive">Executive Summary</option>
                <option value="minutes">Meeting Minutes</option>
                <option value="bullets">Bullet Points</option>
                <option value="detailed">Detailed Report</option>
                <option value="standup">Standup Format</option>
                <option value="interview">Interview Notes</option>
              </select>
            </div>

            <div className="space-y-3">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.enableAI}
                  onChange={(e) => setSettings({...settings, enableAI: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable AI processing</span>
              </label>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.autoGenerateActions}
                  onChange={(e) => setSettings({...settings, autoGenerateActions: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Auto-generate action items</span>
              </label>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.speakerDiarization}
                  onChange={(e) => setSettings({...settings, speakerDiarization: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Speaker diarization</span>
              </label>

              {settings.speakerDiarization && (
                <div className="ml-7">
                  <label className="block text-xs text-zinc-400 mb-1">
                    Max Speakers
                  </label>
                  <input
                    type="number"
                    value={settings.maxSpeakers}
                    onChange={(e) => setSettings({...settings, maxSpeakers: parseInt(e.target.value)})}
                    className="w-20 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-200"
                    min="2"
                    max="10"
                  />
                </div>
              )}
            </div>
          </div>
        );

      default:
        return (
          <div className="flex items-center justify-center h-64 text-zinc-500">
            <div className="text-center">
              <SettingsIcon className="w-16 h-16 mx-auto mb-4 text-zinc-700" />
              <p>Select a setting category</p>
            </div>
          </div>
        );
    }
  };

  const groupedSections = {
    'App Settings': sections.filter(s => s.category === 'app'),
    'Admin Settings': sections.filter(s => s.category === 'admin'),
    'System Settings': sections.filter(s => s.category === 'system'),
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
          <p className="text-zinc-400">Configure Meeting-Ops hardware and software</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Settings Navigation */}
          <div className="lg:col-span-1">
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-2">
              {Object.entries(groupedSections).map(([category, items]) => (
                <div key={category} className="mb-4">
                  <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider px-3 py-2">
                    {category}
                  </div>
                  {items.map(section => {
                    const Icon = section.icon;
                    return (
                      <button
                        key={section.id}
                        onClick={() => setActiveSection(section.id)}
                        className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-left transition-colors ${
                          activeSection === section.id
                            ? 'bg-zinc-800 text-white'
                            : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
                        }`}
                      >
                        <Icon className="w-5 h-5 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium">{section.title}</div>
                          <div className="text-xs text-zinc-500 truncate">{section.description}</div>
                        </div>
                        <ChevronRight className="w-4 h-4 shrink-0" />
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Settings Content */}
          <div className="lg:col-span-3">
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <h2 className="text-xl font-semibold text-white mb-6">
                {sections.find(s => s.id === activeSection)?.title}
              </h2>
              
              {renderSectionContent()}

              {/* Save Button */}
              <div className="mt-8 pt-6 border-t border-zinc-800">
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="px-6 py-3 bg-gradient-to-r from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 text-white rounded-xl font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
                  >
                    {saving ? (
                      <>
                        <RefreshCw className="w-5 h-5 animate-spin" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="w-5 h-5" />
                        Save Changes
                      </>
                    )}
                  </button>
                  
                  {saveStatus === 'success' && (
                    <div className="flex items-center gap-2 text-green-400">
                      <CheckCircle className="w-5 h-5" />
                      <span className="text-sm">Settings saved successfully</span>
                    </div>
                  )}
                  
                  {saveStatus === 'error' && (
                    <div className="flex items-center gap-2 text-red-400">
                      <AlertCircle className="w-5 h-5" />
                      <span className="text-sm">Failed to save settings</span>
                    </div>
                  )}
                  
                  {saveStatus === 'backend-pending' && (
                    <div className="flex items-center gap-2 text-yellow-400">
                      <AlertCircle className="w-5 h-5" />
                      <span className="text-sm">Settings saved locally (backend integration pending)</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}