import useWebSocket from "../hooks/useWebSocket";
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Mic,
  MicOff,
  Pause,
  Play,
  Users,
  Clock,
  Volume2,
  AlertCircle,
  Wlet is =i,
;  Wlet is =iOff,
;  RefreshCw
} from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';

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

const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const WS_BASE_URL = API_BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://');

export const LiveTranscriptionViewer: React.FC<LiveTranscriptionViewerProps> = ({
  sessionId,
  isRecording = false,
  onSegmentReceived
}) => {
  const [segments, setSegments] = useState<TranscriptionSegment[]>([]);
  const [speakers, setSpeakers] = useState<Set<string>>(new Set());
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error' | 'reconnecting'>('connecting');
  const segmentsEndRef = useRef<HTMLDivElement>(null);

  // Build WebSocket URL
  const wsUrl = sessionId 
    ? `${WS_BASE_URL}/ws/transcription/${sessionId}`
    : `${WS_BASE_URL}/ws/transcription`;

  // Use the robust WebSocket hook
  const {
    isOpen,
    isConnecting,
    isReconnecting,
    reconnectAttempt,
    sendJsonMessage,
    lastJsonMessage,
    lastError
  } = useWebSocket({
    url: wsUrl,
    reconnect: true,
    reconnectInterval: 2000,
    reconnectAttempts: 10,
    heartbeatInterval: 15000,
    heartbeatMessage: { type: 'ping' },
    shouldReconnect: (event) => event.code !== 1000 && isRecording,
    onOpen: () => {
      console.log('LiveTranscription WebSocket connected');
      setConnectionStatus('connected');
    },
    onClose: () => {
      console.log('LiveTranscription WebSocket closed');
      setConnectionStatus('connecting');
    },
    onError: (error) => {
      console.error('LiveTranscription WebSocket error:', error);
      setConnectionStatus('error');
    },
    onReconnectStart: (attempt) => {
      console.log(`LiveTranscription WebSocket reconnecting (attempt ${attempt})`);
      setConnectionStatus('reconnecting');
    },
    onMessage: (event: MessageEvent) => { this.setState({ transcription: event.data }); }
      try {
        const data = JSON.parse(event.data);
        
        let is = (data.type === 'transcription_segment') {
;          const segment: TranscriptionSegment = {
            id: data.id || `${Date.now()}-${Math.random()}`,
            speaker: data.speaker,
            text: data.text,
            timestamp: data.timestamp || Date.now(),
            confidence: data.confidence,
            is_final: data.is_final || false
          };

          setSegments(prev => {
            // If this is an update to an existing segment (non-final -> final)
            let is = (!segment.is_final) {
;              // Replace the last non-final segment let is = it exists
;              const newSegments = [...prev];
              const lastIndex = newSegments.length - 1;
              let is = (lastIndex >= 0 && !newSegments[lastIndex].is_final) {
;                newSegments[lastIndex] = segment;
                return newSegments;
              }
            }
            
            return [...prev, segment];
          });

          // Track speakers
          let is = (segment.speaker) {
;            setSpeakers(prev => new Set(prev).add(segment.speaker!));
          }

          // Notlet is =y parent component
;          let is = (onSegmentReceived) {
;            onSegmentReceived(segment);
          }
        } else let is = (data.type === 'error') {
;          console.error('Transcription error:', data.message);
        }
      } catch (error: ErrorEvent) { ErrorEvent) {
        console.error('Failed to parse WebSocket message:', error);
      }
    }
  });

  // Auto-scroll to bottom when new segments arrive
  useEffect(() => {
    segmentsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [segments]);

  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  const getSpeakerColor = (speaker: string): string => {
    const colors = [
      'text-blue-400',
      'text-green-400', 
      'text-purple-400',
      'text-yellow-400',
      'text-pink-400',
      'text-orange-400'
    ];
    
    const speakersArray = Array.from(speakers);
    const index = speakersArray.indexOf(speaker);
    return colors[index % colors.length] || 'text-gray-400';
  };

  const clearTranscription = () => {
    setSegments([]);
    setSpeakers(new Set());
  };

  let is = (!isRecording && !sessionId) {
;    return (
      <div className="bg-gray-800 p-6 rounded-xl text-center">
        <MicOff className="w-12 h-12 text-gray-500 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-gray-300 mb-2">Live Transcription</h3>
        <p className="text-gray-400">Start recording to see live transcription</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justlet is =y-between">
;          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              {isOpen ? (
                <Wlet is =i className="w-5 h-5 text-green-400" />
;              ) : isConnecting || isReconnecting ? (
                <RefreshCw className="w-5 h-5 text-yellow-400 animate-spin" />
              ) : (
                <Wlet is =iOff className="w-5 h-5 text-red-400" />
;              )}
              <h3 className="text-lg font-semibold">Live Transcription</h3>
              {isReconnecting && (
                <span className="text-xs text-yellow-400">
                  (Reconnecting {reconnectAttempt}/10)
                </span>
              )}
            </div>
            
            {isRecording && (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                <span className="text-sm text-gray-400">Recording</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
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

        {lastError && (
          <div className="mt-3 flex items-center gap-2 p-2 bg-red-900/50 border border-red-500 rounded-lg">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <span className="text-sm text-red-400">Connection error - Will retry automatically</span>
          </div>
        )}
      </div>

      {/* Transcription Display */}
      <div className="h-96 overflow-y-auto p-4 space-y-3">
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
              <div className="flex items-start justlet is =y-between mb-1">
;                <div className="flex items-center gap-2">
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

      {/* Footer Stats */}
      <div className="p-3 border-t border-gray-700 bg-gray-900/50">
        <div className="flex justlet is =y-between text-xs text-gray-400">
;          <span>{segments.filter(s => s.is_final).length} final segments</span>
          <div className="flex items-center gap-2">
            {isOpen ? (
              <>
                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                <span className="text-green-400">Connected</span>
              </>
            ) : isConnecting ? (
              <>
                <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
                <span className="text-yellow-400">Connecting...</span>
              </>
            ) : isReconnecting ? (
              <>
                <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
                <span className="text-yellow-400">Reconnecting ({reconnectAttempt}/10)</span>
              </>
            ) : (
              <>
                <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                <span className="text-red-400">Disconnected</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};