import { useState, useEffect, useRef } from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { MicIcon, MicOffIcon, PlayIcon, StopCircle as StopIcon, SettingsIcon, UserIcon, ZapIcon, ActivityIcon } from 'lucide-react';

interface SpeakerInfo {
  speakers: Array<{
    id: string;
    label: string;
    total_time: number;
    segments: number;
  }>;
  timeline: Array<{
    start: number;
    end: number;
    duration: number;
    speaker: string;
    confidence: number;
  }>;
  num_speakers: number;
}

interface TranscriptionData {
  text: string;
  timestamp: string;
  confidence: number;
  duration: number;
  processing_time: number;
  npu_accelerated: boolean;
  speaker_info?: SpeakerInfo;
}

interface SystemStatus {
  transcriber_ready: boolean;
  npu_available: boolean;
  speaker_diarization_ready: boolean;
  active_sessions: number;
  system_info: any;
  diarizer_info: any;
}

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [transcriptions, setTranscriptions] = useState<TranscriptionData[]>([]);
  const [audioLevel, setAudioLevel] = useState(0);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [sessionId, setSessionId] = useState<string>('');
  
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationRef = useRef<number>(0);

  // Generate session ID
  useEffect(() => {
    setSessionId(`session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  }, []);

  // Fetch system status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('http://localhost:9050/api/status');
        const status = await response.json();
        setSystemStatus(status);
      } catch (error) {
        console.error('Failed to fetch system status:', error);
      }
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket connection
  const connectWebSocket = () => {
    if (wsRef.current) return;
    
    const ws = new WebSocket(`ws://localhost:9050/ws/stream/${sessionId}`);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      switch (message.type) {
        case 'status':
          console.log('Connection status:', message);
          break;
        case 'transcription':
          setTranscriptions(prev => [...prev, message.data]);
          break;
        case 'audio_level':
          setAudioLevel(message.level);
          break;
        case 'pong':
          console.log('Pong received');
          break;
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      wsRef.current = null;
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };
    
    wsRef.current = ws;
  };

  // Start recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: { 
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        } 
      });
      
      connectWebSocket();
      
      // Create audio context for real-time processing
      audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      const source = audioContextRef.current.createMediaStreamSource(stream);
      
      // Create MediaRecorder for capturing audio
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      
      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          const arrayBuffer = await event.data.arrayBuffer();
          const audioContext = new AudioContext();
          const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
          
          // Convert to 16-bit PCM
          const pcmData = new Int16Array(audioBuffer.length);
          const float32Data = audioBuffer.getChannelData(0);
          
          for (let i = 0; i < float32Data.length; i++) {
            pcmData[i] = Math.max(-32768, Math.min(32767, float32Data[i] * 32767));
          }
          
          // Send audio data
          wsRef.current.send(JSON.stringify({
            type: 'audio_chunk',
            audio_data: btoa(String.fromCharCode(...new Uint8Array(pcmData.buffer)))
          }));
        }
      };
      
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(500); // Send data every 500ms
      setIsRecording(true);
      
    } catch (error) {
      console.error('Error starting recording:', error);
    }
  };

  // Stop recording
  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsRecording(false);
    setIsConnected(false);
    setAudioLevel(0);
  };

  // Audio level animation
  useEffect(() => {
    if (isRecording) {
      const animate = () => {
        // Audio level will decay over time if no new input
        setAudioLevel(prev => Math.max(0, prev * 0.95));
        animationRef.current = requestAnimationFrame(animate);
      };
      animationRef.current = requestAnimationFrame(animate);
    }
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isRecording]);

  const renderDashboard = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
          Unicorn Commander: Meeting Ops
        </h2>
        <div className="flex items-center space-x-2">
          <Badge variant={systemStatus?.transcriber_ready ? "default" : "destructive"}>
            {systemStatus?.transcriber_ready ? "Ready" : "Not Ready"}
          </Badge>
          {systemStatus?.npu_available && (
            <Badge variant="default" className="bg-green-600">
              <ZapIcon className="w-3 h-3 mr-1" />
              NPU Active
            </Badge>
          )}
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="bg-gray-800 border-gray-700">
          <CardHeader>
            <CardTitle className="flex items-center">
              <ActivityIcon className="w-5 h-5 mr-2 text-blue-400" />
              System Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span>Transcriber:</span>
                <span className={systemStatus?.transcriber_ready ? "text-green-400" : "text-red-400"}>
                  {systemStatus?.transcriber_ready ? "Ready" : "Not Ready"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>NPU:</span>
                <span className={systemStatus?.npu_available ? "text-green-400" : "text-yellow-400"}>
                  {systemStatus?.npu_available ? "Available" : "CPU Mode"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Speaker ID:</span>
                <span className={systemStatus?.speaker_diarization_ready ? "text-green-400" : "text-gray-400"}>
                  {systemStatus?.speaker_diarization_ready ? "Ready" : "Not Available"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Active Sessions:</span>
                <span className="text-blue-400">{systemStatus?.active_sessions || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-gray-800 border-gray-700">
          <CardHeader>
            <CardTitle className="flex items-center">
              <MicIcon className="w-5 h-5 mr-2 text-purple-400" />
              Audio Recording
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span>Status:</span>
                <Badge variant={isRecording ? "default" : "secondary"}>
                  {isRecording ? "Recording" : "Stopped"}
                </Badge>
              </div>
              
              {isRecording && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span>Audio Level:</span>
                    <span className="text-green-400">{(audioLevel * 100).toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div 
                      className="bg-gradient-to-r from-green-400 to-blue-400 h-2 rounded-full transition-all duration-100"
                      style={{ width: `${Math.min(100, audioLevel * 100)}%` }}
                    />
                  </div>
                </div>
              )}
              
              <div className="flex justify-center">
                {!isRecording ? (
                  <Button 
                    onClick={startRecording} 
                    className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600"
                    disabled={!systemStatus?.transcriber_ready}
                  >
                    <PlayIcon className="w-4 h-4 mr-2" />
                    Start Recording
                  </Button>
                ) : (
                  <Button 
                    onClick={stopRecording} 
                    variant="destructive"
                    className="animate-pulse"
                  >
                    <StopIcon className="w-4 h-4 mr-2" />
                    Stop Recording
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-gray-800 border-gray-700">
          <CardHeader>
            <CardTitle className="flex items-center">
              <UserIcon className="w-5 h-5 mr-2 text-green-400" />
              Session Info
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span>Connection:</span>
                <Badge variant={isConnected ? "default" : "secondary"}>
                  {isConnected ? "Connected" : "Disconnected"}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span>Session ID:</span>
                <span className="text-xs text-gray-400 truncate">{sessionId.substring(0, 12)}...</span>
              </div>
              <div className="flex justify-between">
                <span>Transcriptions:</span>
                <span className="text-blue-400">{transcriptions.length}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      
      {/* Real-time Transcription Display */}
      <Card className="bg-gray-800 border-gray-700">
        <CardHeader>
          <CardTitle className="flex items-center">
            <ActivityIcon className="w-5 h-5 mr-2 text-yellow-400" />
            Live Transcription
          </CardTitle>
          <CardDescription>
            Real-time NPU-accelerated speech recognition
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 max-h-96 overflow-y-auto">
            {transcriptions.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                {isRecording ? (
                  <div className="animate-pulse">
                    <MicIcon className="w-8 h-8 mx-auto mb-2" />
                    Listening for speech...
                  </div>
                ) : (
                  <div>
                    <MicOffIcon className="w-8 h-8 mx-auto mb-2" />
                    Start recording to see transcriptions
                  </div>
                )}
              </div>
            ) : (
              transcriptions.map((transcript, index) => (
                <div key={index} className="border-l-4 border-blue-500 pl-4 py-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-400">
                      {new Date(transcript.timestamp).toLocaleTimeString()}
                    </span>
                    <div className="flex items-center space-x-2">
                      {transcript.npu_accelerated && (
                        <Badge variant="default" className="bg-green-600 text-xs">
                          <ZapIcon className="w-3 h-3 mr-1" />
                          NPU
                        </Badge>
                      )}
                      {transcript.speaker_info && transcript.speaker_info.num_speakers > 0 && (
                        <Badge variant="default" className="bg-purple-600 text-xs">
                          <UserIcon className="w-3 h-3 mr-1" />
                          {transcript.speaker_info.num_speakers} speakers
                        </Badge>
                      )}
                      <Badge variant="secondary" className="text-xs">
                        {(transcript.processing_time * 1000).toFixed(0)}ms
                      </Badge>
                    </div>
                  </div>
                  <p className="text-white font-medium">{transcript.text}</p>
                  
                  {/* Speaker Information */}
                  {transcript.speaker_info && transcript.speaker_info.speakers.length > 0 && (
                    <div className="mt-2 p-2 bg-gray-700 rounded text-xs">
                      <div className="font-medium text-purple-400 mb-1">Speaker Analysis:</div>
                      <div className="flex flex-wrap gap-2">
                        {transcript.speaker_info.speakers.map((speaker, idx) => (
                          <div key={idx} className="flex items-center space-x-1">
                            <div className="w-2 h-2 bg-purple-400 rounded-full"></div>
                            <span className="text-gray-300">
                              {speaker.id}: {speaker.total_time.toFixed(1)}s
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );

  const renderMeetings = () => (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold">Meeting History</h2>
      <Card className="bg-gray-800 border-gray-700">
        <CardContent className="p-6">
          <div className="text-center text-gray-500 py-8">
            <UserIcon className="w-12 h-12 mx-auto mb-4" />
            <p>No meetings recorded yet</p>
            <p className="text-sm">Start your first recording to see meeting history</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  const renderSettings = () => (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold">Settings</h2>
      <Card className="bg-gray-800 border-gray-700">
        <CardHeader>
          <CardTitle>System Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span>NPU Acceleration</span>
              <Badge variant={systemStatus?.npu_available ? "default" : "secondary"}>
                {systemStatus?.npu_available ? "Enabled" : "Disabled"}
              </Badge>
            </div>
            <Separator className="bg-gray-700" />
            <div className="flex justify-between items-center">
              <span>Audio Sample Rate</span>
              <span className="text-gray-400">16kHz</span>
            </div>
            <Separator className="bg-gray-700" />
            <div className="flex justify-between items-center">
              <span>Model</span>
              <span className="text-gray-400">Whisper Base (ONNX)</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-900 to-purple-900 text-white flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800/50 backdrop-blur-lg border-r border-gray-700 p-4">
        <div className="flex items-center space-x-2 mb-8">
          <div className="w-8 h-8 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
            <ZapIcon className="w-5 h-5" />
          </div>
          <h1 className="text-xl font-bold">Unicorn Commander</h1>
        </div>
        
        <nav className="space-y-2">
          <button
            onClick={() => setCurrentView('dashboard')}
            className={`w-full text-left py-2 px-4 rounded-lg transition-colors ${
              currentView === 'dashboard' 
                ? 'bg-purple-600 text-white' 
                : 'hover:bg-gray-700'
            }`}
          >
            <ActivityIcon className="w-4 h-4 mr-2 inline" />
            Dashboard
          </button>
          <button
            onClick={() => setCurrentView('meetings')}
            className={`w-full text-left py-2 px-4 rounded-lg transition-colors ${
              currentView === 'meetings' 
                ? 'bg-purple-600 text-white' 
                : 'hover:bg-gray-700'
            }`}
          >
            <UserIcon className="w-4 h-4 mr-2 inline" />
            Meetings
          </button>
          <button
            onClick={() => setCurrentView('settings')}
            className={`w-full text-left py-2 px-4 rounded-lg transition-colors ${
              currentView === 'settings' 
                ? 'bg-purple-600 text-white' 
                : 'hover:bg-gray-700'
            }`}
          >
            <SettingsIcon className="w-4 h-4 mr-2 inline" />
            Settings
          </button>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8">
        {currentView === 'dashboard' && renderDashboard()}
        {currentView === 'meetings' && renderMeetings()}
        {currentView === 'settings' && renderSettings()}
      </main>
    </div>
  );
}

export default App;