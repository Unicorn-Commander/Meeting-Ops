import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Activity, Users, HardDrive, Cpu, Mic, Clock, 
  TrendingUp, Calendar, Mail, AlertCircle, CheckCircle,
  BarChart3, PieChart, Flag, Star, Zap, Database,
  Shield, Wifi, Volume2, Download, Upload, Settings,
  Circle, Square, MicOff, Loader2, Brain, ExternalLink,
  Maximize2, Minimize2
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useRecording } from '../../contexts/RecordingContext';
import { useNavigate } from 'react-router-dom';
import { UnifiedRecordingInterface } from '../UnifiedRecordingInterface';
import { SystemMonitor } from '../SystemMonitor';
import { LiveTranscription } from '../LiveTranscription';
import TranscriptionLoop from '../TranscriptionLoop';
import { MeetingIntelligenceDashboard } from '../MeetingIntelligenceDashboard';
import { config } from '../../config';

interface DashboardMetric {
  label: string;
  value: string | number;
  change?: number;
  icon: React.ElementType;
  color: string;
  trend?: 'up' | 'down' | 'stable';
}

interface SystemService {
  name: string;
  status: 'running' | 'stopped' | 'error';
  cpu?: number;
  memory?: number;
  uptime?: string;
}

export const UltimateDashboard: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { 
    isRecording: globalIsRecording, 
    activeSession,
    transcriptions: globalTranscriptions,
    setActiveSession,
    setIsRecording: setGlobalIsRecording,
    setRecordingTime: setGlobalRecordingTime,
    setTranscriptions: setGlobalTranscriptions,
    addTranscription 
  } = useRecording();
  const [activeView, setActiveView] = useState<'overview' | 'recording' | 'transcription' | 'analytics' | 'system'>('overview');
  const [realTimeData, setRealTimeData] = useState({
    activeSessions: 0,
    totalUsers: 0,
    npuUsage: 0,
    storageUsed: 0,
    transcriptionRate: 0,
    todaysMeetings: 0
  });
  const [loading, setLoading] = useState(true);
  const [fullscreenMode, setFullscreenMode] = useState<string | null>(null);
  const [popoutWindows, setPopoutWindows] = useState<{[key: string]: Window | null}>({});
  
  // Recording state for dashboard - use global state
  const isRecording = globalIsRecording;
  const recordingSessionId = activeSession?.id || null;
  const recordingTime = useRecording().recordingTime; // Use global recording time directly
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  // Key metrics
  const metrics: DashboardMetric[] = [
    {
      label: 'Active Sessions',
      value: realTimeData.activeSessions,
      icon: Mic,
      color: 'text-green-400',
      trend: 'up',
      change: 2
    },
    {
      label: 'Total Users',
      value: realTimeData.totalUsers,
      icon: Users,
      color: 'text-blue-400',
      trend: 'stable'
    },
    {
      label: 'NPU Usage',
      value: `${Math.round(realTimeData.npuUsage)}%`,
      icon: Zap,
      color: 'text-purple-400',
      trend: 'up',
      change: 12
    },
    {
      label: 'Storage',
      value: `${Math.round(realTimeData.storageUsed)}%`,
      icon: HardDrive,
      color: 'text-yellow-400',
      trend: 'up',
      change: 5
    },
    {
      label: 'Accuracy',
      value: `${realTimeData.transcriptionRate.toFixed(1)}%`,
      icon: CheckCircle,
      color: 'text-cyan-400',
      trend: 'stable'
    },
    {
      label: 'Today\'s Meetings',
      value: realTimeData.todaysMeetings,
      icon: Calendar,
      color: 'text-pink-400',
      trend: realTimeData.todaysMeetings > 0 ? 'up' : 'stable'
    }
  ];

  // System services
  const [services, setServices] = useState<SystemService[]>([]);

  // Recent activities
  const [recentActivities, setRecentActivities] = useState<any[]>([]);

  // Pop-out window management
  const openPopoutWindow = (type: string, sessionId: string) => {
    // For now, just show an alert until backend is implemented
    alert(`Pop-out window for ${type} - Feature coming soon!`);
    console.log(`[Dashboard] Pop-out requested for ${type} with session ${sessionId}`);
  };
  
  const toggleFullscreen = (type: string) => {
    setFullscreenMode(prev => prev === type ? null : type);
  };

  // Meeting intelligence data - dynamically computed from global state
  const meetingData = {
    transcript: globalTranscriptions.map(t => t.text).join(' '),
    notes: null,
    sessionId: recordingSessionId || '',
    duration: recordingTime,
    participants: Array.from(new Set(globalTranscriptions.map(t => t.speaker).filter(Boolean))),
    topics: []
  };

  // Recording functions
  const startRecording = useCallback(async () => {
    // If already recording, navigate to recording page
    if (globalIsRecording) {
      console.log('[Dashboard] Already recording, navigating to recording interface');
      navigate('/recording/live');
      return;
    }
    
    try {
      // Create recording session
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: `Dashboard Recording - ${new Date().toLocaleString()}`,
          description: 'Recording started from dashboard'
        })
      });

      if (!response.ok) throw new Error('Failed to create session');
      
      const sessionData = await response.json();
      
      // Start the recording
      const startResponse = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${sessionData.id}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!startResponse.ok) throw new Error('Failed to start recording');

      // Update global recording state
      const newSession = {
        id: sessionData.id,
        name: sessionData.name || `Dashboard Recording - ${new Date().toLocaleString()}`,
        status: 'recording' as const,
        startTime: new Date().toISOString(),
        duration: 0
      };

      setActiveSession(newSession);
      setGlobalIsRecording(true);
      setGlobalRecordingTime(0);
      
      // Setup WebSocket for live transcription
      const wsUrl = `${config.wsEndpoints.base}/ws/transcription/${sessionData.id}`;
      console.log('[Dashboard] Connecting to transcription WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[Dashboard] WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'transcription' && data.segment) {
            const segment = {
              id: Date.now().toString() + '_' + Math.random(),
              text: data.segment.text || '',
              timestamp: new Date().toISOString(),
              speaker: null,  // No speaker for live
              confidence: data.segment.confidence || 0.95,
              isFlagged: false
            };
            
            console.log('[Dashboard] Adding transcription segment:', segment);
            addTranscription(segment);
          }
        } catch (error) {
          console.error('[Dashboard] WebSocket message error:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[Dashboard] WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('[Dashboard] WebSocket closed');
      };
      
      // Start timer - update global recording time
      const startTime = Date.now();
      intervalRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        setGlobalRecordingTime(elapsed);
      }, 1000);

      console.log('[Dashboard] Recording started:', sessionData.id);
      
    } catch (error) {
      console.error('[Dashboard] Failed to start recording:', error);
      alert('Failed to start recording. Please try again.');
    }
  }, [globalIsRecording, navigate, setActiveSession, setGlobalIsRecording, setGlobalRecordingTime, addTranscription]);

  const stopRecording = useCallback(async () => {
    try {
      if (!recordingSessionId) {
        console.log('[Dashboard] No active session to stop');
        return;
      }
      
      // Stop recording on backend
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${recordingSessionId}/stop`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) throw new Error('Failed to stop recording');
      
      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      
      // Clear timer
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      
      // Update global state
      setGlobalIsRecording(false);
      setActiveSession(null);
      setGlobalRecordingTime(0);
      
      console.log('[Dashboard] Recording stopped');
      
    } catch (error) {
      console.error('[Dashboard] Failed to stop recording:', error);
      alert('Failed to stop recording. Please try again.');
    }
  }, [recordingSessionId, setGlobalIsRecording, setActiveSession, setGlobalRecordingTime]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Connect to existing recording WebSocket if recording is active
  useEffect(() => {
    if (globalIsRecording && activeSession?.id && !wsRef.current) {
      const wsUrl = `${config.wsEndpoints.base}/ws/transcription/${activeSession.id}`;
      console.log('[Dashboard] Connecting to existing transcription WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[Dashboard] WebSocket connected to existing session');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'transcription' && data.segment) {
            const segment = {
              id: Date.now().toString() + '_' + Math.random(),
              text: data.segment.text || '',
              timestamp: new Date().toISOString(),
              speaker: null,
              confidence: data.segment.confidence || 0.95,
              isFlagged: false
            };
            
            addTranscription(segment);
          }
        } catch (error) {
          console.error('[Dashboard] WebSocket message error:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[Dashboard] WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('[Dashboard] WebSocket closed');
      };
    }
  }, [globalIsRecording, activeSession, addTranscription]);

  // Auto-scroll dashboard transcription
  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [globalTranscriptions]);

  // Meeting data is now computed directly from global state, no need for effect

  // Fetch real data from backend
  useEffect(() => {
    const fetchDashboardData = async () => {
      setLoading(true);
      
      try {
        const token = localStorage.getItem('token');
        const headers: HeadersInit = token ? { 'Authorization': `Bearer ${token}` } : {};
        
        // Fetch system status
        const statusResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.status}`, { headers });
        if (statusResponse.ok) {
          const statusData = await statusResponse.json();
          
          setRealTimeData(prev => ({
            ...prev,
            activeSessions: statusData.active_sessions || 0,
            npuUsage: statusData.system_info?.npu_usage || 0,
            transcriptionRate: statusData.transcription_accuracy || 99.0
          }));
          
          // Transform service status
          if (statusData.services) {
            const serviceList: SystemService[] = [
              { name: 'PostgreSQL', status: (statusData.services.database ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'Redis Cache', status: (statusData.services.redis ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'NPU Service', status: (statusData.npu_available ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'Whisper Engine', status: (statusData.transcriber_ready ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'WebSocket Server', status: 'running' as const, cpu: 0, memory: 0, uptime: '-' }
            ];
            setServices(serviceList);
          }
        }
        
        // Fetch sessions for activity
        const sessionsResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.simpleRecording.sessions}`, { headers });
        if (sessionsResponse.ok) {
          const sessions = await sessionsResponse.json();
          
          // Create activities from recent sessions
          const activities = sessions.slice(0, 5).map((session: any, index: number) => ({
            id: session.id || index,
            type: 'recording',
            message: `Recording: ${session.title || 'Untitled Session'}`,
            time: new Date(session.created_at).toLocaleString(),
            icon: Mic
          }));
          setRecentActivities(activities);
          
          // Update metrics based on sessions
          const today = new Date().toDateString();
          const todaysSessions = sessions.filter((s: any) => 
            new Date(s.created_at).toDateString() === today
          ).length;
          
          setRealTimeData(prev => ({
            ...prev,
            totalUsers: new Set(sessions.map((s: any) => s.user_id)).size || 1,
            todaysMeetings: todaysSessions
          }));
        }
        
        // Fetch system metrics if available
        const metricsResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.system.metrics}`, { headers });
        if (metricsResponse.ok) {
          const metrics = await metricsResponse.json();
          setRealTimeData(prev => ({
            ...prev,
            storageUsed: metrics.storage_percentage || 0
          }));
        }
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };
    
    // Initial fetch
    fetchDashboardData();
    
    // Poll for updates every 5 seconds
    const interval = setInterval(fetchDashboardData, 5000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-green-500';
      case 'stopped': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const renderTrend = (trend?: 'up' | 'down' | 'stable', change?: number) => {
    if (!trend) return null;
    
    return (
      <span className={`text-xs flex items-center gap-1 ${
        trend === 'up' ? 'text-green-400' :
        trend === 'down' ? 'text-red-400' :
        'text-gray-400'
      }`}>
        {trend === 'up' && '↑'}
        {trend === 'down' && '↓'}
        {trend === 'stable' && '→'}
        {change && `${change > 0 ? '+' : ''}${change}%`}
      </span>
    );
  };

  // Fullscreen overlay
  if (fullscreenMode === 'intelligence') {
    return (
      <div className="fixed inset-0 z-50 bg-gray-950 text-white">
        <div className="h-full flex flex-col">
          <div className="flex items-center justify-between p-4 border-b border-gray-800">
            <h1 className="text-xl font-bold">Meeting Intelligence - Fullscreen</h1>
            <button
              onClick={() => setFullscreenMode(null)}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
            >
              <Minimize2 className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 p-4">
            <MeetingIntelligenceDashboard
              meetingData={{
                transcript: (globalTranscriptions || []).map(t => t.text).join(' '),
                notes: null,
                sessionId: recordingSessionId || '',
                duration: recordingTime,
                participants: Array.from(new Set((globalTranscriptions || []).map(t => t.speaker).filter(Boolean))),
                topics: []
              }}
              isRecording={isRecording}
              className="h-full"
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">
                Welcome back, {user?.username || 'User'}
              </h1>
              <p className="text-gray-400 text-sm mt-1">
                {new Date().toLocaleDateString('en-US', { 
                  weekday: 'long', 
                  year: 'numeric', 
                  month: 'long', 
                  day: 'numeric' 
                })}
              </p>
            </div>
            
            {/* View Switcher */}
            <div className="flex items-center gap-2 bg-gray-900/50 rounded-lg p-1">
              {[
                { id: 'overview', label: 'Overview', icon: Activity },
                { id: 'recording', label: 'Recording', icon: Mic },
                { id: 'transcription', label: 'Transcription', icon: Zap },
                { id: 'analytics', label: 'Analytics', icon: BarChart3 },
                { id: 'system', label: 'System', icon: Cpu }
              ].map(view => (
                <button
                  key={view.id}
                  onClick={() => setActiveView(view.id as any)}
                  className={`flex items-center gap-2 px-4 py-2 rounded transition-all ${
                    activeView === view.id
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
                >
                  <view.icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{view.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-6">
        {activeView === 'overview' && (
          <div className="space-y-6">
            {/* Metrics Grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {metrics.map((metric, index) => (
                <div key={index} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  <div className="flex items-start justify-between mb-2">
                    <metric.icon className={`w-5 h-5 ${metric.color}`} />
                    {renderTrend(metric.trend, metric.change)}
                  </div>
                  <p className="text-2xl font-bold text-white">{metric.value}</p>
                  <p className="text-xs text-gray-500 mt-1">{metric.label}</p>
                </div>
              ))}
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Meeting Intelligence with Recording Controls */}
              <div className="lg:col-span-2">
                <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  {/* Recording Header */}
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      <Brain className="w-5 h-5 text-purple-400" />
                      Meeting Intelligence
                      {isRecording && (
                        <span className="ml-2 px-2 py-1 bg-red-500/20 text-red-400 text-xs rounded-full flex items-center gap-1">
                          <Circle className="w-2 h-2 fill-current animate-pulse" />
                          Recording
                        </span>
                      )}
                    </h3>
                    
                    {/* Recording Controls */}
                    <div className="flex items-center gap-3">
                      {isRecording && (
                        <span className="text-sm font-mono text-cyan-400">
                          {formatTime(recordingTime)}
                        </span>
                      )}
                      
                      <button
                        onClick={isRecording ? stopRecording : startRecording}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                          isRecording 
                            ? 'bg-red-600 hover:bg-red-700 text-white' 
                            : 'bg-purple-600 hover:bg-purple-700 text-white'
                        }`}
                      >
                        {isRecording ? (
                          <>
                            <Square className="w-4 h-4" />
                            <span>Stop</span>
                          </>
                        ) : (
                          <>
                            <Circle className="w-4 h-4" />
                            <span>Record</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                  
                  {/* Meeting Intelligence Dashboard */}
                  <div className="h-[450px] relative">
                    {/* Hidden LiveTranscription component to handle WebSocket updates */}
                    {isRecording && recordingSessionId && (
                      <div style={{ display: 'none' }}>
                        <LiveTranscription 
                          sessionId={recordingSessionId} 
                          isRecording={isRecording} 
                        />
                      </div>
                    )}
                    
                    <MeetingIntelligenceDashboard
                      meetingData={{
                        transcript: (globalTranscriptions || []).map(t => t.text).join(' '),
                        notes: null,
                        sessionId: recordingSessionId || '',
                        duration: recordingTime,
                        participants: Array.from(new Set((globalTranscriptions || []).map(t => t.speaker).filter(Boolean))),
                        topics: []
                      }}
                      isRecording={isRecording}
                      className="h-full"
                    />
                    
                    {/* Pop-out and Full-screen Controls */}
                    <div className="absolute top-2 right-2 flex items-center gap-1">
                      <button
                        onClick={() => openPopoutWindow('intelligence', recordingSessionId || '')}
                        className="p-1.5 rounded bg-gray-800 hover:bg-gray-700 transition-colors"
                        title="Open in new window"
                      >
                        <ExternalLink className="w-3 h-3 text-gray-400" />
                      </button>
                      <button
                        onClick={() => toggleFullscreen('intelligence')}
                        className="p-1.5 rounded bg-gray-800 hover:bg-gray-700 transition-colors"
                        title="Toggle fullscreen"
                      >
                        <Maximize2 className="w-3 h-3 text-gray-400" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recent Activity */}
              <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-purple-400" />
                  Recent Activity
                </h3>
                <div className="space-y-3">
                  {recentActivities.map(activity => (
                    <div key={activity.id} className="flex items-start gap-3 p-3 bg-gray-800/50 rounded-lg">
                      <div className="w-8 h-8 rounded-full bg-purple-600/20 flex items-center justify-center flex-shrink-0">
                        <activity.icon className="w-4 h-4 text-purple-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-200">{activity.message}</p>
                        <p className="text-xs text-gray-500 mt-1">{activity.time}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Services Grid */}
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Shield className="w-5 h-5 text-blue-400" />
                System Services
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {services.map(service => (
                  <div key={service.name} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(service.status)}`} />
                      <span className="text-sm font-medium text-gray-200">{service.name}</span>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">CPU</span>
                        <span className="text-gray-400">{service.cpu}%</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Memory</span>
                        <span className="text-gray-400">{service.memory}MB</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Uptime</span>
                        <span className="text-gray-400">{service.uptime}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeView === 'recording' && (
          <UnifiedRecordingInterface />
        )}

        {activeView === 'transcription' && (
          <TranscriptionLoop />
        )}

        {activeView === 'analytics' && (
          <div className="space-y-6">
            <div className="h-[600px]">
              <MeetingIntelligenceDashboard
                meetingData={{
                  transcript: (globalTranscriptions || []).map(t => t.text).join(' '),
                  notes: null,
                  sessionId: recordingSessionId || '',
                  duration: recordingTime,
                  participants: Array.from(new Set((globalTranscriptions || []).map(t => t.speaker).filter(Boolean))),
                  topics: []
                }}
                isRecording={isRecording}
                className="h-full w-full"
              />
            </div>
            
            {/* Additional Analytics Components */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-green-400" />
                  Performance Trends
                </h3>
                <p className="text-gray-400 text-sm">
                  Historical performance metrics and trends will appear here as more meetings are recorded.
                </p>
              </div>
              
              <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-blue-400" />
                  Usage Analytics
                </h3>
                <p className="text-gray-400 text-sm">
                  Meeting duration, frequency, and participation analytics will be displayed here.
                </p>
              </div>
            </div>
          </div>
        )}

        {activeView === 'system' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold mb-4">System Control</h2>
            <p className="text-gray-400">System control panels will be integrated here...</p>
          </div>
        )}
      </div>

      {/* Footer Status Bar - with proper spacing */}
      <div className="bg-gray-900 border-t border-gray-800 px-6 py-2 mt-4">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-gray-400">System Online</span>
            </span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">NPU: AMD Phoenix 16 TOPS</span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">Version: 2.0.0</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-gray-400">Storage: {realTimeData.storageUsed}% Used</span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">Network: <Wifi className="w-3 h-3 inline text-green-400" /> Connected</span>
          </div>
        </div>
      </div>
    </div>
  );
};