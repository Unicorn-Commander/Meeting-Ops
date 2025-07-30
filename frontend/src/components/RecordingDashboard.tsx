import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  MicOff,
  Square,
  Download,
  FileText,
  List,
  Clock,
  MessageSquare,
  Volume2,
  Settings,
  Pause,
  Play,
  AlertCircle
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface TranscriptionChunk {
  id: string;
  text: string;
  timestamp: string;
  speaker?: string;
  confidence?: number;
}

interface SummaryTemplate {
  id: string;
  name: string;
  icon: React.ReactNode;
  prompt: string;
}

export const RecordingDashboard: React.FC = () => {
  const { user } = useAuth();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [inputGain, setInputGain] = useState(1.0);
  const [transcriptionChunks, setTranscriptionChunks] = useState<TranscriptionChunk[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [npuStatus, setNpuStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('narrative');
  const [summary, setSummary] = useState<string>('');
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioWsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('access_token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const summaryTemplates: SummaryTemplate[] = [
    {
      id: 'narrative',
      name: 'Narrative',
      icon: <FileText className="h-4 w-4" />,
      prompt: 'Create a narrative summary of this meeting, including key discussions and outcomes.'
    },
    {
      id: 'bullets',
      name: 'Bullet Points',
      icon: <List className="h-4 w-4" />,
      prompt: 'Summarize this meeting in clear bullet points, highlighting key decisions and action items.'
    },
    {
      id: 'timeline',
      name: 'Timeline',
      icon: <Clock className="h-4 w-4" />,
      prompt: 'Create a chronological timeline of the meeting, showing when each topic was discussed.'
    },
    {
      id: 'actions',
      name: 'Action Items',
      icon: <MessageSquare className="h-4 w-4" />,
      prompt: 'Extract all action items, decisions, and follow-ups from this meeting with assigned owners.'
    }
  ];

  // Connect to audio level WebSocket
  useEffect(() => {
    connectAudioLevels();
    checkNpuStatus();

    return () => {
      if (audioWsRef.current) {
        audioWsRef.current.close();
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const connectAudioLevels = () => {
    const token = localStorage.getItem('access_token');
    const wsUrl = `ws://localhost:9050/ws/audio-levels?token=${token}`;
    audioWsRef.current = new WebSocket(wsUrl);

    audioWsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'error') {
        setError(`Audio WS Error: ${data.message}`);
        return;
      }
      if (data.level !== undefined) {
        setAudioLevel(data.level * inputGain);
      }
    };

    audioWsRef.current.onerror = (error) => {
      console.error('Audio WebSocket error:', error);
      setError('Failed to connect to audio level service.');
    };

    audioWsRef.current.onclose = () => {
      // Reconnect after a delay
      setTimeout(connectAudioLevels, 5000);
    };
  };

  const checkNpuStatus = async () => {
    try {
      const response = await fetch('/api/status', { headers: getAuthHeaders() });
      if (!response.ok) {
        throw new Error('Failed to fetch NPU status');
      }
      const data = await response.json();
      setNpuStatus(data.npu_available ? 'ready' : 'error');
    } catch (error) {
      console.error(error);
      setNpuStatus('error');
      setError('Could not verify NPU status.');
    }
  };

  const handleStartRecording = async () => {
    setError(null);
    try {
      const response = await fetch('/api/recording-sessions', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          name: `Recording ${new Date().toLocaleString()}`,
          description: 'Live recording from USB microphone'
        })
      });
      if (!response.ok) throw new Error('Failed to create session.');

      const data = await response.json();
      if (data.success) {
        const sessionId = data.session.session_id;
        setCurrentSessionId(sessionId);
        
        const startResponse = await fetch(`/api/recording-sessions/${sessionId}/start`, {
          method: 'POST',
          headers: getAuthHeaders()
        });
        if (!startResponse.ok) throw new Error('Failed to start recording.');

        setIsRecording(true);
        setTranscriptionChunks([]);
        setSummary('');
        
        timerRef.current = setInterval(() => {
          setRecordingTime(prev => prev + 1);
        }, 1000);

        connectTranscription(sessionId);
      }
    } catch (error: any) {
      console.error('Failed to start recording:', error);
      setError(error.message || 'Failed to start recording.');
    }
  };

  const connectTranscription = (sessionId: string) => {
    const token = localStorage.getItem('access_token');
    const wsUrl = `ws://localhost:9050/ws/stream/${sessionId}?token=${token}`;
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      console.log(`Transcription WebSocket connected for session ${sessionId}`);
    };

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'error') {
        setError(`Transcription Error: ${data.message}`);
        return;
      }
      if (data.type === 'transcription' && data.text) {
        const chunk: TranscriptionChunk = {
          id: Date.now().toString(),
          text: data.text,
          timestamp: new Date().toLocaleTimeString(),
          speaker: data.speaker_name || 'Unknown',
          confidence: data.confidence
        };
        setTranscriptionChunks(prev => [...prev, chunk]);
      }
    };

    wsRef.current.onerror = (error) => {
      console.error('Transcription WebSocket error:', error);
      setError('Live transcription service disconnected.');
    };
  };

  const handleStopRecording = async () => {
    if (currentSessionId) {
      try {
        const response = await fetch(`/api/recording-sessions/${currentSessionId}/stop`, {
          method: 'POST',
          headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Failed to stop recording cleanly.');
      } catch (error: any) {
        console.error('Failed to stop recording:', error);
        setError(error.message || 'Failed to stop recording.');
      }
    }

    setIsRecording(false);
    setIsPaused(false);
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  const handlePauseResume = async () => {
    if (currentSessionId) {
      try {
        const endpoint = isPaused ? 'resume' : 'pause';
        const response = await fetch(`/api/recording-sessions/${currentSessionId}/${endpoint}`, {
          method: 'POST',
          headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error(`Failed to ${endpoint} recording.`);
        setIsPaused(!isPaused);
      } catch (error: any) {
        console.error(`Failed to ${isPaused ? 'resume' : 'pause'} recording:`, error);
        setError(error.message || 'Failed to update recording state.');
      }
    }
  };

  const handleGenerateSummary = async () => {
    if (!currentSessionId || transcriptionChunks.length === 0) return;

    setIsGeneratingSummary(true);
    setError(null);
    const template = summaryTemplates.find(t => t.id === selectedTemplate);
    
    try {
      const response = await fetch(`/api/recording-sessions/${currentSessionId}/summary`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          summary_style: selectedTemplate,
          focus_areas: [template?.prompt || '']
        })
      });
      if (!response.ok) throw new Error('Summary generation failed.');

      const data = await response.json();
      if (data.summary) {
        setSummary(data.summary.full_summary);
      }
    } catch (error: any) {
      console.error('Failed to generate summary:', error);
      setError(error.message || 'Failed to generate summary.');
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const handleExportTranscription = async () => {
    if (!currentSessionId) return;

    try {
      const response = await fetch(`/api/recording-sessions/${currentSessionId}/export?format=txt`, {
        headers: getAuthHeaders()
      });
      if (!response.ok) throw new Error('Failed to download transcription.');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transcription_${currentSessionId}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (error: any) {
      console.error('Failed to export transcription:', error);
      setError(error.message || 'Failed to export transcription.');
    }
  };

  const handleExportSummary = () => {
    if (!summary) return;

    const blob = new Blob([summary], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `summary_${currentSessionId}_${selectedTemplate}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold mb-2">Recording Studio</h1>
        <p className="text-gray-400">Server-side USB microphone recording with NPU acceleration</p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="bg-red-900/20 border border-red-600 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-500" />
          <span className="text-red-200">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-200">X</button>
        </div>
      )}

      {/* NPU Status Alert */}
      {npuStatus !== 'ready' && !error && (
        <div className="bg-yellow-900/20 border border-yellow-600 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-yellow-500" />
          <span className="text-yellow-200">
            {npuStatus === 'loading' ? 'Verifying NPU acceleration...' : 'NPU not available. Transcription will use CPU.'}
          </span>
        </div>
      )}

      {/* Main Recording Interface */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Audio Controls */}
        <div className="lg:col-span-1 space-y-6">
          {/* Audio Level Meter */}
          <div className="bg-gray-800 p-6 rounded-xl">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Volume2 className="h-5 w-5" />
              Audio Level
            </h3>
            
            <div className="space-y-4">
              {/* Level Meter */}
              <div className="relative h-8 bg-gray-700 rounded-full overflow-hidden">
                <div 
                  className="absolute inset-y-0 left-0 bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 transition-all duration-100"
                  style={{ width: `${Math.min(audioLevel * 100, 100)}%` }}
                />
                <div className="absolute inset-0 flex items-center justify-center text-sm font-medium">
                  {Math.round(audioLevel * 100)}%
                </div>
              </div>

              {/* Gain Control */}
              <div>
                <label className="text-sm text-gray-400 mb-1 block">Input Gain</label>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={inputGain}
                  onChange={(e) => setInputGain(parseFloat(e.target.value))}
                  className="w-full"
                  disabled={isRecording}
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>50%</span>
                  <span>{Math.round(inputGain * 100)}%</span>
                  <span>200%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Recording Controls */}
          <div className="bg-gray-800 p-6 rounded-xl text-center">
            <div className="mb-4 h-8">
              {isRecording && (
                <div className="text-3xl font-mono text-red-400">
                  {formatTime(recordingTime)}
                </div>
              )}
            </div>

            <div className="flex justify-center gap-3">
              {!isRecording ? (
                <button
                  onClick={handleStartRecording}
                  className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 rounded-lg font-medium transition-colors"
                >
                  <Mic className="h-5 w-5" />
                  Start Recording
                </button>
              ) : (
                <>
                  <button
                    onClick={handlePauseResume}
                    className="flex items-center gap-2 px-4 py-3 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors"
                  >
                    {isPaused ? <Play className="h-5 w-5" /> : <Pause className="h-5 w-5" />}
                  </button>
                  <button
                    onClick={handleStopRecording}
                    className="flex items-center gap-2 px-6 py-3 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors"
                  >
                    <Square className="h-5 w-5" />
                    Stop
                  </button>
                </>
              )}
            </div>

            {isRecording && (
              <div className="mt-4 h-5">
                <div className="flex items-center justify-center gap-2 text-red-400">
                  <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                  <span className="text-sm">{isPaused ? 'Recording Paused' : 'Recording in progress...'}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Live Transcription */}
        <div className="lg:col-span-2">
          <div className="bg-gray-800 p-6 rounded-xl h-full">
            <h3 className="text-lg font-semibold mb-4">Live Transcription</h3>
            
            <div className="bg-gray-900 rounded-lg p-4 h-96 overflow-y-auto">
              {transcriptionChunks.length === 0 ? (
                <div className="text-center text-gray-500 mt-20">
                  {isRecording ? 'Waiting for speech...' : 'Start recording to see live transcription'}
                </div>
              ) : (
                <div className="space-y-3">
                  {transcriptionChunks.map((chunk) => (
                    <div key={chunk.id} className="bg-gray-800 p-3 rounded">
                      <div className="flex items-start justify-between mb-1">
                        <span className="text-xs text-gray-400">{chunk.timestamp}</span>
                        {chunk.speaker && (
                          <span className="text-xs bg-blue-600 px-2 py-1 rounded">
                            {chunk.speaker}
                          </span>
                        )}
                      </div>
                      <p className="text-sm">{chunk.text}</p>
                      {chunk.confidence && (
                        <div className="mt-1">
                          <div className="text-xs text-gray-500">
                            Confidence: {Math.round(chunk.confidence * 100)}%
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Summary Section */}
      {transcriptionChunks.length > 0 && !isRecording && (
        <div className="bg-gray-800 p-6 rounded-xl">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Summary & Export</h3>
            <div className="flex gap-2">
              {summaryTemplates.map((template) => (
                <button
                  key={template.id}
                  onClick={() => setSelectedTemplate(template.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-xs ${
                    selectedTemplate === template.id
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 hover:bg-gray-600'
                  }`}
                >
                  {template.icon}
                  <span className="text-sm">{template.name}</span>
                </button>
              ))}
            </div>
          </div>

          {summary ? (
            <div className="bg-gray-900 rounded-lg p-4 mb-4">
              <pre className="whitespace-pre-wrap text-sm font-sans">{summary}</pre>
            </div>
          ) : (
            <div className="text-center py-8">
              <button
                onClick={handleGenerateSummary}
                disabled={isGeneratingSummary || isRecording}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isGeneratingSummary ? 'Generating Summary...' : `Generate ${summaryTemplates.find(t=>t.id === selectedTemplate)?.name} Summary`}
              </button>
            </div>
          )}

          {/* Export Buttons */}
          <div className="flex gap-3 justify-end border-t border-gray-700 pt-4 mt-4">
            <button
              onClick={handleExportTranscription}
              disabled={!currentSessionId}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download className="h-4 w-4" />
              Export Transcription
            </button>
            <button
              onClick={handleExportSummary}
              disabled={!summary}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download className="h-4 w-4" />
              Export Summary
            </button>
          </div>
        </div>
      )}
    </div>
  );
};