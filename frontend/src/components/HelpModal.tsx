import { useState } from 'react';
import { X, Book, Zap, Brain, Mic, Globe, FileText, HelpCircle, Keyboard } from 'lucide-react';

interface HelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function HelpModal({ isOpen, onClose }: HelpModalProps) {
  const [activeSection, setActiveSection] = useState('getting-started');

  if (!isOpen) return null;

  const sections = [
    { id: 'getting-started', title: 'Getting Started', icon: Book },
    { id: 'npu-acceleration', title: 'NPU Acceleration', icon: Zap },
    { id: 'transcription', title: 'Transcription', icon: Mic },
    { id: 'diarization', title: 'Speaker Diarization', icon: Brain },
    { id: 'inference-server', title: 'Inference Server', icon: Globe },
    { id: 'export-formats', title: 'Export Formats', icon: FileText },
    { id: 'keyboard-shortcuts', title: 'Keyboard Shortcuts', icon: Keyboard },
    { id: 'troubleshooting', title: 'Troubleshooting', icon: HelpCircle }
  ];

  const content = {
    'getting-started': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Welcome to Unicorn Commander Meeting Ops!</h3>
        
        <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
          <h4 className="font-semibold text-blue-400 mb-2">Quick Start</h4>
          <ol className="list-decimal list-inside space-y-2 text-gray-300">
            <li>Configure your inference server in Settings → Inference Server</li>
            <li>Select your audio input device in Settings → Audio</li>
            <li>Click "Start Recording" to begin a new meeting session</li>
            <li>Real-time transcription will appear automatically</li>
            <li>Stop recording to save and process the session</li>
          </ol>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Key Features</h4>
          <ul className="space-y-2 text-gray-300">
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>Real-time Transcription:</strong> See words as they're spoken with sub-second latency</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>Speaker Diarization:</strong> Automatically identify and separate different speakers</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>NPU Acceleration:</strong> 220x-7800x faster processing with AMD NPU</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span><strong>AI Summarization:</strong> Get intelligent meeting summaries with action items</span>
            </li>
          </ul>
        </div>

        <div className="bg-purple-900/20 border border-purple-700 rounded-lg p-4">
          <h4 className="font-semibold text-purple-400 mb-2">Pro Tip</h4>
          <p className="text-gray-300">
            Enable NPU acceleration in Settings for blazing fast transcription. With NPU enabled,
            a 1-hour meeting processes in just 1.2 seconds!
          </p>
        </div>
      </div>
    ),

    'npu-acceleration': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">NPU Acceleration Guide</h3>
        
        <div className="bg-green-900/20 border border-green-700 rounded-lg p-4">
          <h4 className="font-semibold text-green-400 mb-2">Performance Gains</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-400">CPU Baseline:</span>
              <p className="text-white font-mono">13.6x real-time</p>
            </div>
            <div>
              <span className="text-gray-400">NPU Accelerated:</span>
              <p className="text-green-400 font-mono">2,985x real-time</p>
            </div>
            <div>
              <span className="text-gray-400">Tokens/second:</span>
              <p className="text-white font-mono">22 → 4,789</p>
            </div>
            <div>
              <span className="text-gray-400">8-min audio:</span>
              <p className="text-green-400 font-mono">38s → 0.175s</p>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">NPU Requirements</h4>
          <ul className="space-y-2 text-gray-300">
            <li>• AMD Ryzen AI (Phoenix/Hawk Point) processor</li>
            <li>• 16 TOPS INT8 performance</li>
            <li>• XRT drivers installed</li>
            <li>• 4GB+ available memory</li>
          </ul>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Optimization Levels</h4>
          <div className="space-y-2">
            <div className="bg-gray-800 rounded p-3">
              <div className="flex justify-between items-center mb-1">
                <span className="font-medium">INT8 Quantization</span>
                <span className="text-green-400">Recommended</span>
              </div>
              <p className="text-sm text-gray-400">Best balance of speed and accuracy. 16 TOPS INT8 performance.</p>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="flex justify-between items-center mb-1">
                <span className="font-medium">INT4 Quantization</span>
                <span className="text-yellow-400">Experimental</span>
              </div>
              <p className="text-sm text-gray-400">Maximum speed (32 TOPS INT4) with slight accuracy trade-off.</p>
            </div>
          </div>
        </div>

