import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Save, HardDrive, Cpu, Zap, AlertCircle } from 'lucide-react';
import config from '../config';

interface TranscriptionSegment {
  time: string;
  text: string;
  speaker: string;
}

interface BufferStatus {
  is_transcribing: boolean;
  is_saving: boolean;
  audio_mode: 'off' | 'ram' | 'disk' | 'both';
  buffer_size: number;
  buffer_duration_minutes: number;
  audio_ram_usage_mb: number;
  audio_ram_limit_mb: number;
  last_update: string;
}

const TranscriptionLoop: React.FC = () => {
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [audioMode, setAudioMode] = useState<'off' | 'ram' | 'disk' | 'both'>('off');
  const [bufferStatus, setBufferStatus] = useState<BufferStatus | null>(null);
  const [recentTranscripts, setRecentTranscripts] = useState<TranscriptionSegment[]>([]);
  const [savingMeeting, setSavingMeeting] = useState(false);
  const [meetingName, setMeetingName] = useState('');
  const [saveAudio, setSaveAudio] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const statusIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch buffer status periodically
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/transcription-loop/status`);
        if (response.ok) {
          const data = await response.json();
          setBufferStatus(data);
          setIsTranscribing(data.is_transcribing);
          setAudioMode(data.audio_mode);
        }
      } catch (err) {
        console.error('Failed to fetch status:', err);
      }
    };

    fetchStatus();
    statusIntervalRef.current = setInterval(fetchStatus, 2000);

    return () => {
      if (statusIntervalRef.current) {
        clearInterval(statusIntervalRef.current);
      }
    };
  }, []);

  // WebSocket for live transcription
  useEffect(() => {
    if (isTranscribing && !wsRef.current) {
      const wsUrl = `${config.wsUrl}/ws/transcription/live`;
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'transcript') {
          const newSegment: TranscriptionSegment = {
            time: new Date().toLocaleTimeString(),
            text: data.text,
            speaker: data.speaker || 'Unknown'
          };
          setRecentTranscripts(prev => [newSegment, ...prev].slice(0, 10));
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    } else if (!isTranscribing && wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [isTranscribing]);

  const handleStartStop = async () => {
    setError(null);
    const endpoint = isTranscribing ? 'stop' : 'start';
    
    try {
      const response = await fetch(`${config.apiUrl}/api/transcription-loop/${endpoint}`, {
        method: 'POST'
      });

      if (response.ok) {
        const data = await response.json();
        setIsTranscribing(!isTranscribing);
        
        if (!isTranscribing) {
          setRecentTranscripts([]);
        }
      } else {
        throw new Error(`Failed to ${endpoint} transcription`);
      }
    } catch (err) {
      setError(`Failed to ${endpoint} transcription`);
      console.error(err);
    }
  };

  const handleAudioModeChange = async (mode: 'off' | 'ram' | 'disk' | 'both') => {
    setError(null);
    
    try {
      const response = await fetch(`${config.apiUrl}/api/transcription-loop/audio-recording`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });

      if (response.ok) {
        setAudioMode(mode);
      } else {
        throw new Error('Failed to change audio mode');
      }
    } catch (err) {
      setError('Failed to change audio mode');
      console.error(err);
    }
  };

  const handleSaveMeeting = async () => {
    if (!meetingName.trim()) {
      setError('Please enter a meeting name');
      return;
    }

    setSavingMeeting(true);
    setError(null);

    try {
      const response = await fetch(`${config.apiUrl}/api/transcription-loop/save-meeting`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: meetingName,
          save_audio: saveAudio && audioMode !== 'off'
        })
      });

      if (response.ok) {
        const data = await response.json();
        setShowSaveDialog(false);
        setMeetingName('');
        setSaveAudio(false);
        setRecentTranscripts([]);
        alert(`Meeting saved successfully! Session ID: ${data.session_id}`);
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save meeting');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to save meeting');
      console.error(err);
    } finally {
      setSavingMeeting(false);
    }
  };

  const getAudioModeIcon = () => {
    switch (audioMode) {
      case 'ram': return <Cpu className="w-4 h-4" />;
      case 'disk': return <HardDrive className="w-4 h-4" />;
      case 'both': return <Zap className="w-4 h-4" />;
      default: return null;
    }
  };

  const getAudioModeLabel = () => {
    switch (audioMode) {
      case 'ram': return 'RAM Buffer';
      case 'disk': return 'Disk Recording';
      case 'both': return 'RAM + Disk';
      default: return 'Transcript Only';
    }
  };

  const getRamUsagePercentage = () => {
    if (!bufferStatus || audioMode === 'off') return 0;
    return (bufferStatus.audio_ram_usage_mb / bufferStatus.audio_ram_limit_mb) * 100;
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">Transcription-First Mode</h2>
        
        {/* Status Indicator */}
        <div className={`flex items-center gap-2 px-3 py-1 rounded-full ${
          isTranscribing ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-gray-400'
        }`}>
          {isTranscribing ? (
            <>
              <Mic className="w-4 h-4 animate-pulse" />
              <span className="text-sm font-medium">Listening</span>
            </>
          ) : (
            <>
              <MicOff className="w-4 h-4" />
              <span className="text-sm font-medium">Stopped</span>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-500/20 border border-red-500 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400">{error}</span>
        </div>
      )}

      {/* Control Buttons */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <button
          onClick={handleStartStop}
          className={`py-3 px-6 rounded-lg font-medium transition-colors ${
            isTranscribing
              ? 'bg-red-600 hover:bg-red-700 text-white'
              : 'bg-green-600 hover:bg-green-700 text-white'
          }`}
        >
          {isTranscribing ? 'Stop Listening' : 'Start Listening'}
        </button>

        <button
          onClick={() => setShowSaveDialog(true)}
          disabled={!bufferStatus || bufferStatus.buffer_size === 0}
          className="py-3 px-6 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <Save className="w-5 h-5" />
          Save Meeting
        </button>
      </div>

      {/* Audio Mode Selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Audio Recording Mode
        </label>
        <div className="grid grid-cols-4 gap-2">
          {(['off', 'ram', 'disk', 'both'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => handleAudioModeChange(mode)}
              className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                audioMode === mode
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              {mode === 'off' && 'Transcript Only'}
              {mode === 'ram' && 'RAM Buffer'}
              {mode === 'disk' && 'Disk'}
              {mode === 'both' && 'RAM + Disk'}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-gray-400">
          {audioMode === 'off' && '1700x storage savings - transcripts only (3KB/min)'}
          {audioMode === 'ram' && 'No disk wear - audio in RAM only (0.15MB/min)'}
          {audioMode === 'disk' && 'Traditional recording to disk (5.3MB/min WAV)'}
          {audioMode === 'both' && 'RAM buffer with disk backup for reliability'}
        </p>
      </div>

      {/* Buffer Status */}
      {bufferStatus && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-gray-700 rounded-lg p-3">
            <div className="text-sm text-gray-400 mb-1">Buffer Size</div>
            <div className="text-xl font-bold text-white">
              {bufferStatus.buffer_size} segments
            </div>
          </div>

          <div className="bg-gray-700 rounded-lg p-3">
            <div className="text-sm text-gray-400 mb-1">Audio Mode</div>
            <div className="flex items-center gap-2">
              {getAudioModeIcon()}
              <span className="text-xl font-bold text-white">{getAudioModeLabel()}</span>
            </div>
          </div>

          {audioMode !== 'off' && (
            <div className="bg-gray-700 rounded-lg p-3">
              <div className="text-sm text-gray-400 mb-1">RAM Usage</div>
              <div className="text-xl font-bold text-white">
                {bufferStatus.audio_ram_usage_mb.toFixed(1)}MB
              </div>
              <div className="mt-1 h-2 bg-gray-600 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-purple-500 transition-all duration-300"
                  style={{ width: `${getRamUsagePercentage()}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recent Transcripts */}
      <div className="bg-gray-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-3">Recent Transcripts</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {recentTranscripts.length > 0 ? (
            recentTranscripts.map((segment, index) => (
              <div key={index} className="bg-gray-800 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-400">{segment.time}</span>
                  <span className="text-xs text-purple-400">{segment.speaker}</span>
                </div>
                <p className="text-sm text-gray-200">{segment.text}</p>
              </div>
            ))
          ) : (
            <p className="text-gray-400 text-center py-8">
              {isTranscribing ? 'Waiting for speech...' : 'Start listening to see transcripts'}
            </p>
          )}
        </div>
      </div>

      {/* Save Meeting Dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-white mb-4">Save Meeting</h3>
            
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Meeting Name
              </label>
              <input
                type="text"
                value={meetingName}
                onChange={(e) => setMeetingName(e.target.value)}
                placeholder="e.g., Team Standup - Jan 9"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            {audioMode !== 'off' && (
              <div className="mb-4">
                <label className="flex items-center gap-2 text-gray-300">
                  <input
                    type="checkbox"
                    checked={saveAudio}
                    onChange={(e) => setSaveAudio(e.target.checked)}
                    className="rounded bg-gray-700 border-gray-600 text-purple-600 focus:ring-purple-500"
                  />
                  <span className="text-sm">Save audio recording (MKV format)</span>
                </label>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="flex-1 py-2 px-4 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveMeeting}
                disabled={savingMeeting || !meetingName.trim()}
                className="flex-1 py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {savingMeeting ? 'Saving...' : 'Save Meeting'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TranscriptionLoop;