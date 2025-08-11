import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Mic, MicOff, Play, Pause, Square, Circle, Flag, 
  Volume2, Settings, Zap, CheckCircle, AlertCircle,
  Activity, Users, Clock, Save, Download, Share2,
  Brain, TrendingUp, Loader2, Info, Trash2
} from 'lucide-react';
import { WaveformVisualizer } from './WaveformVisualizer';
import { NpuStatusIndicator } from './NpuStatusIndicator';
import { LiveTranscriptionChat } from './LiveTranscriptionChat';
import { config } from '../config';
import { toast } from 'react-toastify';
import { useRecording } from '../contexts/RecordingContext';

interface TranscriptionSegment {
  id: string;
  text: string;
  timestamp: string;
  speaker?: string;
  confidence?: number;
  isFlagged?: boolean;
}

interface RecordingSession {
  id: string;
  title: string;
  status: 'idle' | 'recording' | 'paused' | 'stopped';
  duration: number;
  segments: TranscriptionSegment[];
}

export const UnifiedRecordingInterface: React.FC = () => {
  const { 
    activeSession, 
    isRecording: globalIsRecording, 
    recordingTime: globalRecordingTime,
    transcriptions: globalTranscriptions,
    setActiveSession,
    setIsRecording: setGlobalIsRecording,
    setRecordingTime: setGlobalRecordingTime,
    setTranscriptions: setGlobalTranscriptions,
    addTranscription
  } = useRecording();
  
  const [session, setSession] = useState<RecordingSession | null>(activeSession);
  const [isRecording, setIsRecording] = useState(globalIsRecording);
  const [isPaused, setIsPaused] = useState(false);
  const [transcriptions, setTranscriptions] = useState<TranscriptionSegment[]>(globalTranscriptions);
  const [isConnected, setIsConnected] = useState(false);
  const [micStatus, setMicStatus] = useState<'idle' | 'connecting' | 'active' | 'error'>('idle');
  const [audioLevel, setAudioLevel] = useState(0);
  const [recordingTime, setRecordingTime] = useState(globalRecordingTime);
  const [showInsights, setShowInsights] = useState(true);
  
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Check server-side audio status
  const checkServerAudio = useCallback(async () => {
    try {
      setMicStatus('connecting');
      
      // Check server audio device status (using main API that has USB device info)
      const url = `${config.apiBaseUrl}${config.apiEndpoints.audioDevices}`;
      console.log('[Recording] Fetching audio devices from:', url);
      const response = await fetch(url);
      
      if (response.ok) {
        const data = await response.json();
        console.log('[Recording] Server audio devices response:', data);
        
        // Check if server microphone is available in the devices array
        const devices = data.devices || data;
        console.log('[Recording] Available devices:', devices);
        
        // Look for USB microphone - be more flexible with the check
        const serverMic = devices.find((d: any) => {
          const name = (d.name || '').toLowerCase();
          console.log('[Recording] Checking device:', d.name, '-> lowercase:', name);
          return name.includes('usb') || name.includes('m-305') || 
                 name.includes('pcm2902') || name.includes('pnp');
        });
        
        if (serverMic) {
          console.log('[Recording] Server mic found:', serverMic.name);
          setMicStatus('ready');  // Set to ready when mic is found (active is for recording)
          return true;
        } else {
          console.warn('[Recording] No server mic found in devices:', devices);
          console.warn('[Recording] Looking for USB/M-305/PCM2902 in device names');
          setMicStatus('error');
          return false;
        }
      } else {
        console.error('[Recording] Failed to check server audio devices');
        setMicStatus('error');
        return false;
      }
      
    } catch (error) {
      console.error('[Recording] Server audio check failed:', error);
      setMicStatus('error');
      return false;
    }
  }, []);

  // Start recording session
  const startRecording = useCallback(async () => {
    try {
      // Prevent starting if already recording
      if (isRecording || globalIsRecording) {
        console.log('[Recording] Already recording, ignoring start request');
        return;
      }
      
      // Check server audio first
      const audioReady = await checkServerAudio();
      if (!audioReady) {
        alert('Server USB microphone not available. Please check server audio configuration.');
        return;
      }

      // Create recording session using simple API (no auth required)
      const response = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.simpleRecording.sessions}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: `Meeting Recording - ${new Date().toLocaleString()}`,
          description: 'Live recording with NPU transcription'
        })
      });

      if (!response.ok) throw new Error('Failed to create session');
      
      const sessionData = await response.json();
      
      // Start the session
      const startResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.simpleRecording.start(sessionData.id)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!startResponse.ok) throw new Error('Failed to start session');

      // Setup WebSocket for real-time transcription
      // Use session-specific WebSocket for live transcription
      const wsUrl = `${config.wsEndpoints.base}/ws/transcription/${sessionData.id}`;
      console.log('[Recording] Connecting to transcription WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        console.log('[Recording] WebSocket connected for server-side recording at:', wsUrl);
        
        // Server handles audio capture from USB mic
        // No need to send audio from browser
        
        // Send periodic pings to keep connection alive
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000); // Every 30 seconds
        
        // Store interval ID for cleanup
        (ws as any).pingInterval = pingInterval;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[Recording] WebSocket message received:', data);
          
          if (data.type === 'transcription' && data.segment) {
            console.log('[Recording] Transcription segment received:', data.segment);
            const segment: TranscriptionSegment = {
              id: Date.now().toString() + '_' + Math.random(),
              text: data.segment.text || '',
              timestamp: new Date().toISOString(),
              speaker: null,  // No speaker for live
              confidence: data.segment.confidence || 0.95,
              isFlagged: false
            };
            
            console.log('[Recording] Adding transcription segment:', segment);
            setTranscriptions(prev => {
              const newTranscriptions = [...prev, segment];
              console.log('[Recording] Total transcriptions:', newTranscriptions.length);
              setGlobalTranscriptions(newTranscriptions);
              return newTranscriptions;
            });
            
            // Auto-scroll to bottom
            setTimeout(() => {
              transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 100);
          } else if (data.type === 'status') {
            console.log('[Recording] Status update:', data.message);
            if (data.npu_status) {
              console.log('[Recording] NPU Status:', data.npu_status);
            }
          } else if (data.type === 'keepalive' || data.type === 'pong') {
            // Keep-alive messages, ignore
          } else {
            console.log('[Recording] Unknown WebSocket message type:', data.type, data);
          }
        } catch (err) {
          console.error('[Recording] WebSocket message error:', err);
        }
      };

      ws.onerror = () => setIsConnected(false);
      ws.onclose = () => setIsConnected(false);

      // Set recording state
      const newSession = {
        id: sessionData.id,
        title: sessionData.name || `Meeting Recording - ${new Date().toLocaleString()}`,
        status: 'recording' as const,
        duration: 0,
        segments: []
      };
      setSession(newSession);
      
      // Update global state
      setActiveSession({
        id: sessionData.id,
        name: sessionData.name || `Meeting Recording - ${new Date().toLocaleString()}`,
        status: 'recording',
        startTime: new Date().toISOString(),
        duration: 0
      });
      
      setIsRecording(true);
      setGlobalIsRecording(true);
      setRecordingTime(0);
      setGlobalRecordingTime(0);
      setMicStatus('active'); // Set mic status to active when recording starts
      
      // Start timer
      intervalRef.current = setInterval(() => {
        setRecordingTime(prev => {
          const newTime = prev + 1;
          setGlobalRecordingTime(newTime);
          return newTime;
        });
      }, 1000);
      
    } catch (error) {
      console.error('[Recording] Start failed:', error);
      // Don't change mic status on recording error - mic might still be available
      alert('Failed to start recording. Please try again.');
      setIsRecording(false);
    }
  }, [checkServerAudio]);

  // Stop recording
  const stopRecording = useCallback(async () => {
    try {
      // Server will stop recording
      console.log('[Recording] Stopping server-side recording...');
      
      // Get session ID - either from state or check for active recording
      let sessionId = session?.id;
      
      if (!sessionId) {
        const statusResponse = await fetch(`${config.apiBaseUrl}/api/simple/recording-status`);
        if (statusResponse.ok) {
          const status = await statusResponse.json();
          if (status.is_recording) {
            sessionId = status.session_id;
          }
        }
      }
      
      if (!sessionId) {
        console.error('[Recording] No active recording to stop');
        return;
      }
      
      // Close WebSocket
      if (wsRef.current) {
        // Clear ping interval if exists
        const ws = wsRef.current as any;
        if (ws.pingInterval) {
          clearInterval(ws.pingInterval);
        }
        wsRef.current.close();
        wsRef.current = null;
      }
      
      // Stop timer
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }

      // Stop recording on backend
      const stopResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.simpleRecording.stop(sessionId)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!stopResponse.ok) {
        throw new Error('Failed to stop recording on server');
      }
      
      console.log('[Recording] Server recording stopped');

      setIsRecording(false);
      setGlobalIsRecording(false);
      setIsPaused(false);
      setIsConnected(false);
      setMicStatus('idle');
      setAudioLevel(0);
      setSession(null);
      setActiveSession(null);
      setTranscriptions([]);
      setGlobalTranscriptions([]);
      
    } catch (error) {
      console.error('[Recording] Stop failed:', error);
    }
  }, [session]);

  // Toggle recording
  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // Toggle pause
  const togglePause = () => {
    if (!isRecording) return;
    
    setIsPaused(!isPaused);
    
    if (mediaRecorderRef.current) {
      if (isPaused) {
        mediaRecorderRef.current.resume();
      } else {
        mediaRecorderRef.current.pause();
      }
    }
  };

  // Flag moment
  const flagMoment = () => {
    if (transcriptions.length > 0) {
      const lastSegment = transcriptions[transcriptions.length - 1];
      setTranscriptions(prev => 
        prev.map(seg => 
          seg.id === lastSegment.id ? { ...seg, isFlagged: true } : seg
        )
      );
    }
  };

  // Clear transcription
  const clearTranscription = () => {
    setTranscriptions([]);
    setGlobalTranscriptions([]);
    console.log('[Recording] Cleared transcription');
  };

  // Format time
  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Check recording status on mount
  const checkRecordingStatus = useCallback(async () => {
    try {
      console.log('[Recording] Checking for active recording status...');
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-status`);
      if (response.ok) {
        const status = await response.json();
        console.log('[Recording] Recording status response:', status);
        if (status.is_recording) {
          console.log('[Recording] Active recording found! Session:', status.session_id);
          setIsRecording(true);
          setGlobalIsRecording(true);
          const restoredSession = {
            id: status.session_id,
            title: status.session_name || `Meeting Recording - ${new Date().toLocaleString()}`,
            status: 'recording' as const,
            duration: 0,
            segments: []
          };
          setSession(restoredSession);
          setActiveSession({
            id: status.session_id,
            name: status.session_name || `Meeting Recording - ${new Date().toLocaleString()}`,
            status: 'recording',
            startTime: status.started_at || new Date().toISOString(),
            duration: 0
          });
          setMicStatus('active');
          console.log('[Recording] Found active recording session:', status.session_id);
          
          // Restore timer (estimate based on when recording might have started)
          if (status.started_at) {
            const startTime = new Date(status.started_at).getTime();
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            setRecordingTime(elapsed);
          }
          
          // Start timer
          intervalRef.current = setInterval(() => {
            setRecordingTime(prev => {
              const newTime = prev + 1;
              setGlobalRecordingTime(newTime);
              return newTime;
            });
          }, 1000);
          
          // Reconnect WebSocket for live transcription
          const wsUrl = `${config.wsEndpoints.base}/ws/transcription/${status.session_id}`;
          const ws = new WebSocket(wsUrl);
          wsRef.current = ws;
          
          ws.onopen = () => {
            setIsConnected(true);
            console.log('[Recording] Reconnected to transcription WebSocket');
          };
          
          ws.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              console.log('[Recording] Reconnected WebSocket message:', data);
              
              if (data.type === 'transcription' && data.segment) {
                const segment: TranscriptionSegment = {
                  id: Date.now().toString() + '_' + Math.random(),
                  text: data.segment.text || '',
                  timestamp: new Date().toISOString(),
                  speaker: null,  // No speaker for live
                  confidence: data.segment.confidence || 0.95,
                  isFlagged: false
                };
                
                console.log('[Recording] Adding reconnected segment:', segment);
                setTranscriptions(prev => {
                  const updated = [...prev, segment];
                  setGlobalTranscriptions(updated);
                  return updated;
                });
                
                // Auto-scroll
                setTimeout(() => {
                  transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
                }, 100);
              } else if (data.type === 'status') {
                console.log('[Recording] Reconnected status:', data.message);
              }
            } catch (error) {
              console.error('[Recording] Reconnected WebSocket error:', error);
            }
          };
          
          ws.onerror = (error) => {
            console.error('[Recording] WebSocket error:', error);
          };
          
          ws.onclose = () => {
            setIsConnected(false);
          };
        }
      }
    } catch (error) {
      console.error('[Recording] Failed to check recording status:', error);
    }
  }, []);

  // Check server mic and recording status on mount
  useEffect(() => {
    // Only check server audio if not already recording
    if (!globalIsRecording) {
      checkServerAudio();
    } else {
      // If already recording globally, restore that state
      setIsRecording(true);
      setRecordingTime(globalRecordingTime);
      setMicStatus('active');
      setSession(activeSession as any);
      setTranscriptions(globalTranscriptions);
      
      // Reconnect WebSocket if we have an active session
      if (activeSession?.id) {
        const wsUrl = `${config.wsEndpoints.base}/ws/transcription/${activeSession.id}`;
        console.log('[Recording] Reconnecting to active session:', activeSession.id);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        
        ws.onopen = () => {
          setIsConnected(true);
          console.log('[Recording] Reconnected to transcription WebSocket');
        };
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'transcription' && data.segment) {
              const segment: TranscriptionSegment = {
                id: Date.now().toString() + '_' + Math.random(),
                text: data.segment.text || '',
                timestamp: new Date().toISOString(),
                speaker: null,  // No speaker for live
                confidence: data.segment.confidence || 0.95,
                isFlagged: false
              };
              
              setTranscriptions(prev => {
                const updated = [...prev, segment];
                setGlobalTranscriptions(updated);
                return updated;
              });
              
              // Auto-scroll
              setTimeout(() => {
                transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
              }, 100);
            }
          } catch (error) {
            console.error('[Recording] WebSocket error:', error);
          }
        };
        
        ws.onerror = () => setIsConnected(false);
        ws.onclose = () => setIsConnected(false);
        
        // Resume timer
        intervalRef.current = setInterval(() => {
          setRecordingTime(prev => {
            const newTime = prev + 1;
            setGlobalRecordingTime(newTime);
            return newTime;
          });
        }, 1000);
      }
    }
    
    // Always check recording status to sync with backend
    checkRecordingStatus();
  }, []);  // Only run once on mount
  
  // Cleanup on unmount - but don't stop recording, just cleanup local resources
  useEffect(() => {
    return () => {
      // Clear timer but don't stop recording (it continues in background)
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      // Close WebSocket but recording continues
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, []);

  // Get mic status color and text
  const getMicStatusDisplay = () => {
    switch (micStatus) {
      case 'active':
        return { color: 'text-green-400', text: 'Recording - Server Mic Active', icon: CheckCircle };
      case 'ready':
        return { color: 'text-blue-400', text: 'Server Mic Available', icon: Mic };
      case 'connecting':
        return { color: 'text-yellow-400', text: 'Connecting to Server...', icon: Loader2 };
      case 'error':
        return { color: 'text-red-400', text: 'Server Mic Unavailable', icon: AlertCircle };
      default:
        return { color: 'text-gray-400', text: 'Checking Server Audio...', icon: Info };
    }
  };

  const micDisplay = getMicStatusDisplay();

  return (
    <div className="flex flex-col h-full bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 border-b border-gray-800 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* Recording Button */}
            <button
              onClick={toggleRecording}
              className={`p-4 rounded-full transition-all duration-200 ${
                isRecording 
                  ? 'bg-red-600 hover:bg-red-700 animate-pulse shadow-lg' 
                  : 'bg-purple-600 hover:bg-purple-700 shadow-lg hover:scale-105'
              }`}
            >
              {isRecording ? (
                <Square className="w-8 h-8 text-white" />
              ) : (
                <Circle className="w-8 h-8 text-white" />
              )}
            </button>

            <div>
              <h1 className="text-2xl font-bold text-white">
                {isRecording ? 'Recording in Progress' : 'Meeting Recorder'}
              </h1>
              <div className="flex items-center gap-4 mt-1">
                {/* Mic Status */}
                <div className={`flex items-center gap-2 ${micDisplay.color}`}>
                  <micDisplay.icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{micDisplay.text}</span>
                </div>
                
                {/* Connection Status */}
                <div className={`flex items-center gap-2 ${
                  isConnected ? 'text-green-400' : 'text-gray-400'
                }`}>
                  <Activity className="w-4 h-4" />
                  <span className="text-sm">
                    {isConnected ? 'NPU Connected' : 'Standby'}
                  </span>
                </div>

                {/* Recording Time */}
                {isRecording && (
                  <div className="flex items-center gap-2 text-cyan-400">
                    <Clock className="w-4 h-4" />
                    <span className="font-mono text-lg font-semibold">
                      {formatTime(recordingTime)}
                    </span>
                    {isPaused && <span className="text-yellow-400 text-sm">(Paused)</span>}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={togglePause}
              disabled={!isRecording}
              className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isPaused ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
            </button>
            
            <button
              onClick={flagMoment}
              disabled={!isRecording}
              className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Flag moment"
            >
              <Flag className="w-5 h-5" />
            </button>

            <button 
              onClick={clearTranscription}
              disabled={transcriptions.length === 0}
              className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Clear transcription"
            >
              <Trash2 className="w-5 h-5" />
            </button>

            <button className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 transition-colors" title="Save">
              <Save className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex gap-6 p-6 overflow-hidden">
        {/* Left Panel - Live Transcription Chat */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Use new chat-style component */}
          <LiveTranscriptionChat 
            transcriptions={transcriptions}
            isRecording={isRecording}
            className="flex-1"
          />

          {/* Real-time Insights */}
          {showInsights && transcriptions.length > 0 && (
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                AI Insights
              </h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div className="bg-gray-800/50 rounded p-3">
                  <p className="text-purple-400 font-medium">Topics</p>
                  <p className="text-gray-300">NPU optimization, performance</p>
                </div>
                <div className="bg-gray-800/50 rounded p-3">
                  <p className="text-blue-400 font-medium">Speakers</p>
                  <p className="text-gray-300">{new Set(transcriptions.map(t => t.speaker)).size} identified</p>
                </div>
                <div className="bg-gray-800/50 rounded p-3">
                  <p className="text-green-400 font-medium">Sentiment</p>
                  <p className="text-gray-300">Positive (78%)</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Panel */}
        <div className="w-80 flex flex-col gap-4">
          {/* Audio Visualization */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
              <Volume2 className="w-4 h-4 text-blue-400" />
              Audio Levels
            </h3>
            <WaveformVisualizer 
              className="h-48"
              showControls={false}
              animate={isRecording}
            />
          </div>

          {/* NPU Status */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
              <Zap className="w-4 h-4 text-green-400" />
              NPU Status
            </h3>
            <NpuStatusIndicator />
          </div>
        </div>
      </div>
    </div>
  );
};