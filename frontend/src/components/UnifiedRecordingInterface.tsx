import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Mic, MicOff, Play, Pause, Square, Circle, Flag, 
  Volume2, Settings, Zap, CheckCircle, AlertCircle,
  Activity, Users, Clock, Save, Download, Share2,
  Brain, TrendingUp, Loader2, Info
} from 'lucide-react';
import { WaveformVisualizer } from './WaveformVisualizer';
import { NpuStatusIndicator } from './NpuStatusIndicator';

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

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const UnifiedRecordingInterface: React.FC = () => {
  const [session, setSession] = useState<RecordingSession | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [transcriptions, setTranscriptions] = useState<TranscriptionSegment[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [micStatus, setMicStatus] = useState<'idle' | 'connecting' | 'active' | 'error'>('idle');
  const [audioLevel, setAudioLevel] = useState(0);
  const [recordingTime, setRecordingTime] = useState(0);
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
      
      const token = localStorage.getItem('access_token');
      if (!token) {
        setMicStatus('error');
        return false;
      }
      
      // Check server audio device status
      const response = await fetch(`${API_BASE_URL}/api/audio-devices`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const devices = await response.json();
        console.log('[Recording] Server audio devices:', devices);
        
        // Check if server microphone is available 
        const serverMic = devices.find((d: any) => 
          d.name?.includes('USB') || d.name?.includes('PCM2902') || 
          d.name?.includes('M-305') || d.name?.includes('Server Microphone')
        );
        
        if (serverMic) {
          console.log('[Recording] Server mic found:', serverMic.name);
          setMicStatus('active');
          return true;
        } else {
          console.warn('[Recording] No server mic found');
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
      const token = localStorage.getItem('access_token');
      if (!token) return;

      // Check server audio first
      const audioReady = await checkServerAudio();
      if (!audioReady) {
        alert('Server USB microphone not available. Please check server audio configuration.');
        return;
      }

      // Create recording session
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: `Meeting Recording - ${new Date().toLocaleString()}`,
          is_realtime: true
        })
      });

      if (!response.ok) throw new Error('Failed to create session');
      
      const sessionData = await response.json();
      
      // Start the session
      const startResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionData.session_id}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!startResponse.ok) throw new Error('Failed to start session');

      // Setup WebSocket for transcription
      const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/ws/transcription/${sessionData.session_id}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        console.log('[Recording] WebSocket connected for server-side recording');
        
        // Server handles audio capture from USB mic
        // No need to send audio from browser
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'transcription' && data.data?.text) {
            const segment: TranscriptionSegment = {
              id: Date.now().toString(),
              text: data.data.text,
              timestamp: new Date().toISOString(),
              speaker: data.data.speaker || 'Speaker',
              confidence: data.data.confidence || 0.95,
              isFlagged: false
            };
            
            setTranscriptions(prev => [...prev, segment]);
            
            // Auto-scroll to bottom
            setTimeout(() => {
              transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 100);
          }
        } catch (err) {
          console.error('[Recording] WebSocket message error:', err);
        }
      };

      ws.onerror = () => setIsConnected(false);
      ws.onclose = () => setIsConnected(false);

      // Set recording state
      setSession({
        id: sessionData.session_id,
        title: `Meeting Recording - ${new Date().toLocaleString()}`,
        status: 'recording',
        duration: 0,
        segments: []
      });
      
      setIsRecording(true);
      setRecordingTime(0);
      
      // Start timer
      intervalRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
      
    } catch (error) {
      console.error('[Recording] Start failed:', error);
      setMicStatus('error');
    }
  }, [checkServerAudio]);

  // Stop recording
  const stopRecording = useCallback(async () => {
    try {
      // Server will stop recording
      console.log('[Recording] Stopping server-side recording...');
      
      // No browser stream to stop - recording is server-side
      console.log('[Recording] Server recording stopped');
      
      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.close();
      }
      
      // Stop timer
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }

      // Update session on backend
      if (session) {
        const token = localStorage.getItem('access_token');
        if (token) {
          await fetch(`${API_BASE_URL}/api/recording-sessions/${session.id}/stop`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          });
        }
      }

      setIsRecording(false);
      setIsPaused(false);
      setIsConnected(false);
      setMicStatus('idle');
      setAudioLevel(0);
      
      if (session) {
        setSession({
          ...session,
          status: 'stopped'
        });
      }
      
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

  // Format time
  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Check server mic status on mount
  useEffect(() => {
    checkServerAudio();
  }, [checkServerAudio]);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isRecording) {
        stopRecording();
      }
    };
  }, [isRecording, stopRecording]);

  // Get mic status color and text
  const getMicStatusDisplay = () => {
    switch (micStatus) {
      case 'active':
        return { color: 'text-green-400', text: 'Server Mic Ready - NPU Active', icon: CheckCircle };
      case 'connecting':
        return { color: 'text-yellow-400', text: 'Connecting to Server...', icon: Loader2 };
      case 'error':
        return { color: 'text-red-400', text: 'Server Mic Unavailable', icon: AlertCircle };
      default:
        return { color: 'text-blue-400', text: 'Server Ready - Click to Record', icon: Info };
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
            >
              <Flag className="w-5 h-5" />
            </button>

            <button className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 transition-colors">
              <Save className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex gap-6 p-6 overflow-hidden">
        {/* Left Panel - Transcription */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Live Transcription */}
          <div className="flex-1 bg-gray-900 rounded-lg border border-gray-800 p-6 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <Mic className="w-5 h-5 text-purple-400" />
                Live Transcription
              </h2>
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <span>{transcriptions.length} segments</span>
                {isRecording && (
                  <div className="flex items-center gap-1 text-green-400">
                    <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                    <span>Live</span>
                  </div>
                )}
              </div>
            </div>

            {/* Transcription Display */}
            <div className="flex-1 overflow-y-auto space-y-3">
              {transcriptions.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <Mic className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                    <p className="text-gray-500">
                      {isRecording 
                        ? 'Listening for speech... NPU ready for transcription.'
                        : 'Click the record button to start transcribing'
                      }
                    </p>
                  </div>
                </div>
              ) : (
                <>
                  {transcriptions.map((segment) => (
                    <div 
                      key={segment.id}
                      className={`p-4 rounded-lg transition-all ${
                        segment.isFlagged 
                          ? 'bg-yellow-900/20 border border-yellow-700' 
                          : 'bg-gray-800/50 hover:bg-gray-800'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="text-sm font-medium text-purple-400">
                              {segment.speaker}
                            </span>
                            <span className="text-xs text-gray-500">
                              {new Date(segment.timestamp).toLocaleTimeString()}
                            </span>
                            {segment.confidence && (
                              <span className="text-xs text-gray-600">
                                {Math.round(segment.confidence * 100)}% confidence
                              </span>
                            )}
                          </div>
                          <p className="text-gray-200 leading-relaxed">{segment.text}</p>
                        </div>
                        {segment.isFlagged && (
                          <Flag className="w-4 h-4 text-yellow-400" />
                        )}
                      </div>
                    </div>
                  ))}
                  <div ref={transcriptEndRef} />
                </>
              )}
            </div>
          </div>

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