        <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-4">
          <h4 className="font-semibold text-yellow-400 mb-2">Note</h4>
          <p className="text-gray-300">
            NPU acceleration requires compatible hardware. The system will automatically fall back
            to CPU if NPU is not available.
          </p>
        </div>
      </div>
    ),

    'transcription': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Transcription Settings</h3>
        
        <div className="space-y-3">
          <h4 className="font-semibold text-white">Model Sizes</h4>
          <div className="space-y-2 text-sm">
            <div className="bg-gray-800 rounded p-3">
              <div className="flex justify-between items-center">
                <span className="font-medium">Tiny (39M)</span>
                <span className="text-gray-400">Fastest, lowest accuracy</span>
              </div>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="flex justify-between items-center">
                <span className="font-medium">Base (74M)</span>
                <span className="text-gray-400">Good for quick drafts</span>
              </div>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="flex justify-between items-center">
                <span className="font-medium">Small (244M)</span>
                <span className="text-gray-400">Balanced performance</span>
              </div>
            </div>
            <div className="bg-gray-800 rounded p-3 border border-green-600">
              <div className="flex justify-between items-center">
                <span className="font-medium">Medium (769M)</span>
                <span className="text-green-400">Recommended ⭐</span>
              </div>
            </div>
            <div className="bg-gray-800 rounded p-3">
              <div className="flex justify-between items-center">
                <span className="font-medium">Large (1550M)</span>
                <span className="text-gray-400">Maximum accuracy</span>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Key Parameters</h4>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="font-medium text-gray-300">Beam Size</dt>
              <dd className="text-gray-400">Higher values (5-10) improve accuracy but slow down processing</dd>
            </div>
            <div>
              <dt className="font-medium text-gray-300">Temperature</dt>
              <dd className="text-gray-400">0 for deterministic output, higher for more variation</dd>
            </div>
            <div>
              <dt className="font-medium text-gray-300">Language</dt>
              <dd className="text-gray-400">Set to 'auto' for detection or specify for 2x faster processing</dd>
            </div>
          </dl>
        </div>

        <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
          <h4 className="font-semibold text-blue-400 mb-2">Best Practices</h4>
          <ul className="list-disc list-inside space-y-1 text-gray-300 text-sm">
            <li>Use Medium model for meetings (best accuracy/speed balance)</li>
            <li>Enable word timestamps for synchronized playback</li>
            <li>Set language explicitly if known (2x speed boost)</li>
            <li>Keep beam size at 5 unless accuracy is critical</li>
          </ul>
        </div>
      </div>
    ),

    'diarization': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Speaker Diarization</h3>
        
        <div className="bg-purple-900/20 border border-purple-700 rounded-lg p-4">
          <h4 className="font-semibold text-purple-400 mb-2">What is Diarization?</h4>
          <p className="text-gray-300">
            Speaker diarization automatically identifies "who spoke when" in your recordings,
            separating different speakers and labeling their segments.
          </p>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Configuration Options</h4>
          
          <div className="space-y-2">
            <h5 className="font-medium text-gray-300">Speaker Count</h5>
            <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm ml-4">
              <li>Min Speakers: Set to expected minimum (e.g., 2 for interviews)</li>
              <li>Max Speakers: Upper limit to prevent over-segmentation</li>
              <li>Auto-detection works well for 2-10 speakers</li>
            </ul>
          </div>

          <div className="space-y-2">
            <h5 className="font-medium text-gray-300">Clustering Methods</h5>
            <ul className="space-y-1 text-gray-400 text-sm">
              <li><strong>Spectral:</strong> Best overall accuracy (recommended)</li>
              <li><strong>Agglomerative:</strong> Good for clear speaker separation</li>
              <li><strong>K-Means:</strong> Fastest but less accurate</li>
            </ul>
          </div>

          <div className="space-y-2">
            <h5 className="font-medium text-gray-300">Embedding Models</h5>
            <ul className="space-y-1 text-gray-400 text-sm">
              <li><strong>TitanNet:</strong> NPU-optimized, best accuracy ⭐</li>
              <li><strong>ECAPA-TDNN:</strong> Good CPU performance</li>
              <li><strong>ResNet34:</strong> Lightweight option</li>
            </ul>
          </div>
        </div>

        <div className="bg-green-900/20 border border-green-700 rounded-lg p-4">
          <h4 className="font-semibold text-green-400 mb-2">With WhisperX</h4>
          <p className="text-gray-300 text-sm">
            Our WhisperX integration provides unified transcription + diarization in a single
            pass, achieving 7,866x real-time performance with NPU acceleration!
          </p>
        </div>
      </div>
    ),

    'inference-server': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Inference Server Setup</h3>
        
        <div className="space-y-3">
          <h4 className="font-semibold text-white">Supported Servers</h4>
          <ul className="space-y-2 text-gray-300">
            <li className="flex items-start gap-2">
              <span className="text-green-400">•</span>
              <span><strong>Whisper Server:</strong> OpenAI's official implementation</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">•</span>
              <span><strong>WhisperX Server:</strong> With built-in diarization</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">•</span>
              <span><strong>Custom ONNX:</strong> Your own ONNX runtime server</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">•</span>
              <span><strong>Local NPU:</strong> Direct hardware acceleration</span>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Configuration</h4>
          <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm">
            <div className="text-gray-400"># Example configuration</div>
            <div className="text-white">Server URL: http://localhost:8080</div>
            <div className="text-white">API Key: sk-your-api-key</div>
            <div className="text-white">Endpoint: /v1/transcribe</div>
            <div className="text-white">Timeout: 30000ms</div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Testing Connection</h4>
          <ol className="list-decimal list-inside space-y-1 text-gray-300">
            <li>Enter your server URL and API key</li>
            <li>Click "Test Connection"</li>
            <li>Look for the green checkmark</li>
            <li>If it fails, check server logs and firewall</li>
          </ol>
        </div>

        <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-4">
          <h4 className="font-semibold text-yellow-400 mb-2">Security Note</h4>
          <p className="text-gray-300 text-sm">
            API keys are stored securely and never exposed in the frontend. Always use HTTPS
            in production environments.
          </p>
        </div>
      </div>
    ),

    'export-formats': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Export Formats</h3>
        
        <div className="space-y-3">
          <h4 className="font-semibold text-white">Available Formats</h4>
          
          <div className="space-y-2">
            <div className="bg-gray-800 rounded p-3">
              <h5 className="font-medium text-green-400">JSON</h5>
              <p className="text-sm text-gray-400">
                Complete data with timestamps, speakers, confidence scores. Best for API integration.
              </p>
            </div>
            
            <div className="bg-gray-800 rounded p-3">
              <h5 className="font-medium text-blue-400">TXT</h5>
              <p className="text-sm text-gray-400">
                Plain text transcript with optional timestamps and speakers. Human-readable.
              </p>
            </div>
            
            <div className="bg-gray-800 rounded p-3">
              <h5 className="font-medium text-purple-400">SRT/VTT</h5>
              <p className="text-sm text-gray-400">
                Subtitle formats for video synchronization. Includes precise timing.
              </p>
            </div>
            
            <div className="bg-gray-800 rounded p-3">
              <h5 className="font-medium text-yellow-400">PDF</h5>
              <p className="text-sm text-gray-400">
                Formatted document with headers, speakers, and summary. Print-ready.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Export Options</h4>
          <ul className="space-y-2 text-gray-300 text-sm">
            <li>• <strong>Include Timestamps:</strong> Add time markers to text</li>
            <li>• <strong>Speaker Labels:</strong> Show who said what</li>
            <li>• <strong>Confidence Scores:</strong> Include accuracy metrics</li>
            <li>• <strong>Word Timestamps:</strong> Precise timing for each word</li>
            <li>• <strong>Summary:</strong> Add AI-generated summary section</li>
          </ul>
        </div>

        <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
          <h4 className="font-semibold text-blue-400 mb-2">Format Examples</h4>
          <div className="font-mono text-xs space-y-2">
            <div className="text-gray-400"># With speaker prefix:</div>
            <div className="text-white">[SPEAKER_01] Hello everyone</div>
            <div className="text-white">[SPEAKER_02] Good morning</div>
            <div className="text-gray-400 mt-2"># With timestamps:</div>
            <div className="text-white">[00:00:00] Hello everyone</div>
            <div className="text-white">[00:00:02] Good morning</div>
          </div>
        </div>
      </div>
    ),

    'keyboard-shortcuts': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Keyboard Shortcuts</h3>
        
        <div className="space-y-3">
          <h4 className="font-semibold text-white">Recording Controls</h4>
          <div className="space-y-2">
            {[
              { keys: 'Ctrl+R', action: 'Start/Resume Recording' },
              { keys: 'Ctrl+S', action: 'Stop Recording' },
              { keys: 'Ctrl+P', action: 'Pause Recording' },
              { keys: 'Ctrl+N', action: 'New Session' },
            ].map(({ keys, action }) => (
              <div key={keys} className="flex justify-between items-center bg-gray-800 rounded p-2">
                <span className="text-gray-300">{action}</span>
                <kbd className="bg-gray-700 px-2 py-1 rounded text-sm font-mono">{keys}</kbd>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Navigation</h4>
          <div className="space-y-2">
            {[
              { keys: 'Ctrl+,', action: 'Open Settings' },
              { keys: 'Ctrl+/', action: 'Show Help' },
              { keys: 'Ctrl+E', action: 'Export Session' },
              { keys: 'Escape', action: 'Close Modal/Dialog' },
            ].map(({ keys, action }) => (
              <div key={keys} className="flex justify-between items-center bg-gray-800 rounded p-2">
                <span className="text-gray-300">{action}</span>
                <kbd className="bg-gray-700 px-2 py-1 rounded text-sm font-mono">{keys}</kbd>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-semibold text-white">Playback</h4>
          <div className="space-y-2">
            {[
              { keys: 'Space', action: 'Play/Pause Audio' },
              { keys: '←/→', action: 'Seek 5 seconds' },
              { keys: 'Shift+←/→', action: 'Seek 30 seconds' },
              { keys: '↑/↓', action: 'Volume Up/Down' },
            ].map(({ keys, action }) => (
              <div key={keys} className="flex justify-between items-center bg-gray-800 rounded p-2">
                <span className="text-gray-300">{action}</span>
                <kbd className="bg-gray-700 px-2 py-1 rounded text-sm font-mono">{keys}</kbd>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-purple-900/20 border border-purple-700 rounded-lg p-4">
          <h4 className="font-semibold text-purple-400 mb-2">Customization</h4>
          <p className="text-gray-300 text-sm">
            You can customize all keyboard shortcuts in Settings → UI & Shortcuts
          </p>
        </div>
      </div>
    ),

    'troubleshooting': (
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white mb-4">Troubleshooting</h3>
        
        <div className="space-y-4">
          <div className="bg-gray-800 rounded-lg p-4">
            <h4 className="font-semibold text-red-400 mb-2">No Audio Input</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-300 text-sm">
              <li>Check microphone permissions in your OS</li>
              <li>Verify correct input device in Settings → Audio</li>
              <li>Test with system audio recorder first</li>
              <li>Restart the audio service: <code className="bg-gray-700 px-1 rounded">systemctl restart unicorn-audio</code></li>
            </ul>
          </div>

          <div className="bg-gray-800 rounded-lg p-4">
            <h4 className="font-semibold text-red-400 mb-2">Slow Transcription</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-300 text-sm">
              <li>Enable NPU acceleration if available</li>
              <li>Reduce model size (try Base or Small)</li>
              <li>Lower beam size to 3-5</li>
              <li>Check CPU/memory usage</li>
            </ul>
          </div>

          <div className="bg-gray-800 rounded-lg p-4">
            <h4 className="font-semibold text-red-400 mb-2">NPU Not Detected</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-300 text-sm">
              <li>Verify AMD Ryzen AI processor</li>
              <li>Install XRT drivers: <code className="bg-gray-700 px-1 rounded">sudo apt install xrt</code></li>
              <li>Check dmesg for NPU errors</li>
              <li>Update BIOS to latest version</li>
            </ul>
          </div>

          <div className="bg-gray-800 rounded-lg p-4">
            <h4 className="font-semibold text-red-400 mb-2">Inference Server Connection Failed</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-300 text-sm">
              <li>Verify server is running and accessible</li>
              <li>Check firewall rules (port 8080)</li>
              <li>Test with curl: <code className="bg-gray-700 px-1 rounded">curl http://localhost:8080/health</code></li>
              <li>Verify API key is correct</li>
            </ul>
          </div>
        </div>

        <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
          <h4 className="font-semibold text-blue-400 mb-2">Need More Help?</h4>
          <p className="text-gray-300 text-sm">
            Check the logs at <code className="bg-gray-700 px-1 rounded">/var/log/unicorn-commander/</code>
            or file an issue on our GitHub repository.
          </p>
        </div>
      </div>
    )
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-gray-900 rounded-lg shadow-2xl max-w-5xl w-full max-h-[90vh] flex">
        {/* Sidebar */}
        <div className="w-64 bg-gray-800 rounded-l-lg p-4 border-r border-gray-700">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-white">Help & Docs</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          
          <nav className="space-y-1">
            {sections.map(section => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-2 transition-colors ${
                  activeSection === section.id
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:bg-gray-700'
                }`}
              >
                <section.icon className="w-4 h-4" />
                <span className="text-sm">{section.title}</span>
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto">
          {content[activeSection as keyof typeof content]}
          
          <div className="mt-8 pt-4 border-t border-gray-700">
            <p className="text-gray-400 text-sm">
              Unicorn Commander Meeting Ops v1.0 • Powered by WhisperX + NPU
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}