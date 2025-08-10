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
      id: data.id || Date.now().toString(),
      text: data.text || '',
      speaker: data.speaker_id || data.speaker,
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
    if (!speaker) return 'text-gray-600';
    const colors = [
      'text-blue-600',
      'text-green-600',
      'text-purple-600',
      'text-orange-600',
      'text-pink-600',
      'text-indigo-600'
    ];
    const index = parseInt(speaker.replace(/\D/g, '')) % colors.length;
    return colors[index];
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
          <div className="space-y-4">
            {/* Completed transcriptions */}
            {transcriptions.map((segment) => (
              <div 
                key={segment.id}
                className="border-l-2 border-gray-200 pl-4 hover:border-blue-400 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {segment.speaker && (
                        <span className={`flex items-center gap-1 text-sm font-medium ${getSpeakerColor(segment.speaker)}`}>
                          <User className="w-3 h-3" />
                          {segment.speaker}
                        </span>
                      )}
                      <span className="text-xs text-gray-500">
                        {formatTime(segment.timestamp)}
                      </span>
                      {segment.confidence > 0 && (
                        <span className="text-xs text-gray-400">
                          {Math.round(segment.confidence * 100)}%
                        </span>
                      )}
                    </div>
                    <p className="text-gray-800">{segment.text}</p>
                  </div>
                </div>
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