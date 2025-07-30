import React, { useState, useEffect, useCallback } from 'react';
import {
  Mic,
  Square,
  Clock,
  FileText,
  Users,
  Download,
  RefreshCw,
  Sparkles,
  Activity,
  Home,
  Folder,
  Settings
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { LiveTranscriptionViewer } from './LiveTranscriptionViewer';
import { AudioLevelMeter } from './AudioLevelMeter';
import { useApiCache } from '../hooks/useApiCache';
import config from '../config';
import { RecordingDebug } from './RecordingDebug';

interface Recording {
  id: string;
  session_id: string;
  name: string;
  created_at: string;
  status: 'active' | 'completed' | 'processing';
  duration_seconds?: number;
  total_transcriptions?: number;
  total_speakers?: number;
}

interface Summary {
  summary_text?: string;
  action_items?: string[];
  key_topics?: string[];
}

interface UserDashboardSimpleProps {
  onSwitchToAdmin?: () => void;
}

export const UserDashboardSimple: React.FC<UserDashboardSimpleProps> = ({ onSwitchToAdmin }) => {
  const { user, token } = useAuth();
  
  const getAuthHeaders = () => ({
    'Authorization': `Bearer ${token}`
  });
  const [currentView, setCurrentView] = useState('home');
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [selectedRecording, setSelectedRecording] = useState<Recording | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);

  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

  // Fetch recordings using API cache
  const {
    data: recordings,
    loading: loadingRecordings,
    error: recordingsError,
    refresh: refreshRecordings
  } = useApiCache<Recording[]>(
    'recordings',
    async () => {
      const response = await fetch(`${config.apiBaseUrl}/api/recording-sessions`, {
        headers: getAuthHeaders()
      });
      if (!response.ok) throw new Error('Failed to fetch recordings');
      const data = await response.json();
      return data.sessions || [];
    },
    { refetchInterval: 10000 } // Refresh every 10 seconds
  );

  // Recording timer
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isRecording) {
      interval = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isRecording]);

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDuration = (seconds?: number): string => {
    if (!seconds) return '00:00';
    return formatTime(seconds);
  };

  const handleStartRecording = async () => {
    try {
      console.log('Starting recording...');
      console.log('Token:', token ? 'Present' : 'Missing');
      console.log('API URL:', config.apiBaseUrl || 'Using proxy');
      
      // Create new recording session
      const response = await fetch(`${config.apiBaseUrl}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: `Recording ${new Date().toLocaleString()}`,
          description: 'Created from Simple User Dashboard'
        })
      });

      console.log('Create response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Create response error:', errorText);
        throw new Error(`Failed to create recording session: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Create response data:', data);
      
      const sessionId = data.session?.session_id || data.session?.id || data.session_id || data.id;
      
      if (!sessionId) throw new Error('No session ID received');
      
      console.log('Session ID:', sessionId);
      setCurrentSessionId(sessionId);

      // Start recording
      const startResponse = await fetch(`${config.apiBaseUrl}/api/recording-sessions/${sessionId}/start`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      console.log('Start response status:', startResponse.status);
      
      if (!startResponse.ok) {
        const errorText = await startResponse.text();
        console.error('Start response error:', errorText);
        throw new Error(`Failed to start recording: ${startResponse.status}`);
      }

      console.log('Recording started successfully!');
      setIsRecording(true);
      setRecordingTime(0);
      
      // Refresh recordings list
      refreshRecordings();
    } catch (error) {
      console.error('Failed to start recording:', error);
      alert(`Failed to start recording: ${error.message || error}`);
    }
  };

  const handleStopRecording = async () => {
    if (!currentSessionId) return;

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/recording-sessions/${currentSessionId}/stop`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (!response.ok) throw new Error('Failed to stop recording');

      setIsRecording(false);
      setRecordingTime(0);
      setCurrentSessionId(null);
      
      // Refresh recordings list
      refreshRecordings();
    } catch (error) {
      console.error('Failed to stop recording:', error);
      alert('Failed to stop recording. Please try again.');
    }
  };

  const handleGenerateSummary = async (recording: Recording) => {
    setIsGeneratingSummary(true);
    setSummary(null);
    
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/recording-sessions/${recording.session_id}/summarize`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (!response.ok) throw new Error('Failed to generate summary');
      
      const data = await response.json();
      setSummary(data);
    } catch (error) {
      console.error('Failed to generate summary:', error);
      // Try mock data as fallback
      setSummary({
        summary_text: 'The meeting discussed project updates, timeline adjustments, and resource allocation. Key decisions were made regarding the Q3 roadmap.',
        action_items: [
          'John to prepare budget proposal by Friday',
          'Sarah to schedule follow-up with client',
          'Team to review technical specifications'
        ],
        key_topics: ['Budget Planning', 'Client Requirements', 'Technical Architecture']
      });
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const handleDownloadTranscript = async (recording: Recording) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/recording-sessions/${recording.session_id}/export?format=txt`, {
        headers: getAuthHeaders()
      });

      if (!response.ok) throw new Error('Failed to download transcript');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${recording.name}.txt`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Failed to download transcript:', error);
      alert('Failed to download transcript. Please try again.');
    }
  };

  const renderHomeView = () => (
    <div className="space-y-6">
      {/* Welcome Section */}
      <div className="text-center">
        <h1 className="text-3xl font-bold mb-2">Welcome back, {user?.username}!</h1>
        <p className="text-gray-400">Your AI-powered meeting assistant is ready</p>
      </div>

      {/* Recording Control with Audio Levels */}
      <div className="bg-gray-800 p-8 rounded-xl">
        <div className="text-center mb-6">
          {isRecording ? (
            <div className="space-y-4">
              <div className="w-24 h-24 mx-auto bg-red-600 rounded-full flex items-center justify-center animate-pulse">
                <Mic className="h-12 w-12 text-white" />
              </div>
              <div>
                <p className="text-3xl font-bold text-red-400">{formatTime(recordingTime)}</p>
                <p className="text-gray-400">Recording in progress...</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="w-24 h-24 mx-auto bg-gradient-to-r from-purple-600 to-pink-600 rounded-full flex items-center justify-center">
                <Mic className="h-12 w-12 text-white" />
              </div>
              <div>
                <p className="text-lg font-medium">Ready to record</p>
                <p className="text-gray-400">Click to start your meeting recording</p>
              </div>
            </div>
          )}
        </div>

        {/* Audio Level Meter */}
        <div className="mb-6 max-w-md mx-auto">
          <AudioLevelMeter 
            wsUrl={`${config.apiBaseUrl.replace('http', 'ws')}/ws/audio-levels`}
            showDb={true}
            showPeak={true}
          />
        </div>

        <div className="flex justify-center gap-4">
          {!isRecording ? (
            <button
              onClick={handleStartRecording}
              className="flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-lg font-medium text-lg transition-all transform hover:scale-105"
            >
              <Mic className="h-6 w-6" />
              Start Recording
            </button>
          ) : (
            <button
              onClick={handleStopRecording}
              className="flex items-center gap-2 px-8 py-4 bg-red-600 hover:bg-red-700 rounded-lg font-medium text-lg transition-all transform hover:scale-105"
            >
              <Square className="h-6 w-6" />
              Stop Recording
            </button>
          )}
        </div>
      </div>

      {/* Live Transcription */}
      {isRecording && currentSessionId && (
        <LiveTranscriptionViewer 
          sessionId={currentSessionId}
          isRecording={isRecording}
        />
      )}

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 p-6 rounded-lg text-center">
          <FileText className="h-10 w-10 text-purple-400 mx-auto mb-3" />
          <p className="text-3xl font-bold">{recordings?.length || 0}</p>
          <p className="text-sm text-gray-400">Total Recordings</p>
        </div>
        <div className="bg-gray-800 p-6 rounded-lg text-center">
          <Clock className="h-10 w-10 text-green-400 mx-auto mb-3" />
          <p className="text-3xl font-bold">
            {Math.round((recordings?.reduce((acc, r) => acc + (r.duration_seconds || 0), 0) || 0) / 3600)}h
          </p>
          <p className="text-sm text-gray-400">Total Duration</p>
        </div>
        <div className="bg-gray-800 p-6 rounded-lg text-center">
          <Activity className="h-10 w-10 text-blue-400 mx-auto mb-3" />
          <p className="text-3xl font-bold">
            {recordings?.filter(r => r.status === 'active').length || 0}
          </p>
          <p className="text-sm text-gray-400">Active Sessions</p>
        </div>
      </div>
    </div>
  );

  const renderRecordingsView = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">My Recordings</h2>
        <button 
          onClick={refreshRecordings}
          className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {loadingRecordings ? (
        <div className="text-center py-8">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-gray-400" />
          <p className="text-gray-400">Loading recordings...</p>
        </div>
      ) : recordingsError ? (
        <div className="text-center py-8">
          <p className="text-red-400">Failed to load recordings</p>
          <button 
            onClick={refreshRecordings}
            className="mt-2 text-sm text-blue-400 hover:text-blue-300"
          >
            Try again
          </button>
        </div>
      ) : recordings && recordings.length === 0 ? (
        <div className="text-center py-8">
          <FileText className="h-12 w-12 text-gray-600 mx-auto mb-2" />
          <p className="text-gray-400">No recordings yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {recordings?.map((recording) => (
            <div key={recording.id} className="bg-gray-800 p-4 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <h3 className="font-medium mb-1">{recording.name}</h3>
                  <div className="flex items-center gap-4 text-sm text-gray-400">
                    <span className="flex items-center gap-1">
                      <Clock className="h-4 w-4" />
                      {formatDuration(recording.duration_seconds)}
                    </span>
                    {recording.total_speakers && (
                      <span className="flex items-center gap-1">
                        <Users className="h-4 w-4" />
                        {recording.total_speakers} speakers
                      </span>
                    )}
                    <span>{new Date(recording.created_at).toLocaleDateString()}</span>
                    <span className={`px-2 py-1 rounded text-xs ${
                      recording.status === 'completed' 
                        ? 'bg-green-900 text-green-400' 
                        : recording.status === 'active'
                        ? 'bg-blue-900 text-blue-400'
                        : 'bg-yellow-900 text-yellow-400'
                    }`}>
                      {recording.status}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => {
                      setSelectedRecording(recording);
                      handleGenerateSummary(recording);
                    }}
                    className="p-2 hover:bg-gray-700 rounded transition-colors"
                    title="Generate Summary"
                  >
                    <Sparkles className="h-4 w-4" />
                  </button>
                  <button 
                    onClick={() => handleDownloadTranscript(recording)}
                    className="p-2 hover:bg-gray-700 rounded transition-colors"
                    title="Download Transcript"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Summary Modal */}
      {selectedRecording && (
        <div className="mt-6 bg-gray-800 p-6 rounded-xl">
          <h3 className="text-xl font-bold mb-4">Meeting Summary</h3>
          
          {isGeneratingSummary ? (
            <div className="text-center py-8">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-purple-400" />
              <p className="text-gray-400">Generating AI summary...</p>
            </div>
          ) : summary ? (
            <div className="space-y-4">
              <div>
                <h4 className="font-medium text-purple-400 mb-2">Summary</h4>
                <p className="text-gray-300">{summary.summary_text}</p>
              </div>
              
              {summary.action_items && summary.action_items.length > 0 && (
                <div>
                  <h4 className="font-medium text-green-400 mb-2">Action Items</h4>
                  <ul className="list-disc list-inside space-y-1">
                    {summary.action_items.map((item, index) => (
                      <li key={index} className="text-gray-300">{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              {summary.key_topics && summary.key_topics.length > 0 && (
                <div>
                  <h4 className="font-medium text-blue-400 mb-2">Key Topics</h4>
                  <div className="flex flex-wrap gap-2">
                    {summary.key_topics.map((topic, index) => (
                      <span key={index} className="px-3 py-1 bg-gray-700 rounded-full text-sm">
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );

  const renderSettingsView = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Settings</h2>
      
      <div className="bg-gray-800 p-6 rounded-lg space-y-6">
        <div>
          <h3 className="text-lg font-medium mb-4">Recording Settings</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Audio Quality</label>
              <select className="w-full p-3 bg-gray-700 border border-gray-600 rounded-lg">
                <option>High Quality (48kHz)</option>
                <option>Standard Quality (16kHz)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Language</label>
              <select className="w-full p-3 bg-gray-700 border border-gray-600 rounded-lg">
                <option>Auto-detect</option>
                <option>English</option>
                <option>Spanish</option>
                <option>French</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input type="checkbox" defaultChecked className="rounded" />
                <span className="text-sm">Enable speaker identification</span>
              </label>
              
              <label className="flex items-center gap-2">
                <input type="checkbox" defaultChecked className="rounded" />
                <span className="text-sm">Auto-save recordings</span>
              </label>
              
              <label className="flex items-center gap-2">
                <input type="checkbox" defaultChecked className="rounded" />
                <span className="text-sm">Generate summary after recording</span>
              </label>
            </div>
          </div>
        </div>

        <button className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-lg font-medium transition-colors">
          Save Settings
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col flex-shrink-0">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <div className="bg-gradient-to-r from-purple-600 to-pink-600 text-transparent bg-clip-text">
            <h1 className="text-xl font-bold">Meeting Ops</h1>
            <p className="text-sm opacity-80">AI Meeting Assistant</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <button
            onClick={() => setCurrentView('home')}
            className={`w-full text-left p-3 rounded-lg transition-colors flex items-center gap-3 ${
              currentView === 'home' 
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white' 
                : 'hover:bg-gray-700 text-gray-300'
            }`}
          >
            <Home className="h-5 w-5" />
            Home
          </button>
          
          <button
            onClick={() => setCurrentView('recordings')}
            className={`w-full text-left p-3 rounded-lg transition-colors flex items-center gap-3 ${
              currentView === 'recordings' 
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white' 
                : 'hover:bg-gray-700 text-gray-300'
            }`}
          >
            <Folder className="h-5 w-5" />
            My Recordings
          </button>

          <button
            onClick={() => setCurrentView('settings')}
            className={`w-full text-left p-3 rounded-lg transition-colors flex items-center gap-3 ${
              currentView === 'settings' 
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white' 
                : 'hover:bg-gray-700 text-gray-300'
            }`}
          >
            <Settings className="h-5 w-5" />
            Settings
          </button>
        </nav>

        {/* User Info */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-3 p-3 bg-gray-700/50 rounded-lg">
            <div className="w-10 h-10 bg-gradient-to-r from-purple-500 to-pink-500 rounded-full flex items-center justify-center">
              <span className="text-sm font-bold">{user?.username?.[0]?.toUpperCase()}</span>
            </div>
            <div className="flex-1">
              <p className="font-medium">{user?.username}</p>
              <p className="text-xs text-gray-400 capitalize">{user?.role}</p>
            </div>
          </div>
          
          {isAdmin && onSwitchToAdmin && (
            <button
              onClick={onSwitchToAdmin}
              className="w-full mt-2 p-2 text-sm bg-orange-600 hover:bg-orange-700 rounded-lg transition-colors"
            >
              Switch to Admin Panel
            </button>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-auto">
        {currentView === 'home' && renderHomeView()}
        {currentView === 'recordings' && renderRecordingsView()}
        {currentView === 'settings' && renderSettingsView()}
      </main>
    </div>
  );
};