import { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Square, Download, Loader2 } from 'lucide-react';

interface RecordingInterfaceProps {
  token: string;
  apiBaseUrl: string;
}

interface Session {
  session_id: string;
  title: string;
  status: string;
  created_at: string;
}

export function RecordingInterface({ token, apiBaseUrl }: RecordingInterfaceProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [transcription, setTranscription] = useState<string[]>([]);
  const [audioLevel, setAudioLevel] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const wsRef = useRef<WebSocket | null>(null);
  const audioWsRef = useRef<WebSocket | null>(null);

  // Cleanup WebSockets on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (audioWsRef.current) {
        audioWsRef.current.close();
      }
    };
  }, []);

  // Connect to audio level WebSocket
  useEffect(() => {
    const connectAudioWs = () => {
      // Use relative URL to work with Vite proxy
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const ws = new WebSocket(`${protocol}//${host}/ws/audio-levels`);
      
      ws.onopen = () => {
        console.log('Audio level WebSocket connected');
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Audio level data:', data);
        if (data.type === 'audio_level') {
          // Convert from 0-1 range to 0-100 percentage
          const level = (data.level || 0) * 100;
          console.log('Setting audio level to:', level);
          setAudioLevel(level);
        }
      };

      ws.onerror = (error) => {
        console.error('Audio WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('Audio WebSocket closed');
        // Reconnect after 2 seconds
        setTimeout(connectAudioWs, 2000);
      };

      audioWsRef.current = ws;
    };

    connectAudioWs();

    return () => {
      if (audioWsRef.current) {
        audioWsRef.current.close();
      }
    };
  }, []);

  const startRecording = async () => {
    setLoading(true);
    setError('');

    try {
      // Create a new session
      const createResponse = await fetch(`${apiBaseUrl}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: `Meeting ${new Date().toLocaleString()}`,
          description: 'Recording from Meeting-Ops appliance'
        }),
      });

      if (!createResponse.ok) {
        throw new Error('Failed to create session');
      }

      const session = await createResponse.json();
      setCurrentSession(session);

      // Start recording
      const startResponse = await fetch(`${apiBaseUrl}/api/recording-sessions/${session.session_id}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!startResponse.ok) {
        throw new Error('Failed to start recording');
      }

      setIsRecording(true);
      setTranscription([]);

      // Connect to transcription WebSocket
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const ws = new WebSocket(`${protocol}//${host}/ws/stream/${session.session_id}?token=${token}`);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.transcription?.text) {
          setTranscription(prev => [...prev, data.transcription.text]);
        }
      };

      ws.onerror = (error) => {
        console.error('Transcription WebSocket error:', error);
      };

      wsRef.current = ws;

    } catch (err) {
      setError('Failed to start recording');
      console.error('Start recording error:', err);
    } finally {
      setLoading(false);
    }
  };

  const stopRecording = async () => {
    if (!currentSession) return;

    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${apiBaseUrl}/api/recording-sessions/${currentSession.session_id}/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to stop recording');
      }

      setIsRecording(false);
      
      // Close transcription WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

    } catch (err) {
      setError('Failed to stop recording');
      console.error('Stop recording error:', err);
    } finally {
      setLoading(false);
    }
  };

  const exportTranscript = async () => {
    if (!currentSession) return;

    try {
      const response = await fetch(`${apiBaseUrl}/api/recording-sessions/${currentSession.session_id}/export?format=txt`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcript-${currentSession.session_id}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }
    } catch (err) {
      console.error('Export error:', err);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold mb-4">Recording Control</h2>
      
      {error && (
        <div className="text-red-400 text-sm mb-4">{error}</div>
      )}

      <div className="space-y-6">
        {/* Recording Controls */}
        <div className="flex items-center justify-center space-x-4">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={loading}
            className={`p-6 rounded-full transition-all ${
              isRecording
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-purple-600 hover:bg-purple-700'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {loading ? (
              <Loader2 className="h-8 w-8 animate-spin" />
            ) : isRecording ? (
              <Square className="h-8 w-8" />
            ) : (
              <Mic className="h-8 w-8" />
            )}
          </button>
        </div>

        {/* Recording Status */}
        <div className="text-center">
          {isRecording ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="h-3 w-3 bg-red-500 rounded-full animate-pulse" />
              <span className="text-lg">Recording in progress...</span>
            </div>
          ) : (
            <span className="text-gray-400">Ready to record</span>
          )}
        </div>

        {/* Audio Level Meter */}
        <div className="space-y-2 p-4 bg-gray-800 rounded-lg border border-purple-500">
          <div className="flex items-center justify-between text-sm">
            <span className="text-white font-semibold">🎤 USB Microphone Level</span>
            <span className="text-lg font-bold text-purple-400">{Math.round(audioLevel)}%</span>
          </div>
          <div className="w-full bg-gray-900 rounded-full h-6 overflow-hidden">
            <div 
              className={`h-full rounded-full transition-all duration-100 ${
                audioLevel > 80 ? 'bg-red-500' : 
                audioLevel > 50 ? 'bg-yellow-500' : 
                'bg-green-500'
              }`}
              style={{ width: `${audioLevel}%` }}
            />
          </div>
          <div className="text-xs text-gray-500">
            {audioWsRef.current?.readyState === WebSocket.OPEN ? (
              <span className="text-green-400">✓ Connected to audio stream</span>
            ) : (
              <span className="text-red-400">✗ Disconnected from audio stream</span>
            )}
          </div>
        </div>

        {/* Live Transcription */}
        {isRecording && transcription.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-300">Live Transcription</h3>
              <button
                onClick={exportTranscript}
                className="text-sm text-purple-400 hover:text-purple-300 flex items-center space-x-1"
              >
                <Download className="h-4 w-4" />
                <span>Export</span>
              </button>
            </div>
            <div className="bg-gray-900 rounded p-4 max-h-48 overflow-y-auto">
              {transcription.map((text, index) => (
                <p key={index} className="text-sm text-gray-300 mb-2">
                  {text}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Current Session Info */}
        {currentSession && !isRecording && (
          <div className="bg-gray-900 rounded p-4">
            <h3 className="text-sm font-medium text-gray-300 mb-2">Last Recording</h3>
            <div className="text-sm text-gray-400">
              <p>Session ID: {currentSession.session_id}</p>
              <p>Title: {currentSession.title}</p>
              <button
                onClick={exportTranscript}
                className="mt-2 text-purple-400 hover:text-purple-300 flex items-center space-x-1"
              >
                <Download className="h-4 w-4" />
                <span>Download Transcript</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}