import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, 
  MicOff, 
  Play, 
  Square, 
  Download, 
  FileText,
  Activity,
  Clock,
  Cpu,
  HardDrive,
  Zap,
  Settings,
  Users,
  BarChart
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { AlwaysOnTranscription } from './AlwaysOnTranscription';

interface SessionData {
  session_id: string;
  name: string;
  status: string;
  created_at: string;
  duration?: number;
  transcriptions?: any[];
}

export const ProductionDashboard: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [currentSession, setCurrentSession] = useState<SessionData | null>(null);
  const [recentSessions, setRecentSessions] = useState<SessionData[]>([]);
  const [audioLevel, setAudioLevel] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [systemStatus, setSystemStatus] = useState<any>({});
  const [liveTranscript, setLiveTranscript] = useState('');
  const [isStopping, setIsStopping] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptionWsRef = useRef<WebSocket | null>(null);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetchRecentSessions();
    fetchSystemStatus();
    
    const interval = setInterval(() => {
      fetchSystemStatus();
    }, 5000);
    
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isRecording && !isPaused) {
      durationIntervalRef.current = setInterval(() => {
        setRecordingDuration(prev => prev + 1);
      }, 1000);
    } else {
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
    }
    
    return () => {
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
    };
  }, [isRecording, isPaused]);

  useEffect(() => {
    // Connect to audio levels WebSocket
    connectAudioLevelWS();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectAudioLevelWS = () => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/audio-levels`;
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'audio_level') {
            setAudioLevel(Math.min(1, Math.max(0, data.level || 0)));
          }
        } catch (e) {
          console.error('Error parsing audio level:', e);
        }
      };

      ws.onerror = () => {
        // Reconnect after 2 seconds
        setTimeout(connectAudioLevelWS, 2000);
      };

      ws.onclose = () => {
        // Reconnect after 2 seconds
        setTimeout(connectAudioLevelWS, 2000);
      };
    } catch (error) {
      console.error('Failed to connect to audio levels:', error);
    }
  };

  const fetchRecentSessions = async () => {
    try {
      const response = await fetch('/api/recording-sessions?limit=5', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setRecentSessions(data.sessions || []);
      }
    } catch (error) {
      console.error('Error fetching sessions:', error);
    }
  };

  const fetchSystemStatus = async () => {
    try {
      const response = await fetch('/api/status');
      if (response.ok) {
        const data = await response.json();
        setSystemStatus(data);
      }
    } catch (error) {
      console.error('Error fetching status:', error);
    }
  };

  const startRecording = async () => {
    try {
      // Create new session
      const sessionResponse = await fetch('/api/recording-sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          name: `Recording ${new Date().toLocaleTimeString()}`,
          description: 'Voice recording session',
          meeting_type: 'audio_recording'
        })
      });

      if (!sessionResponse.ok) {
        throw new Error('Failed to create session');
      }

      const sessionData = await sessionResponse.json();
      const session = sessionData.session;
      setCurrentSession(session);

      // Start recording
      const startResponse = await fetch(`/api/recording-sessions/${session.session_id}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (!startResponse.ok) {
        throw new Error('Failed to start recording');
      }

      setIsRecording(true);
      setRecordingDuration(0);
      setLiveTranscript('');
      
      // Connect to transcription WebSocket
      connectTranscriptionWS(session.session_id);
      
    } catch (error) {
      console.error('Error starting recording:', error);
      alert('Failed to start recording. Please try again.');
    }
  };

  const stopRecording = async () => {
    if (!currentSession || isStopping) return;

    setIsStopping(true);
    
    try {
      const response = await fetch(`/api/recording-sessions/${currentSession.session_id}/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to stop recording');
      }

      setIsRecording(false);
      setIsPaused(false);
      setRecordingDuration(0);
      setCurrentSession(null);
      
      // Close transcription WebSocket
      if (transcriptionWsRef.current) {
        transcriptionWsRef.current.close();
        transcriptionWsRef.current = null;
      }
      
      // Refresh sessions list
      fetchRecentSessions();
      
    } catch (error) {
      console.error('Error stopping recording:', error);
      alert('Failed to stop recording. Please try again.');
    } finally {
      setIsStopping(false);
    }
  };

  const pauseRecording = async () => {
    if (!currentSession) return;

    try {
      const response = await fetch(`/api/recording-sessions/${currentSession.session_id}/pause`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to pause recording');
      }

      setIsPaused(!isPaused);
      
    } catch (error) {
      console.error('Error pausing recording:', error);
    }
  };

  const connectTranscriptionWS = (sessionId: string) => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/stream/${sessionId}`;
      
      const ws = new WebSocket(wsUrl);
      transcriptionWsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Transcription WS received:', data);
          if (data.type === 'transcription' && data.data?.text) {
            setLiveTranscript(prev => prev + ' ' + data.data.text);
          } else if (data.transcription) {
            // Handle alternative format
            setLiveTranscript(prev => prev + ' ' + data.transcription);
          } else if (data.text) {
            // Handle direct text format
            setLiveTranscript(prev => prev + ' ' + data.text);
          }
        } catch (e) {
          console.error('Error parsing transcription:', e);
        }
      };

      ws.onerror = (error) => {
        console.error('Transcription WebSocket error:', error);
      };
      
      ws.onclose = () => {
        transcriptionWsRef.current = null;
      };

    } catch (error) {
      console.error('Failed to connect to transcription:', error);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const downloadSession = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/recording-sessions/${sessionId}/export?format=txt`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (!response.ok) throw new Error('Failed to download');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transcript_${sessionId}.txt`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading session:', error);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">
          Welcome back, {user?.full_name || user?.username}
        </h1>
        <p className="text-gray-400">
          Start recording to capture and transcribe your audio with NPU acceleration
        </p>
        
        
      </div>

      {/* Main Recording Interface */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Recording Controls */}
        <div className="lg:col-span-2 bg-gray-800 rounded-xl p-6">
          <h2 className="text-xl font-semibold text-white mb-6">Recording Studio</h2>
          
          {/* Audio Level Meter */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-400">Audio Input Level</span>
              <div className="flex items-center gap-2">
                {audioLevel > 0.01 ? (
                  <Activity className="w-4 h-4 text-green-400" />
                ) : (
                  <Activity className="w-4 h-4 text-gray-600" />
                )}
                <span className="text-xs text-gray-500">
                  {audioLevel > 0.01 ? 'Detecting audio' : 'No audio'}
                </span>
              </div>
            </div>
            
            <div className="relative h-6 bg-gray-700 rounded-full overflow-hidden">
              <div 
                className="absolute inset-y-0 left-0 transition-all duration-100"
                style={{
                  width: `${audioLevel * 100}%`,
                  background: audioLevel > 0.8 
                    ? 'linear-gradient(to right, #10b981, #f59e0b, #ef4444)'
                    : audioLevel > 0.5
                    ? 'linear-gradient(to right, #10b981, #f59e0b)'
                    : '#10b981'
                }}
              />
              
              {/* Level markers */}
              <div className="absolute inset-0 flex items-center">
                {[25, 50, 75].map(mark => (
                  <div
                    key={mark}
                    className="absolute w-px h-full bg-gray-600 opacity-50"
                    style={{ left: `${mark}%` }}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Recording Status */}
          {isRecording && (
            <div className="mb-6 p-4 bg-gray-700 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                    <div className="absolute inset-0 w-3 h-3 bg-red-400 rounded-full animate-ping"></div>
                  </div>
                  <span className="text-white font-medium">
                    {isPaused ? 'Recording Paused' : 'Recording...'}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <Clock className="w-4 h-4" />
                  <span className="font-mono">{formatDuration(recordingDuration)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Control Buttons */}
          <div className="flex items-center justify-center gap-4">
            {!isRecording ? (
              <button
                onClick={startRecording}
                className="flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl hover:from-purple-700 hover:to-pink-700 transition-all transform hover:scale-105 shadow-lg"
              >
                <Mic className="w-6 h-6" />
                <span className="text-lg font-semibold">Start Recording</span>
              </button>
            ) : (
              <>
                <button
                  onClick={pauseRecording}
                  className="p-4 bg-gray-700 text-white rounded-xl hover:bg-gray-600 transition-colors"
                >
                  {isPaused ? <Play className="w-6 h-6" /> : <MicOff className="w-6 h-6" />}
                </button>
                <button
                  onClick={stopRecording}
                  disabled={isStopping}
                  className={`flex items-center gap-3 px-8 py-4 text-white rounded-xl transition-colors shadow-lg ${
                    isStopping 
                      ? 'bg-gray-600 cursor-not-allowed' 
                      : 'bg-red-600 hover:bg-red-700'
                  }`}
                >
                  <Square className="w-6 h-6" />
                  <span className="text-lg font-semibold">
                    {isStopping ? 'Stopping...' : 'Stop Recording'}
                  </span>
                </button>
              </>
            )}
          </div>

          {/* Always-On Live Transcription */}
          <div className="mt-6">
            <AlwaysOnTranscription 
              userRole="admin"
              maxBufferMinutes={10}
              className="h-full"
            />
          </div>
        </div>

        {/* System Status */}
        <div className="bg-gray-800 rounded-xl p-6">
          <h2 className="text-xl font-semibold text-white mb-6">System Status</h2>
          
          <div className="space-y-4">
            {/* NPU Status */}
            <div className="flex items-center justify-between p-3 bg-gray-700 rounded-lg">
              <div className="flex items-center gap-3">
                <Cpu className="w-5 h-5 text-purple-400" />
                <span className="text-gray-300">NPU Acceleration</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-xs text-green-400">Active</span>
              </div>
            </div>

            {/* Transcription Engine */}
            <div className="flex items-center justify-between p-3 bg-gray-700 rounded-lg">
              <div className="flex items-center gap-3">
                <Zap className="w-5 h-5 text-yellow-400" />
                <span className="text-gray-300">Whisper Engine</span>
              </div>
              <span className="text-xs text-green-400">
                {systemStatus.transcriber_ready ? 'Ready' : 'Loading...'}
              </span>
            </div>

            {/* Storage */}
            <div className="flex items-center justify-between p-3 bg-gray-700 rounded-lg">
              <div className="flex items-center gap-3">
                <HardDrive className="w-5 h-5 text-blue-400" />
                <span className="text-gray-300">Storage</span>
              </div>
              <span className="text-xs text-gray-400">
                {recentSessions.length} sessions
              </span>
            </div>
          </div>

          {/* NPU Performance */}
          <div className="mt-6 p-4 bg-gradient-to-r from-purple-900/50 to-pink-900/50 rounded-lg border border-purple-700/50">
            <h3 className="text-sm font-medium text-gray-300 mb-2">NPU Performance</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Processing Speed</span>
                <span className="text-green-400">0.06x Real-time</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Model</span>
                <span className="text-gray-300">Whisper Base</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Hardware</span>
                <span className="text-gray-300">AMD NPU</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Sessions */}
      <div className="bg-gray-800 rounded-xl p-6">
        <h2 className="text-xl font-semibold text-white mb-6">Recent Recordings</h2>
        
        {recentSessions.length > 0 ? (
          <div className="space-y-3">
            {recentSessions.map((session) => (
              <div
                key={session.session_id}
                className="flex items-center justify-between p-4 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <FileText className="w-5 h-5 text-gray-400" />
                  <div>
                    <h4 className="text-white font-medium">{session.name}</h4>
                    <p className="text-sm text-gray-400">
                      {new Date(session.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-400">
                    {session.transcriptions?.length || 0} segments
                  </span>
                  <button
                    onClick={() => downloadSession(session.session_id)}
                    className="p-2 text-gray-400 hover:text-white transition-colors"
                    title="Download transcript"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-400 text-center py-8">
            No recordings yet. Start recording to see your sessions here.
          </p>
        )}
      </div>
    </div>
  );
};