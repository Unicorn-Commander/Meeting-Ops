import React, { useState } from 'react';
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
  ChevronRight
} from 'lucide-react';

interface SettingsSection {
  id: string;
  title: string;
  icon: React.ElementType;
  description: string;
}

export default function Settings() {
  const [activeSection, setActiveSection] = useState('audio');
  const [settings, setSettings] = useState({
    // Audio Settings
    defaultDevice: 'default',
    sampleRate: '16000',
    transcriptionModel: 'large-v3',
    liveTranscription: true,
    vadEnabled: true,
    
    // AI Settings
    enableAI: true,
    summaryFormat: 'executive',
    autoGenerateActions: true,
    speakerDiarization: true,
    
    // Export Settings
    defaultExportFormat: 'txt',
    includeTimestamps: true,
    includeSpeakerLabels: true,
    
    // Notifications
    emailNotifications: false,
    notificationEmail: '',
    sendOnComplete: false,
    sendActionItems: false,
  });

  const sections: SettingsSection[] = [
    { id: 'audio', title: 'Audio & Recording', icon: Mic, description: 'Configure audio input and recording settings' },
    { id: 'ai', title: 'AI & Transcription', icon: Cpu, description: 'AI models and processing options' },
    { id: 'export', title: 'Export & Sharing', icon: Database, description: 'Default export formats and options' },
    { id: 'notifications', title: 'Notifications', icon: Bell, description: 'Email and alert preferences' },
    { id: 'users', title: 'Users & Access', icon: Users, description: 'Manage users and permissions' },
    { id: 'security', title: 'Security', icon: Shield, description: 'Security and privacy settings' },
    { id: 'api', title: 'API & Integrations', icon: Key, description: 'API keys and third-party integrations' },
    { id: 'system', title: 'System', icon: Globe, description: 'System configuration and maintenance' },
  ];

  const handleSave = () => {
    // Save settings to backend
    console.log('Saving settings:', settings);
    alert('Settings saved successfully!');
  };

  const renderSectionContent = () => {
    switch (activeSection) {
      case 'audio':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Default Audio Device
              </label>
              <select 
                value={settings.defaultDevice}
                onChange={(e) => setSettings({...settings, defaultDevice: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="default">System Default</option>
                <option value="usb">USB Microphone</option>
                <option value="builtin">Built-in Microphone</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Sample Rate
              </label>
              <select 
                value={settings.sampleRate}
                onChange={(e) => setSettings({...settings, sampleRate: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="16000">16 kHz (Optimal for transcription)</option>
                <option value="44100">44.1 kHz (CD Quality)</option>
                <option value="48000">48 kHz (Professional)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Transcription Model
              </label>
              <select 
                value={settings.transcriptionModel}
                onChange={(e) => setSettings({...settings, transcriptionModel: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="base">Whisper Base (Fast)</option>
                <option value="small">Whisper Small</option>
                <option value="medium">Whisper Medium</option>
                <option value="large">Whisper Large</option>
                <option value="large-v2">Whisper Large-v2</option>
                <option value="large-v3">Whisper Large-v3 (Best)</option>
              </select>
            </div>

            <div className="space-y-3">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.liveTranscription}
                  onChange={(e) => setSettings({...settings, liveTranscription: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable live transcription</span>
              </label>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.vadEnabled}
                  onChange={(e) => setSettings({...settings, vadEnabled: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Voice Activity Detection (VAD)</span>
              </label>
            </div>
          </div>
        );

      case 'ai':
        return (
          <div className="space-y-6">
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
            </div>
          </div>
        );

      case 'export':
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Default Export Format
              </label>
              <select 
                value={settings.defaultExportFormat}
                onChange={(e) => setSettings({...settings, defaultExportFormat: e.target.value})}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="txt">Plain Text (.txt)</option>
                <option value="pdf">PDF Document</option>
                <option value="docx">Word Document (.docx)</option>
                <option value="md">Markdown (.md)</option>
                <option value="json">JSON Data</option>
              </select>
            </div>

            <div className="space-y-3">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.includeTimestamps}
                  onChange={(e) => setSettings({...settings, includeTimestamps: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Include timestamps</span>
              </label>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={settings.includeSpeakerLabels}
                  onChange={(e) => setSettings({...settings, includeSpeakerLabels: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Include speaker labels</span>
              </label>
            </div>
          </div>
        );

      case 'notifications':
        return (
          <div className="space-y-6">
            <div>
              <label className="flex items-center gap-3 mb-4">
                <input
                  type="checkbox"
                  checked={settings.emailNotifications}
                  onChange={(e) => setSettings({...settings, emailNotifications: e.target.checked})}
                  className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                />
                <span className="text-sm text-zinc-300">Enable email notifications</span>
              </label>

              {settings.emailNotifications && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Notification Email
                    </label>
                    <input
                      type="email"
                      value={settings.notificationEmail}
                      onChange={(e) => setSettings({...settings, notificationEmail: e.target.value})}
                      placeholder="your@email.com"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
                    />
                  </div>

                  <div className="space-y-3">
                    <label className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={settings.sendOnComplete}
                        onChange={(e) => setSettings({...settings, sendOnComplete: e.target.checked})}
                        className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                      />
                      <span className="text-sm text-zinc-300">Send summary when recording completes</span>
                    </label>

                    <label className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={settings.sendActionItems}
                        onChange={(e) => setSettings({...settings, sendActionItems: e.target.checked})}
                        className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
                      />
                      <span className="text-sm text-zinc-300">Send action items to participants</span>
                    </label>
                  </div>
                </>
              )}
            </div>
          </div>
        );

      default:
        return (
          <div className="flex items-center justify-center h-64 text-zinc-500">
            <div className="text-center">
              <SettingsIcon className="w-16 h-16 mx-auto mb-4 text-zinc-700" />
              <p>This section is coming soon</p>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
          <p className="text-zinc-400">Configure your Meeting-Ops experience</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Settings Navigation */}
          <div className="lg:col-span-1">
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-2">
              {sections.map(section => {
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
                <button
                  onClick={handleSave}
                  className="px-6 py-3 bg-gradient-to-r from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 text-white rounded-xl font-medium flex items-center gap-2 transition-colors"
                >
                  <Save className="w-5 h-5" />
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}