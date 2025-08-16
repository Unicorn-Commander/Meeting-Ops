import React, { useState, useEffect } from 'react';
import {
  Settings, Mic, Brain, FileText, Volume2, Book,
  Save, RefreshCw, AlertCircle, Check, Info,
  Zap, Globe, Sliders, Download, Upload
} from 'lucide-react';
import { VocabularySettings } from './VocabularySettings';

interface SettingsTab {
  id: string;
  name: string;
  icon: React.ReactNode;
  component: React.ReactNode;
}

interface TranscriptionSettings {
  model: string;
  language: string;
  vadSensitivity: number;
  enableTimestamps: boolean;
  enableSpeakerDiarization: boolean;
  maxSpeakers: number;
}

interface AISettings {
  summaryLength: 'short' | 'medium' | 'long';
  progressiveIntervals: number[];
  temperature: number;
  enableAutoTitle: boolean;
  enableActionItems: boolean;
  enableDecisions: boolean;
  model: string;
}

interface AudioSettings {
  inputDevice: string;
  sampleRate: number;
  channels: 'mono' | 'stereo';
  noiseReduction: boolean;
  autoGainControl: boolean;
  echoCancellation: boolean;
}

interface ExportSettings {
  defaultFormats: string[];
  includeTimestamps: boolean;
  includeSpeakerLabels: boolean;
  includeConfidenceScores: boolean;
  templateStyle: 'formal' | 'casual' | 'technical';
  pdfOptions: {
    fontSize: number;
    pageSize: 'A4' | 'Letter';
    includeHeader: boolean;
    includeFooter: boolean;
  };
}

const TranscriptionSettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<TranscriptionSettings>({
    model: 'large-v3',
    language: 'en',
    vadSensitivity: 0.5,
    enableTimestamps: true,
    enableSpeakerDiarization: true,
    maxSpeakers: 4
  });

  useEffect(() => {
    const saved = localStorage.getItem('transcriptionSettings');
    if (saved) {
      setSettings(JSON.parse(saved));
    }
  }, []);

  const saveSettings = () => {
    localStorage.setItem('transcriptionSettings', JSON.stringify(settings));
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-4">Transcription Settings</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Model Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Whisper Model
            </label>
            <select
              value={settings.model}
              onChange={(e) => setSettings({ ...settings, model: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="base">Base (74M params) - Fastest</option>
              <option value="small">Small (244M params)</option>
              <option value="medium">Medium (769M params)</option>
              <option value="large">Large (1550M params)</option>
              <option value="large-v2">Large-v2 (1550M params)</option>
              <option value="large-v3">Large-v3 (1550M params) - Most Accurate</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Larger models are more accurate but slower. NPU acceleration available for all models.
            </p>
          </div>

          {/* Language */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Primary Language
            </label>
            <select
              value={settings.language}
              onChange={(e) => setSettings({ ...settings, language: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="auto">Auto-detect</option>
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="zh">Chinese</option>
              <option value="ja">Japanese</option>
              <option value="ko">Korean</option>
            </select>
          </div>

          {/* VAD Sensitivity */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Voice Activity Detection Sensitivity
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={settings.vadSensitivity}
                onChange={(e) => setSettings({ ...settings, vadSensitivity: parseFloat(e.target.value) })}
                className="flex-1"
              />
              <span className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                {settings.vadSensitivity.toFixed(1)}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Higher values detect more speech but may include noise
            </p>
          </div>

          {/* Max Speakers */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Maximum Speakers
            </label>
            <input
              type="number"
              min="1"
              max="10"
              value={settings.maxSpeakers}
              onChange={(e) => setSettings({ ...settings, maxSpeakers: parseInt(e.target.value) })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Number of speakers to detect in diarization
            </p>
          </div>
        </div>

        {/* Toggles */}
        <div className="mt-6 space-y-3">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.enableTimestamps}
              onChange={(e) => setSettings({ ...settings, enableTimestamps: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Enable word-level timestamps</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.enableSpeakerDiarization}
              onChange={(e) => setSettings({ ...settings, enableSpeakerDiarization: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Enable speaker diarization</span>
          </label>
        </div>

        <button
          onClick={saveSettings}
          className="mt-6 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          Save Transcription Settings
        </button>
      </div>
    </div>
  );
};

const AISettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<AISettings>({
    summaryLength: 'medium',
    progressiveIntervals: [50, 75, 113, 170, 255],
    temperature: 0.7,
    enableAutoTitle: true,
    enableActionItems: true,
    enableDecisions: true,
    model: 'granite3.3:8b'
  });

  useEffect(() => {
    const saved = localStorage.getItem('aiSettings');
    if (saved) {
      setSettings(JSON.parse(saved));
    }
  }, []);

  const saveSettings = () => {
    localStorage.setItem('aiSettings', JSON.stringify(settings));
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-4">AI & Intelligence Settings</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Model Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              AI Model
            </label>
            <select
              value={settings.model}
              onChange={(e) => setSettings({ ...settings, model: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="granite3.3:8b">Granite 3.3 8B (Default)</option>
              <option value="phi4-mini">Phi-4 Mini (Fast)</option>
              <option value="llama3.2:3b">Llama 3.2 3B</option>
              <option value="gemma2:9b">Gemma 2 9B</option>
            </select>
          </div>

          {/* Summary Length */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Summary Length
            </label>
            <select
              value={settings.summaryLength}
              onChange={(e) => setSettings({ ...settings, summaryLength: e.target.value as any })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="short">Short (2-3 sentences)</option>
              <option value="medium">Medium (1 paragraph)</option>
              <option value="long">Long (detailed)</option>
            </select>
          </div>

          {/* Temperature */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              AI Temperature (Creativity)
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={settings.temperature}
                onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
                className="flex-1"
              />
              <span className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                {settings.temperature.toFixed(1)}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Lower = more focused, Higher = more creative
            </p>
          </div>

          {/* Progressive Intervals */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Progressive Summary Intervals (words)
            </label>
            <input
              type="text"
              value={settings.progressiveIntervals.join(', ')}
              onChange={(e) => {
                const intervals = e.target.value.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n));
                setSettings({ ...settings, progressiveIntervals: intervals });
              }}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="50, 75, 113, 170, 255"
            />
            <p className="text-xs text-gray-500 mt-1">
              Word counts that trigger progressive summaries
            </p>
          </div>
        </div>

        {/* Feature Toggles */}
        <div className="mt-6 space-y-3">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.enableAutoTitle}
              onChange={(e) => setSettings({ ...settings, enableAutoTitle: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Auto-generate meeting titles</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.enableActionItems}
              onChange={(e) => setSettings({ ...settings, enableActionItems: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Extract action items</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.enableDecisions}
              onChange={(e) => setSettings({ ...settings, enableDecisions: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Track key decisions</span>
          </label>
        </div>

        <button
          onClick={saveSettings}
          className="mt-6 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          Save AI Settings
        </button>
      </div>
    </div>
  );
};

const AudioSettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<AudioSettings>({
    inputDevice: 'default',
    sampleRate: 44100,
    channels: 'mono',
    noiseReduction: true,
    autoGainControl: true,
    echoCancellation: false
  });

  const [availableDevices, setAvailableDevices] = useState<MediaDeviceInfo[]>([]);

  useEffect(() => {
    const saved = localStorage.getItem('audioSettings');
    if (saved) {
      setSettings(JSON.parse(saved));
    }
    
    // Get available audio devices
    navigator.mediaDevices.enumerateDevices().then(devices => {
      setAvailableDevices(devices.filter(d => d.kind === 'audioinput'));
    });
  }, []);

  const saveSettings = () => {
    localStorage.setItem('audioSettings', JSON.stringify(settings));
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-4">Audio Settings</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Input Device */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Input Device
            </label>
            <select
              value={settings.inputDevice}
              onChange={(e) => setSettings({ ...settings, inputDevice: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="default">System Default</option>
              {availableDevices.map(device => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `Device ${device.deviceId.slice(0, 8)}`}
                </option>
              ))}
            </select>
          </div>

          {/* Sample Rate */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Sample Rate
            </label>
            <select
              value={settings.sampleRate}
              onChange={(e) => setSettings({ ...settings, sampleRate: parseInt(e.target.value) })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="16000">16 kHz (Whisper native)</option>
              <option value="44100">44.1 kHz (CD quality)</option>
              <option value="48000">48 kHz (Professional)</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Higher rates capture more detail but increase file size
            </p>
          </div>

          {/* Channels */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Recording Channels
            </label>
            <select
              value={settings.channels}
              onChange={(e) => setSettings({ ...settings, channels: e.target.value as any })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="mono">Mono (recommended)</option>
              <option value="stereo">Stereo</option>
            </select>
          </div>
        </div>

        {/* Audio Processing */}
        <div className="mt-6 space-y-3">
          <h4 className="text-sm font-medium text-gray-700">Audio Processing</h4>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.noiseReduction}
              onChange={(e) => setSettings({ ...settings, noiseReduction: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Noise Reduction</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.autoGainControl}
              onChange={(e) => setSettings({ ...settings, autoGainControl: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Auto Gain Control (AGC)</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={settings.echoCancellation}
              onChange={(e) => setSettings({ ...settings, echoCancellation: e.target.checked })}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <span className="text-sm">Echo Cancellation</span>
          </label>
        </div>

        <button
          onClick={saveSettings}
          className="mt-6 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          Save Audio Settings
        </button>
      </div>
    </div>
  );
};

const ExportSettingsTab: React.FC = () => {
  const [settings, setSettings] = useState<ExportSettings>({
    defaultFormats: ['txt', 'pdf'],
    includeTimestamps: true,
    includeSpeakerLabels: true,
    includeConfidenceScores: false,
    templateStyle: 'formal',
    pdfOptions: {
      fontSize: 12,
      pageSize: 'A4',
      includeHeader: true,
      includeFooter: true
    }
  });

  useEffect(() => {
    const saved = localStorage.getItem('exportSettings');
    if (saved) {
      setSettings(JSON.parse(saved));
    }
  }, []);

  const saveSettings = () => {
    localStorage.setItem('exportSettings', JSON.stringify(settings));
  };

  const toggleFormat = (format: string) => {
    setSettings(prev => ({
      ...prev,
      defaultFormats: prev.defaultFormats.includes(format)
        ? prev.defaultFormats.filter(f => f !== format)
        : [...prev.defaultFormats, format]
    }));
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-4">Export Settings</h3>
        
        <div className="space-y-6">
          {/* Default Formats */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Default Export Formats
            </label>
            <div className="flex flex-wrap gap-3">
              {['txt', 'pdf', 'docx', 'srt', 'vtt', 'json'].map(format => (
                <label key={format} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={settings.defaultFormats.includes(format)}
                    onChange={() => toggleFormat(format)}
                    className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
                  />
                  <span className="text-sm uppercase">{format}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Template Style */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Template Style
            </label>
            <select
              value={settings.templateStyle}
              onChange={(e) => setSettings({ ...settings, templateStyle: e.target.value as any })}
              className="w-full max-w-xs px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="formal">Formal (Business)</option>
              <option value="casual">Casual (Informal)</option>
              <option value="technical">Technical (Detailed)</option>
            </select>
          </div>

          {/* Export Options */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-700">Include in Exports</h4>
            
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.includeTimestamps}
                onChange={(e) => setSettings({ ...settings, includeTimestamps: e.target.checked })}
                className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
              />
              <span className="text-sm">Timestamps</span>
            </label>
            
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.includeSpeakerLabels}
                onChange={(e) => setSettings({ ...settings, includeSpeakerLabels: e.target.checked })}
                className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
              />
              <span className="text-sm">Speaker Labels</span>
            </label>
            
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.includeConfidenceScores}
                onChange={(e) => setSettings({ ...settings, includeConfidenceScores: e.target.checked })}
                className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
              />
              <span className="text-sm">Confidence Scores</span>
            </label>
          </div>

          {/* PDF Options */}
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-gray-700 mb-3">PDF Options</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Font Size</label>
                <input
                  type="number"
                  min="8"
                  max="16"
                  value={settings.pdfOptions.fontSize}
                  onChange={(e) => setSettings({
                    ...settings,
                    pdfOptions: { ...settings.pdfOptions, fontSize: parseInt(e.target.value) }
                  })}
                  className="w-full px-3 py-1 border rounded focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              
              <div>
                <label className="block text-xs text-gray-600 mb-1">Page Size</label>
                <select
                  value={settings.pdfOptions.pageSize}
                  onChange={(e) => setSettings({
                    ...settings,
                    pdfOptions: { ...settings.pdfOptions, pageSize: e.target.value as any }
                  })}
                  className="w-full px-3 py-1 border rounded focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="A4">A4</option>
                  <option value="Letter">Letter</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        <button
          onClick={saveSettings}
          className="mt-6 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          Save Export Settings
        </button>
      </div>
    </div>
  );
};

export const SettingsHome: React.FC = () => {
  const [activeTab, setActiveTab] = useState('transcription');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');

  const tabs: SettingsTab[] = [
    {
      id: 'transcription',
      name: 'Transcription',
      icon: <Mic className="w-5 h-5" />,
      component: <TranscriptionSettingsTab />
    },
    {
      id: 'ai',
      name: 'AI & Intelligence',
      icon: <Brain className="w-5 h-5" />,
      component: <AISettingsTab />
    },
    {
      id: 'audio',
      name: 'Audio',
      icon: <Volume2 className="w-5 h-5" />,
      component: <AudioSettingsTab />
    },
    {
      id: 'export',
      name: 'Export',
      icon: <FileText className="w-5 h-5" />,
      component: <ExportSettingsTab />
    },
    {
      id: 'vocabulary',
      name: 'Vocabulary',
      icon: <Book className="w-5 h-5" />,
      component: <VocabularySettings />
    }
  ];

  const activeTabData = tabs.find(tab => tab.id === activeTab);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
            <Settings className="w-8 h-8 text-purple-600" />
            Settings
          </h1>
          <p className="text-gray-600 mt-2">
            Configure transcription, AI, audio, and export preferences for Meeting-Ops
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <div className="border-b">
            <nav className="flex space-x-1 p-1">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                    activeTab === tab.id
                      ? 'bg-purple-100 text-purple-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  {tab.icon}
                  <span className="font-medium">{tab.name}</span>
                </button>
              ))}
            </nav>
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {activeTabData?.component}
          </div>
        </div>

        {/* Global Actions */}
        <div className="bg-white rounded-lg shadow-sm p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Info className="w-4 h-4" />
              <span>Settings are saved locally and will sync with the backend when available</span>
            </div>
            
            <div className="flex items-center gap-3">
              <button className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 flex items-center gap-2">
                <RefreshCw className="w-4 h-4" />
                Reset to Defaults
              </button>
              
              {saveStatus === 'saved' && (
                <div className="flex items-center gap-2 text-green-600">
                  <Check className="w-4 h-4" />
                  <span className="text-sm">Settings saved</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};