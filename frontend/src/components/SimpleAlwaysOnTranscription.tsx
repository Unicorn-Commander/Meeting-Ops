import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Volume2, Circle, Square, Flag, Star, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  text: string;
  timestamp: string;
  isSaved?: boolean;
  isFlagged?: boolean;
  speaker?: string;
  confidence?: number;
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
  const [micStatus, setMicStatus] = useState<'idle' | 'connecting' | 'active' | 'error'>('idle');
  const [audioLevel, setAudioLevel] = useState(0);
  
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const continuousSessionRef = useRef<string>(`continuous_${Date.now()}`);
  const audioIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Initialize audio capture and processing
  const initializeAudioCapture = useCallback(async () => {
    try {
      setMicStatus('connecting');
      
      // Get user media
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      
      streamRef.current = stream;
      
      // Create audio context for level monitoring
      audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      const source = audioContextRef.current.createMediaStreamSource(stream);
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      source.connect(analyserRef.current);
      
      // Start audio level monitoring
      const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
      audioIntervalRef.current = setInterval(() => {
        if (analyserRef.current) {
          analyserRef.current.getByteFrequencyData(dataArray);
          const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
          setAudioLevel(Math.min(100, (average / 128) * 100));
        }
      }, 100);
      
      // Create MediaRecorder for chunked audio sending
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
        ? 'audio/webm;codecs=opus' 
        : 'audio/webm';
      
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 16000
      });
      
      mediaRecorderRef.current = mediaRecorder;
      
      // Send audio chunks every 500ms
      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          // Convert blob to array buffer and send
          const arrayBuffer = await event.data.arrayBuffer();
          wsRef.current.send(arrayBuffer);
        }
      };
      
      mediaRecorder.onstart = () => {
        setMicStatus('active');
        console.log('[Audio] MediaRecorder started');
      };
      
      mediaRecorder.onstop = () => {
        setMicStatus('idle');
        console.log('[Audio] MediaRecorder stopped');
      };
      
      return true;
    } catch (error) {
      console.error('[Audio] Failed to initialize:', error);
      setMicStatus('error');
      return false;
    }
  }, []);

  // Start continuous transcription with audio capture
  const startContinuousTranscription = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        console.error('No auth token');
        return;
      }

      // Initialize audio capture first
      const audioReady = await initializeAudioCapture();
      if (!audioReady) {
        throw new Error('Failed to initialize audio capture');
      }

      // Create a background session for continuous transcription
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: `Always-On Transcription ${new Date().toLocaleTimeString()}`,
          is_realtime: true
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create session');
      }

      const session = await response.json();
      continuousSessionRef.current = session.id;
      setCurrentSession(session.id);

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
      console.log('[WebSocket] Connecting to:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] Connected successfully');
        setIsConnected(true);
        setIsListening(true);
        
        // Start recording audio chunks
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'inactive') {
          mediaRecorderRef.current.start(500); // Send chunks every 500ms
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[WebSocket] Received:', data);
          
          if (data.type === 'transcription' && data.data?.text) {
            const segmentId = Date.now().toString();
            const segment: TranscriptionSegment = {
              id: segmentId,
              text: data.data.text,
              timestamp: new Date().toISOString(),
              isSaved: isSaving,
              isFlagged: flaggedSegments.has(segmentId),
              speaker: data.data.speaker || 'Speaker',
              confidence: data.data.confidence || 0.95
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
          } else if (data.type === 'status') {
            console.log('[WebSocket] Status:', data.message);
          }
        } catch (err) {
          console.error('[WebSocket] Parse error:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        setMicStatus('error');
      };

      ws.onclose = () => {
        console.log('[WebSocket] Connection closed');
        setIsConnected(false);
        
        // Stop MediaRecorder
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
        }
        
        // Auto-reconnect after 3 seconds if still listening
        if (isListening) {
          setTimeout(() => {
            if (isListening) {
              console.log('[WebSocket] Attempting reconnect...');
              startContinuousTranscription();
            }
          }, 3000);
        }
      };

    } catch (error) {
      console.error('[Transcription] Failed to start:', error);
      setIsListening(false);
      setMicStatus('error');
    }
  }, [isSaving, flaggedSegments, initializeAudioCapture]);

  // Stop continuous transcription
  const stopContinuousTranscription = useCallback(async () => {
    try {
      // Stop MediaRecorder
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      
      // Stop audio stream
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      
      // Clear audio level monitoring
      if (audioIntervalRef.current) {
        clearInterval(audioIntervalRef.current);
        audioIntervalRef.current = null;
      }
      
      // Close audio context
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      
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
      setMicStatus('idle');
      setAudioLevel(0);
    } catch (error) {
      console.error('[Transcription] Failed to stop:', error);
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

      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: `Saved Session - ${new Date().toLocaleString()}`,
          is_realtime: false
        })
      });

      if (response.ok) {
        const session = await response.json();
        setCurrentSession(session.id);
        setIsSaving(true);
      }
    } catch (error) {
      console.error('Failed to start saving session:', error);
    }
  };

  // Stop saving
  const stopSavingSession = () => {
    setIsSaving(false);
    setCurrentSession(null);
  };

  // Flag a segment
  const toggleFlag = (segmentId: string) => {
    setFlaggedSegments(prev => {
      const newSet = new Set(prev);
      if (newSet.has(segmentId)) {
        newSet.delete(segmentId);
      } else {
        newSet.add(segmentId);
      }
      return newSet;
    });
  };

  // Clear transcriptions
  const clearTranscriptions = () => {
    setTranscriptions([]);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopContinuousTranscription();
    };
  }, [stopContinuousTranscription]);

  // Start listening automatically
  useEffect(() => {
    const autoStart = setTimeout(() => {
      if (!isListening) {
        startContinuousTranscription();
      }
    }, 1000);
    
    return () => clearTimeout(autoStart);
  }, []);

  return (
    <div className={`flex flex-col h-full bg-gray-900 rounded-lg border border-gray-800 ${className}`}>
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 p-4 rounded-t-lg border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={toggleListening}
              className={`p-3 rounded-full transition-all ${
                isListening 
                  ? 'bg-red-600 hover:bg-red-700 animate-pulse' 
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              {isListening ? (
                <Mic className="w-5 h-5 text-white" />
              ) : (
                <MicOff className="w-5 h-5 text-gray-300" />
              )}
            </button>
            
            <div className="flex flex-col">
              <h3 className="text-white font-semibold">Always-On Transcription</h3>
              <div className="flex items-center gap-2 text-xs">
                {/* Connection Status */}
                <span className={`flex items-center gap-1 ${
                  isConnected ? 'text-green-400' : 'text-gray-400'
                }`}>
                  <Circle className={`w-2 h-2 ${isConnected ? 'fill-green-400' : ''}`} />
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
                
                {/* Mic Status */}
                {micStatus === 'active' && (
                  <span className="flex items-center gap-1 text-blue-400">
                    <CheckCircle className="w-3 h-3" />
                    Mic Active
                  </span>
                )}
                {micStatus === 'error' && (
                  <span className="flex items-center gap-1 text-red-400">
                    <AlertCircle className="w-3 h-3" />
                    Mic Error
                  </span>
                )}
                {micStatus === 'connecting' && (
                  <span className="flex items-center gap-1 text-yellow-400">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Connecting...
                  </span>
                )}
                
                {/* Segment Count */}
                <span className="text-gray-400">
                  {transcriptions.length} segments
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Audio Level Meter */}
            <div className="flex items-center gap-2">
              <Volume2 className="w-4 h-4 text-gray-400" />
              <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 transition-all duration-100"
                  style={{ width: `${audioLevel}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 w-10 text-right">{Math.round(audioLevel)}%</span>
            </div>
            
            {/* Save Button */}
            <button
              onClick={isSaving ? stopSavingSession : startSavingSession}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                isSaving 
                  ? 'bg-green-600 hover:bg-green-700 text-white' 
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
              }`}
            >
              {isSaving ? (
                <>
                  <Square className="w-3 h-3 inline mr-1" />
                  Stop Saving
                </>
              ) : (
                <>
                  <Circle className="w-3 h-3 inline mr-1" />
                  Start Saving
                </>
              )}
            </button>

            {/* Clear Button */}
            <button
              onClick={clearTranscriptions}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg text-sm font-medium transition-all"
            >
              Clear
            </button>
          </div>
        </div>
      </div>

      {/* Transcription Area */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4 space-y-2"
      >
        {transcriptions.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500">
              {isListening ? 'Listening for speech...' : 'Click the microphone to start transcribing'}
            </p>
          </div>
        ) : (
          transcriptions.map((segment) => (
            <div 
              key={segment.id}
              className={`p-3 rounded-lg transition-all ${
                segment.isFlagged 
                  ? 'bg-yellow-900/20 border border-yellow-700' 
                  : 'bg-gray-800/50 hover:bg-gray-800'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-purple-400 font-medium">
                      {segment.speaker || 'Speaker'}
                    </span>
                    <span className="text-xs text-gray-500">
                      {new Date(segment.timestamp).toLocaleTimeString()}
                    </span>
                    {segment.confidence && (
                      <span className="text-xs text-gray-600">
                        {Math.round(segment.confidence * 100)}%
                      </span>
                    )}
                    {segment.isSaved && (
                      <span className="text-xs bg-green-600/20 text-green-400 px-2 py-0.5 rounded">
                        Saved
                      </span>
                    )}
                  </div>
                  <p className="text-gray-200">{segment.text}</p>
                </div>
                <button
                  onClick={() => toggleFlag(segment.id)}
                  className={`p-1 rounded transition-all ${
                    segment.isFlagged 
                      ? 'text-yellow-400 hover:text-yellow-300' 
                      : 'text-gray-600 hover:text-gray-400'
                  }`}
                >
                  <Flag className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))
        )}
        <div ref={transcriptEndRef} />
      </div>
    </div>
  );
};