import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, MicOff, Play, Pause, Square, Download, Save, 
  Clock, Users, FileText, Settings, AlertCircle, CheckCircle,
  Cpu, Zap, Activity
} from 'lucide-react';
import { LiveTranscriptionViewer } from '../components/LiveTranscriptionViewer';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';

interface RecordingSession {
  id: string;
  name: string;
  startTime: Date;
  duration: number;
  status: 'recording' | 'paused' | 'stopped' | 'processing';
  audioLevel: number;
  npuActive: boolean;
  speakerCount: number;
  wordCount: number;
}

export const RecordingPage: React.FC = () => {
  const navigate = useNavigate();
  
  // Safely get user - useAuth might not work in all contexts
  let user = null;
  try {
    const auth = useAuth();
    user = auth?.user;
  } catch (e) {
    console.log('Auth context not available');
  }
  
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [currentSession, setCurrentSession] = useState<RecordingSession | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [duration, setDuration] = useState(0);
  const [countdown, setCountdown] = useState<number | null>(null);
  
  // Generate default meeting name with timestamp
  const getDefaultMeetingName = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
    return `Meeting - ${dateStr} at ${timeStr}`;
  };
  
  const [sessionName, setSessionName] = useState(getDefaultMeetingName());
  const [npuStatus, setNpuStatus] = useState<'active' | 'idle' | 'error'>('idle');
  const [processingSpeed, setProcessingSpeed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Check NPU status on mount
  useEffect(() => {
    // Check NPU status
    checkNPUStatus();
    const npuInterval = setInterval(checkNPUStatus, 5000);

    return () => {
      clearInterval(npuInterval);
    };
  }, []);

  const checkNPUStatus = async () => {
    try {
      const response = await fetch('/api/system/npu-status');
      const data = await response.json();
      setNpuStatus(data.status);
      setProcessingSpeed(data.processingSpeed || 0);
    } catch (err) {
      setNpuStatus('error');
    }
  };

  const startRecording = async () => {
    if (!sessionName.trim()) {
      setError('Please enter a session name');
      return;
    }

    try {
      // Start countdown (3, 2, 1, Go!)
      setCountdown(3);
      await new Promise(resolve => {
        let count = 3;
        const countInterval = setInterval(() => {
          count--;
          if (count > 0) {
            setCountdown(count);
          } else {
            setCountdown(null);
            clearInterval(countInterval);
            resolve(null);
          }
        }, 1000);
      });
      
      // Create session in backend - using simple API for now to test audio recording
      const response = await fetch('/api/simple/recording-sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: sessionName,
          description: `Recording started at ${new Date().toLocaleString()}`
        })
      });

      if (!response.ok) throw new Error('Failed to create session');
      
      const session = await response.json();
      sessionIdRef.current = session.id;

      // Start recording
      const startResponse = await fetch(`/api/simple/recording-sessions/${session.id}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!startResponse.ok) throw new Error('Failed to start recording');

      // We're recording on the server, not in the browser
      // Start polling for audio levels from the server instead
      startAudioLevelPolling();

      // Start duration timer
      const startTime = Date.now();
      durationIntervalRef.current = setInterval(() => {
        setDuration(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);

      setCurrentSession({
        id: session.id,
        name: sessionName,
        startTime: new Date(),
        duration: 0,
        status: 'recording',
        audioLevel: 0,
        npuActive: true,
        speakerCount: 0,
        wordCount: 0
      });

      setIsRecording(true);
      setSuccess('Recording started successfully');
      setError(null);
    } catch (err) {
      setCountdown(null); // Clear countdown on error
      setError(`Failed to start recording: ${err.message}`);
      console.error('Recording error:', err);
    }
  };

  const stopRecording = async () => {
    if (!sessionIdRef.current) return;

    try {
      // Stop backend recording - using simple API for now
      const stopResponse = await fetch(`/api/simple/recording-sessions/${sessionIdRef.current}/stop`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      // Request LLM to generate a better name based on content
      if (stopResponse.ok) {
        setTimeout(async () => {
          try {
            const renameResponse = await fetch(`/api/simple/recording-sessions/${sessionIdRef.current}/auto-rename`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json'
              }
            });
            
            if (renameResponse.ok) {
              const { newName } = await renameResponse.json();
              setSuccess(`Recording saved as: "${newName}"`);
              
              // Reset for next recording with new default name
              setSessionName(getDefaultMeetingName());
            }
          } catch (err) {
            console.log('Auto-rename not available');
          }
        }, 2000); // Give it 2 seconds for processing to complete
      }

      // Stop timers
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
        durationIntervalRef.current = null;
      }

      // Stop audio level polling
      stopAudioLevelPolling();

      setIsRecording(false);
      setIsPaused(false);
      setDuration(0);
      setAudioLevel(0);
      setSuccess('Recording saved successfully');
      
      // Navigate to session details after 2 seconds
      setTimeout(() => {
        navigate(`/sessions/${sessionIdRef.current}`);
      }, 2000);
    } catch (err) {
      setError(`Failed to stop recording: ${err.message}`);
    }
  };

  const pauseRecording = async () => {
    if (!sessionIdRef.current) return;

    try {
      await fetch(`/api/simple/recording-sessions/${sessionIdRef.current}/pause`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      setIsPaused(!isPaused);
    } catch (err) {
      setError(`Failed to pause recording: ${err.message}`);
    }
  };

  // WebSocket for real audio levels from USB mic
  const audioWsRef = useRef<WebSocket | null>(null);
  
  const startAudioLevelPolling = () => {
    // Connect to the real audio level WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const port = '9050'; // Backend port
    const wsUrl = `${protocol}//${host}:${port}/ws/audio-levels`;
    
    console.log('Connecting to audio level WebSocket:', wsUrl);
    
    try {
      const ws = new WebSocket(wsUrl);
      audioWsRef.current = ws;
      
      ws.onopen = () => {
        console.log('Audio level WebSocket connected');
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // The WebSocket sends level in the format: {"level": value, "timestamp": ...}
          if (data.level !== undefined) {
            setAudioLevel(Math.min(100, Math.max(0, data.level)));
          }
        } catch (err) {
          console.error('Error parsing audio level:', err);
        }
      };
      
      ws.onerror = (error) => {
        console.error('Audio level WebSocket error:', error);
      };
      
      ws.onclose = () => {
        console.log('Audio level WebSocket closed');
        setAudioLevel(0);
      };
    } catch (err) {
      console.error('Failed to connect to audio level WebSocket:', err);
    }
  };
  
  const stopAudioLevelPolling = () => {
    if (audioWsRef.current) {
      audioWsRef.current.close();
      audioWsRef.current = null;
    }
    setAudioLevel(0);
  };

  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Countdown Overlay */}
        {countdown !== null && (
          <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50">
            <div className="text-center">
              <div className="text-9xl font-bold text-white animate-pulse">
                {countdown}
              </div>
              <div className="text-2xl text-gray-300 mt-4">
                Recording starting...
              </div>
            </div>
          </div>
        )}
        
        {/* Header */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h1 className="text-3xl font-bold text-white mb-4">Recording Studio</h1>
          
          {/* NPU Status Bar */}
          <div className="flex items-center justify-between p-4 bg-gray-700 rounded-lg">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Cpu className={`w-5 h-5 ${npuStatus === 'active' ? 'text-green-400' : npuStatus === 'error' ? 'text-red-400' : 'text-yellow-400'}`} />
                <span className="text-sm text-gray-300">NPU Status:</span>
                <span className={`text-sm font-semibold ${npuStatus === 'active' ? 'text-green-400' : npuStatus === 'error' ? 'text-red-400' : 'text-yellow-400'}`}>
                  {npuStatus.toUpperCase()}
                </span>
              </div>
              {npuStatus === 'active' && (
                <div className="flex items-center gap-2">
                  <Zap className="w-5 h-5 text-blue-400" />
                  <span className="text-sm text-gray-300">Processing Speed:</span>
                  <span className="text-sm font-semibold text-blue-400">{processingSpeed}x realtime</span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Activity className="w-4 h-4" />
              <span>AMD Phoenix 16 TOPS</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recording Controls */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-4">Recording Controls</h2>
            
            {/* Session Name Input */}
            {!isRecording && (
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Session Name
                </label>
                <input
                  type="text"
                  value={sessionName}
                  onChange={(e) => setSessionName(e.target.value)}
                  placeholder="Enter meeting name..."
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-purple-500"
                />
              </div>
            )}

            {/* Server Recording Info */}
            {!isRecording && (
              <div className="mb-6 p-3 bg-gray-700 rounded-lg">
                <div className="flex items-center gap-2 text-sm text-gray-300">
                  <Mic className="w-4 h-4" />
                  <span>Recording from server microphone</span>
                </div>
              </div>
            )}

            {/* Recording Status */}
            {isRecording && (
              <div className="mb-6 p-4 bg-gray-700 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                    <span className="text-white font-medium">
                      {isPaused ? 'Paused' : 'Recording'}
                    </span>
                  </div>
                  <span className="text-2xl font-mono text-white">
                    {formatDuration(duration)}
                  </span>
                </div>
                
                {/* Audio Level Meter */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>Audio Level</span>
                    <span>{Math.round(audioLevel)}%</span>
                  </div>
                  <div className="h-2 bg-gray-600 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 transition-all duration-100"
                      style={{ width: `${audioLevel}%` }}
                    />
                  </div>
                </div>
                
                {/* Recording Quality Indicator */}
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-xs text-gray-400">Recording Quality</span>
                  <div className="flex items-center gap-2">
                    {audioLevel < 10 ? (
                      <>
                        <div className="w-2 h-2 bg-red-500 rounded-full" />
                        <span className="text-xs text-red-400">Poor - Check microphone</span>
                      </>
                    ) : audioLevel < 30 ? (
                      <>
                        <div className="w-2 h-2 bg-yellow-500 rounded-full" />
                        <span className="text-xs text-yellow-400">Fair - Speak louder</span>
                      </>
                    ) : audioLevel < 70 ? (
                      <>
                        <div className="w-2 h-2 bg-green-500 rounded-full" />
                        <span className="text-xs text-green-400">Good</span>
                      </>
                    ) : audioLevel < 90 ? (
                      <>
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        <span className="text-xs text-green-400">Excellent</span>
                      </>
                    ) : (
                      <>
                        <div className="w-2 h-2 bg-yellow-500 rounded-full" />
                        <span className="text-xs text-yellow-400">Too loud</span>
                      </>
                    )}
                  </div>
                </div>
                
                {/* NPU Processing Indicator */}
                {npuStatus === 'active' && (
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-xs text-gray-400">NPU Processing</span>
                    <div className="flex items-center gap-1">
                      <Zap className="w-3 h-3 text-green-400 animate-pulse" />
                      <span className="text-xs text-green-400">Active</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Control Buttons */}
            <div className="flex gap-3">
              {!isRecording ? (
                <button
                  onClick={startRecording}
                  className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                >
                  <Mic className="w-5 h-5" />
                  Start Recording
                </button>
              ) : (
                <>
                  <button
                    onClick={pauseRecording}
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors"
                  >
                    {isPaused ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
                    {isPaused ? 'Resume' : 'Pause'}
                  </button>
                  <button
                    onClick={stopRecording}
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gray-600 hover:bg-gray-700 text-white rounded-lg transition-colors"
                  >
                    <Square className="w-5 h-5" />
                    Stop
                  </button>
                </>
              )}
            </div>

            {/* Status Messages */}
            {error && (
              <div className="mt-4 p-3 bg-red-900/50 border border-red-500 rounded-lg flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-red-400" />
                <span className="text-red-400">{error}</span>
              </div>
            )}
            {success && (
              <div className="mt-4 p-3 bg-green-900/50 border border-green-500 rounded-lg flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <span className="text-green-400">{success}</span>
              </div>
            )}

            {/* Session Stats */}
            {currentSession && (
              <div className="mt-6 grid grid-cols-2 gap-4">
                <div className="p-3 bg-gray-700 rounded-lg">
                  <div className="flex items-center gap-2 text-gray-400 mb-1">
                    <Users className="w-4 h-4" />
                    <span className="text-xs">Speakers</span>
                  </div>
                  <span className="text-xl font-semibold text-white">
                    {currentSession.speakerCount}
                  </span>
                </div>
                <div className="p-3 bg-gray-700 rounded-lg">
                  <div className="flex items-center gap-2 text-gray-400 mb-1">
                    <FileText className="w-4 h-4" />
                    <span className="text-xs">Words</span>
                  </div>
                  <span className="text-xl font-semibold text-white">
                    {currentSession.wordCount}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Live Transcription */}
          <div className="bg-gray-800 rounded-lg overflow-hidden">
            <LiveTranscriptionViewer
              sessionId={sessionIdRef.current}
              isRecording={isRecording && !isPaused}
              onSegmentReceived={(segment) => {
                // Update word count and speaker count
                if (currentSession) {
                  const words = segment.text.split(' ').length;
                  setCurrentSession(prev => ({
                    ...prev!,
                    wordCount: prev!.wordCount + words,
                    speakerCount: segment.speaker ? Math.max(prev!.speakerCount, parseInt(segment.speaker.replace('Speaker ', ''), 10)) : prev!.speakerCount
                  }));
                }
              }}
            />
          </div>
        </div>

      </div>
    </div>
  );
};