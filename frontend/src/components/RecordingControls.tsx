import useWebSocket from "../hooks/useWebSocket";
import React, { useState, useEffect, useCallback } from 'react';
import { 
  Mic, 
  MicOff, 
  Square, 
  Play, 
  Pause, 
  AlertCircle,
  CheckCircle,
  Clock,
  Users,
  Volume2,
  Zap
} from 'lucide-react';
import { LiveTranscriptionViewer } from './LiveTranscriptionViewer';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const WS_BASE_URL = (import.meta.env.VITE_API_URL || 'ws://localhost:1950').replace('http', 'ws');

interface RecordingSession {
  session_id: string;
  title: string;
  status: 'recording' | 'paused' | 'stopped';
  start_time: string;
  duration: number;
  speakers_detected?: number;
  audio_level?: number;
  npu_accelerated?: boolean;
}

interface RecordingControlsProps {
  onSessionStart?: (session: RecordingSession) => void;
  onSessionEnd?: (session: RecordingSession) => void;
}

export const RecordingControls: React.FC<RecordingControlsProps> = ({
  onSessionStart,
  onSessionEnd
}) => {
  const [currentSession, setCurrentSession] = useState<RecordingSession | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [sessionTitle, setSessionTitle] = useState('');
  const [audioLevel, setAudioLevel] = useState(0);
const { audioLevel: serverAudioLevel } = useWebSocket('ws://localhost:8000/ws/audio');
  const [error, setError] = useState<string | null>(null);

  // Fetch current session status
  const fetchSessionStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/current`);
      if (response.ok) {
        const session = await response.json();
        setCurrentSession(session);
      } else if (response.status === 404) {
        setCurrentSession(null);
      }
    } catch (error) {
      console.error('Failed to fetch session status:', error);
    }
  }, []);

  useEffect(() => {
    fetchSessionStatus();
    
    // Poll for session status every 2 seconds
    const interval = setInterval(fetchSessionStatus, 2000);
    return () => clearInterval(interval);
  }, [fetchSessionStatus]);

  // WebSocket for real-time audio level monitoring
  useEffect(() => {
    let ws: WebSocket | null = null;
    
    if (currentSession?.status === 'recording') {
      try {
        ws = new WebSocket(`${WS_BASE_URL}/ws/audio-levels`);
        
        ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          setAudioLevel(data.level || 0);
        };
        
        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
        };
      } catch (error) {
        console.error('Failed to connect to audio levels WebSocket:', error);
      }
    }
    
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [currentSession?.status]);

  const startRecording = async () => {
    if (!sessionTitle.trim()) {
      setError('Please enter a session title');
      return;
    }

    setIsStarting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: sessionTitle.trim(),
          description: `Recording session started at ${new Date().toLocaleString()}`
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.statusText}`);
      }

      const session = await response.json();

      // Start the recording
      const startResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${session.session_id}/start`, {
        method: 'POST',
      });

      if (!startResponse.ok) {
        throw new Error(`Failed to start recording: ${startResponse.statusText}`);
      }

      const recordingSession: RecordingSession = {
        session_id: session.session_id,
        title: sessionTitle.trim(),
        status: 'recording',
        start_time: new Date().toISOString(),
        duration: 0,
      };

      setCurrentSession(recordingSession);
      setSessionTitle('');
      
      if (onSessionStart) {
        onSessionStart(recordingSession);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to start recording');
      console.error('Start recording error:', error);
    } finally {
      setIsStarting(false);
    }
  };

  const stopRecording = async () => {
    if (!currentSession) return;

    setIsStopping(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${currentSession.session_id}/stop`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`Failed to stop recording: ${response.statusText}`);
      }

      const stoppedSession = { ...currentSession, status: 'stopped' as const };
      
      if (onSessionEnd) {
        onSessionEnd(stoppedSession);
      }
      
      setCurrentSession(null);
      setAudioLevel(0);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to stop recording');
      console.error('Stop recording error:', error);
    } finally {
      setIsStopping(false);
    }
  };

  const pauseRecording = async () => {
    if (!currentSession) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${currentSession.session_id}/pause`, {
        method: 'POST',
      });

      if (response.ok) {
        setCurrentSession(prev => prev ? { ...prev, status: 'paused' } : null);
      }
    } catch (error) {
      console.error('Pause recording error:', error);
    }
  };

  const resumeRecording = async () => {
    if (!currentSession) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${currentSession.session_id}/start`, {
        method: 'POST',
      });

      if (response.ok) {
        setCurrentSession(prev => prev ? { ...prev, status: 'recording' } : null);
      }
    } catch (error) {
      console.error('Resume recording error:', error);
    }
  };

  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getAudioLevelColor = (level: number): string => {
    if (level < 20) return 'bg-green-500';
    if (level < 60) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className="bg-gray-800 p-6 rounded-xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Recording Controls</h2>
        {currentSession && (
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${
                currentSession.status === 'recording' ? 'bg-red-500 animate-pulse' :
                currentSession.status === 'paused' ? 'bg-yellow-500' : 'bg-gray-500'
              }`}></div>
              <span className="text-sm text-gray-300 capitalize">{currentSession.status}</span>
            </div>
            <div className="flex items-center gap-2">
              <Zap className={`w-4 h-4 ${currentSession.npu_accelerated !== false ? 'text-green-400' : 'text-red-400'}`} />
              <span className="text-sm text-gray-300">
                {currentSession.npu_accelerated !== false ? 'NPU Active' : 'NPU Required'}
              </span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-900/50 border border-red-500 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400">{error}</span>
        </div>
      )}

      {!currentSession ? (
        // Start Recording Form
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Session Title</label>
            <input
              type="text"
              value={sessionTitle}
              onChange={(e) => setSessionTitle(e.target.value)}
              placeholder="Enter meeting title..."
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:border-purple-500 focus:outline-none"
              maxLength={100}
            />
          </div>
          
          <button
            onClick={startRecording}
            disabled={isStarting || !sessionTitle.trim()}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
          >
            {isStarting ? (
              <>
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                Starting...
              </>
            ) : (
              <>
                <Mic className="w-5 h-5" />
                Start Recording
                <span className="text-xs opacity-70">(NPU Accelerated)</span>
              </>
            )}
          </button>
        </div>
      ) : (
        // Active Recording Interface
        <div className="space-y-4">
          <div className="bg-gray-700 p-4 rounded-lg">
            <h3 className="font-semibold mb-2">{currentSession.title}</h3>
            <div className="flex items-center justify-between text-sm text-gray-300">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  <span>{formatDuration(currentSession.duration)}</span>
                </div>
                {currentSession.speakers_detected && (
                  <div className="flex items-center gap-1">
                    <Users className="w-4 h-4" />
                    <span>{currentSession.speakers_detected} speakers</span>
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-400">
                Started: {new Date(currentSession.start_time).toLocaleTimeString()}
              </div>
            </div>
          </div>

          {/* Audio Level Monitor */}
          {currentSession.status === 'recording' && (
            <div className="bg-gray-700 p-4 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Volume2 className="w-4 h-4 text-blue-400" />
                  <span className="text-sm">Audio Level</span>
                </div>
                <span className="text-sm text-gray-400">{audioLevel.toFixed(1)} dB</span>
              </div>
              <div className="w-full bg-gray-800 rounded-full h-2">
                <div 
                  className={`h-2 rounded-full transition-all duration-200 ${getAudioLevelColor(audioLevel)}`}
                  style={{ width: `${Math.min(audioLevel, 100)}%` }}
                ></div>
              </div>
            </div>
          )}

          {/* Control Buttons */}
          <div className="flex gap-3">
            {currentSession.status === 'recording' ? (
              <>
                <button
                  onClick={pauseRecording}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg font-medium transition-colors"
                >
                  <Pause className="w-4 h-4" />
                  Pause
                </button>
                <button
                  onClick={stopRecording}
                  disabled={isStopping}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded-lg font-medium transition-colors"
                >
                  {isStopping ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                  Stop
                </button>
              </>
            ) : currentSession.status === 'paused' ? (
              <>
                <button
                  onClick={resumeRecording}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-medium transition-colors"
                >
                  <Play className="w-4 h-4" />
                  Resume
                </button>
                <button
                  onClick={stopRecording}
                  disabled={isStopping}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded-lg font-medium transition-colors"
                >
                  {isStopping ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                  Stop
                </button>
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* Live Transcription */}
      {currentSession && (
        <div className="mt-6">
          <LiveTranscriptionViewer 
            sessionId={currentSession.session_id}
            isRecording={currentSession.status === 'recording'}
            onSegmentReceived={(segment) => {
              console.log('Received transcription segment:', segment);
            }}
          />
        </div>
      )}
    </div>
  );
};