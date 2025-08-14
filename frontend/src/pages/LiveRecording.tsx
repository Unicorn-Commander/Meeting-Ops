import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, 
  MicOff, 
  Play, 
  Pause, 
  FileText, 
  ListChecks, 
  Flag, 
  Users, 
  Clock, 
  Sparkles,
  Activity,
  Cpu,
  HardDrive,
  CheckCircle,
  AlertCircle,
  Volume2
} from 'lucide-react';
import { config } from '../config';

interface SummaryFormats {
  executive: boolean;
  minutes: boolean;
  bullets: boolean;
  actions: boolean;
  decisions: boolean;
  tasks: boolean;
  transcript: boolean;
}

interface ActionItem {
  id: string;
  action: string;
  owner?: string;
  dueDate?: string;
  status: 'pending' | 'completed';
}

interface SessionData {
  id: string;
  title: string;
  startTime: string;
  duration: number;
  isRecording: boolean;
  transcript: string;
  summary?: {
    executive?: string;
    bullets?: string[];
    actions?: ActionItem[];
    decisions?: string[];
    tasks?: Array<{task: string; assignee: string}>;
  };
}

export default function LiveRecording() {
  // Check for existing recording session on mount
  const getStoredSession = () => {
    const stored = localStorage.getItem('activeRecordingSession');
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch (e) {
        console.error('Failed to parse stored session:', e);
        localStorage.removeItem('activeRecordingSession');
      }
    }
    return null;
  };

  const storedSession = getStoredSession();
  
  const [isRecording, setIsRecording] = useState(storedSession?.isRecording || false);
  const [sessionData, setSessionData] = useState<SessionData | null>(storedSession);
  const [audioLevel, setAudioLevel] = useState(0);
  const [duration, setDuration] = useState(storedSession?.duration || 0);
  const [summaryFormats, setSummaryFormats] = useState<SummaryFormats>({
    executive: true,
    minutes: false,
    bullets: true,
    actions: true,
    decisions: true,
    tasks: false,
    transcript: false
  });
  const [liveTranscript, setLiveTranscript] = useState<string[]>([]);
  const [wordCount, setWordCount] = useState(0);
  const [lastSummaryWordCount, setLastSummaryWordCount] = useState(0);
  const [audioDevices, setAudioDevices] = useState<any[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  
  const wsRef = useRef<WebSocket | null>(null);
  const audioWsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<Date | null>(storedSession && storedSession.startTime ? (() => {
    const date = new Date(storedSession.startTime);
    return isNaN(date.getTime()) ? null : date;
  })() : null);
  const AUTO_SUMMARY_WORD_THRESHOLD = 100; // Summarize every 100 words

  // Save session state to localStorage whenever it changes
  useEffect(() => {
    if (sessionData) {
      const toStore = {
        ...sessionData,
        isRecording,
        duration,
        startTime: startTimeRef.current ? startTimeRef.current.toISOString() : sessionData.startTime
      };
      localStorage.setItem('activeRecordingSession', JSON.stringify(toStore));
    } else if (!isRecording) {
      localStorage.removeItem('activeRecordingSession');
    }
  }, [sessionData, isRecording, duration]);

  // Reconnect to existing session if stored
  useEffect(() => {
    if (storedSession && storedSession.isRecording && storedSession.id) {
      console.log('Reconnecting to existing session:', storedSession.id);
      
      // Reconnect WebSocket for live transcription for this session
      const ws = new WebSocket(`${config.wsEndpoints.base}/ws/transcription/${storedSession.id}`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Handle live transcription segments
          if (data.type === 'transcription') {
            // Handle both formats: data.segment and data.text
            const text = data.segment?.text || data.text || '';
            if (text.trim()) {
              console.log('Live transcription (reconnected):', text);
              setLiveTranscript(prev => [...prev, text]);
              
              // Count words for auto-summary trigger
              const words = text.split(/\s+/).filter(w => w.length > 0).length;
              setWordCount(prev => {
                const newCount = prev + words;
                
                // Check if we should trigger summary generation
                if (newCount - lastSummaryWordCount >= AUTO_SUMMARY_WORD_THRESHOLD) {
                  console.log(`Triggering auto-summary at ${newCount} words`);
                  triggerSummaryGeneration(storedSession.id);
                  setLastSummaryWordCount(newCount);
                }
                
                return newCount;
              });
            }
          } else if (data.type === 'status') {
            console.log('Transcription loop status:', data.data);
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      wsRef.current = ws;
      
      // Audio levels are already connected via the always-on WebSocket
    }
    
    return () => {
      if (wsRef.current) wsRef.current.close();
      // Keep audio levels WebSocket running
    };
  }, []);

  // Connect to audio levels WebSocket (always on for monitoring)
  useEffect(() => {
    const connectAudioLevels = () => {
      const audioWs = new WebSocket(`${config.wsEndpoints.base}/ws/audio-levels`);
      
      audioWs.onopen = () => {
        console.log('Connected to audio level monitoring');
      };
      
      audioWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'audio_level' || data.level !== undefined) {
            setAudioLevel(data.level || data.audio_level || 0);
          }
        } catch (e) {
          console.error('Error parsing audio level:', e);
        }
      };
      
      audioWs.onerror = (error) => {
        console.error('Audio level WebSocket error:', error);
      };
      
      audioWs.onclose = () => {
        console.log('Audio level WebSocket closed, reconnecting in 2s...');
        setTimeout(connectAudioLevels, 2000);
      };
      
      audioWsRef.current = audioWs;
    };
    
    connectAudioLevels();
    
    return () => {
      if (audioWsRef.current) {
        audioWsRef.current.close();
      }
    };
  }, []); // Connect once on mount
  
  // Check audio devices
  useEffect(() => {
    const checkDevices = async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/simple/audio-devices`);
        if (response.ok) {
          const data = await response.json();
          const devices = data.devices || data; // Handle both formats
          
          // Map devices to expected format
          const mappedDevices = devices.map((device: any) => ({
            id: device.deviceId || device.id || `hw:${device.index},0`,
            deviceId: device.deviceId || device.id || `hw:${device.index},0`,
            label: device.label || device.name || 'Unknown Device',
            name: device.name || device.label || 'Unknown Device',
            ...device
          }));
          
          setAudioDevices(mappedDevices);
          if (mappedDevices.length > 0 && !selectedDevice) {
            setSelectedDevice(mappedDevices[0].id || mappedDevices[0].deviceId);
          }
        }
      } catch (error) {
        console.error('Failed to fetch audio devices:', error);
      }
    };
    checkDevices();
  }, []);

  // Duration timer
  useEffect(() => {
    if (isRecording && startTimeRef.current) {
      // Calculate initial duration if reconnecting
      const now = new Date();
      const elapsed = Math.floor((now.getTime() - startTimeRef.current.getTime()) / 1000);
      setDuration(elapsed);
      
      intervalRef.current = setInterval(() => {
        const currentTime = new Date();
        const elapsedSeconds = Math.floor((currentTime.getTime() - startTimeRef.current!.getTime()) / 1000);
        setDuration(elapsedSeconds);
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRecording]);

  const triggerSummaryGeneration = async (sessionId: string) => {
    try {
      // Trigger AI summary generation
      const response = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${sessionId}/insights`,
        { method: 'POST' }
      );
      
      if (response.ok) {
        const insights = await response.json();
        setSessionData(prev => prev ? {
          ...prev,
          summary: insights
        } : null);
      }
    } catch (error) {
      console.error('Failed to generate summary:', error);
    }
  };

  const formatDuration = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const startRecording = async () => {
    console.log('Starting recording...');
    try {
      // Create session
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          name: `Meeting ${new Date().toLocaleString()}`,
          description: 'Recording from Meeting-Ops'
        })
      });
      
      if (!response.ok) {
        const error = await response.text();
        console.error('Failed to create session:', error);
        throw new Error(`Failed to create session: ${error}`);
      }
      const session = await response.json();
      console.log('Session created:', session);
      
      // Start recording
      const startResponse = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${session.id}/start`,
        { method: 'POST' }
      );
      
      if (!startResponse.ok) {
        const error = await startResponse.text();
        console.error('Failed to start recording:', error);
        throw new Error(`Failed to start recording: ${error}`);
      }
      
      const startData = await startResponse.json();
      console.log('Recording started:', startData);
      
      const newSession = {
        id: session.id,
        title: session.title || session.name,
        startTime: new Date().toISOString(),
        duration: 0,
        isRecording: true,
        transcript: ''
      };
      
      setSessionData(newSession);
      startTimeRef.current = new Date();
      setWordCount(0);
      setLastSummaryWordCount(0);
      
      // Connect WebSocket for live transcription for this session
      const ws = new WebSocket(`${config.wsEndpoints.base}/ws/transcription/${session.id}`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message received:', data);
          
          // Handle live transcription segments
          if (data.type === 'transcription') {
            // Handle both formats: data.segment and data.text
            const text = data.segment?.text || data.text || '';
            if (text.trim()) {
              console.log('Live transcription received:', text);
              setLiveTranscript(prev => [...prev, text]);
              
              // Count words for auto-summary trigger
              const words = text.split(/\s+/).filter(w => w.length > 0).length;
              setWordCount(prev => {
                const newCount = prev + words;
                
                // Check if we should trigger summary generation
                if (newCount - lastSummaryWordCount >= AUTO_SUMMARY_WORD_THRESHOLD) {
                  console.log(`Triggering auto-summary at ${newCount} words`);
                  triggerSummaryGeneration(session.id);
                  setLastSummaryWordCount(newCount);
                }
                
                return newCount;
              });
            }
          } else if (data.type === 'status') {
            console.log('Transcription loop status:', data.data);
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      wsRef.current = ws;
      
      // Audio levels are already connected via the always-on WebSocket
      
      setIsRecording(true);
      setDuration(0);
      
      // Show success feedback
      console.log('Recording started successfully!');
    } catch (error: any) {
      console.error('Failed to start recording:', error);
      alert(`Failed to start recording: ${error.message}`);
      setIsRecording(false);
    }
  };

  const stopRecording = async () => {
    if (!sessionData) {
      console.error('No session data to stop');
      return;
    }
    
    console.log('Stopping recording...');
    try {
      const stopResponse = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${sessionData.id}/stop`,
        { method: 'POST' }
      );
      
      if (!stopResponse.ok) {
        console.error('Stop response not ok');
      }
      
      // Clean up transcription WebSocket only (keep audio levels running)
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      
      setIsRecording(false);
      // Keep audio level monitoring active
      startTimeRef.current = null;
      localStorage.removeItem('activeRecordingSession');
      
      // Fetch final session data with AI summaries
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions/${sessionData.id}`);
      if (response.ok) {
        const finalData = await response.json();
        setSessionData(prev => ({
          ...prev!,
          isRecording: false,
          transcript: finalData.transcript_text || liveTranscript.join(' '),
          summary: finalData.ai_insights
        }));
      }
    } catch (error) {
      console.error('Failed to stop recording:', error);
    }
  };

  const toggleFormat = (format: keyof SummaryFormats) => {
    setSummaryFormats(prev => ({ ...prev, [format]: !prev[format] }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100 p-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fuchsia-500 to-indigo-500 flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              Live Recording
            </h1>
            <p className="text-zinc-400 mt-1">AI-powered meeting intelligence in real-time</p>
          </div>
          
          {/* Format Toggles */}
          <div className="flex items-center gap-2">
            {Object.entries({
              executive: 'Executive',
              minutes: 'Minutes',
              bullets: 'Bullets',
              actions: 'Actions',
              decisions: 'Decisions',
              tasks: 'Tasks',
              transcript: 'Transcript'
            }).map(([key, label]) => (
              <button
                key={key}
                onClick={() => toggleFormat(key as keyof SummaryFormats)}
                className={`px-3 py-1.5 text-xs rounded-full border transition-all ${
                  summaryFormats[key as keyof SummaryFormats]
                    ? 'bg-zinc-800 border-zinc-700 text-white'
                    : 'bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Recording Control & Summaries */}
        <div className="lg:col-span-2 space-y-6">
          {/* Recording Control */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-8">
            <div className="flex flex-col items-center">
              {/* Big Record Button */}
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={audioDevices.length === 0}
                className={`relative w-32 h-32 rounded-full transition-all transform hover:scale-105 ${
                  isRecording 
                    ? 'bg-red-600 hover:bg-red-500 animate-pulse' 
                    : 'bg-gradient-to-br from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500'
                } ${audioDevices.length === 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={isRecording ? 'Click to stop recording' : 'Click to start recording'}
              >
                <div className="absolute inset-0 flex items-center justify-center">
                  {isRecording ? (
                    <Pause className="w-12 h-12 text-white" />
                  ) : (
                    <Mic className="w-12 h-12 text-white" />
                  )}
                </div>
                {isRecording && (
                  <div className="absolute inset-0 rounded-full border-4 border-red-400 animate-ping" />
                )}
              </button>
              
              {/* Status */}
              <div className="mt-6 text-center">
                <div className="text-2xl font-semibold text-white">
                  {isRecording ? 'Recording...' : 'Ready to Record'}
                </div>
                {isRecording && (
                  <div className="text-4xl font-mono text-zinc-300 mt-2">
                    {formatDuration(duration)}
                  </div>
                )}
                {audioDevices.length === 0 && (
                  <div className="text-red-400 text-sm mt-2 flex items-center gap-2 justify-center">
                    <AlertCircle className="w-4 h-4" />
                    No audio device detected
                  </div>
                )}
              </div>
              
              {/* Audio Level - Always visible for monitoring */}
              <div className="w-full max-w-xs mt-6">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <Volume2 className="w-4 h-4" />
                  Audio Level {!isRecording && <span className="text-xs">(monitoring)</span>}
                </div>
                <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-100 ${
                      isRecording 
                        ? 'bg-gradient-to-r from-green-500 to-yellow-500' 
                        : 'bg-gradient-to-r from-zinc-600 to-zinc-500'
                    }`}
                    style={{ width: `${Math.min(audioLevel * 100, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Executive Summary */}
          {summaryFormats.executive && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-fuchsia-400" />
                  Executive Summary
                </h3>
                <span className="text-xs px-2 py-1 rounded-full bg-fuchsia-500/10 text-fuchsia-300 border border-fuchsia-500/30">
                  AI Generated
                </span>
              </div>
              <div className="text-zinc-300 leading-relaxed">
                {sessionData?.summary?.executive || (
                  <span className="text-zinc-500 italic">
                    {isRecording ? 'Summary will update every 30-60 seconds...' : 'Start recording to generate summary'}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Two Column Layout for Actions & Decisions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Action Items */}
            {summaryFormats.actions && (
              <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                  <Flag className="w-5 h-5 text-orange-400" />
                  Action Items
                </h3>
                <div className="space-y-3">
                  {sessionData?.summary?.actions?.map((action, idx) => (
                    <div key={action.id || idx} className="flex items-start gap-3">
                      <CheckCircle className="w-4 h-4 text-green-400 mt-0.5" />
                      <div className="flex-1">
                        <div className="text-sm text-zinc-200">{action.action}</div>
                        {action.owner && (
                          <div className="text-xs text-zinc-400 mt-1">Owner: {action.owner}</div>
                        )}
                      </div>
                    </div>
                  )) || (
                    <span className="text-zinc-500 text-sm italic">
                      Actions will appear as they're identified...
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Key Decisions */}
            {summaryFormats.decisions && (
              <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                  <CheckCircle className="w-5 h-5 text-green-400" />
                  Key Decisions
                </h3>
                <div className="space-y-3">
                  {sessionData?.summary?.decisions?.map((decision, idx) => (
                    <div key={idx} className="flex items-start gap-3">
                      <div className="w-2 h-2 rounded-full bg-green-400 mt-1.5" />
                      <div className="text-sm text-zinc-200">{decision}</div>
                    </div>
                  )) || (
                    <span className="text-zinc-500 text-sm italic">
                      Decisions will be tracked in real-time...
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Bullet Points */}
          {summaryFormats.bullets && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                <ListChecks className="w-5 h-5 text-blue-400" />
                Key Points
              </h3>
              <ul className="space-y-2">
                {sessionData?.summary?.bullets?.map((bullet, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5" />
                    <span className="text-sm text-zinc-200">{bullet}</span>
                  </li>
                )) || (
                  <li className="text-zinc-500 text-sm italic">
                    • Key points will be extracted automatically...
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* Live Transcript (Optional) */}
          {summaryFormats.transcript && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Live Transcript</h3>
              <div className="h-64 overflow-y-auto space-y-2 font-mono text-xs text-zinc-300 bg-black/30 rounded-lg p-4">
                {liveTranscript.length > 0 ? (
                  liveTranscript.map((line, idx) => (
                    <div key={idx} className="flex gap-2">
                      <span className="text-zinc-500">[{new Date().toLocaleTimeString()}]</span>
                      <span>{line}</span>
                    </div>
                  ))
                ) : (
                  <span className="text-zinc-500">
                    {isRecording ? 'Waiting for speech...' : 'Transcript will appear here during recording'}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: Status & Metrics */}
        <div className="space-y-6">
          {/* Device Status */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Device Status</h3>
            
            {/* Audio Device */}
            <div className="space-y-4">
              <div>
                <label className="text-sm text-zinc-400 mb-2 block">Audio Input</label>
                <select 
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  disabled={isRecording}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
                >
                  {audioDevices.map(device => (
                    <option key={device.id || device.deviceId || device.index} value={device.id || device.deviceId}>
                      {device.label || device.name || 'Unknown Device'}
                    </option>
                  ))}
                  {audioDevices.length === 0 && (
                    <option value="">No devices found</option>
                  )}
                </select>
              </div>
            </div>
          </div>

          {/* Live Transcription */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-green-400" />
              Live Transcription
            </h3>
            <div className="h-64 overflow-y-auto space-y-2 font-mono text-xs text-zinc-300 bg-black/30 rounded-lg p-4">
              {liveTranscript.length > 0 ? (
                liveTranscript.slice(-20).map((line, idx) => (
                  <div key={idx} className="animate-fadeIn">
                    <span className="text-zinc-500">[{new Date().toLocaleTimeString('en-US', { 
                      hour: '2-digit', 
                      minute: '2-digit', 
                      second: '2-digit' 
                    })}]</span>
                    <span className="ml-2">{line}</span>
                  </div>
                ))
              ) : (
                <div className="text-zinc-500 italic">
                  {isRecording ? (
                    <>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        <span>Listening for speech...</span>
                      </div>
                      <div className="mt-2 text-xs">Session: {sessionData?.id ? sessionData.id.substring(0, 8) + '...' : 'initializing'}</div>
                      <div className="mt-1 text-xs text-zinc-600">
                        Transcription appears after ~5 seconds of speech
                      </div>
                    </>
                  ) : (
                    'Transcript will appear here during recording'
                  )}
                </div>
              )}
            </div>
            
            {isRecording && (
              <div className="mt-4 pt-4 border-t border-zinc-800">
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-400">Words Transcribed</span>
                  <span className="text-white font-mono">{wordCount}</span>
                </div>
                <div className="flex justify-between text-sm mt-2">
                  <span className="text-zinc-400">Auto-Summary</span>
                  <span className="text-zinc-300 text-xs">
                    {wordCount >= AUTO_SUMMARY_WORD_THRESHOLD 
                      ? `Next at ${lastSummaryWordCount + AUTO_SUMMARY_WORD_THRESHOLD} words`
                      : `At ${AUTO_SUMMARY_WORD_THRESHOLD} words`}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Session Info */}
          {sessionData && (
            <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Session Info</h3>
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-zinc-400">Session ID</div>
                  <div className="text-sm font-mono text-zinc-200 mt-1">{sessionData.id}</div>
                </div>
                <div>
                  <div className="text-xs text-zinc-400">Started</div>
                  <div className="text-sm text-zinc-200 mt-1">
                    {new Date(sessionData.startTime).toLocaleTimeString()}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-zinc-400">Duration</div>
                  <div className="text-sm text-zinc-200 mt-1">{formatDuration(duration)}</div>
                </div>
              </div>
            </div>
          )}

          {/* Quick Actions */}
          <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Quick Actions</h3>
            <div className="space-y-2">
              <button 
                className="w-full px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
                disabled={!sessionData || isRecording}
              >
                Export Summary
              </button>
              <button 
                className="w-full px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
                disabled={!sessionData || isRecording}
              >
                Email Action Items
              </button>
              <button className="w-full px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors">
                View All Sessions
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}