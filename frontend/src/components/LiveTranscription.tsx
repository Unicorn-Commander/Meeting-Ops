import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Volume2, Zap, Loader2, User } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  text: string;
  speaker?: string;
  timestamp: string;
  confidence: number;
  isComplete: boolean;
}

interface LiveTranscriptionProps {
  sessionId?: string;
  isRecording?: boolean;
  className?: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const LiveTranscription: React.FC<LiveTranscriptionProps> = ({ 
  sessionId, 
  isRecording = false,
  className = ''
}) => {
  const [transcriptions, setTranscriptions] = useState<TranscriptionSegment[]>([]);
  const [currentSegment, setCurrentSegment] = useState<string>('');
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeModel, setActiveModel] = useState<string>('NPU-Accelerated Whisper');
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sessionId || !isRecording) {
      // Clear transcriptions when not recording
      if (!isRecording) {
        setTranscriptions([]);
        setCurrentSegment('');
      }
      return;
    }

    // Connect to transcription WebSocket for this session
    const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/ws/transcription/${sessionId}`;
    console.log('[LiveTranscription] Connecting to WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[LiveTranscription] WebSocket connected');
      setIsConnected(true);
      
      // Send ping to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
      
      // Store interval for cleanup
      (ws as any).pingInterval = pingInterval;
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('[LiveTranscription] Received:', data);

      if (data.type === 'transcription' && data.segment) {
        // Handle transcription segment from our backend
        handleTranscriptionData(data.segment);
        setIsProcessing(false);
      } else if (data.type === 'status') {
        console.log('[LiveTranscription] Status:', data.message);
        if (data.npu_status) {
          setActiveModel('NPU-Accelerated Whisper');
        }
      } else if (data.type === 'keepalive' || data.type === 'pong') {
        // Keep-alive messages
      }
    };

    ws.onerror = (error) => {
      console.error('[LiveTranscription] WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('[LiveTranscription] WebSocket disconnected');
      setIsConnected(false);
      setIsProcessing(false);
    };

    return () => {
      // Clear ping interval if exists
      const wsWithInterval = ws as any;
      if (wsWithInterval.pingInterval) {
        clearInterval(wsWithInterval.pingInterval);
      }
      
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [sessionId, isRecording]);

  const handleTranscriptionData = (data: any) => {
    const newSegment: TranscriptionSegment = {
      id: data.id || `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      text: data.text || '',
      speaker: data.speaker_id || data.speaker || null,  // Can be null for live (no diarization)
      timestamp: data.timestamp || new Date().toISOString(),
      confidence: data.confidence || 0,
      isComplete: true
    };

    setTranscriptions(prev => [...prev, newSegment]);
    setCurrentSegment('');
    setIsProcessing(false);

    // Only auto-scroll if user is near bottom (text editor behavior)
    setTimeout(() => {
      const container = document.querySelector('.transcription-container');
      if (container) {
        const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;
        if (isNearBottom) {
          transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
      }
    }, 100);
  };

  const getSpeakerColor = (speaker?: string) => {
    if (!speaker) return 'text-gray-400';
    const colors = [
      'text-blue-400',
      'text-green-400',
      'text-purple-400',
      'text-orange-400',
      'text-pink-400',
      'text-indigo-400'
    ];
    const index = parseInt(speaker.replace(/\D/g, '')) % colors.length;
    return colors[index];
  };

  // Group consecutive transcriptions by speaker for conversational display
  const groupTranscriptionsBySpeaker = (segments: TranscriptionSegment[]) => {
    const groups: Array<{
      speaker: string | undefined;
      segments: TranscriptionSegment[];
      startTime: string;
      endTime: string;
    }> = [];

    segments.forEach((segment) => {
      const lastGroup = groups[groups.length - 1];
      
      if (lastGroup && lastGroup.speaker === segment.speaker) {
        // Add to existing speaker group
        lastGroup.segments.push(segment);
        lastGroup.endTime = segment.timestamp;
      } else {
        // Create new speaker group
        groups.push({
          speaker: segment.speaker,
          segments: [segment],
          startTime: segment.timestamp,
          endTime: segment.timestamp
        });
      }
    });

    return groups;
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-800 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold flex items-center gap-2 text-white">
            <Volume2 className="w-5 h-5" />
            Live Transcription
          </h2>
          
          <div className="flex items-center gap-3">
            <span className="text-sm flex items-center gap-1">
              <Zap className="w-3 h-3 text-purple-400 animate-pulse" />
              <span className="text-purple-400 font-medium">NPU Active</span>
              <span className="text-gray-500 text-xs ml-1">(16 TOPS)</span>
            </span>
            
            <div className="flex items-center gap-2">
              {isConnected ? (
                <span className="flex items-center gap-1 text-green-600">
                  <Mic className="w-4 h-4" />
                  <span className="text-sm">Connected</span>
                </span>
              ) : (
                <span className="flex items-center gap-1 text-gray-400">
                  <MicOff className="w-4 h-4" />
                  <span className="text-sm">Disconnected</span>
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Transcription Display */}
      <div className="transcription-container p-4 max-h-96 overflow-y-auto scroll-smooth">
        {!isRecording ? (
          <div className="text-center py-12 text-gray-500">
            <MicOff className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>Start recording to see live transcription</p>
          </div>
        ) : transcriptions.length === 0 && !currentSegment ? (
          <div className="text-center py-12 text-gray-400">
            <Loader2 className="w-8 h-8 mx-auto mb-4 animate-spin text-gray-500" />
            <p className="text-gray-300">Waiting for speech...</p>
            <p className="text-sm text-gray-500 mt-2">Speak into the microphone</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Grouped transcriptions by speaker */}
            {groupTranscriptionsBySpeaker(transcriptions).map((group, groupIndex) => (
              <div 
                key={`group-${groupIndex}`}
                className="bg-gray-800/30 rounded-lg p-4 border-l-4 transition-all hover:bg-gray-800/40"
                style={{ borderColor: group.speaker ? getSpeakerColor(group.speaker).replace('text-', '#').replace('-400', '') : '#6b7280' }}
              >
                {/* Speaker header */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {group.speaker ? (
                      <span className={`flex items-center gap-2 font-semibold ${getSpeakerColor(group.speaker)}`}>
                        <User className="w-4 h-4" />
                        {group.speaker}
                      </span>
                    ) : (
                      <span className="flex items-center gap-2 font-medium text-gray-400">
                        <User className="w-4 h-4" />
                        Unknown Speaker
                      </span>
                    )}
                    <span className="text-xs text-gray-500">
                      {formatTime(group.startTime)}
                      {group.startTime !== group.endTime && ` - ${formatTime(group.endTime)}`}
                    </span>
                  </div>
                  {group.segments.length > 1 && (
                    <span className="text-xs text-gray-500">
                      {group.segments.length} segments
                    </span>
                  )}
                </div>
                
                {/* Conversational text */}
                <div className="text-gray-200 leading-relaxed space-y-2">
                  {group.segments.map((segment, index) => (
                    <p key={segment.id} className="inline">
                      {segment.text}
                      {index < group.segments.length - 1 && ' '}
                    </p>
                  ))}
                </div>
                
                {/* Average confidence if available */}
                {group.segments.some(s => s.confidence > 0) && (
                  <div className="mt-2 text-xs text-gray-500">
                    Confidence: {Math.round(
                      group.segments.reduce((acc, s) => acc + s.confidence, 0) / group.segments.length * 100
                    )}%
                  </div>
                )}
              </div>
            ))}

            {/* Current segment being processed */}
            {currentSegment && (
              <div className="border-l-2 border-blue-400 pl-4 animate-pulse">
                <div className="flex items-center gap-2 mb-1">
                  <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
                  <span className="text-xs text-blue-500">Processing...</span>
                </div>
                <p className="text-gray-600 italic">{currentSegment}</p>
              </div>
            )}

            {/* Scroll anchor */}
            <div ref={transcriptEndRef} />
          </div>
        )}
      </div>

      {/* Footer with stats */}
      {isRecording && transcriptions.length > 0 && (
        <div className="p-3 border-t bg-gray-50 text-sm text-gray-600">
          <div className="flex items-center justify-between">
            <span>{transcriptions.length} segments transcribed</span>
            <span>{transcriptions.reduce((acc, seg) => acc + seg.text.split(' ').length, 0)} words</span>
          </div>
        </div>
      )}
    </div>
  );
};