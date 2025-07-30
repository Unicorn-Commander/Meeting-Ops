import React, { useState, useEffect } from 'react';
import { Save, TestTube, Loader } from 'lucide-react';

interface ConfigurationProps {
  activeTab?: string;
}

export const Configuration: React.FC<ConfigurationProps> = ({ activeTab }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTabState, setActiveTabState] = useState<'audio' | 'stt' | 'export' | 'notifications' | 'system'>('audio');

  useEffect(() => {
    setLoading(false);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    // Simulate save
    await new Promise(resolve => setTimeout(resolve, 1000));
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-white">Configuration</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 px-4 py-2 rounded-lg font-medium transition-all duration-200 disabled:opacity-50"
        >
          {saving ? <Loader className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-gray-800 p-1 rounded-lg">
        {[
          { id: 'audio', label: 'Audio Settings' },
          { id: 'stt', label: 'Speech-to-Text' },
          { id: 'export', label: 'Export Options' },
          { id: 'notifications', label: 'Notifications' },
          { id: 'system', label: 'System' }
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTabState(tab.id as any)}
            className={`px-4 py-2 rounded-md font-medium transition-all duration-200 ${
              activeTabState === tab.id
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        {activeTabState === 'audio' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold text-white mb-4">Audio Configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Input Device
                </label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white">
                  <option>Default Microphone</option>
                  <option>USB Audio Device</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Sample Rate
                </label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white">
                  <option>16000 Hz</option>
                  <option>44100 Hz</option>
                  <option>48000 Hz</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {activeTabState === 'stt' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold text-white mb-4">Speech-to-Text Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Model
                </label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white">
                  <option>WhisperX NPU (Recommended)</option>
                  <option>Whisper Base</option>
                  <option>Whisper Small</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Language
                </label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white">
                  <option>Auto-detect</option>
                  <option>English</option>
                  <option>Spanish</option>
                  <option>French</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {activeTabState === 'export' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold text-white mb-4">Export Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="flex items-center space-x-2">
                  <input type="checkbox" className="rounded bg-gray-700 border-gray-600" defaultChecked />
                  <span className="text-white">Include timestamps</span>
                </label>
              </div>
              <div>
                <label className="flex items-center space-x-2">
                  <input type="checkbox" className="rounded bg-gray-700 border-gray-600" defaultChecked />
                  <span className="text-white">Include speaker labels</span>
                </label>
              </div>
              <div>
                <label className="flex items-center space-x-2">
                  <input type="checkbox" className="rounded bg-gray-700 border-gray-600" />
                  <span className="text-white">Include confidence scores</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTabState === 'notifications' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold text-white mb-4">Notification Settings</h2>
            <div className="space-y-4">
              <div>
                <label className="flex items-center space-x-2">
                  <input type="checkbox" className="rounded bg-gray-700 border-gray-600" defaultChecked />
                  <span className="text-white">Email notifications</span>  
                </label>
              </div>
              <div>
                <label className="flex items-center space-x-2">
                  <input type="checkbox" className="rounded bg-gray-700 border-gray-600" />
                  <span className="text-white">Webhook notifications</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTabState === 'system' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold text-white mb-4">System Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Storage Path
                </label>
                <input 
                  type="text" 
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  defaultValue="/opt/meeting-ops/storage"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max Storage (GB)
                </label>
                <input 
                  type="number" 
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  defaultValue={100}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};