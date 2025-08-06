import React, { useState, useEffect, useRef } from 'react';
import { Mic, Users, Clock, AlertCircle, Wifi, WifiOff, User, Zap } from 'lucide-react';

interface Word {
  word: string;
  start: number;
  end: number;
  confidence: number;
}

interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
  speaker: string;
  words?: Word[];
  confidence?: number;
  is_partial?: boolean;
}

interface LiveTranscriptionViewerProps {
  sessionId?: string | null;
  isRecording?: boolean;
  onSegmentReceived?: (segment: TranscriptionSegment) => void;
}

export const LiveTranscriptionViewer: React.FC<LiveTranscriptionViewerProps> = ({
  sessionId,
  isRecording = false,
  onSegmentReceived
}) => {
  const [segments, setSegments] = useState<TranscriptionSegment[]>([]);
  const [speakers, setSpeakers] = useState<Map<string, { color: string; duration: number }>>(new Map());
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error' | 'idle'>('idle');
  const [npuActive, setNpuActive] = useState(false);
  const segmentsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Speaker colors for differentiation
  const speakerColors = [
    'text-blue-400',
    'text-green-400',
    'text-purple-400',
    'text-yellow-400',
    'text-pink-400',
    'text-cyan-400'
  ];

  // Format timestamp
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Get speaker color
  const getSpeakerColor = (speaker: string): string => {
    if (!speakers.has(speaker)) {
      const newSpeakers = new Map(speakers);
      const colorIndex = speakers.size % speakerColors.length;
      newSpeakers.set(speaker, { 
        color: speakerColors[colorIndex], 
        duration: 0 
      });
      setSpeakers(newSpeakers);
      return speakerColors[colorIndex];
    }
    return speakers.get(speaker)?.color || 'text-gray-400';
  };

  // WebSocket connection
  useEffect(() => {
    if (!isRecording || !sessionId) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnectionStatus('idle');
      return;
    }

    setConnectionStatus('connecting');
    
    // Use proxy path for WebSocket
    const wsUrl = `/ws/transcription/${sessionId}`;
    console.log('Connecting to transcription WebSocket:', wsUrl);
    
    try {
      // Create WebSocket with absolute URL
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = '9050'; // Backend port
      const fullWsUrl = `${protocol}//${host}:${port}${wsUrl}`;
      
      const ws = new WebSocket(fullWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('Transcription WebSocket connected');
        setConnectionStatus('connected');
        
        // Send initial configuration
        ws.send(JSON.stringify({
          type: 'config',
          session_id: sessionId
        }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'status' && data.npu_status) {
            setNpuActive(data.npu_status.npu_available);
          }
          
          if (data.type === 'transcription' && data.segment) {
            const segment = data.segment;
            
            // Add segment to list
            setSegments(prev => {
              // If it's a partial segment, replace the last partial
              if (segment.is_partial && prev.length > 0 && prev[prev.length - 1].is_partial) {
                return [...prev.slice(0, -1), segment];
              }
              return [...prev, segment];
            });
            
            // Update speaker stats
            if (segment.speaker && !segment.is_partial) {
              setSpeakers(prev => {
                const newSpeakers = new Map(prev);
                const current = newSpeakers.get(segment.speaker) || { color: '', duration: 0 };
                current.duration += (segment.end - segment.start);
                newSpeakers.set(segment.speaker, current);
                return newSpeakers;
              });
            }
            
            // Callback
            if (onSegmentReceived && !segment.is_partial) {
              onSegmentReceived(segment);
            }
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus('error');
      };

      ws.onclose = () => {
        console.log('WebSocket closed');
        setConnectionStatus('idle');
        wsRef.current = null;
      };

    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      setConnectionStatus('error');
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [isRecording, sessionId, onSegmentReceived]);

  // Auto-scroll to bottom
  useEffect(() => {
    segmentsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [segments]);

  // Mock data for testing when not recording
  useEffect(() => {
    if (!isRecording && segments.length === 0) {
      // Add some example segments
      setSegments([
        {
          start: 0,
          end: 5.2,
          text: "Welcome to the Meeting-Ops transcription viewer.",
          speaker: "SPEAKER_01",
          confidence: 0.98
        },
        {
          start: 5.5,
          end: 10.3,
          text: "This shows real-time transcription with speaker diarization.",
          speaker: "SPEAKER_01",
          confidence: 0.97
        },
        {
          start: 10.8,
          end: 15.5,
          text: "The NPU acceleration provides 200x speedup for transcription.",
          speaker: "SPEAKER_02",
          confidence: 0.96
        }
      ]);
    }
  }, [isRecording, segments.length]);

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-lg">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-white">Live Transcription</h3>
          <div className="flex items-center gap-3">
            {/* NPU Status */}
            {npuActive && (
              <div className="flex items-center gap-1 text-xs text-green-400">
                <Zap className="w-3 h-3" />
                <span>NPU Active</span>
              </div>
            )}
            
            {/* Connection Status */}
            <div className="flex items-center gap-1">
              {connectionStatus === 'connected' ? (
                <>
                  <Wifi className="w-4 h-4 text-green-400" />
                  <span className="text-xs text-green-400">Connected</span>
                </>
              ) : connectionStatus === 'connecting' ? (
                <>
                  <Wifi className="w-4 h-4 text-yellow-400 animate-pulse" />
                  <span className="text-xs text-yellow-400">Connecting...</span>
                </>
              ) : connectionStatus === 'error' ? (
                <>
                  <WifiOff className="w-4 h-4 text-red-400" />
                  <span className="text-xs text-red-400">Disconnected</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-4 h-4 text-gray-500" />
                  <span className="text-xs text-gray-500">Idle</span>
                </>
              )}
            </div>
          </div>
        </div>
        
        {/* Speaker Stats */}
        {speakers.size > 0 && (
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1 text-gray-400">
              <Users className="w-3 h-3" />
              <span>{speakers.size} speakers</span>
            </div>
            {Array.from(speakers.entries()).map(([speaker, info]) => (
              <div key={speaker} className={`flex items-center gap-1 ${info.color}`}>
                <User className="w-3 h-3" />
                <span>{speaker.replace('SPEAKER_', 'S')}</span>
                <span className="text-gray-500">({formatTime(info.duration)})</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Transcription Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {segments.length === 0 ? (
          <div className="text-center py-8">
            <Mic className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500">Waiting for transcription...</p>
            {isRecording && (
              <p className="text-xs text-gray-600 mt-2">
                Speaking will appear here in real-time
              </p>
            )}
          </div>
        ) : (
          segments.map((segment, index) => (
            <div 
              key={index} 
              className={`flex gap-3 ${segment.is_partial ? 'opacity-60' : ''}`}
            >
              {/* Timestamp */}
              <div className="flex-shrink-0 w-16 text-xs text-gray-500 pt-1">
                {formatTime(segment.start)}
              </div>
              
              {/* Speaker & Text */}
              <div className="flex-1">
                <div className={`text-xs ${getSpeakerColor(segment.speaker)} mb-1`}>
                  {segment.speaker.replace('SPEAKER_', 'Speaker ')}
                  {segment.confidence && (
                    <span className="text-gray-600 ml-2">
                      ({Math.round(segment.confidence * 100)}%)
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-300">
                  {segment.text}
                  {segment.is_partial && (
                    <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-1" />
                  )}
                </div>
                
                {/* Word-level details (collapsed by default) */}
                {segment.words && segment.words.length > 0 && (
                  <details className="mt-1">
                    <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                      Word timings
                    </summary>
                    <div className="mt-1 text-xs text-gray-600 space-x-2">
                      {segment.words.map((word, i) => (
                        <span key={i} title={`${formatTime(word.start)} - ${formatTime(word.end)}`}>
                          {word.word}
                        </span>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={segmentsEndRef} />
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700 text-xs text-gray-500">
        <div className="flex items-center justify-between">
          <span>{segments.length} segments</span>
          <span>
            {segments.length > 0 && 
              `Duration: ${formatTime(segments[segments.length - 1]?.end || 0)}`
            }
          </span>
        </div>
      </div>
    </div>
  );
};