import { useState } from 'react';
import { Book, Zap, Brain, Mic, Globe, FileText, HelpCircle, Keyboard, Command } from 'lucide-react';

export function HelpModal() {
  const [activeSection, setActiveSection] = useState('getting-started');

  const sections = [
    { id: 'getting-started', title: 'Getting Started', icon: Book },
    { id: 'command-center', title: 'Command Center', icon: Command },
    { id: 'npu-acceleration', title: 'NPU Acceleration', icon: Zap },
    { id: 'transcription', title: 'Transcription', icon: Mic },
    { id: 'diarization', title: 'Speaker Diarization', icon: Brain },
    { id: 'integrations', title: 'Integrations', icon: Globe },
    { id: 'export-formats', title: 'Export Formats', icon: FileText },
    { id: 'keyboard-shortcuts', title: 'Keyboard Shortcuts', icon: Keyboard },
    { id: 'troubleshooting', title: 'Troubleshooting', icon: HelpCircle }
  ];

  const content: Record<string, React.JSX.Element> = {
    'getting-started': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Welcome to Unicorn Commander: Meeting Ops!</h3>
        
        <div className="bg-gradient-to-r from-purple-900/20 to-pink-900/20 border border-purple-700 rounded-lg p-4">
          <h4 className="font-semibold text-purple-400 mb-2">Quick Start Guide</h4>
          <ol className="list-decimal list-inside space-y-2 text-gray-300">
            <li>Navigate to <strong>Command Center</strong> for real-time meeting control</li>
            <li>Configure audio devices in <strong>Configuration</strong></li>
            <li>Click the <strong>Quick Record</strong> button to start recording</li>
            <li>View live transcription and audio levels in real-time</li>
            <li>Access recordings in <strong>Meeting Sessions</strong></li>
          </ol>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Key Features</h4>
          <ul className="space-y-2 text-gray-300">
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>NPU Acceleration:</strong> 7,866x real-time transcription speed</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>Real-time Processing:</strong> Live transcription with speaker identification</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>AI Insights:</strong> Meeting summaries and action item extraction</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>Smart Search:</strong> Semantic search across all recordings</span>
            </li>
          </ul>
        </div>
      </div>
    ),
    'command-center': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Command Center</h3>
        <p className="text-gray-300">The Command Center is your real-time meeting operations hub.</p>
        
        <div className="space-y-3">
          <h4 className="font-semibold text-white">Features:</h4>
          <ul className="space-y-2 text-gray-300">
            <li>• <strong>Live Audio Monitoring:</strong> Real-time audio level visualization</li>
            <li>• <strong>NPU Status:</strong> Monitor acceleration performance</li>
            <li>• <strong>Quick Controls:</strong> Start/stop recording with one click</li>
            <li>• <strong>Live Transcription:</strong> See words as they're spoken</li>
            <li>• <strong>Meeting Stats:</strong> Real-time metrics and insights</li>
          </ul>
        </div>

        <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
          <h4 className="font-semibold text-blue-400 mb-2">Pro Tip</h4>
          <p className="text-gray-300">Use keyboard shortcut <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+R</kbd> to quickly start/stop recording from anywhere in the app.</p>
        </div>
      </div>
    ),
    'npu-acceleration': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">NPU Acceleration</h3>
        <p className="text-gray-300">Unicorn Commander leverages AMD Phoenix NPU for incredible performance.</p>
        
        <div className="bg-green-900/20 border border-green-700 rounded-lg p-4">
          <h4 className="font-semibold text-green-400 mb-2">Performance Metrics</h4>
          <ul className="space-y-1 text-gray-300">
            <li>• Transcription Speed: <strong>7,866x real-time</strong></li>
            <li>• Speaker Diarization: <strong>50x real-time</strong></li>
            <li>• Power Efficiency: <strong>10x better than CPU</strong></li>
            <li>• Token Processing: <strong>4,789 tokens/second</strong></li>
          </ul>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">NPU Models</h4>
          <ul className="space-y-2 text-gray-300">
            <li>• <strong>WhisperX:</strong> Unified transcription + diarization</li>
            <li>• <strong>TitanNet:</strong> Speaker identification</li>
            <li>• <strong>Custom MLIR:</strong> Optimized kernels for AMD XDNA</li>
          </ul>
        </div>
      </div>
    ),
    'keyboard-shortcuts': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Keyboard Shortcuts</h3>
        
        <div className="space-y-4">
          <div>
            <h4 className="font-semibold text-white mb-2">Recording Controls</h4>
            <div className="space-y-2 text-gray-300">
              <div className="flex justify-between">
                <span>Start/Stop Recording</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+R</kbd>
              </div>
              <div className="flex justify-between">
                <span>Pause/Resume</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+P</kbd>
              </div>
              <div className="flex justify-between">
                <span>Quick Save</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+S</kbd>
              </div>
            </div>
          </div>

          <div>
            <h4 className="font-semibold text-white mb-2">Navigation</h4>
            <div className="space-y-2 text-gray-300">
              <div className="flex justify-between">
                <span>Command Center</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+1</kbd>
              </div>
              <div className="flex justify-between">
                <span>Sessions</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+2</kbd>
              </div>
              <div className="flex justify-between">
                <span>Smart Search</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+/</kbd>
              </div>
              <div className="flex justify-between">
                <span>Settings</span>
                <kbd className="px-2 py-1 bg-gray-700 rounded">Ctrl+,</kbd>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  };

  // Add default content for sections not defined
  const defaultContent = (
    <div className="space-y-4">
      <h3 className="text-xl font-bold text-white mb-4">Documentation Coming Soon</h3>
      <p className="text-gray-300">This section is being prepared. Check back soon!</p>
    </div>
  );

  return (
    <div className="bg-gray-800 rounded-lg overflow-hidden">
      <div className="flex h-[600px]">
        {/* Sidebar */}
        <div className="w-64 bg-gray-900 border-r border-gray-700 p-4">
          <h2 className="text-lg font-bold text-white mb-4">Help Topics</h2>
          <nav className="space-y-1">
            {sections.map((section) => {
              const Icon = section.icon;
              return (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg transition-colors flex items-center gap-3 ${
                    activeSection === section.id
                      ? 'bg-gradient-to-r from-purple-600/20 to-pink-600/20 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="text-sm">{section.title}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto">
          {content[activeSection] || defaultContent}
        </div>
      </div>
    </div>
  );
}