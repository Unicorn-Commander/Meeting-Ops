import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Play, Pause, Square, Camera, Clock, Settings, 
  Zap, Activity, Save, RotateCcw, Loader2, 
  CheckCircle, AlertCircle, Users, Volume2
} from 'lucide-react';

interface TranscriptionSegment {
  text: string;
  timestamp: string;
  speaker: string;
  confidence: number;
  processing_time_ms?: number;
  npu_active?: boolean;
}

interface DashcamStatus {
  enabled: boolean;
  display_enabled: boolean;
  buffer_enabled: boolean;
  buffer_duration_minutes: number;
  segments_in_buffer: number;
  buffer_size_gb: number;
  segments_processed: number;
  active_connections: number;
  npu_available: boolean;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const TimeShiftRecording: React.FC = () => {
  // State
  const [status, setStatus] = useState<DashcamStatus | null>(null);
  const [segments, setSegments] = useState<TranscriptionSegment[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Configuration
  const [displayEnabled, setDisplayEnabled] = useState(true);
  const [bufferEnabled, setBufferEnabled] = useState(true);
  const [bufferDuration, setBufferDuration] = useState(60);
  
  // WebSocket
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  
  // API calls
  const fetchStatus = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/live-transcription/status`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      
      if (response.ok) {
        const data = await response.json();
        setStatus(data);
        setDisplayEnabled(data.display_enabled);
        setBufferEnabled(data.buffer_enabled);
        setBufferDuration(data.buffer_duration_minutes);
      }
    } catch (err) {
      setError('Failed to fetch status');
    } finally {
      setLoading(false);
    }
  }, []);
  
  const startLiveTranscription = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      
      const response = await fetch(`${API_BASE_URL}/api/live-transcription/start`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        await fetchStatus();
      } else {
        throw new Error('Failed to start');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Start failed');
    }
  }, [fetchStatus]);
  
  const stopLiveTranscription = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      
      const response = await fetch(`${API_BASE_URL}/api/live-transcription/stop`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        await fetchStatus();
        setSegments([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stop failed');
    }
  }, [fetchStatus]);
  
  const updateConfiguration = useCallback(async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      
      const response = await fetch(`${API_BASE_URL}/api/live-transcription/configure`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          enabled: status?.enabled || false,
          display_enabled: displayEnabled,
          buffer_enabled: bufferEnabled,
          buffer_duration_minutes: bufferDuration
        })
      });
      
      if (response.ok) {
        await fetchStatus();
      }
    } catch (err) {
      setError('Configuration update failed');
    }
  }, [status?.enabled, displayEnabled, bufferEnabled, bufferDuration, fetchStatus]);
  
  const createRetroactiveSession = useCallback(async (minutes: number) => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      
      const response = await fetch(`${API_BASE_URL}/api/live-transcription/create-retroactive-session`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          since_minutes: minutes,
          title: `Time-Shift Save - Last ${minutes} minutes`
        })
      });
      
      if (response.ok) {
        const session = await response.json();
        alert(`✅ Saved! Created session with ${session.segments.length} segments from last ${minutes} minutes`);
      } else {
        throw new Error('Failed to create retroactive session');
      }
    } catch (err) {
      alert(`❌ Save failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, []);
  
  // WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/api/live-transcription/ws`;
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      setIsConnected(true);
      setError(null);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'transcription') {
          const segment: TranscriptionSegment = data.data;
          setSegments(prev => [...prev.slice(-50), segment]); // Keep last 50 segments
          
          // Auto-scroll to bottom
          setTimeout(() => {
            transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
          }, 100);
        } else if (data.type === 'status') {
          setStatus(data.data);
        }
      } catch (err) {
        console.error('WebSocket message error:', err);
      }
    };
    
    ws.onerror = () => {
      setIsConnected(false);
      setError('WebSocket connection error');
    };
    
    ws.onclose = () => {
      setIsConnected(false);
      // Reconnect after 2 seconds
      setTimeout(connectWebSocket, 2000);
    };
    
    wsRef.current = ws;
  }, []);
  
  // Initialize
  useEffect(() => {
    fetchStatus();
    connectWebSocket();
    
    return () => {
      wsRef.current?.close();
    };
  }, [fetchStatus, connectWebSocket]);
  
  // Auto-update configuration
  useEffect(() => {
    if (status) {
      const timer = setTimeout(updateConfiguration, 500);
      return () => clearTimeout(timer);
    }
  }, [displayEnabled, bufferEnabled, bufferDuration, updateConfiguration, status]);
  
  if (loading) {
    return (
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-purple-400 animate-spin" />
          <span className="ml-2 text-gray-400">Loading time-shift system...</span>
        </div>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      {/* Header with Status */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 border border-gray-800 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-full ${status?.enabled ? 'bg-red-500/20' : 'bg-gray-500/20'}`}>
              <Camera className={`w-8 h-8 ${status?.enabled ? 'text-red-400' : 'text-gray-400'}`} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">
                🎯 Time-Shift Recording {status?.enabled ? '(LIVE)' : '(STOPPED)'}
              </h1>
              <p className="text-gray-400">
                Continuous NPU recording with time-rewind capability
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
              <Activity className="w-4 h-4" />
              <span className="text-sm">{isConnected ? 'Connected' : 'Disconnected'}</span>
            </div>
            
            {status?.npu_available && (
              <div className="flex items-center gap-2 text-purple-400">
                <Zap className="w-4 h-4" />
                <span className="text-sm">NPU Ready</span>
              </div>
            )}
          </div>
        </div>
        
        {/* Main Controls */}
        <div className="flex items-center gap-4">
          {!status?.enabled ? (
            <button
              onClick={startLiveTranscription}
              className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded-lg flex items-center gap-2 font-semibold"
            >
              <Play className="w-5 h-5" />
              START TIME-SHIFT
            </button>
          ) : (
            <button
              onClick={stopLiveTranscription}
              className="bg-gray-600 hover:bg-gray-700 text-white px-6 py-3 rounded-lg flex items-center gap-2 font-semibold"
            >
              <Square className="w-5 h-5" />
              STOP TIME-SHIFT
            </button>
          )}
          
          {/* Jump-Back Buttons */}
          {status?.enabled && bufferEnabled && (
            <>
              <button
                onClick={() => createRetroactiveSession(15)}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-3 rounded-lg flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" />
                Save Last 15min
              </button>
              <button
                onClick={() => createRetroactiveSession(30)}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-3 rounded-lg flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" />
                Save Last 30min
              </button>
              <button
                onClick={() => createRetroactiveSession(60)}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-3 rounded-lg flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" />
                Save Last 60min
              </button>
            </>
          )}
        </div>
      </div>
      
      {/* Configuration Panel */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5 text-gray-400" />
          Time-Shift Configuration
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="space-y-2">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={displayEnabled}
                onChange={(e) => setDisplayEnabled(e.target.checked)}
                className="w-5 h-5 text-purple-600 rounded"
              />
              <span className="text-white">Display Live Transcription</span>
            </label>
            <p className="text-xs text-gray-500">Show real-time text on screen</p>
          </div>
          
          <div className="space-y-2">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={bufferEnabled}
                onChange={(e) => setBufferEnabled(e.target.checked)}
                className="w-5 h-5 text-purple-600 rounded"
              />
              <span className="text-white">Buffer for Jump-Back</span>
            </label>
            <p className="text-xs text-gray-500">Enable time-rewind recording</p>
          </div>
          
          <div className="space-y-2">
            <label className="block text-white">Buffer Duration</label>
            <select
              value={bufferDuration}
              onChange={(e) => setBufferDuration(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            >
              <option value={15}>15 minutes</option>
              <option value={30}>30 minutes</option>
              <option value={60}>60 minutes</option>
              <option value={120}>2 hours</option>
            </select>
            <p className="text-xs text-gray-500">Maximum buffer time</p>
          </div>
        </div>
      </div>
      
      {/* Stats */}
      {status && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <h3 className="text-white font-semibold mb-4">System Stats</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="w-4 h-4 text-blue-400" />
                <span className="text-xs text-gray-500">Buffer</span>
              </div>
              <p className="text-lg font-bold text-blue-400">{status.segments_in_buffer}</p>
              <p className="text-xs text-gray-400">segments</p>
            </div>
            
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Volume2 className="w-4 h-4 text-green-400" />
                <span className="text-xs text-gray-500">RAM Used</span>
              </div>
              <p className="text-lg font-bold text-green-400">{status.buffer_size_gb}</p>
              <p className="text-xs text-gray-400">GB</p>
            </div>
            
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Zap className="w-4 h-4 text-purple-400" />
                <span className="text-xs text-gray-500">Processed</span>
              </div>
              <p className="text-lg font-bold text-purple-400">{status.segments_processed}</p>
              <p className="text-xs text-gray-400">segments</p>
            </div>
            
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Users className="w-4 h-4 text-cyan-400" />
                <span className="text-xs text-gray-500">Connections</span>
              </div>
              <p className="text-lg font-bold text-cyan-400">{status.active_connections}</p>
              <p className="text-xs text-gray-400">active</p>
            </div>
          </div>
        </div>
      )}
      
      {/* Live Transcription Display */}
      {status?.enabled && displayEnabled && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-red-400 animate-pulse" />
            Live NPU Transcription
          </h3>
          
          <div className="bg-gray-800/50 rounded-lg p-4 h-64 overflow-y-auto">
            {segments.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <Activity className="w-8 h-8 mx-auto mb-2" />
                  <p>Waiting for speech...</p>
                  <p className="text-xs">NPU ready for real-time transcription</p>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {segments.map((segment, index) => (
                  <div key={index} className="bg-gray-900/50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-purple-400 font-medium text-sm">{segment.speaker}</span>
                      <span className="text-xs text-gray-500">
                        {new Date(segment.timestamp).toLocaleTimeString()}
                      </span>
                      {segment.npu_active && (
                        <span className="text-xs bg-purple-600 text-white px-2 py-1 rounded">NPU</span>
                      )}
                      {segment.processing_time_ms && (
                        <span className="text-xs text-gray-400">
                          {segment.processing_time_ms}ms
                        </span>
                      )}
                    </div>
                    <p className="text-gray-200">{segment.text}</p>
                  </div>
                ))}
                <div ref={transcriptEndRef} />
              </div>
            )}
          </div>
        </div>
      )}
      
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-400" />
            <span className="text-red-300">{error}</span>
          </div>
        </div>
      )}
    </div>
  );
};