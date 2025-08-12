import React, { useState, useEffect, useRef } from 'react';
import {
  FileText, Brain, Mic, MicOff, Loader2, AlertCircle,
  ToggleLeft, ToggleRight, Eye, EyeOff, Zap, Settings,
  ChevronDown, ChevronUp, Volume2, VolumeX, CheckCircle
} from 'lucide-react';
import { config } from '../config';

interface TranscriptionSegment {
  text: string;
  timestamp: string;
  speaker?: string;
  confidence?: number;
}

interface LiveSummary {
  keyPoints: string[];
  decisions: string[];
  actionItems: Array<{
    task: string;
    owner?: string;
    deadline?: string;
  }>;
  lastUpdated: string;
}

interface LiveTranscriptionEnhancedProps {
  sessionId: string;
  isRecording: boolean;
  onTranscriptionUpdate?: (text: string) => void;
  className?: string;
}

export const LiveTranscriptionEnhanced: React.FC<LiveTranscriptionEnhancedProps> = ({
  sessionId,
  isRecording,
  onTranscriptionUpdate,
  className = ''
}) => {
  // State for controls
  const [liveGenerationEnabled, setLiveGenerationEnabled] = useState(true);
  const [viewMode, setViewMode] = useState<'summary' | 'transcript'>('summary');
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  
  // State for generation settings
  const [generateSummary, setGenerateSummary] = useState(true);
  const [generateActionItems, setGenerateActionItems] = useState(true);
  const [generateDecisions, setGenerateDecisions] = useState(true);
  const [updateInterval, setUpdateInterval] = useState(30); // seconds
  
  // State for data
  const [segments, setSegments] = useState<TranscriptionSegment[]>([]);
  const [liveSummary, setLiveSummary] = useState<LiveSummary | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const lastGenerationTime = useRef<number>(0);

  // WebSocket connection for live transcription
  useEffect(() => {
    if (!isRecording || !sessionId) return;

    const connectWebSocket = () => {
      const wsUrl = `${config.wsEndpoints.base}/ws/transcription/${sessionId}`;
      console.log('[LiveTranscription] Connecting to:', wsUrl);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[LiveTranscription] WebSocket connected');
        setIsConnected(true);
        setError(null);
        
        // Send initial configuration
        ws.send(JSON.stringify({
          type: 'config',
          generateLive: liveGenerationEnabled,
          settings: {
            summary: generateSummary,
            actionItems: generateActionItems,
            decisions: generateDecisions,
            interval: updateInterval
          }
        }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'transcription') {
            const newSegment: TranscriptionSegment = {
              text: data.text,
              timestamp: data.timestamp || new Date().toISOString(),
              speaker: data.speaker,
              confidence: data.confidence
            };
            
            setSegments(prev => [...prev, newSegment]);
            
            if (onTranscriptionUpdate) {
              onTranscriptionUpdate(data.text);
            }
            
            // Trigger summary generation if enabled and interval passed
            if (liveGenerationEnabled && shouldGenerateSummary()) {
              generateLiveSummary();
            }
          } else if (data.type === 'summary') {
            setLiveSummary({
              keyPoints: data.keyPoints || [],
              decisions: data.decisions || [],
              actionItems: data.actionItems || [],
              lastUpdated: new Date().toISOString()
            });
            setIsGenerating(false);
          }
        } catch (err) {
          console.error('[LiveTranscription] Error parsing message:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('[LiveTranscription] WebSocket error:', error);
        setError('Connection error occurred');
      };

      ws.onclose = () => {
        console.log('[LiveTranscription] WebSocket disconnected');
        setIsConnected(false);
        
        // Attempt to reconnect if still recording
        if (isRecording) {
          setTimeout(connectWebSocket, 2000);
        }
      };
    };

    connectWebSocket();

    return () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [sessionId, isRecording]);

  // Update WebSocket configuration when settings change
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'config',
        generateLive: liveGenerationEnabled,
        settings: {
          summary: generateSummary,
          actionItems: generateActionItems,
          decisions: generateDecisions,
          interval: updateInterval
        }
      }));
    }
  }, [liveGenerationEnabled, generateSummary, generateActionItems, generateDecisions, updateInterval]);

  // Auto-scroll functionality
  useEffect(() => {
    if (autoScrollEnabled) {
      if (viewMode === 'transcript' && transcriptRef.current) {
        transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
      } else if (viewMode === 'summary' && summaryRef.current) {
        summaryRef.current.scrollTop = summaryRef.current.scrollHeight;
      }
    }
  }, [segments, liveSummary, viewMode, autoScrollEnabled]);

  const shouldGenerateSummary = (): boolean => {
    const now = Date.now();
    const timeSinceLastGeneration = (now - lastGenerationTime.current) / 1000;
    return timeSinceLastGeneration >= updateInterval;
  };

  const generateLiveSummary = async () => {
    if (isGenerating || segments.length === 0) return;
    
    setIsGenerating(true);
    lastGenerationTime.current = Date.now();
    
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/meeting-intelligence/generate-live`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          sessionId,
          transcript: segments.map(s => s.text).join(' '),
          settings: {
            summary: generateSummary,
            actionItems: generateActionItems,
            decisions: generateDecisions
          }
        })
      });

      if (response.ok) {
        const data = await response.json();
        setLiveSummary(data);
      }
    } catch (error) {
      console.error('[LiveTranscription] Failed to generate summary:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  const toggleGeneration = () => {
    setLiveGenerationEnabled(!liveGenerationEnabled);
  };

  const toggleViewMode = () => {
    setViewMode(viewMode === 'summary' ? 'transcript' : 'summary');
  };

  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-800 ${className}`}>
      {/* Header with Controls */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isConnected ? 'bg-green-500/20' : 'bg-gray-800'}`}>
              {isRecording ? (
                <Mic className={`w-4 h-4 ${isConnected ? 'text-green-400' : 'text-gray-400'}`} />
              ) : (
                <MicOff className="w-4 h-4 text-gray-400" />
              )}
            </div>
            <div>
              <h3 className="text-sm font-medium text-white">
                Live {viewMode === 'summary' ? 'Summary' : 'Transcription'}
              </h3>
              <p className="text-xs text-gray-400">
                {isConnected ? 'Connected' : 'Disconnected'} • {segments.length} segments
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
          >
            <Settings className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* Main Controls */}
        <div className="flex items-center gap-3">
          {/* Generation Toggle */}
          <button
            onClick={toggleGeneration}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors ${
              liveGenerationEnabled 
                ? 'bg-purple-500/20 text-purple-400' 
                : 'bg-gray-800 text-gray-400'
            }`}
          >
            {liveGenerationEnabled ? (
              <ToggleRight className="w-4 h-4" />
            ) : (
              <ToggleLeft className="w-4 h-4" />
            )}
            <span>AI Generation</span>
            {liveGenerationEnabled && isGenerating && (
              <Loader2 className="w-3 h-3 animate-spin ml-1" />
            )}
          </button>

          {/* View Mode Toggle */}
          <button
            onClick={toggleViewMode}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs transition-colors"
          >
            {viewMode === 'summary' ? (
              <>
                <Brain className="w-3 h-3 text-purple-400" />
                <span className="text-gray-300">Summary</span>
              </>
            ) : (
              <>
                <FileText className="w-3 h-3 text-blue-400" />
                <span className="text-gray-300">Transcript</span>
              </>
            )}
          </button>

          {/* Auto-scroll Toggle */}
          <button
            onClick={() => setAutoScrollEnabled(!autoScrollEnabled)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors ${
              autoScrollEnabled 
                ? 'bg-blue-500/20 text-blue-400' 
                : 'bg-gray-800 text-gray-400'
            }`}
          >
            {autoScrollEnabled ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
            <span>Auto-scroll</span>
          </button>
        </div>

        {/* Settings Panel */}
        {showSettings && (
          <div className="mt-3 p-3 bg-gray-800 rounded-lg">
            <h4 className="text-xs font-medium text-gray-300 mb-2">Generation Settings</h4>
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-gray-400">
                <input
                  type="checkbox"
                  checked={generateSummary}
                  onChange={(e) => setGenerateSummary(e.target.checked)}
                  className="rounded bg-gray-700 border-gray-600"
                />
                Generate Summary
              </label>
              <label className="flex items-center gap-2 text-xs text-gray-400">
                <input
                  type="checkbox"
                  checked={generateActionItems}
                  onChange={(e) => setGenerateActionItems(e.target.checked)}
                  className="rounded bg-gray-700 border-gray-600"
                />
                Extract Action Items
              </label>
              <label className="flex items-center gap-2 text-xs text-gray-400">
                <input
                  type="checkbox"
                  checked={generateDecisions}
                  onChange={(e) => setGenerateDecisions(e.target.checked)}
                  className="rounded bg-gray-700 border-gray-600"
                />
                Track Decisions
              </label>
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span>Update every</span>
                <select
                  value={updateInterval}
                  onChange={(e) => setUpdateInterval(Number(e.target.value))}
                  className="bg-gray-700 border border-gray-600 rounded px-2 py-1"
                >
                  <option value={15}>15 sec</option>
                  <option value={30}>30 sec</option>
                  <option value={60}>1 min</option>
                  <option value={120}>2 min</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Content Area */}
      <div className="h-[500px] overflow-hidden">
        {viewMode === 'summary' ? (
          /* Summary View */
          <div ref={summaryRef} className="h-full overflow-y-auto p-4 space-y-3">
            {liveSummary ? (
              <>
                {/* Key Points */}
                {liveSummary.keyPoints.length > 0 ? (
                  <div className="bg-gray-800/50 rounded-lg p-3 border-l-4 border-purple-400">
                    <h4 className="text-sm font-medium text-purple-400 mb-2 flex items-center gap-2">
                      <Zap className="w-4 h-4" />
                      Key Points
                    </h4>
                    <ul className="space-y-2">
                      {liveSummary.keyPoints.map((point, idx) => (
                        <li key={idx} className="text-sm text-gray-300 flex items-start gap-2">
                          <span className="text-purple-400 mt-0.5 flex-shrink-0">•</span>
                          <span className="leading-relaxed">{point}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700 border-dashed">
                    <div className="text-center">
                      <Zap className="w-6 h-6 text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-500">Key points will appear here as the meeting progresses</p>
                    </div>
                  </div>
                )}

                {/* Action Items */}
                {liveSummary.actionItems.length > 0 ? (
                  <div className="bg-gray-800/50 rounded-lg p-3 border-l-4 border-blue-400">
                    <h4 className="text-sm font-medium text-blue-400 mb-2 flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      Action Items
                    </h4>
                    <ul className="space-y-2">
                      {liveSummary.actionItems.map((item, idx) => (
                        <li key={idx} className="text-sm text-gray-300">
                          <div className="flex items-start gap-2">
                            <span className="text-blue-400 mt-0.5 flex-shrink-0">□</span>
                            <div className="leading-relaxed">
                              <span>{item.task}</span>
                              {item.owner && (
                                <div className="text-xs text-gray-500 mt-1">→ Assigned to: {item.owner}</div>
                              )}
                              {item.deadline && (
                                <div className="text-xs text-gray-500 mt-1">📅 Due: {item.deadline}</div>
                              )}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700 border-dashed">
                    <div className="text-center">
                      <FileText className="w-6 h-6 text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-500">Action items will be identified automatically</p>
                    </div>
                  </div>
                )}

                {/* Decisions */}
                {liveSummary.decisions.length > 0 ? (
                  <div className="bg-gray-800/50 rounded-lg p-3 border-l-4 border-green-400">
                    <h4 className="text-sm font-medium text-green-400 mb-2 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      Decisions Made
                    </h4>
                    <ul className="space-y-2">
                      {liveSummary.decisions.map((decision, idx) => (
                        <li key={idx} className="text-sm text-gray-300 flex items-start gap-2">
                          <span className="text-green-400 mt-0.5 flex-shrink-0">✓</span>
                          <span className="leading-relaxed">{decision}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700 border-dashed">
                    <div className="text-center">
                      <CheckCircle className="w-6 h-6 text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-500">Decisions will be tracked here</p>
                    </div>
                  </div>
                )}

                <div className="text-xs text-gray-500 text-center py-2 border-t border-gray-800">
                  🤖 Last updated: {new Date(liveSummary.lastUpdated).toLocaleTimeString()}
                </div>
              </>
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  {liveGenerationEnabled ? (
                    <>
                      <Brain className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-400">Waiting for summary generation...</p>
                      <p className="text-xs text-gray-500 mt-1">
                        Summary will appear after {updateInterval} seconds of transcription
                      </p>
                    </>
                  ) : (
                    <>
                      <EyeOff className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-400">AI Generation Disabled</p>
                      <p className="text-xs text-gray-500 mt-1">
                        Enable AI generation to see live summaries
                      </p>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Transcript View */
          <div ref={transcriptRef} className="h-full overflow-y-auto p-4">
            {segments.length > 0 ? (
              <div className="space-y-2">
                {segments.map((segment, idx) => (
                  <div key={idx} className="group hover:bg-gray-800/30 rounded p-2 transition-colors">
                    <div className="flex items-start gap-3">
                      <span className="text-xs text-gray-500 mt-0.5">
                        {new Date(segment.timestamp).toLocaleTimeString()}
                      </span>
                      {segment.speaker && (
                        <span className="text-xs px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">
                          {segment.speaker}
                        </span>
                      )}
                      <p className="text-sm text-gray-300 flex-1">{segment.text}</p>
                      {segment.confidence && (
                        <span className="text-xs text-gray-600">
                          {Math.round(segment.confidence * 100)}%
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <FileText className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                  <p className="text-sm text-gray-400">No transcription yet</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {isRecording ? 'Waiting for speech...' : 'Start recording to begin'}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-3 bg-red-500/10 border-t border-red-500/20">
          <div className="flex items-center gap-2 text-xs text-red-400">
            <AlertCircle className="w-3 h-3" />
            <span>{error}</span>
          </div>
        </div>
      )}
    </div>
  );
};