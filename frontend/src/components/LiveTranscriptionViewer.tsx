import React, { useState, useEffect, useRef } from 'react';
import { Mic, Users, Clock, AlertCircle, Wifi, WifiOff } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  speaker?: string;
  text: string;
  timestamp: number;
  confidence?: number;
  is_final: boolean;
}

interface LiveTranscriptionViewerProps {
  sessionId?: string;
  isRecording?: boolean;
  onSegmentReceived?: (segment: TranscriptionSegment) => void;
}

export const LiveTranscriptionViewer: React.FC<LiveTranscriptionViewerProps> = ({
  sessionId,
  isRecording = false,
  onSegmentReceived
}) => {
  const [segments, setSegments] = useState<TranscriptionSegment[]>([]);
  const [speakers, setSpeakers] = useState<Set<string>>(new Set());
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error'>('connecting');
  const segmentsEndRef = useRef<HTMLDivElement>(null);

  // Simplified WebSocket connection
  useEffect(() => {
    if (!isRecording) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = sessionId 
      ? `${protocol}//${host}/ws/transcription/${sessionId}`
      : `${protocol}//${host}/ws/transcription`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnectionStatus('connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'transcription_segment') {
          const segment: TranscriptionSegment = {
            id: data.id || `${Date.now()}-${Math.random()}`,
            speaker: data.speaker,
            text: data.text,
            timestamp: data.timestamp || Date.now(),
            confidence: data.confidence,
            is_final: data.is_final || false
          };

          setSegments(prev => [...prev, segment]);

          if (segment.speaker) {
            setSpeakers(prev => new Set(prev).add(segment.speaker!));
          }

          if (onSegmentReceived) {
            onSegmentReceived(segment);
          }
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnectionStatus('error');
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
      setConnectionStatus('connecting');
    };

    return () => {
      ws.close();
    };
  }, [isRecording, sessionId, onSegmentReceived]);

  // Auto-scroll to bottom
  useEffect(() => {
    segmentsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [segments]);

  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  const getSpeakerColor = (speaker: string): string => {
    const colors = ['text-blue-400', 'text-green-400', 'text-purple-400', 'text-yellow-400'];
    const index = speaker.charCodeAt(0) % colors.length;
    return colors[index];
  };

  const clearTranscription = () => {
    setSegments([]);
    setSpeakers(new Set());
  };

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {connectionStatus === 'connected' ? (
              <Wifi className="w-5 h-5 text-green-400" />
            ) : connectionStatus === 'error' ? (
              <WifiOff className="w-5 h-5 text-red-400" />
            ) : (
              <Wifi className="w-5 h-5 text-yellow-400 animate-pulse" />
            )}
            <h3 className="text-lg font-semibold">Live Transcription</h3>
          </div>
          {isRecording && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
              <span className="text-sm text-gray-400">Recording</span>
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          {speakers.size > 0 && (
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-gray-400" />
              <span className="text-sm text-gray-400">{speakers.size} speakers</span>
            </div>
          )}
          <button
            onClick={clearTranscription}
            className="text-sm px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Transcription Display */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {segments.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            <Mic className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>Waiting for speech...</p>
          </div>
        ) : (
          segments.map((segment) => (
            <div
              key={segment.id}
              className={`p-3 rounded-lg ${
                segment.is_final ? 'bg-gray-700' : 'bg-gray-600 opacity-75'
              }`}
            >
              <div className="flex items-start justify-between mb-1">
                <div className="flex items-center gap-2">
                  {segment.speaker && (
                    <span className={`text-sm font-medium ${getSpeakerColor(segment.speaker)}`}>
                      {segment.speaker}
                    </span>
                  )}
                  {!segment.is_final && (
                    <span className="text-xs px-2 py-1 bg-yellow-600 text-yellow-100 rounded-full">
                      Interim
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  {segment.confidence && (
                    <span>{(segment.confidence * 100).toFixed(0)}%</span>
                  )}
                  <Clock className="w-3 h-3" />
                  <span>{formatTimestamp(segment.timestamp)}</span>
                </div>
              </div>
              <p className="text-white leading-relaxed">{segment.text}</p>
            </div>
          ))
        )}
        <div ref={segmentsEndRef} />
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700 bg-gray-900/50">
        <div className="flex justify-between text-xs text-gray-400">
          <span>{segments.filter(s => s.is_final).length} final segments</span>
          <div className="flex items-center gap-2">
            {connectionStatus === 'connected' ? (
              <>
                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                <span className="text-green-400">Connected</span>
              </>
            ) : connectionStatus === 'error' ? (
              <>
                <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                <span className="text-red-400">Error</span>
              </>
            ) : (
              <>
                <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
                <span className="text-yellow-400">Connecting...</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};