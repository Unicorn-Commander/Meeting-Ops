import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Volume2, Zap, User, Play, Square, Circle } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  text: string;
  speaker?: string;
  timestamp: string;
  confidence: number;
  isComplete: boolean;
  isRecorded?: boolean; // Track if this was during an active recording
}

interface AlwaysOnTranscriptionProps {
  className?: string;
  maxBufferMinutes?: number; // How many minutes to keep in rolling buffer
  userRole?: 'admin' | 'user' | 'superuser'; // User role determines buffer behavior
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const AlwaysOnTranscription: React.FC<AlwaysOnTranscriptionProps> = ({ 
  className = '',
  maxBufferMinutes: propMaxBufferMinutes,
  userRole = 'user' // Default to user role
}) => {
  // Load buffer settings from localStorage
  const [maxBufferMinutes, setMaxBufferMinutes] = useState(propMaxBufferMinutes || 10);
  
  useEffect(() => {
    const storedSettings = localStorage.getItem('transcription_settings');
    if (storedSettings) {
      try {
        const settings = JSON.parse(storedSettings);
        if (settings.bufferMinutes) {
          setMaxBufferMinutes(settings.bufferMinutes);
        }
      } catch (e) {
        console.error('Failed to load transcription settings:', e);
      }
    }
  }, []);
  const [transcriptions, setTranscriptions] = useState<TranscriptionSegment[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const alwaysOnSessionRef = useRef<string>(`always_on_${Date.now()}`);
  const [currentSegment, setCurrentSegment] = useState<string>('');
  const [activeModel, setActiveModel] = useState<string>('');
  
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const bufferCleanupRef = useRef<NodeJS.Timeout | undefined>(undefined);

  // Start always-on listening
  const startListening = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;

      // Connect to working transcription WebSocket endpoint with session ID in path
      // Create a temporary session ID for always-on listening
      const sessionId = alwaysOnSessionRef.current;
      const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/ws/transcription/${sessionId}`;
      console.log('[AlwaysOnTranscription] Connecting to:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[AlwaysOnTranscription] WebSocket connected to session:', sessionId);
        setIsConnected(true);
        setIsListening(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[AlwaysOnTranscription] Received message:', data);
          
          if (data.type === 'transcription') {
            console.log('[AlwaysOnTranscription] Got transcription:', data.data);
            handleTranscriptionData(data.data, false); // Not recorded by default
          } else if (data.type === 'partial') {
            console.log('[AlwaysOnTranscription] Got partial:', data.text);
            setCurrentSegment(data.text || '');
          } else if (data.type === 'status') {
            console.log('[AlwaysOnTranscription] Got status:', data);
            if (data.model) {
              setActiveModel(data.model);
            }
          } else if (data.type === 'recording_started') {
            setIsRecording(true);
            setActiveSession(data.session_id);
          } else if (data.type === 'recording_stopped') {
            setIsRecording(false);
            setActiveSession(null);
            // Mark recent segments as recorded
            markRecentAsRecorded();
          } else if (data.type === 'error') {
            console.error('[AlwaysOnTranscription] WebSocket error:', data.message);
          }
        } catch (err) {
          console.error('[AlwaysOnTranscription] Failed to parse message:', err, event.data);
        }
      };

      ws.onerror = (error) => {
        console.error('[AlwaysOnTranscription] WebSocket error:', error);
        setIsConnected(false);
        setIsListening(false);
      };

      ws.onclose = () => {
        console.log('[AlwaysOnTranscription] WebSocket closed');
        setIsConnected(false);
        setIsListening(false);
      };

    } catch (error) {
      console.error('[AlwaysOnTranscription] Failed to start listening:', error);
    }
  }, []);

  // Stop listening
  const stopListening = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsListening(false);
    setCurrentSegment('');
  }, []);

  // Handle new transcription data
  const handleTranscriptionData = (data: any, isFromRecording: boolean) => {
    const newSegment: TranscriptionSegment = {
      id: data.id || Date.now().toString(),
      text: data.text || '',
      speaker: data.speaker_id || data.speaker,
      timestamp: data.timestamp || new Date().toISOString(),
      confidence: data.confidence || 0,
      isComplete: true,
      isRecorded: isFromRecording || isRecording
    };

    // Role-based filtering: Regular users only see transcriptions during recording
    if (userRole === 'user' && !isRecording && !newSegment.isRecorded) {
      return; // Don't show transcription to regular users unless recording
    }

    setTranscriptions(prev => {
      const updated = [...prev, newSegment];
      
      // Admin users get rolling buffer, regular users only get recorded content
      if (userRole === 'admin' || userRole === 'superuser') {
        // Clean old segments beyond buffer time for admins
        const cutoffTime = Date.now() - (maxBufferMinutes * 60 * 1000);
        return updated.filter(seg => new Date(seg.timestamp).getTime() > cutoffTime);
      } else {
        // Regular users: only keep recorded segments
        return updated.filter(seg => seg.isRecorded);
      }
    });
    
    setCurrentSegment('');

    // Auto-scroll if user is at bottom
    if (autoScroll && scrollContainerRef.current) {
      setTimeout(() => {
        transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  };

  // Mark recent segments as recorded when recording stops
  const markRecentAsRecorded = () => {
    const recordingStartTime = Date.now() - 60000; // Last minute as example
    setTranscriptions(prev => 
      prev.map(seg => ({
        ...seg,
        isRecorded: seg.isRecorded || new Date(seg.timestamp).getTime() > recordingStartTime
      }))
    );
  };

  // Start/Stop recording session
  const toggleRecording = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    try {
      if (isRecording) {
        // Stop recording
        const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${activeSession}/stop`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          setIsRecording(false);
          setActiveSession(null);
        }
      } else {
        // Start recording
        const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            title: `Recording ${new Date().toLocaleString()}`,
            is_realtime: true
          })
        });
        
        if (response.ok) {
          const session = await response.json();
          
          // Start the session
          const startResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${session.id}/start`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          });
          
          if (startResponse.ok) {
            setIsRecording(true);
            setActiveSession(session.id);
          }
        }
      }
    } catch (error) {
      console.error('[AlwaysOnTranscription] Recording toggle error:', error);
    }
  };

  // Handle scroll events
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const container = e.currentTarget;
    const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;
    setAutoScroll(isNearBottom);
  };

  // Auto-start listening on mount for admin users
  useEffect(() => {
    // Only auto-start for admin/superuser roles
    if (userRole === 'admin' || userRole === 'superuser') {
      startListening();
    }
    return () => {
      if (bufferCleanupRef.current) {
        clearInterval(bufferCleanupRef.current);
      }
      stopListening();
    };
  }, [userRole, startListening, stopListening]);

  // Periodic buffer cleanup
  useEffect(() => {
    bufferCleanupRef.current = setInterval(() => {
      const cutoffTime = Date.now() - (maxBufferMinutes * 60 * 1000);
      setTranscriptions(prev => 
        prev.filter(seg => new Date(seg.timestamp).getTime() > cutoffTime)
      );
    }, 60000); // Clean every minute

    return () => {
      if (bufferCleanupRef.current) {
        clearInterval(bufferCleanupRef.current);
      }
    };
  }, [maxBufferMinutes]);

  const getSpeakerColor = (speaker?: string) => {
    if (!speaker) return 'text-gray-400';
    const colors = [
      'text-blue-400',
      'text-green-400', 
      'text-purple-400',
      'text-orange-400',
      'text-pink-400',
      'text-cyan-400'
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
    <div className={`bg-gray-900 rounded-lg border border-gray-700 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Volume2 className="w-5 h-5" />
            {userRole === 'admin' || userRole === 'superuser' 
              ? 'Always-On Live Transcription'
              : 'Live Transcription'
            }
            {(userRole === 'admin' || userRole === 'superuser') && (
              <span className="text-sm text-gray-400 ml-2">
                ({maxBufferMinutes}min buffer)
              </span>
            )}
          </h2>
          
          <div className="flex items-center gap-3">
            {/* Model Info */}
            {activeModel && (
              <span className="text-sm text-gray-400 flex items-center gap-1">
                <Zap className="w-3 h-3" />
                {activeModel}
              </span>
            )}
            
            {/* Always-On Toggle Slider */}
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={isListening}
                onChange={() => isListening ? stopListening() : startListening()}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
              <span className="ml-3 text-sm font-medium text-gray-300">
                {isListening ? 'Listening' : 'Off'}
              </span>
            </label>
            
            {/* Recording Status (separate from always-on) */}
            {isListening && (
              <button
                onClick={toggleRecording}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  isRecording
                    ? 'bg-red-600/80 hover:bg-red-700 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                {isRecording ? (
                  <>
                    <Square className="w-3 h-3" />
                    Recording
                  </>
                ) : (
                  <>
                    <Circle className="w-3 h-3" />
                    Save to Session
                  </>
                )}
              </button>
            )}
            
            {/* Connection Status */}
            <div className="flex items-center gap-2">
              {isConnected ? (
                <span className="flex items-center gap-1 text-green-400">
                  <Mic className="w-4 h-4" />
                  <span className="text-sm">Live</span>
                </span>
              ) : (
                <span className="flex items-center gap-1 text-gray-500">
                  <MicOff className="w-4 h-4" />
                  <span className="text-sm">Offline</span>
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Transcription Display */}
      <div 
        ref={scrollContainerRef}
        className="h-96 overflow-y-auto p-4 space-y-3 scroll-smooth bg-gray-950"
        onScroll={handleScroll}
      >
        {transcriptions.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            {isListening ? (
              <>
                <Mic className="w-12 h-12 mx-auto mb-4 text-green-500 animate-pulse" />
                <p className="text-gray-300">
                  {userRole === 'admin' || userRole === 'superuser' 
                    ? 'Listening for audio input...' 
                    : 'Microphone ready'
                  }
                </p>
                <p className="text-sm text-gray-500 mt-2">
                  {userRole === 'admin' || userRole === 'superuser' 
                    ? `Continuous transcription active • ${maxBufferMinutes} minute buffer`
                    : 'Click "Save to Session" to start recording'
                  }
                </p>
                <p className="text-xs text-gray-600 mt-3 bg-gray-800/50 px-3 py-2 rounded-lg">
                  💡 <strong>Tip:</strong> Speak clearly near the microphone. If no audio appears, check:
                  <span className="block mt-1 ml-4">• Microphone is connected (USB)</span>
                  <span className="block ml-4">• Browser has microphone permission</span>
                  <span className="block ml-4">• Audio input level in system settings</span>
                </p>
              </>
            ) : (
              <>
                <MicOff className="w-12 h-12 mx-auto mb-4 text-gray-600" />
                <p className="text-gray-500">
                  Transcription paused
                </p>
                <p className="text-sm text-gray-600 mt-2">
                  Toggle the switch above to enable {userRole === 'admin' || userRole === 'superuser' ? 'always-on' : 'live'} transcription
                </p>
                <p className="text-xs text-gray-700 mt-3 bg-gray-800/50 px-3 py-2 rounded-lg">
                  📌 <strong>Note:</strong> Transcription requires:
                  <span className="block mt-1 ml-4">• Working microphone (USB recommended)</span>
                  <span className="block ml-4">• Backend service running on port 9050</span>
                  <span className="block ml-4">• Active NPU/CPU transcription service</span>
                </p>
              </>
            )}
          </div>
        ) : (
          transcriptions.map((segment, index) => (
            <div 
              key={segment.id}
              className={`border-l-2 pl-4 transition-all ${
                segment.isRecorded 
                  ? 'border-green-500 bg-green-900/20' 
                  : 'border-gray-600 hover:border-blue-400'
              }`}
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
                    {segment.isRecorded && (
                      <span className="text-xs bg-green-600 text-white px-2 py-0.5 rounded-full">
                        Recorded
                      </span>
                    )}
                  </div>
                  <p className={`${segment.isRecorded ? 'text-green-100' : 'text-gray-300'}`}>
                    {segment.text}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}

        {/* Current segment being processed */}
        {currentSegment && (
          <div className="border-l-2 border-blue-400 pl-4 animate-pulse">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
              <span className="text-xs text-blue-400">Processing...</span>
            </div>
            <p className="text-gray-400 italic">{currentSegment}</p>
          </div>
        )}

        <div ref={transcriptEndRef} />
      </div>

      {/* Footer Stats */}
      <div className="p-3 border-t border-gray-700 bg-gray-800 text-sm text-gray-400">
        <div className="flex items-center justify-between">
          <span>
            {transcriptions.length} segments • 
            {transcriptions.filter(s => s.isRecorded).length} recorded
          </span>
          <span>
            Buffer: {transcriptions.length > 0 ? Math.round(
              (Date.now() - new Date(transcriptions[0]?.timestamp).getTime()) / 60000
            ) : 0}min
          </span>
        </div>
      </div>
    </div>
  );
};