import React, { useState, useEffect } from 'react';
import { Settings, Clock, Save, CheckCircle, AlertCircle, FileAudio, HardDrive } from 'lucide-react';

interface TranscriptionSettingsProps {
  userRole?: 'admin' | 'superuser' | 'user';
  onSettingsChange?: (settings: TranscriptionSettingsData) => void;
}

export interface TranscriptionSettingsData {
  bufferMinutes: number;
  autoStart: boolean;
  saveUnrecorded: boolean;
  audioGain: number;
  vadThreshold: number;
  audioFormat: 'opus' | 'aac' | 'wav' | 'flac';
  audioBitrate: number;
  audioSampleRate: number;
  whisperModel: 'base' | 'small' | 'medium' | 'large' | 'large-v2' | 'large-v3';
  enableVAD: boolean;
  enableWordTimestamps: boolean;
  enableDiarization: boolean;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const TranscriptionSettings: React.FC<TranscriptionSettingsProps> = ({
  userRole = 'user',
  onSettingsChange
}) => {
  const [settings, setSettings] = useState<TranscriptionSettingsData>({
    bufferMinutes: 15,
    autoStart: true,
    saveUnrecorded: false,
    audioGain: 100,
    vadThreshold: 0.001,
    audioFormat: 'opus',
    audioBitrate: 64,
    audioSampleRate: 16000,
    whisperModel: 'large-v3',  // Default to best model
    enableVAD: true,
    enableWordTimestamps: true,
    enableDiarization: true
  });
  
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');

  // Buffer duration options
  const bufferOptions = [
    { value: 5, label: '5 minutes', description: 'Minimal buffer for quick sessions' },
    { value: 10, label: '10 minutes', description: 'Short meetings and standup calls' },
    { value: 15, label: '15 minutes', description: 'Standard buffer (recommended)' },
    { value: 30, label: '30 minutes', description: 'Extended meetings' },
    { value: 60, label: '1 hour', description: 'Long conferences and presentations' },
    { value: 120, label: '2 hours', description: 'Workshop and training sessions' },
  ];

  // Load settings from localStorage or API
  useEffect(() => {
    const loadSettings = async () => {
      try {
        // First try localStorage
        const storedSettings = localStorage.getItem('transcription_settings');
        if (storedSettings) {
          const parsed = JSON.parse(storedSettings);
          setSettings(parsed);
        }

        // Then try to fetch from API if admin
        if (userRole === 'admin' || userRole === 'superuser') {
          const token = localStorage.getItem('access_token');
          if (token) {
            const response = await fetch(`${API_BASE_URL}/api/settings/transcription`, {
              headers: {
                'Authorization': `Bearer ${token}`
              }
            });
            
            if (response.ok) {
              const apiSettings = await response.json();
              setSettings(prev => ({
                ...prev,
                ...apiSettings
              }));
            }
          }
        }
      } catch (error) {
        console.error('Failed to load transcription settings:', error);
      }
    };

    loadSettings();
  }, [userRole]);

  // Save settings
  const saveSettings = async () => {
    setIsSaving(true);
    setSaveStatus('idle');

    try {
      // Save to localStorage
      localStorage.setItem('transcription_settings', JSON.stringify(settings));

      // Save to API if admin
      if (userRole === 'admin' || userRole === 'superuser') {
        const token = localStorage.getItem('access_token');
        if (token) {
          const response = await fetch(`${API_BASE_URL}/api/settings/transcription`, {
            method: 'PUT',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
          });

          if (!response.ok) {
            throw new Error('Failed to save to server');
          }
        }
      }

      setSaveStatus('success');
      if (onSettingsChange) {
        onSettingsChange(settings);
      }

      // Clear success message after 3 seconds
      setTimeout(() => setSaveStatus('idle'), 3000);
    } catch (error) {
      console.error('Failed to save settings:', error);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  // Handle setting changes
  const updateSetting = <K extends keyof TranscriptionSettingsData>(
    key: K,
    value: TranscriptionSettingsData[K]
  ) => {
    setSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };

  // Only show settings for admin/superuser
  if (userRole !== 'admin' && userRole !== 'superuser') {
    return (
      <div className="bg-gray-800 rounded-lg p-6">
        <div className="flex items-center gap-2 text-gray-400">
          <Settings className="w-5 h-5" />
          <span>Transcription settings are only available for administrators</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Settings className="w-5 h-5" />
          Transcription Settings
        </h2>
        
        <button
          onClick={saveSettings}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          {isSaving ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              Save Settings
            </>
          )}
        </button>
      </div>

      {/* Save Status */}
      {saveStatus !== 'idle' && (
        <div className={`p-3 rounded-lg flex items-center gap-2 ${
          saveStatus === 'success' 
            ? 'bg-green-900/50 text-green-400 border border-green-700' 
            : 'bg-red-900/50 text-red-400 border border-red-700'
        }`}>
          {saveStatus === 'success' ? (
            <>
              <CheckCircle className="w-4 h-4" />
              Settings saved successfully
            </>
          ) : (
            <>
              <AlertCircle className="w-4 h-4" />
              Failed to save settings
            </>
          )}
        </div>
      )}

      {/* Buffer Duration Setting */}
      <div className="space-y-3">
        <label className="block">
          <div className="flex items-center gap-2 text-gray-200 mb-3">
            <Clock className="w-4 h-4" />
            <span className="font-medium">Buffer Duration</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {bufferOptions.map(option => (
              <button
                key={option.value}
                onClick={() => updateSetting('bufferMinutes', option.value)}
                className={`p-3 rounded-lg border transition-all text-left ${
                  settings.bufferMinutes === option.value
                    ? 'border-purple-500 bg-purple-900/30 text-purple-300'
                    : 'border-gray-600 bg-gray-700/50 text-gray-300 hover:border-gray-500'
                }`}
              >
                <div className="font-medium">{option.label}</div>
                <div className="text-xs mt-1 opacity-75">{option.description}</div>
              </button>
            ))}
          </div>
        </label>
      </div>

      {/* Other Settings */}
      <div className="space-y-4">
        {/* Auto-start */}
        <label className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg cursor-pointer hover:bg-gray-700/70 transition-colors">
          <div>
            <div className="text-gray-200 font-medium">Auto-start Listening</div>
            <div className="text-xs text-gray-400 mt-1">
              Automatically begin transcription when dashboard loads
            </div>
          </div>
          <input
            type="checkbox"
            checked={settings.autoStart}
            onChange={(e) => updateSetting('autoStart', e.target.checked)}
            className="w-5 h-5 text-purple-600 bg-gray-700 border-gray-600 rounded focus:ring-purple-500"
          />
        </label>

        {/* Save Unrecorded */}
        <label className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg cursor-pointer hover:bg-gray-700/70 transition-colors">
          <div>
            <div className="text-gray-200 font-medium">Save Buffer on Stop</div>
            <div className="text-xs text-gray-400 mt-1">
              Save buffered transcription even when not recording
            </div>
          </div>
          <input
            type="checkbox"
            checked={settings.saveUnrecorded}
            onChange={(e) => updateSetting('saveUnrecorded', e.target.checked)}
            className="w-5 h-5 text-purple-600 bg-gray-700 border-gray-600 rounded focus:ring-purple-500"
          />
        </label>

        {/* Audio Gain */}
        <div className="p-3 bg-gray-700/50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="text-gray-200 font-medium">Audio Gain</div>
            <div className="text-sm text-gray-400">{settings.audioGain}x</div>
          </div>
          <input
            type="range"
            min="1"
            max="200"
            value={settings.audioGain}
            onChange={(e) => updateSetting('audioGain', parseInt(e.target.value))}
            className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer accent-purple-600"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>1x</span>
            <span>100x</span>
            <span>200x</span>
          </div>
        </div>

        {/* VAD Threshold */}
        <div className="p-3 bg-gray-700/50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="text-gray-200 font-medium">Voice Detection Sensitivity</div>
            <div className="text-sm text-gray-400">
              {settings.vadThreshold < 0.0005 ? 'Very High' :
               settings.vadThreshold < 0.001 ? 'High' :
               settings.vadThreshold < 0.005 ? 'Medium' : 'Low'}
            </div>
          </div>
          <input
            type="range"
            min="0.0001"
            max="0.01"
            step="0.0001"
            value={settings.vadThreshold}
            onChange={(e) => updateSetting('vadThreshold', parseFloat(e.target.value))}
            className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer accent-purple-600"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>Sensitive</span>
            <span>Balanced</span>
            <span>Noise Resistant</span>
          </div>
        </div>
      </div>

      {/* Whisper Model Settings */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-gray-200">
          <HardDrive className="w-4 h-4" />
          <span className="font-medium">Whisper Model Selection</span>
        </div>
        
        {/* Model Selection */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { 
              value: 'large-v3', 
              label: 'Large v3', 
              description: 'Best accuracy (99%)',
              speed: '2.2x realtime',
              size: '1.5GB',
              recommended: true
            },
            { 
              value: 'base', 
              label: 'Base', 
              description: 'Fast (85% accuracy)',
              speed: '3.4x realtime',
              size: '142MB'
            },
            { 
              value: 'small', 
              label: 'Small', 
              description: 'Balanced (90%)',
              speed: '2.8x realtime',
              size: '461MB'
            },
            { 
              value: 'medium', 
              label: 'Medium', 
              description: 'Good (95%)',
              speed: '2.5x realtime',
              size: '1.5GB'
            },
            { 
              value: 'large', 
              label: 'Large v2', 
              description: 'High accuracy (98%)',
              speed: '2.0x realtime',
              size: '3GB'
            },
            { 
              value: 'large-v2', 
              label: 'Large v2', 
              description: 'Previous best (98%)',
              speed: '2.0x realtime',
              size: '3GB'
            }
          ].map(model => (
            <button
              key={model.value}
              onClick={() => updateSetting('whisperModel', model.value as any)}
              className={`p-3 rounded-lg border transition-all text-left relative ${
                settings.whisperModel === model.value
                  ? 'border-purple-500 bg-purple-900/30 text-purple-300'
                  : 'border-gray-600 bg-gray-700/50 text-gray-300 hover:border-gray-500'
              }`}
            >
              {model.recommended && (
                <div className="absolute -top-2 -right-2 bg-purple-600 text-white text-xs px-2 py-1 rounded-full">
                  Recommended
                </div>
              )}
              <div className="font-medium">{model.label}</div>
              <div className="text-xs mt-1 opacity-75">{model.description}</div>
              <div className="text-xs mt-1 text-gray-500">
                {model.speed} • {model.size}
              </div>
            </button>
          ))}
        </div>
        
        {/* NPU Features */}
        <div className="space-y-2 mt-4">
          <label className="flex items-center justify-between p-2 bg-gray-700/50 rounded-lg cursor-pointer hover:bg-gray-700/70 transition-colors">
            <div>
              <div className="text-gray-200 text-sm font-medium">Voice Activity Detection (VAD)</div>
              <div className="text-xs text-gray-400">Remove silence automatically</div>
            </div>
            <input
              type="checkbox"
              checked={settings.enableVAD}
              onChange={(e) => updateSetting('enableVAD', e.target.checked)}
              className="w-5 h-5 text-purple-600 rounded focus:ring-purple-500 bg-gray-700 border-gray-600"
            />
          </label>
          
          <label className="flex items-center justify-between p-2 bg-gray-700/50 rounded-lg cursor-pointer hover:bg-gray-700/70 transition-colors">
            <div>
              <div className="text-gray-200 text-sm font-medium">Word-level Timestamps</div>
              <div className="text-xs text-gray-400">Precise timing for each word</div>
            </div>
            <input
              type="checkbox"
              checked={settings.enableWordTimestamps}
              onChange={(e) => updateSetting('enableWordTimestamps', e.target.checked)}
              className="w-5 h-5 text-purple-600 rounded focus:ring-purple-500 bg-gray-700 border-gray-600"
            />
          </label>
          
          <label className="flex items-center justify-between p-2 bg-gray-700/50 rounded-lg cursor-pointer hover:bg-gray-700/70 transition-colors">
            <div>
              <div className="text-gray-200 text-sm font-medium">Speaker Diarization</div>
              <div className="text-xs text-gray-400">Identify different speakers</div>
            </div>
            <input
              type="checkbox"
              checked={settings.enableDiarization}
              onChange={(e) => updateSetting('enableDiarization', e.target.checked)}
              className="w-5 h-5 text-purple-600 rounded focus:ring-purple-500 bg-gray-700 border-gray-600"
            />
          </label>
        </div>
      </div>

      {/* Audio Format Settings */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-gray-200">
          <FileAudio className="w-4 h-4" />
          <span className="font-medium">Audio Storage Optimization</span>
        </div>
        
        {/* Audio Format Selection */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { 
              value: 'opus', 
              label: 'Opus', 
              description: 'Best compression',
              size: '~0.5 MB/min'
            },
            { 
              value: 'aac', 
              label: 'AAC', 
              description: 'Hardware accelerated',
              size: '~1 MB/min'
            },
            { 
              value: 'wav', 
              label: 'WAV', 
              description: 'Uncompressed',
              size: '~10 MB/min'
            },
            { 
              value: 'flac', 
              label: 'FLAC', 
              description: 'Lossless',
              size: '~5 MB/min'
            }
          ].map(format => (
            <button
              key={format.value}
              onClick={() => updateSetting('audioFormat', format.value as any)}
              className={`p-3 rounded-lg border transition-all text-left ${
                settings.audioFormat === format.value
                  ? 'border-purple-500 bg-purple-900/30 text-purple-300'
                  : 'border-gray-600 bg-gray-700/50 text-gray-300 hover:border-gray-500'
              }`}
            >
              <div className="font-medium">{format.label}</div>
              <div className="text-xs mt-1 opacity-75">{format.description}</div>
              <div className="text-xs mt-1 text-gray-500">{format.size}</div>
            </button>
          ))}
        </div>

        {/* Audio Quality Settings */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Bitrate */}
          <div className="p-3 bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-200 font-medium">Audio Bitrate</div>
              <div className="text-sm text-gray-400">{settings.audioBitrate} kbps</div>
            </div>
            <input
              type="range"
              min="32"
              max="256"
              step="32"
              value={settings.audioBitrate}
              onChange={(e) => updateSetting('audioBitrate', parseInt(e.target.value))}
              className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer accent-purple-600"
              disabled={settings.audioFormat === 'wav' || settings.audioFormat === 'flac'}
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>32 kbps</span>
              <span>128 kbps</span>
              <span>256 kbps</span>
            </div>
          </div>

          {/* Sample Rate */}
          <div className="p-3 bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-200 font-medium">Sample Rate</div>
              <div className="text-sm text-gray-400">{settings.audioSampleRate / 1000} kHz</div>
            </div>
            <select
              value={settings.audioSampleRate}
              onChange={(e) => updateSetting('audioSampleRate', parseInt(e.target.value))}
              className="w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-gray-100 focus:ring-2 focus:ring-purple-500"
            >
              <option value="8000">8 kHz (Phone quality)</option>
              <option value="16000">16 kHz (Speech optimized)</option>
              <option value="22050">22.05 kHz (FM Radio)</option>
              <option value="44100">44.1 kHz (CD quality)</option>
              <option value="48000">48 kHz (Studio quality)</option>
            </select>
          </div>
        </div>

        {/* Storage Estimate */}
        <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-3">
          <div className="flex items-center gap-2 text-sm">
            <HardDrive className="w-4 h-4 text-gray-400" />
            <span className="text-gray-300">Storage Estimate:</span>
            <span className="text-gray-400">
              {settings.audioFormat === 'opus' ? '~30 MB/hour' :
               settings.audioFormat === 'aac' ? '~60 MB/hour' :
               settings.audioFormat === 'flac' ? '~300 MB/hour' :
               '~600 MB/hour'} at {settings.audioSampleRate / 1000} kHz
            </span>
          </div>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
        <div className="text-sm text-gray-400">
          <p className="mb-2">
            <strong className="text-gray-300">Buffer Duration:</strong> Controls how much transcription history is kept in memory. 
            Longer buffers use more memory but preserve more context.
          </p>
          <p className="mb-2">
            <strong className="text-gray-300">Audio Format:</strong> Opus provides the best compression with minimal quality loss, 
            ideal for AMD hardware. AAC is hardware-accelerated on most devices.
          </p>
          <p>
            <strong className="text-gray-300">Current Usage:</strong> Approximately {' '}
            {Math.round(settings.bufferMinutes * 0.5)}MB RAM for {settings.bufferMinutes} minutes of buffer.
          </p>
        </div>
      </div>
    </div>
  );
};