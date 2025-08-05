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
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [currentSession, setCurrentSession] = useState<RecordingSession | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [duration, setDuration] = useState(0);
  const [sessionName, setSessionName] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('default');
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [npuStatus, setNpuStatus] = useState<'active' | 'idle' | 'error'>('idle');
  const [processingSpeed, setProcessingSpeed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Get audio devices on mount
  useEffect(() => {
    navigator.mediaDevices.enumerateDevices().then(devices => {
      const audioInputs = devices.filter(device => device.kind === 'audioinput');
      setAudioDevices(audioInputs);
    });

    // Check NPU status
    checkNPUStatus();
    const npuInterval = setInterval(checkNPUStatus, 5000);

    return () => {
      clearInterval(npuInterval);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
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
      // Create session in backend
      const response = await fetch('/api/recording-sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
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
      const startResponse = await fetch(`/api/recording-sessions/${session.id}/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (!startResponse.ok) throw new Error('Failed to start recording');

      // Get user media
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          deviceId: selectedDevice === 'default' ? undefined : selectedDevice,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });

      audioStreamRef.current = stream;

      // Setup audio analysis
      audioContextRef.current = new AudioContext();
      analyserRef.current = audioContextRef.current.createAnalyser();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);
      analyserRef.current.fftSize = 256;

      // Start audio level monitoring
      monitorAudioLevel();

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
      setError(`Failed to start recording: ${err.message}`);
      console.error('Recording error:', err);
    }
  };

  const stopRecording = async () => {
    if (!sessionIdRef.current) return;

    try {
      // Stop backend recording
      await fetch(`/api/recording-sessions/${sessionIdRef.current}/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      // Stop media stream
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(track => track.stop());
        audioStreamRef.current = null;
      }

      // Stop audio context
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }

      // Stop timers
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
        durationIntervalRef.current = null;
      }

      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }

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
      await fetch(`/api/recording-sessions/${sessionIdRef.current}/pause`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      setIsPaused(!isPaused);
    } catch (err) {
      setError(`Failed to pause recording: ${err.message}`);
    }
  };

  const monitorAudioLevel = () => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    // Calculate average volume
    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    setAudioLevel(Math.min(100, (average / 128) * 100));

    animationRef.current = requestAnimationFrame(monitorAudioLevel);
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

            {/* Audio Device Selection */}
            {!isRecording && (
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Audio Input Device
                </label>
                <select
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="default">Default Device</option>
                  {audioDevices.map(device => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.label || `Device ${device.deviceId.substring(0, 8)}`}
                    </option>
                  ))}
                </select>
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

        {/* Quick Actions */}
        <div className="mt-6 bg-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <button
              onClick={() => navigate('/sessions')}
              className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg text-center transition-colors"
            >
              <FileText className="w-6 h-6 text-blue-400 mx-auto mb-2" />
              <span className="text-sm text-gray-300">View Sessions</span>
            </button>
            <button
              onClick={() => navigate('/templates')}
              className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg text-center transition-colors"
            >
              <Settings className="w-6 h-6 text-purple-400 mx-auto mb-2" />
              <span className="text-sm text-gray-300">Templates</span>
            </button>
            <button
              onClick={() => navigate('/analytics')}
              className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg text-center transition-colors"
            >
              <Activity className="w-6 h-6 text-green-400 mx-auto mb-2" />
              <span className="text-sm text-gray-300">Analytics</span>
            </button>
            <button
              onClick={() => navigate('/settings')}
              className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg text-center transition-colors"
            >
              <Settings className="w-6 h-6 text-gray-400 mx-auto mb-2" />
              <span className="text-sm text-gray-300">Settings</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};