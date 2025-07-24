import { useState, useEffect } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { User, LogOut, Settings as SettingsIcon } from 'lucide-react';
import SessionDetails from './SessionDetails';
import { FileManager } from './components/FileManager';
import { AudioPlayer } from './components/AudioPlayer';
import { useAuth } from './contexts/AuthContext';
import { SettingsPage } from './components/Settings/SettingsPage';
import { PerformanceMonitor } from './components/PerformanceMonitor';
import ModelPerformanceDashboard from './components/ModelPerformanceDashboard';
import { getErrorMessage } from './utils/errorHandling';
import { HelpModal } from './components/HelpModal';
import { CalendarManager } from './components/CalendarManager';
import { WebhookManager } from './components/WebhookManager';
import { AIModelsManager } from './components/AIModelsManager';
import { MeetingTemplateSelector } from './components/MeetingTemplateSelector';
import { Tooltip } from './components/Tooltip';
import { LiveTranscriptionFeed } from './components/LiveTranscriptionFeed';
import { LiveSummarization } from './components/LiveSummarization';
import { UnifiedSearchInterface } from './components/UnifiedSearchInterface';
import { IntelligentAssistantDraggable } from './components/IntelligentAssistantDraggable';
import { SessionReport } from './components/SessionReport';
import { AuthErrorHandler } from './components/AuthErrorHandler';
import { NPUModelSettings } from './components/NPUModelSettings';
import { UserManagement } from './components/UserManagement';
import { AIAgents } from './components/AIAgents';

interface SystemStatus {
  transcriber_ready: boolean;
  npu_available: boolean;
  speaker_diarization_ready: boolean;
  active_sessions: number;
  system_info: {
    onnx_whisper_ready: boolean;
    npu_available: boolean;
    onnx_providers: string[];
    model_path: string;
  };
  diarizer_info: {
    ready: boolean;
    device: string;
    model: string;
  };
}

interface TranscriptionData {
  text: string;
  timestamp: string;
  confidence: number;
  processing_time: number;
  npu_accelerated: boolean;
  speaker_info?: {
    num_speakers: number;
    speakers: Array<{
      id: string;
      total_time: number;
      segments: number;
    }>;
  };
}

interface RecordingSession {
  id: number;
  session_id: string;
  name: string;
  description?: string;
  start_time: string;
  end_time?: string;
  duration_seconds: number;
  status: 'active' | 'completed' | 'paused' | 'failed';
  total_transcriptions: number;
  total_speakers: number;
  meeting_type?: string;
  npu_accelerated: boolean;
}

interface AudioDevice {
  id: string;
  name: string;
  channels: number;
  sample_rate: number;
}

interface Settings {
  audio: {
    input_source: { value: string };
    sample_rate: { value: number };
    channels: { value: number };
    input_gain: { value: number };
    noise_reduction: { value: boolean };
    auto_gain_control: { value: boolean };
  };
  ai: {
    npu_acceleration: { value: boolean };
    speaker_diarization: { value: boolean };
    real_time_processing: { value: boolean };
    whisper_model: { value: string };
    language: { value: string };
    max_speakers: { value: number };
  };
  storage: {
    auto_cleanup_days: { value: number };
    export_format: { value: string };
    recording_format: { value: string };
    compression: { value: boolean };
    max_storage_gb: { value: number };
  };
  network: {
    remote_access: { value: boolean };
    api_port: { value: number };
    websocket_port: { value: number };
    ssl_enabled: { value: boolean };
    allowed_origins: { value: string[] };
  };
}

function Dashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [performanceView, setPerformanceView] = useState<'system' | 'models'>('models');
  
  // Parse current view from URL hash or default to dashboard
  const getCurrentView = () => {
    const hash = location.hash.replace('#', '');
    return hash || 'dashboard';
  };
  
  const [currentView, setCurrentView] = useState(getCurrentView());
  const [selectedAudioFile, setSelectedAudioFile] = useState<any>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [activeSession, setActiveSession] = useState<RecordingSession | null>(null);
  const [recentTranscriptions, setRecentTranscriptions] = useState<TranscriptionData[]>([]);
  const [recentSessions, setRecentSessions] = useState<RecordingSession[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([]);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [showTemplateSelector, setShowTemplateSelector] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  
  // Update view when URL hash changes
  useEffect(() => {
    const handleHashChange = () => {
      changeView(getCurrentView());
    };
    
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);
  
  // Function to change view and update URL
  const changeView = (view: string) => {
    setCurrentView(view);
    navigate(`#${view}`);
  };

  // Fetch system status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('/api/status');
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

  // Fetch recent sessions
  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('/api/recording-sessions?limit=10');
        const data = await response.json();
        setRecentSessions(data.sessions || []);
        
        // Don't automatically set active sessions on page load
        // User should explicitly start recording to create a new session
      } catch (error) {
        console.error('Failed to fetch sessions:', error);
      }
    };
    
    fetchSessions();
    const interval = setInterval(fetchSessions, 10000);
    return () => clearInterval(interval);
  }, []);

  // Fetch settings
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        setSettings(data.settings);
      } catch (error) {
        console.error('Failed to fetch settings:', error);
      }
    };
    
    fetchSettings();
  }, []);

  // Fetch audio devices
  useEffect(() => {
    const fetchAudioDevices = async () => {
      try {
        const response = await fetch('/api/audio-devices');
        const data = await response.json();
        setAudioDevices(data.devices || []);
      } catch (error) {
        console.error('Failed to fetch audio devices:', error);
      }
    };
    
    fetchAudioDevices();
  }, []);

  // Fetch audio level when recording
  useEffect(() => {
    if (!activeSession) {
      setAudioLevel(0);
      return;
    }
    
    const fetchAudioLevel = async () => {
      try {
        const response = await fetch('/api/audio-level');
        const data = await response.json();
        setAudioLevel(data.level || 0);
      } catch (error) {
        console.error('Failed to fetch audio level:', error);
      }
    };
    
    const interval = setInterval(fetchAudioLevel, 100); // Update 10 times per second
    return () => clearInterval(interval);
  }, [activeSession]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === '/') {
        event.preventDefault();
        setShowHelpModal(true);
      }
      if (event.key === 'Escape') {
        setShowHelpModal(false);
        setShowAdvancedSettings(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  // API functions for session management
  const startRecording = async () => {
    if (isCreatingSession) return;
    
    setIsCreatingSession(true);
    try {
      // Create new session
      const response = await fetch('/api/recording-sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: `Meeting ${new Date().toLocaleString()}`,
          description: 'Live recording session',
          meeting_type: selectedTemplate || 'general',
          template_id: selectedTemplate
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const session = data.session;
        
        // Start recording for the session
        const startResponse = await fetch(`/api/recording-sessions/${session.session_id}/start`, {
          method: 'POST',
        });

        if (startResponse.ok) {
          const startData = await startResponse.json();
          setActiveSession(startData.session);
          console.log('🎙️ Recording started:', startData.session);
        } else {
          const errorData = await startResponse.json().catch(() => ({}));
          console.error('Failed to start recording:', errorData);
          alert(`Failed to start recording: ${errorData.detail || startResponse.statusText}`);
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error('Failed to create session:', errorData);
        alert(`Failed to create session: ${errorData.detail || response.statusText}`);
      }
    } catch (error) {
      console.error('Error starting recording:', error);
      alert(`Error starting recording: ${getErrorMessage(error)}`);
    } finally {
      setIsCreatingSession(false);
    }
  };

  const stopRecording = async () => {
    if (!activeSession) return;
    
    try {
      const response = await fetch(`/api/recording-sessions/${activeSession.session_id}/stop`, {
        method: 'POST',
      });

      if (response.ok) {
        const data = await response.json();
        console.log('⏹️ Recording stopped:', data.session);
        setActiveSession(null);
        
        // Refresh sessions list
        const sessionsResponse = await fetch('/api/recording-sessions?limit=10');
        const sessionsData = await sessionsResponse.json();
        setRecentSessions(sessionsData.sessions || []);
      } else {
        console.error('Failed to stop recording:', response.statusText);
      }
    } catch (error) {
      console.error('Error stopping recording:', error);
    }
  };

  const pauseRecording = async () => {
    if (!activeSession) return;
    
    try {
      const response = await fetch(`/api/recording-sessions/${activeSession.session_id}/pause`, {
        method: 'POST',
      });

      if (response.ok) {
        const data = await response.json();
        setActiveSession(data.session);
        console.log('⏸️ Recording paused:', data.session);
      } else {
        console.error('Failed to pause recording:', response.statusText);
      }
    } catch (error) {
      console.error('Error pausing recording:', error);
    }
  };

  const resumeRecording = async () => {
    if (!activeSession) return;
    
    try {
      const response = await fetch(`/api/recording-sessions/${activeSession.session_id}/start`, {
        method: 'POST',
      });

      if (response.ok) {
        const data = await response.json();
        setActiveSession(data.session);
        console.log('▶️ Recording resumed:', data.session);
      } else {
        console.error('Failed to resume recording:', response.statusText);
      }
    } catch (error) {
      console.error('Error resuming recording:', error);
    }
  };

  // Session management functions
  const viewSessionDetails = async (sessionId: string) => {
    setSelectedSessionId(sessionId);
  };

  const exportSession = async (sessionId: string, format: string = 'json') => {
    try {
      const response = await fetch(`/api/recording-sessions/${sessionId}/export?format=${format}`);
      if (response.ok) {
        const data = await response.json();
        
        // Create download link
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `session_${sessionId}_export.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('Session exported successfully');
      }
    } catch (error) {
      console.error('Error exporting session:', error);
    }
  };

  // Settings management functions
  const saveSettings = async (category: string, updatedSettings: any) => {
    setIsSavingSettings(true);
    try {
      const response = await fetch(`/api/settings/${category}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updatedSettings),
      });

      if (response.ok) {
        console.log(`✅ ${category} settings saved successfully`);
        
        // Refresh settings
        const settingsResponse = await fetch('/api/settings');
        const settingsData = await settingsResponse.json();
        setSettings(settingsData.settings);
      } else {
        console.error('Failed to save settings:', response.statusText);
      }
    } catch (error) {
      console.error('Error saving settings:', error);
    } finally {
      setIsSavingSettings(false);
    }
  };

  const updateLocalSetting = (category: string, key: string, value: any) => {
    if (!settings) return;
    
    setSettings(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        [category]: {
          ...prev[category as keyof Settings],
          [key]: { value }
        }
      };
    });
  };

  const renderDashboard = () => (
    <div className="space-y-8">
      
      {/* Hero Section */}
      <div className="text-center bg-gradient-to-r from-purple-900/30 to-pink-900/30 rounded-lg p-8 border border-purple-700/50">
        <h1 className="text-5xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-4">
          Unicorn Commander: Meeting Ops
        </h1>
        <p className="text-xl text-gray-300 mb-2">NPU-Accelerated Meeting Recording Appliance</p>
        <p className="text-gray-400">Real-time transcription • Speaker diarization • AI summarization</p>
      </div>

      {/* System Health Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        
        {/* System Status */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-blue-400">System Status</h3>
            <div className={`w-3 h-3 rounded-full ${systemStatus?.transcriber_ready ? 'bg-green-400' : 'bg-red-400'}`}></div>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span>Transcriber:</span>
              <span className={systemStatus?.transcriber_ready ? "text-green-400" : "text-red-400"}>
                {systemStatus?.transcriber_ready ? "Ready" : "Error"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Processing:</span>
              <span className={systemStatus?.npu_available ? "text-green-400" : "text-yellow-400"}>
                {systemStatus?.npu_available ? "NPU" : "CPU"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Audio Input:</span>
              <span className="text-green-400">Connected</span>
            </div>
          </div>
        </div>

        {/* Hardware Status */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-purple-400">Hardware</h3>
            <div className="w-3 h-3 rounded-full bg-green-400"></div>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span>NPU:</span>
              <Tooltip content={systemStatus?.npu_available ? "NPU acceleration active - 16 TOPS INT8 performance" : "NPU not detected - using CPU fallback"}>
                <span className={systemStatus?.npu_available ? "text-green-400" : "text-gray-400"}>
                  {systemStatus?.npu_available ? "Phoenix" : "N/A"}
                </span>
              </Tooltip>
            </div>
            <div className="flex justify-between">
              <span>Model:</span>
              <span className="text-blue-400">Whisper Base</span>
            </div>
            <div className="flex justify-between">
              <span>Storage:</span>
              <span className="text-green-400">78% Free</span>
            </div>
          </div>
        </div>

        {/* Audio Input */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-green-400">Audio Input</h3>
            <div className={`w-3 h-3 rounded-full ${audioLevel > 0.1 ? 'bg-green-400 animate-pulse' : 'bg-green-400'}`}></div>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span>Source:</span>
              <span className="text-blue-400">{audioDevices.find(d => d.id === settings?.audio.input_source.value)?.name || 'Default'}</span>
            </div>
            <div className="flex justify-between">
              <span>Sample Rate:</span>
              <span className="text-gray-300">{(settings?.audio.sample_rate.value || 16000) / 1000}kHz</span>
            </div>
            <div className="flex justify-between items-center">
              <span>Level:</span>
              <div className="flex items-center space-x-2">
                <div className="w-24 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-100 ${
                      audioLevel > 0.8 ? 'bg-red-500' : 
                      audioLevel > 0.5 ? 'bg-yellow-500' : 'bg-green-400'
                    }`}
                    style={{width: `${audioLevel * 100}%`}}
                  />
                </div>
                <span className="text-gray-300 text-xs">{Math.round(audioLevel * 100)}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Current Session */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-yellow-400">Active Session</h3>
            <div className={`w-3 h-3 rounded-full ${activeSession ? 'bg-red-400 animate-pulse' : 'bg-gray-600'}`}></div>
          </div>
          {activeSession ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span>Duration:</span>
                <span className="text-green-400">
                  {Math.floor(activeSession.duration_seconds / 60) || Math.floor((Date.now() - new Date(activeSession.start_time).getTime()) / 60000)}m
                </span>
              </div>
              <div className="flex justify-between">
                <span>Speakers:</span>
                <span className="text-blue-400">{activeSession.total_speakers || 0}</span>
              </div>
              <div className="flex justify-between">
                <span>Transcriptions:</span>
                <span className="text-purple-400">{activeSession.total_transcriptions || 0}</span>
              </div>
              <div className="flex justify-between">
                <span>Status:</span>
                <span className="text-yellow-400 capitalize">{activeSession.status}</span>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No active recording</p>
          )}
        </div>
      </div>

      {/* Recording Controls */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-6 text-center">Recording Controls</h3>
        
        {/* Template Selection for new recordings */}
        {!activeSession && !showTemplateSelector && (
          <div className="mb-4 text-center">
            <button
              onClick={() => setShowTemplateSelector(true)}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Select meeting template ({selectedTemplate ? selectedTemplate.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'General Meeting'})
            </button>
          </div>
        )}
        
        {/* Template Selector */}
        {showTemplateSelector && !activeSession && (
          <div className="mb-6">
            <MeetingTemplateSelector
              onTemplateSelect={(templateId) => {
                setSelectedTemplate(templateId);
                setShowTemplateSelector(false);
              }}
              selectedTemplate={selectedTemplate}
              compact={true}
            />
          </div>
        )}
        
        <div className="flex justify-center space-x-4">
          {!activeSession ? (
            <Tooltip content={!systemStatus?.transcriber_ready ? "System not ready - check transcriber status" : "Start a new recording session"}>
              <button 
                onClick={startRecording}
                disabled={!systemStatus?.transcriber_ready || isCreatingSession}
                className="bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 px-8 py-4 rounded-lg font-medium transition-all text-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              >
                <div className="w-4 h-4 bg-white rounded-full"></div>
                <span>{isCreatingSession ? 'Starting...' : 'Start Recording'}</span>
              </button>
            </Tooltip>
          ) : (
            <div className="flex space-x-4">
              {activeSession.status === 'active' ? (
                <button 
                  onClick={pauseRecording}
                  className="bg-gradient-to-r from-yellow-500 to-orange-500 hover:from-yellow-600 hover:to-orange-600 px-6 py-3 rounded-lg font-medium transition-all flex items-center space-x-2"
                >
                  <div className="w-2 h-4 bg-white"></div>
                  <div className="w-2 h-4 bg-white"></div>
                  <span>Pause</span>
                </button>
              ) : (
                <button 
                  onClick={resumeRecording}
                  className="bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 px-6 py-3 rounded-lg font-medium transition-all flex items-center space-x-2"
                >
                  <div className="w-0 h-0 border-l-4 border-l-white border-y-2 border-y-transparent"></div>
                  <span>Resume</span>
                </button>
              )}
              <button 
                onClick={stopRecording}
                className="bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 px-6 py-3 rounded-lg font-medium transition-all flex items-center space-x-2"
              >
                <div className="w-4 h-4 bg-white"></div>
                <span>Stop & Save</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Live Transcription and Summarization */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <LiveTranscriptionFeed 
          sessionId={activeSession?.session_id || null}
          isActive={activeSession?.status === 'active'}
        />
        <LiveSummarization
          sessionId={activeSession?.session_id || null}
          isActive={activeSession?.status === 'active'}
          templateType={selectedTemplate}
        />
      </div>
    </div>
  );

  const renderSessions = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Recording Sessions</h2>
        <button className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 px-4 py-2 rounded-lg font-medium transition-all">
          Export All
        </button>
      </div>
      
      <div className="grid gap-4">
        {recentSessions.length === 0 ? (
          <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center">
            <div className="w-16 h-16 bg-gray-700 rounded-full mx-auto mb-4 flex items-center justify-center">
              <div className="w-6 h-6 bg-gray-500 rounded-full"></div>
            </div>
            <p className="text-gray-400">No recording sessions yet</p>
            <p className="text-sm text-gray-500 mt-2">Start your first recording to see session history</p>
          </div>
        ) : (
          recentSessions.map((session, index) => (
            <div key={session.session_id || index} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-white">{session.name}</h3>
                  <p className="text-gray-400 mb-2">
                    {new Date(session.start_time).toLocaleString()} • 
                    {session.duration_seconds > 0 ? ` ${Math.floor(session.duration_seconds / 60)}m` : ' In Progress'} •
                    {session.meeting_type && ` ${session.meeting_type}`}
                  </p>
                  <div className="flex items-center space-x-4 text-sm text-gray-500">
                    <span>🎤 {session.total_transcriptions} transcriptions</span>
                    <span>👥 {session.total_speakers} speakers</span>
                    {session.npu_accelerated && <span className="bg-green-600 text-xs px-2 py-1 rounded">NPU</span>}
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                    session.status === 'completed' ? 'bg-green-600' : 
                    session.status === 'active' ? 'bg-red-600' : 
                    session.status === 'paused' ? 'bg-yellow-600' : 'bg-gray-600'
                  }`}>
                    {session.status}
                  </span>
                  <button 
                    onClick={() => viewSessionDetails(session.session_id)}
                    className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                  >
                    View Details
                  </button>
                  <button 
                    onClick={() => setSelectedReportId(session.session_id)}
                    className="bg-green-600 hover:bg-green-700 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                  >
                    View Report
                  </button>
                  <button 
                    onClick={() => exportSession(session.session_id)}
                    className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                  >
                    Export
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  const renderSettings = () => {
    if (showAdvancedSettings) {
      return <SettingsPage />;
    }
    
    return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">System Settings</h2>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowAdvancedSettings(true)}
            className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg text-sm"
          >
            Advanced Settings
          </button>
          {isSavingSettings && (
            <span className="text-yellow-400 animate-pulse">Saving...</span>
          )}
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Audio Settings */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold text-blue-400">Audio Input</h3>
            <button
              onClick={() => {
                if (!settings) return;
                const audioSettings: any = {};
                Object.entries(settings.audio).forEach(([key, val]) => {
                  audioSettings[key] = val.value;
                });
                saveSettings('audio', audioSettings);
              }}
              className="bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded text-sm"
            >
              Save
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Input Source</label>
              <select 
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none"
                value={settings?.audio.input_source.value || 'default'}
                onChange={(e) => updateLocalSetting('audio', 'input_source', e.target.value)}
                title="Select the audio input device for recording. Default uses system default microphone."
              >
                {audioDevices.map(device => (
                  <option key={device.id} value={device.id} className="bg-gray-700 text-white">
                    {device.name} ({device.channels}ch, {device.sample_rate}Hz)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center">
                Sample Rate 
                <Tooltip content="Audio sampling rate. 16kHz is recommended for speech (smaller files, faster processing). 44.1kHz/48kHz for music quality (larger files, more processing)." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </label>
              <select 
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none"
                value={settings?.audio.sample_rate.value || 16000}
                onChange={(e) => updateLocalSetting('audio', 'sample_rate', parseInt(e.target.value))}
                title="Higher sample rates provide better quality but use more processing power and storage"
              >
                <option value="16000" className="bg-gray-700 text-white">16kHz (Recommended for speech)</option>
                <option value="44100" className="bg-gray-700 text-white">44.1kHz (CD quality)</option>
                <option value="48000" className="bg-gray-700 text-white">48kHz (Professional quality)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center">
                Input Gain: {settings?.audio.input_gain.value || 70}%
                <Tooltip content="Adjust microphone input level. 70% is recommended. Too low = quiet audio, too high = distortion and clipping." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </label>
              <input 
                type="range" 
                className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer slider:bg-blue-500" 
                min="0" 
                max="100" 
                value={settings?.audio.input_gain.value || 70}
                onChange={(e) => updateLocalSetting('audio', 'input_gain', parseInt(e.target.value))}
                title={`Current gain: ${settings?.audio.input_gain.value || 70}% - Adjust based on your microphone`}
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>Quiet</span>
                <span className="text-green-400">Optimal (70%)</span>
                <span>Loud</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <span>Noise Reduction</span>
                <Tooltip content="Reduces background noise like keyboard clicks, air conditioning, etc. Recommended ON for better audio quality." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </div>
              <button
                onClick={() => updateLocalSetting('audio', 'noise_reduction', !settings?.audio.noise_reduction.value)}
                className={`w-12 h-6 rounded-full relative transition-colors ${settings?.audio.noise_reduction.value ? 'bg-green-600' : 'bg-gray-600'}`}
                title={`Noise reduction is ${settings?.audio.noise_reduction.value ? 'enabled' : 'disabled'}`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings?.audio.noise_reduction.value ? 'left-6' : 'left-0.5'}`}></div>
              </button>
            </div>
          </div>
        </div>

        {/* AI Processing */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold text-purple-400">AI Processing</h3>
            <button
              onClick={() => {
                if (!settings) return;
                const aiSettings: any = {};
                Object.entries(settings.ai).forEach(([key, val]) => {
                  aiSettings[key] = val.value;
                });
                saveSettings('ai', aiSettings);
              }}
              className="bg-purple-600 hover:bg-purple-700 px-3 py-1 rounded text-sm"
            >
              Save
            </button>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <span>NPU Acceleration</span>
                <Tooltip content={systemStatus?.npu_available ? "AMD Phoenix NPU detected! Provides up to 220x faster AI processing than CPU. Recommended ON for best performance." : "NPU not available. Using CPU processing. Install AMD NPU drivers for hardware acceleration."} position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </div>
              <button
                onClick={() => updateLocalSetting('ai', 'npu_acceleration', !settings?.ai.npu_acceleration.value)}
                className={`w-12 h-6 rounded-full relative transition-colors ${settings?.ai.npu_acceleration.value && systemStatus?.npu_available ? 'bg-green-600' : 'bg-gray-600'}`}
                disabled={!systemStatus?.npu_available}
                title={systemStatus?.npu_available ? `NPU acceleration ${settings?.ai.npu_acceleration.value ? 'enabled' : 'disabled'}` : 'NPU not available'}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings?.ai.npu_acceleration.value ? 'left-6' : 'left-0.5'}`}></div>
              </button>
              {!systemStatus?.npu_available && (
                <span className="ml-2 text-xs text-yellow-400">CPU only</span>
              )}
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <span>Speaker Diarization</span>
                <Tooltip content="Identifies different speakers in the recording (Speaker 1, Speaker 2, etc.). Recommended ON for meetings with multiple participants." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </div>
              <button
                onClick={() => updateLocalSetting('ai', 'speaker_diarization', !settings?.ai.speaker_diarization.value)}
                className={`w-12 h-6 rounded-full relative transition-colors ${settings?.ai.speaker_diarization.value ? 'bg-green-600' : 'bg-gray-600'}`}
                title={`Speaker identification is ${settings?.ai.speaker_diarization.value ? 'enabled' : 'disabled'}`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings?.ai.speaker_diarization.value ? 'left-6' : 'left-0.5'}`}></div>
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <span>Real-time Processing</span>
                <Tooltip content="Process audio as it's being recorded for live transcription. Turn OFF for batch processing only (uses less resources during recording)." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </div>
              <button
                onClick={() => updateLocalSetting('ai', 'real_time_processing', !settings?.ai.real_time_processing.value)}
                className={`w-12 h-6 rounded-full relative transition-colors ${settings?.ai.real_time_processing.value ? 'bg-green-600' : 'bg-gray-600'}`}
                title={`Real-time processing is ${settings?.ai.real_time_processing.value ? 'enabled' : 'disabled'}`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings?.ai.real_time_processing.value ? 'left-6' : 'left-0.5'}`}></div>
              </button>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center">
                Whisper Model 
                <Tooltip content="AI transcription model size. Tiny = fastest/less accurate, Base = balanced (recommended), Small = slower/more accurate. With NPU acceleration, all models are fast." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </label>
              <select 
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 focus:outline-none"
                value={settings?.ai.whisper_model.value || 'base'}
                onChange={(e) => updateLocalSetting('ai', 'whisper_model', e.target.value)}
                title="Balance speed vs accuracy based on your needs"
              >
                <option value="tiny" className="bg-gray-700 text-white">Tiny (Fastest, basic accuracy)</option>
                <option value="base" className="bg-gray-700 text-white">Base (Recommended - balanced)</option>
                <option value="small" className="bg-gray-700 text-white">Small (Slower, better accuracy)</option>
                <option value="medium" className="bg-gray-700 text-white">Medium (Much slower, high accuracy)</option>
              </select>
              <div className="text-xs text-gray-500 mt-1">
                {systemStatus?.npu_available ? "🚀 NPU accelerated - all models are fast!" : "💻 CPU only - consider Tiny or Base for better performance"}
              </div>
            </div>
          </div>
        </div>

        {/* Storage */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold text-green-400">Storage</h3>
            <button
              onClick={() => {
                if (!settings) return;
                const storageSettings: any = {};
                Object.entries(settings.storage).forEach(([key, val]) => {
                  storageSettings[key] = val.value;
                });
                saveSettings('storage', storageSettings);
              }}
              className="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-sm"
            >
              Save
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-2">
                <span>Local Storage</span>
                <span className="text-green-400">256GB Free</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-3">
                <div className="bg-green-400 h-3 rounded-full" style={{width: '78%'}}></div>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <span>Auto-cleanup after</span>
                <Tooltip content="Automatically delete old recordings and transcriptions to save disk space. Recommended: 30-60 days. Set to 'Never' if you need long-term storage." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </div>
              <select 
                className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-white focus:border-green-500 focus:ring-2 focus:ring-green-500/20 focus:outline-none"
                value={settings?.storage.auto_cleanup_days.value || 30}
                onChange={(e) => updateLocalSetting('storage', 'auto_cleanup_days', parseInt(e.target.value))}
                title="Balance storage space with data retention needs"
              >
                <option value="30" className="bg-gray-700 text-white">30 days (Recommended)</option>
                <option value="60" className="bg-gray-700 text-white">60 days</option>
                <option value="90" className="bg-gray-700 text-white">90 days</option>
                <option value="180" className="bg-gray-700 text-white">180 days</option>
                <option value="0" className="bg-gray-700 text-white">Never delete</option>
              </select>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <span>Export Format</span>
                <Tooltip content="Default format for exporting meeting transcripts. JSON = machine readable with metadata, TXT = human readable plain text, PDF = formatted document." position="right">
                  <span className="ml-2 text-gray-400 hover:text-gray-300 cursor-help">ℹ️</span>
                </Tooltip>
              </div>
              <select 
                className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-white focus:border-green-500 focus:ring-2 focus:ring-green-500/20 focus:outline-none"
                value={settings?.storage.export_format.value || 'json'}
                onChange={(e) => updateLocalSetting('storage', 'export_format', e.target.value)}
              >
                <option value="json" className="bg-gray-700 text-white">JSON (with metadata)</option>
                <option value="txt" className="bg-gray-700 text-white">Text (plain format)</option>
                <option value="pdf" className="bg-gray-700 text-white">PDF (formatted document)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Network */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold text-yellow-400">Network</h3>
            <button
              onClick={() => {
                if (!settings) return;
                const networkSettings: any = {};
                Object.entries(settings.network).forEach(([key, val]) => {
                  networkSettings[key] = val.value;
                });
                saveSettings('network', networkSettings);
              }}
              className="bg-yellow-600 hover:bg-yellow-700 px-3 py-1 rounded text-sm"
            >
              Save
            </button>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span>Status</span>
              <span className="text-green-400">Connected</span>
            </div>
            <div className="flex items-center justify-between">
              <span>IP Address</span>
              <span className="text-gray-300">192.168.1.100</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Remote Access</span>
              <button
                onClick={() => updateLocalSetting('network', 'remote_access', !settings?.network.remote_access.value)}
                className={`w-12 h-6 rounded-full relative ${settings?.network.remote_access.value ? 'bg-green-600' : 'bg-gray-600'}`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${settings?.network.remote_access.value ? 'left-6' : 'left-0.5'}`}></div>
              </button>
            </div>
            <div className="flex items-center justify-between">
              <span>API Port</span>
              <input 
                type="number"
                className="bg-gray-700 border border-gray-600 rounded px-2 py-1 w-24"
                value={settings?.network.api_port.value || 9050}
                onChange={(e) => updateLocalSetting('network', 'api_port', parseInt(e.target.value))}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
  };

  const renderFiles = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Audio Files</h2>
        <button className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 px-4 py-2 rounded-lg font-medium transition-all">
          Storage Stats
        </button>
      </div>
      
      <FileManager
        onFileSelect={(file) => setSelectedAudioFile(file)}
      />
    </div>
  );

  const renderAIModels = () => <AIModelsManager />;

  const renderPerformance = () => {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold">Performance Dashboard</h2>
          <div className="flex space-x-2 bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setPerformanceView('models')}
              className={`px-4 py-2 rounded-md transition-colors ${
                performanceView === 'models'
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Model Performance
            </button>
            <button
              onClick={() => setPerformanceView('system')}
              className={`px-4 py-2 rounded-md transition-colors ${
                performanceView === 'system'
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              System Monitor
            </button>
          </div>
        </div>
        
        {performanceView === 'models' ? (
          <ModelPerformanceDashboard />
        ) : (
          <PerformanceMonitor />
        )}
      </div>
    );
  };

  const renderAIAgents = () => {
    return <AIAgents />;
  };

  const renderUserManagement = () => {
    return <UserManagement />;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-900 to-purple-900 text-white flex">
      {/* Session Details Modal */}
      {selectedSessionId && (
        <SessionDetails 
          sessionId={selectedSessionId} 
          onClose={() => setSelectedSessionId(null)} 
        />
      )}
      
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800/50 backdrop-blur-lg border-r border-gray-700 p-4">
        <div className="flex items-center space-x-2 mb-8">
          <div className="w-8 h-8 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
            <div className="w-4 h-4 bg-white rounded-full"></div>
          </div>
          <h1 className="text-xl font-bold">Meeting Ops</h1>
        </div>
        
        <nav className="space-y-4">
          {/* Recording & Content Group */}
          <div>
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-4">
              Recording & Content
            </div>
            <div className="space-y-1">
              <Tooltip content="Main overview and recording controls" position="right">
                <button
                  onClick={() => changeView('dashboard')}
                  className={`w-full text-left py-3 px-4 rounded-lg transition-all ${ 
                    currentView === 'dashboard' 
                      ? 'bg-blue-600 text-white' 
                      : 'hover:bg-gray-700'
                  }`}
                >
                  📊 Dashboard
                </button>
              </Tooltip>
              <Tooltip content="View and manage recording sessions" position="right">
                <button
                  onClick={() => changeView('sessions')}
                  className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                    currentView === 'sessions' 
                      ? 'bg-blue-600 text-white' 
                      : 'hover:bg-gray-700'
                  }`}
                >
                  🎙️ Sessions
                </button>
              </Tooltip>
              <Tooltip content="Browse and manage audio files" position="right">
                <button
                  onClick={() => changeView('files')}
                  className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                    currentView === 'files' 
                      ? 'bg-blue-600 text-white' 
                      : 'hover:bg-gray-700'
                  }`}
                >
                  📁 Files
                </button>
              </Tooltip>
            </div>
          </div>
          {/* AI & Intelligence Group */}
          <div>
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-4">
              AI & Intelligence
            </div>
            <div className="space-y-1">
              <Tooltip content="Search meetings with AI-powered semantic search" position="right">
                <button
              onClick={() => changeView('search')}
              className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                currentView === 'search' 
                  ? 'bg-blue-600 text-white' 
                  : 'hover:bg-gray-700'
              }`}
            >
              🔍 Search
            </button>
          </Tooltip>
          <Tooltip content="Manage AI models and settings" position="right">
            <button
              onClick={() => changeView('ai-models')}
              className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                currentView === 'ai-models' 
                  ? 'bg-purple-600 text-white' 
                  : 'hover:bg-gray-700'
              }`}
            >
              🤖 AI Models
            </button>
          </Tooltip>
          <Tooltip content="Configure AI agents and assistants" position="right">
            <button
              onClick={() => changeView('ai-agents')}
              className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                currentView === 'ai-agents' 
                  ? 'bg-purple-600 text-white' 
                  : 'hover:bg-gray-700'
              }`}
            >
              🤝 AI Agents
            </button>
          </Tooltip>
            </div>
          </div>

          {/* Administration Group */}
          <div>
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-4">
              Administration
            </div>
            <div className="space-y-1">
              <Tooltip content="Manage users and permissions" position="right">
                <button
                  onClick={() => changeView('users')}
                  className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                    currentView === 'users' 
                      ? 'bg-orange-600 text-white' 
                      : 'hover:bg-gray-700'
                  }`}
                >
                  👥 Users
                </button>
              </Tooltip>
              <Tooltip content="Configure system settings" position="right">
                <button
                  onClick={() => changeView('settings')}
                  className={`w-full text-left py-3 px-4 rounded-lg transition-all ${
                    currentView === 'settings' 
                      ? 'bg-orange-600 text-white' 
                      : 'hover:bg-gray-700'
                  }`}
                >
                  <SettingsIcon className="h-4 w-4 inline-block mr-2" /> Settings
                </button>
              </Tooltip>
            </div>
          </div>
        </nav>
        
        {/* Help Button */}
        <div className="mt-4">
          <button
            onClick={() => setShowHelpModal(true)}
            className="w-full text-left py-3 px-4 rounded-lg hover:bg-gray-700 transition-all flex items-center justify-between"
          >
            <span>❓ Help & Docs</span>
            <span className="text-xs text-gray-400">Ctrl+/</span>
          </button>
        </div>

        {/* User Menu */}
        <div className="mt-auto mb-4 border-t border-gray-700 pt-4">
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-gray-700 transition-all"
            >
              <div className="w-8 h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center">
                <User className="h-4 w-4 text-white" />
              </div>
              <div className="flex-1 text-left">
                <p className="text-sm font-medium">{user?.username || 'User'}</p>
                <p className="text-xs text-gray-400">{user?.role || 'Member'}</p>
              </div>
            </button>
            
            {showUserMenu && (
              <div className="absolute bottom-full left-0 right-0 mb-2 bg-gray-700 rounded-lg shadow-lg border border-gray-600 overflow-hidden">
                <Link
                  to="/account"
                  className="flex items-center gap-3 px-4 py-3 hover:bg-gray-600 transition-colors"
                  onClick={() => setShowUserMenu(false)}
                >
                  <SettingsIcon className="h-4 w-4 text-gray-400" />
                  <span className="text-sm">Account Settings</span>
                </Link>
                <button
                  onClick={() => {
                    logout();
                    navigate('/login');
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-600 transition-colors text-red-400"
                >
                  <LogOut className="h-4 w-4" />
                  <span className="text-sm">Sign Out</span>
                </button>
              </div>
            )}
          </div>
        </div>
        
        {/* System Status Indicator */}
        <div className="mt-4 p-4 bg-gray-700/50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">System Health</span>
            <div className={`w-2 h-2 rounded-full ${systemStatus?.transcriber_ready ? 'bg-green-400' : 'bg-red-400'}`}></div>
          </div>
          <div className="text-xs text-gray-400">
            {systemStatus?.active_sessions || 0} active sessions
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-auto">
        {currentView === 'dashboard' && renderDashboard()}
        {currentView === 'sessions' && renderSessions()}
        {currentView === 'files' && renderFiles()}
        {currentView === 'settings' && renderSettings()}
        {currentView === 'performance' && renderPerformance()}
        {currentView === 'calendar' && <CalendarManager />}
        {currentView === 'webhooks' && <WebhookManager />}
        {currentView === 'search' && <UnifiedSearchInterface />}
        {currentView === 'ai-models' && renderAIModels()}
        {currentView === 'ai-agents' && renderAIAgents()}
        {currentView === 'users' && renderUserManagement()}
      </main>
      
      {/* Audio Player */}
      {selectedAudioFile && (
        <AudioPlayer
          file={selectedAudioFile}
          onClose={() => setSelectedAudioFile(null)}
        />
      )}
      
      {/* Session Report Modal */}
      {selectedReportId && (
        <SessionReport
          sessionId={selectedReportId}
          onClose={() => setSelectedReportId(null)}
        />
      )}
      
      {/* Help Modal */}
      {showHelpModal && (
        <HelpModal 
          isOpen={showHelpModal}
          onClose={() => setShowHelpModal(false)}
        />
      )}
      
      {/* Auth Error Handler */}
      <AuthErrorHandler />
      {/* Intelligent Assistant - Draggable and Resizable */}
      <IntelligentAssistantDraggable />
    </div>
  );
}

export default Dashboard;