import React, { useState, useEffect, useRef } from 'react';
import { Mic, User, Clock, Zap, Brain, AlertCircle } from 'lucide-react';
import { Tooltip } from './Tooltip';

interface TranscriptionSegment {
  id: string;
  text: string;
  speaker_id?: string;
  speaker_name?: string;
  timestamp: string;
  confidence: number;
  processing_time?: number;
  npu_accelerated?: boolean;
}

interface LiveTranscriptionFeedProps {
  sessionId: string | null;
  isActive: boolean;
}

export const LiveTranscriptionFeed: React.FC<LiveTranscriptionFeedProps> = ({ sessionId, isActive }) => {
  const [transcriptions, setTranscriptions] = useState<TranscriptionSegment[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [speakers, setSpeakers] = useState<Map<string, string>>(new Map());
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptionEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sessionId && isActive) {
      connectWebSocket();
    } else {
      disconnectWebSocket();
    }

    return () => {
      disconnectWebSocket();
    };
  }, [sessionId, isActive]);

  useEffect(() => {
    // Auto-scroll to bottom when new transcriptions arrive
    transcriptionEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcriptions]);

  const connectWebSocket = () => {
    const token = localStorage.getItem('access_token');
    if (!token || !sessionId) return;

    const wsUrl = `ws://localhost:9050/ws/stream/${sessionId}?token=${token}`;
    
    try {
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('WebSocket connected for live transcription');
        setIsConnected(true);
        setConnectionError(null);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'transcription') {
            const newSegment: TranscriptionSegment = {
              id: `${Date.now()}-${Math.random()}`,
              text: data.text,
              speaker_id: data.speaker_id,
              speaker_name: data.speaker_name,
              timestamp: data.timestamp || new Date().toISOString(),
              confidence: data.confidence || 0.95,
              processing_time: data.processing_time,
              npu_accelerated: data.npu_accelerated
            };

            setTranscriptions(prev => [...prev, newSegment]);

            // Update speaker mapping
            if (data.speaker_id && data.speaker_name) {
              setSpeakers(prev => new Map(prev).set(data.speaker_id, data.speaker_name));
            }
          } else if (data.type === 'speaker_update') {
            // Handle speaker identification updates
            if (data.speakers) {
              const newSpeakers = new Map(speakers);
              data.speakers.forEach((speaker: any) => {
                newSpeakers.set(speaker.id, speaker.name);
              });
              setSpeakers(newSpeakers);
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('Connection error. Please check your network.');
      };

      wsRef.current.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
      };
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      setConnectionError('Failed to connect to transcription service.');
    }
  };

  const disconnectWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  };

  const getSpeakerColor = (speakerId: string): string => {
    const colors = [
      'border-blue-500',
      'border-green-500',
      'border-purple-500',
      'border-yellow-500',
      'border-pink-500',
      'border-indigo-500'
    ];
    
    // Generate consistent color based on speaker ID
    const index = speakerId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[index % colors.length];
  };

  const formatTime = (timestamp: string): string => {
    return new Date(timestamp).toLocaleTimeString();
  };

  if (!isActive) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4 text-yellow-400 flex items-center gap-2">
          <Mic className="h-5 w-5" />
          Live Transcription Feed
        </h3>
        <div className="bg-gray-900 rounded-lg p-8 text-center">
          <div className="w-16 h-16 bg-gray-700 rounded-full mx-auto mb-4 flex items-center justify-center">
            <Mic className="h-8 w-8 text-gray-500" />
          </div>
          <p className="text-gray-400">Start a recording session to see live transcription</p>
          <p className="text-sm text-gray-500 mt-2">Transcriptions will appear here in real-time</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-yellow-400 flex items-center gap-2">
          <Mic className="h-5 w-5" />
          Live Transcription Feed
        </h3>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <Tooltip content="Connected to transcription service">
              <div className="flex items-center gap-2 text-green-400 text-sm">
                <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                <span>Live</span>
              </div>
            </Tooltip>
          ) : (
            <Tooltip content="Connecting to transcription service...">
              <div className="flex items-center gap-2 text-yellow-400 text-sm">
                <div className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />
                <span>Connecting...</span>
              </div>
            </Tooltip>
          )}
        </div>
      </div>

      {connectionError && (
        <div className="mb-4 p-3 bg-red-900/20 border border-red-700 rounded-lg flex items-center gap-2 text-sm">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <span className="text-red-300">{connectionError}</span>
        </div>
      )}

      <div className="bg-gray-900 rounded-lg p-4 h-96 overflow-y-auto">
        {transcriptions.length === 0 ? (
          <div className="text-center py-16">
            <div className="animate-pulse">
              <div className="w-12 h-12 bg-purple-500 rounded-full mx-auto mb-4 flex items-center justify-center">
                <Mic className="h-6 w-6 text-white animate-pulse" />
              </div>
              <p className="text-gray-400">Listening for speech...</p>
              <p className="text-sm text-gray-500 mt-2">Speak into your microphone to begin</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {transcriptions.map((segment) => (
              <div
                key={segment.id}
                className={`border-l-4 ${getSpeakerColor(segment.speaker_id || 'unknown')} pl-4 py-3 hover:bg-gray-800/50 transition-colors rounded-r`}
              >
                <div className="flex items-start justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <User className="h-4 w-4 text-gray-400" />
                    <span className="text-sm font-medium text-gray-300">
                      {segment.speaker_name || speakers.get(segment.speaker_id || '') || `Speaker ${segment.speaker_id?.slice(-4) || 'Unknown'}`}
                    </span>
                    <span className="text-xs text-gray-500">
                      {formatTime(segment.timestamp)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {segment.npu_accelerated && (
                      <Tooltip content="NPU accelerated processing">
                        <div className="flex items-center gap-1 bg-green-900/30 text-green-400 text-xs px-2 py-1 rounded">
                          <Zap className="h-3 w-3" />
                          NPU
                        </div>
                      </Tooltip>
                    )}
                    {segment.processing_time && (
                      <Tooltip content={`Processed in ${(segment.processing_time * 1000).toFixed(0)}ms`}>
                        <span className="text-xs text-gray-500">
                          {(segment.processing_time * 1000).toFixed(0)}ms
                        </span>
                      </Tooltip>
                    )}
                    <Tooltip content={`Confidence: ${(segment.confidence * 100).toFixed(0)}%`}>
                      <div className={`text-xs px-2 py-1 rounded ${
                        segment.confidence > 0.9 
                          ? 'bg-green-900/30 text-green-400' 
                          : segment.confidence > 0.7 
                          ? 'bg-yellow-900/30 text-yellow-400'
                          : 'bg-red-900/30 text-red-400'
                      }`}>
                        {(segment.confidence * 100).toFixed(0)}%
                      </div>
                    </Tooltip>
                  </div>
                </div>
                <p className="text-white">{segment.text}</p>
              </div>
            ))}
            <div ref={transcriptionEndRef} />
          </div>
        )}
      </div>

      {transcriptions.length > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
          <span>{transcriptions.length} segments transcribed</span>
          <button
            onClick={() => setTranscriptions([])}
            className="text-gray-400 hover:text-white transition-colors"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
};