import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Volume2, Circle, Square, Flag, Star } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  text: string;
  timestamp: string;
  isSaved?: boolean;
  isFlagged?: boolean;
}

interface SimpleAlwaysOnTranscriptionProps {
  className?: string;
  userRole?: 'admin' | 'superuser' | 'user';
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const SimpleAlwaysOnTranscription: React.FC<SimpleAlwaysOnTranscriptionProps> = ({ 
  className = '',
  userRole = 'user'
}) => {
  const [transcriptions, setTranscriptions] = useState<TranscriptionSegment[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [currentSession, setCurrentSession] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [flaggedSegments, setFlaggedSegments] = useState<Set<string>>(new Set());
  
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const continuousSessionRef = useRef<string>(`continuous_${Date.now()}`);

  // Start continuous transcription with auto-rotating sessions
  const startContinuousTranscription = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        console.error('No auth token');
        return;
      }

      // Create a background session for continuous transcription
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: `Continuous Transcription ${new Date().toLocaleTimeString()}`,
          is_realtime: true
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create session');
      }

      const session = await response.json();
      continuousSessionRef.current = session.id;

      // Start the recording session
      const startResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${session.id}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!startResponse.ok) {
        throw new Error('Failed to start recording');
      }

      // Connect WebSocket for this session
      const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/ws/transcription/${session.id}`;
      console.log('[SimpleAlwaysOn] Connecting to:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[SimpleAlwaysOn] WebSocket connected');
        setIsConnected(true);
        setIsListening(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[SimpleAlwaysOn] Received:', data);
          
          if (data.type === 'transcription' && data.data?.text) {
            const segmentId = Date.now().toString();
            const segment: TranscriptionSegment = {
              id: segmentId,
              text: data.data.text,
              timestamp: new Date().toISOString(),
              isSaved: isSaving,
              isFlagged: flaggedSegments.has(segmentId)
            };
            
            setTranscriptions(prev => {
              // Keep only last 100 segments for memory efficiency
              const updated = [...prev, segment];
              if (updated.length > 100) {
                return updated.slice(-100);
              }
              return updated;
            });

            // Auto-scroll
            setTimeout(() => {
              if (scrollContainerRef.current) {
                const container = scrollContainerRef.current;
                const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;
                if (isNearBottom) {
                  transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
                }
              }
            }, 100);
          }
        } catch (err) {
          console.error('[SimpleAlwaysOn] Parse error:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('[SimpleAlwaysOn] WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('[SimpleAlwaysOn] WebSocket closed');
        setIsConnected(false);
        
        // Auto-reconnect after 3 seconds if still listening
        if (isListening) {
          setTimeout(() => {
            if (isListening) {
              console.log('[SimpleAlwaysOn] Attempting reconnect...');
              startContinuousTranscription();
            }
          }, 3000);
        }
      };

    } catch (error) {
      console.error('[SimpleAlwaysOn] Failed to start:', error);
      setIsListening(false);
    }
  }, [isSaving, flaggedSegments]);

  // Stop continuous transcription
  const stopContinuousTranscription = useCallback(async () => {
    try {
      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      // Stop the continuous session
      if (continuousSessionRef.current) {
        const token = localStorage.getItem('access_token');
        if (token) {
          await fetch(`${API_BASE_URL}/api/recording-sessions/${continuousSessionRef.current}/stop`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          });
        }
      }

      setIsListening(false);
      setIsConnected(false);
    } catch (error) {
      console.error('[SimpleAlwaysOn] Failed to stop:', error);
    }
  }, []);

  // Toggle listening
  const toggleListening = () => {
    if (isListening) {
      stopContinuousTranscription();
    } else {
      startContinuousTranscription();
    }
  };

  // Start saving to a new session
  const startSavingSession = async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;

      // Create a new session for saved recording
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: `Saved Recording ${new Date().toLocaleString()}`,
          is_realtime: true
        })
      });

      if (!response.ok) throw new Error('Failed to create save session');

      const session = await response.json();
      setCurrentSession(session.id);

      // Start the saved session
      await fetch(`${API_BASE_URL}/api/recording-sessions/${session.id}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      setIsSaving(true);
      
      // Mark future transcriptions as saved
      console.log('[SimpleAlwaysOn] Started saving to session:', session.id);
      
    } catch (error) {
      console.error('[SimpleAlwaysOn] Failed to start saving:', error);
    }
  };

  // Stop saving session
  const stopSavingSession = async () => {
    try {
      if (currentSession) {
        const token = localStorage.getItem('access_token');
        if (token) {
          await fetch(`${API_BASE_URL}/api/recording-sessions/${currentSession}/stop`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          });
        }
      }
      
      setIsSaving(false);
      setCurrentSession(null);
      console.log('[SimpleAlwaysOn] Stopped saving session');
      
    } catch (error) {
      console.error('[SimpleAlwaysOn] Failed to stop saving:', error);
    }
  };

  // Auto-start for admin users
  useEffect(() => {
    if (userRole === 'admin' || userRole === 'superuser') {
      // Auto-start listening for admin users
      setTimeout(() => {
        startContinuousTranscription();
      }, 1000);
    }

    return () => {
      stopContinuousTranscription();
    };
  }, []);

  // Format timestamp
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  // Toggle flag on a segment
  const toggleFlag = (segmentId: string) => {
    setFlaggedSegments(prev => {
      const newSet = new Set(prev);
      if (newSet.has(segmentId)) {
        newSet.delete(segmentId);
      } else {
        newSet.add(segmentId);
      }
      // Save flagged segments to localStorage
      localStorage.setItem('flagged_segments', JSON.stringify(Array.from(newSet)));
      return newSet;
    });
    
    // Update the transcription segment
    setTranscriptions(prev => 
      prev.map(seg => 
        seg.id === segmentId 
          ? { ...seg, isFlagged: !seg.isFlagged }
          : seg
      )
    );
  };

  // Load flagged segments from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('flagged_segments');
    if (stored) {
      try {
        const ids = JSON.parse(stored);
        setFlaggedSegments(new Set(ids));
      } catch (e) {
        console.error('Failed to load flagged segments:', e);
      }
    }
  }, []);

  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-700 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Volume2 className="w-5 h-5" />
            Simple Always-On Transcription
          </h2>
          
          <div className="flex items-center gap-3">
            {/* Always-On Toggle */}
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={isListening}
                onChange={toggleListening}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
              <span className="ml-3 text-sm font-medium text-gray-300">
                {isListening ? 'ON' : 'OFF'}
              </span>
            </label>
            
            {/* Save to Session Button */}
            {isListening && (
              <button
                onClick={isSaving ? stopSavingSession : startSavingSession}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  isSaving
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                {isSaving ? (
                  <>
                    <Square className="w-3 h-3" />
                    Stop Saving
                  </>
                ) : (
                  <>
                    <Circle className="w-3 h-3" />
                    Save to File
                  </>
                )}
              </button>
            )}
            
            {/* Connection Status */}
            <div className="flex items-center gap-2">
              {isConnected ? (
                <span className="flex items-center gap-1 text-green-400 text-sm">
                  <Mic className="w-4 h-4" />
                  Live
                </span>
              ) : (
                <span className="flex items-center gap-1 text-gray-500 text-sm">
                  <MicOff className="w-4 h-4" />
                  Off
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Transcription Display */}
      <div 
        ref={scrollContainerRef}
        className="h-96 overflow-y-auto p-4 space-y-2 bg-gray-950"
      >
        {transcriptions.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            {isListening ? (
              <>
                <Mic className="w-12 h-12 mx-auto mb-4 text-green-500 animate-pulse" />
                <p className="text-gray-300">Listening...</p>
                <p className="text-sm text-gray-500 mt-2">
                  Speak clearly into your microphone
                </p>
              </>
            ) : (
              <>
                <MicOff className="w-12 h-12 mx-auto mb-4 text-gray-600" />
                <p className="text-gray-500">Toggle switch to start</p>
              </>
            )}
          </div>
        ) : (
          transcriptions.map((segment) => (
            <div 
              key={segment.id}
              className={`p-3 rounded-lg transition-all ${
                segment.isFlagged
                  ? 'bg-yellow-900/30 border-l-4 border-yellow-500'
                  : segment.isSaved 
                  ? 'bg-green-900/30 border-l-4 border-green-500' 
                  : 'bg-gray-800/50 border-l-4 border-gray-600'
              }`}
            >
              <div className="flex items-start justify-between">
                <p className="text-gray-200 flex-1">{segment.text}</p>
                <div className="flex items-center gap-2 ml-2">
                  <button
                    onClick={() => toggleFlag(segment.id)}
                    className={`p-1 rounded hover:bg-gray-700 transition-colors ${
                      segment.isFlagged
                        ? 'text-yellow-400'
                        : 'text-gray-500 hover:text-yellow-400'
                    }`}
                    title={segment.isFlagged ? 'Remove flag' : 'Flag this segment'}
                  >
                    {segment.isFlagged ? (
                      <Star className="w-4 h-4 fill-current" />
                    ) : (
                      <Flag className="w-4 h-4" />
                    )}
                  </button>
                  <span className="text-xs text-gray-500">
                    {formatTime(segment.timestamp)}
                  </span>
                  {segment.isSaved && (
                    <span className="text-xs bg-green-600 text-white px-2 py-0.5 rounded">
                      Saved
                    </span>
                  )}
                  {segment.isFlagged && (
                    <span className="text-xs bg-yellow-600 text-white px-2 py-0.5 rounded">
                      Flagged
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
        <div ref={transcriptEndRef} />
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700 bg-gray-800 text-xs text-gray-400">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span>{transcriptions.length} segments</span>
            {flaggedSegments.size > 0 && (
              <span className="flex items-center gap-1 text-yellow-400">
                <Star className="w-3 h-3 fill-current" />
                {flaggedSegments.size} flagged
              </span>
            )}
          </div>
          {isSaving && currentSession && (
            <span className="text-green-400">Recording to session: {currentSession.slice(0, 8)}...</span>
          )}
        </div>
      </div>
    </div>
  );
};