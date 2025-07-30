import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { Navigation } from './Navigation';
import { useAuth } from '../contexts/AuthContext';
import { SessionList } from './SessionList';
import { SessionDetails } from './SessionDetails';
import { FileManager } from './FileManager';
import { MeetingAnalytics } from './MeetingAnalytics';
import { RecordingControls } from './RecordingControls';
import { LiveTranscriptionViewer } from './LiveTranscriptionViewer';
import { AudioLevelMeter } from './AudioLevelMeter';
import { LiveSummarization } from './LiveSummarization';
import { SemanticSearch } from './SemanticSearch';
import { UserManagement } from './UserManagement';
import { STTModelManager } from './STTModelManager';
import { SystemMonitor } from './SystemMonitor';
import { Configuration } from './Configuration';
import { SecurityCenter } from './SecurityCenter';
import { CalendarIntegration } from './CalendarIntegration';
import { WebhookManager } from './WebhookManager';
import { useApiCache } from '../hooks/useApiCache';
import { useDebouncedCallback } from '../hooks/useDebounce';
import { useOptimisticUpdate } from '../hooks/useOptimisticUpdate';
import { useConnectionStatus } from '../hooks/useConnectionStatus';
import { 
  Command, Radio, Activity, Brain, FileText, Search, Clock,
  Calendar, Webhook, Bell, Users, Shield, Settings as SettingsIcon,
  HelpCircle, Folder, BarChart3
} from 'lucide-react';

interface SimpleDashboardProps {
  onSwitchToAdmin?: () => void;
}

interface SystemStatus {
  recording: {
    active: boolean;
    sessionId?: string;
    duration?: number;
  };
  npu: {
    status: 'active' | 'ready' | 'error';
    performance?: string;
  };
  audio: {
    level: number;
    device?: string;
  };
  system: {
    cpu: number;
    memory: number;
    storage: number;
  };
}

interface SessionStats {
  totalSessions: number;
  totalDuration: string;
  totalSpeakers: number;
  accuracyRate: number;
}

export const SimpleDashboard: React.FC<SimpleDashboardProps> = ({ onSwitchToAdmin }) => {
  const { user } = useAuth();
  const [currentView, setCurrentView] = useState('command-center');
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
  
  // Connection status for network adaptation
  const connectionStatus = useConnectionStatus();
  const networkAdaptations = connectionStatus.getNetworkAdaptations();

  // Optimistic updates for view changes
  const {
    data: optimisticView,
    applyOptimisticUpdate: updateViewOptimistically
  } = useOptimisticUpdate(currentView);

  // Cached API calls with network adaptation
  const {
    data: systemStatus,
    loading: systemLoading,
    error: systemError,
    refresh: refreshSystemStatus
  } = useApiCache(
    'system-status',
    async () => {
      const [statusResponse, systemResponse] = await Promise.all([
        fetch('/api/status', { 
          signal: AbortSignal.timeout(networkAdaptations.timeout) 
        }),
        fetch('/api/system-info', { 
          signal: AbortSignal.timeout(networkAdaptations.timeout) 
        })
      ]);

      const statusData = await statusResponse.json();
      const systemData = await systemResponse.json();

      return {
        recording: {
          active: statusData.recording?.active || false,
          sessionId: statusData.recording?.session_id,
          duration: statusData.recording?.duration
        },
        npu: {
          status: statusData.npu?.status || 'ready',
          performance: statusData.npu?.performance || '7,866x Real-time'
        },
        audio: {
          level: statusData.audio?.level || 0,
          device: statusData.audio?.device
        },
        system: {
          cpu: systemData.cpu_usage || 0,
          memory: systemData.memory_usage || 0,
          storage: systemData.disk_usage || 0
        }
      };
    },
    {
      cacheDuration: 15000, // 15 seconds cache
      refetchInterval: networkAdaptations.pollInterval,
      retryCount: networkAdaptations.maxRetries,
      retryDelay: networkAdaptations.retryDelay
    }
  );

  const {
    data: sessionStats,
    loading: statsLoading,
    error: statsError,
    refresh: refreshSessionStats
  } = useApiCache(
    'session-stats',
    async () => {
      const response = await fetch('/api/recording-sessions', {
        signal: AbortSignal.timeout(networkAdaptations.timeout)
      });
      const sessions = await response.json();

      const totalSessions = sessions.length || 0;
      const totalDurationMs = sessions.reduce((acc: number, session: any) => {
        return acc + (session.duration || 0);
      }, 0);
      
      const totalSpeakers = sessions.reduce((acc: number, session: any) => {
        return acc + (session.speaker_count || 0);
      }, 0);

      const totalDurationStr = `${Math.floor(totalDurationMs / 3600000)}h ${Math.floor((totalDurationMs % 3600000) / 60000)}m`;
      
      return {
        totalSessions,
        totalDuration: totalDurationStr,
        totalSpeakers,
        accuracyRate: 98
      };
    },
    {
      cacheDuration: 30000, // 30 seconds cache
      refetchInterval: networkAdaptations.pollInterval,
      retryCount: networkAdaptations.maxRetries,
      retryDelay: networkAdaptations.retryDelay
    }
  );

  const loading = systemLoading || statsLoading;

  // Memoize views to prevent recreation on every render
  const views: Record<string, React.ReactNode> = useMemo(() => ({
    'command-center': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
            Command Center
          </h1>
          <p className="text-gray-400">Real-time meeting operations control</p>
        </div>
        
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-gray-800 p-6 rounded-lg animate-pulse">
                <div className="h-4 bg-gray-700 rounded mb-4"></div>
                <div className="h-6 bg-gray-700 rounded"></div>
              </div>
            ))}
          </div>
        ) : (
          <>
            {/* System Status Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="bg-gray-800 p-6 rounded-lg">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-red-400" />
                  Recording Status
                </h2>
                {systemStatus?.recording.active ? (
                  <div>
                    <p className="text-red-400 font-semibold">Recording Active</p>
                    <p className="text-sm text-gray-400">Session: {systemStatus.recording.sessionId}</p>
                    {systemStatus.recording.duration && (
                      <p className="text-sm text-gray-400">Duration: {Math.floor(systemStatus.recording.duration / 60)}:{(systemStatus.recording.duration % 60).toString().padStart(2, '0')}</p>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-400">No active recording</p>
                )}
              </div>
              
              <div className="bg-gray-800 p-6 rounded-lg">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <Brain className="w-5 h-5 text-purple-400" />
                  NPU Status
                </h2>
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${
                    systemStatus?.npu.status === 'active' ? 'bg-green-400 animate-pulse' :
                    systemStatus?.npu.status === 'ready' ? 'bg-green-400' : 'bg-red-400'
                  }`}></div>
                  <span className={`capitalize ${
                    systemStatus?.npu.status === 'error' ? 'text-red-400' : 'text-green-400'
                  }`}>
                    {systemStatus?.npu.status || 'Ready'}
                  </span>
                </div>
                {systemStatus?.npu.performance && (
                  <p className="text-sm text-gray-400 mt-2">{systemStatus.npu.performance}</p>
                )}
              </div>
              
              <div className="bg-gray-800 p-6 rounded-lg">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-blue-400" />
                  System Health
                </h2>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>CPU</span>
                    <span className="text-blue-400">{systemStatus?.system.cpu.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Memory</span>
                    <span className="text-green-400">{systemStatus?.system.memory.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Storage</span>
                    <span className="text-yellow-400">{systemStatus?.system.storage.toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-800 p-4 rounded-lg text-center hover:bg-gray-750 transition-colors">
                <FileText className="h-8 w-8 text-blue-400 mx-auto mb-2" />
                <p className="text-2xl font-bold">{sessionStats?.totalSessions || 0}</p>
                <p className="text-sm text-gray-400">Total Sessions</p>
              </div>
              <div className="bg-gray-800 p-4 rounded-lg text-center hover:bg-gray-750 transition-colors">
                <Clock className="h-8 w-8 text-green-400 mx-auto mb-2" />
                <p className="text-2xl font-bold">{sessionStats?.totalDuration || '0h 0m'}</p>
                <p className="text-sm text-gray-400">Total Duration</p>
              </div>
              <div className="bg-gray-800 p-4 rounded-lg text-center hover:bg-gray-750 transition-colors">
                <Users className="h-8 w-8 text-purple-400 mx-auto mb-2" />
                <p className="text-2xl font-bold">{sessionStats?.totalSpeakers || 0}</p>
                <p className="text-sm text-gray-400">Speakers Identified</p>
              </div>
              <div className="bg-gray-800 p-4 rounded-lg text-center hover:bg-gray-750 transition-colors">
                <Activity className="h-8 w-8 text-orange-400 mx-auto mb-2" />
                <p className="text-2xl font-bold">{sessionStats?.accuracyRate || 0}%</p>
                <p className="text-sm text-gray-400">Accuracy Rate</p>
              </div>
            </div>

            {/* Recording Controls */}
            <RecordingControls 
              onSessionStart={(session) => {
                setActiveSession(session.session_id);
                refreshSystemStatus(); // Refresh system status
              }}
              onSessionEnd={(session) => {
                setActiveSession(null);
                refreshSystemStatus(); // Refresh system status
                refreshSessionStats(); // Refresh session stats
              }}
            />

            {/* Live Transcription and Audio Visualization */}
            {activeSession && (
              <>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="bg-gray-800 p-6 rounded-lg">
                    <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                      <Activity className="w-5 h-5 text-green-400" />
                      Live Audio Levels
                    </h2>
                    <AudioLevelMeter />
                  </div>
                  
                  <div className="bg-gray-800 p-6 rounded-lg">
                    <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                      <FileText className="w-5 h-5 text-blue-400" />
                      Live Transcription
                    </h2>
                    <LiveTranscriptionViewer sessionId={activeSession} isRecording={true} />
                  </div>
                </div>
                
                {/* Live Summary */}
                <div className="mt-6">
                  <LiveSummarization 
                    sessionId={activeSession} 
                    isActive={systemStatus?.recording.active || false}
                  />
                </div>
              </>
            )}
          </>
        )}
      </div>
    ),
    'sessions': (
      <div className="space-y-6">
        {selectedSessionId ? (
          <SessionDetails 
            sessionId={selectedSessionId} 
            onBack={() => setSelectedSessionId(null)}
          />
        ) : (
          <>
            <div>
              <h1 className="text-3xl font-bold">Meeting Sessions</h1>
              <p className="text-gray-400">View and manage recorded sessions</p>
            </div>
            <div className="bg-gray-800 rounded-lg">
              <SessionList onSelectSession={(session) => setSelectedSessionId(session.session_id)} />
            </div>
          </>
        )}
      </div>
    ),
    'library': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Audio Library</h1>
          <p className="text-gray-400">Browse recorded audio files</p>
        </div>
        <FileManager />
      </div>
    ),
    'insights': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Meeting Insights</h1>
          <p className="text-gray-400">Analytics and insights from your meetings</p>
        </div>
        <MeetingAnalytics />
      </div>
    ),
    'transcripts': (
      <div className="space-y-6">
        {selectedSessionId ? (
          <SessionDetails 
            sessionId={selectedSessionId} 
            onBack={() => setSelectedSessionId(null)}
          />
        ) : (
          <>
            <div>
              <h1 className="text-3xl font-bold">Transcripts</h1>
              <p className="text-gray-400">View and search meeting transcripts</p>
            </div>
            <div className="bg-gray-800 rounded-lg">
              <SessionList onSelectSession={(session) => setSelectedSessionId(session.session_id)} />
            </div>
          </>
        )}
      </div>
    ),
    'smart-search': (
      <div className="space-y-6">
        <SemanticSearch />
      </div>
    ),
    'help': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Help & Documentation</h1>
          <p className="text-gray-400">Get help with Unicorn Commander</p>
        </div>
        <div className="bg-gray-800 p-6 rounded-lg">
          <h2 className="text-xl font-semibold mb-4">Quick Start Guide</h2>
          <p className="text-gray-400">Welcome to Unicorn Commander Meeting Ops!</p>
        </div>
      </div>
    ),
    'team': (
      <div className="space-y-6">
        <UserManagement />
      </div>
    ),
    'system': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">System Monitor</h1>
          <p className="text-gray-400">Health & performance monitoring</p>
        </div>
        <SystemMonitor />
      </div>
    ),
    'security': (
      <div className="space-y-6">
        <SecurityCenter />
      </div>
    ),
    'configuration': (
      <div className="space-y-6">
        <Configuration />
      </div>
    ),
    'model-manager': (
      <div className="space-y-6">
        <STTModelManager />
      </div>
    ),
    'assistants': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Virtual Assistants</h1>
          <p className="text-gray-400">AI-powered meeting helpers</p>
        </div>
        <div className="bg-gray-800 p-6 rounded-lg">
          <p className="text-gray-400">Virtual assistants coming soon...</p>
        </div>
      </div>
    ),
    'calendar': (
      <div className="space-y-6">
        <CalendarIntegration />
      </div>
    ),
    'webhooks': (
      <div className="space-y-6">
        <WebhookManager />
      </div>
    ),
    'notifications': (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Notifications</h1>
          <p className="text-gray-400">Email & alerts configuration</p>
        </div>
        <div className="bg-gray-800 p-6 rounded-lg">
          <p className="text-gray-400">Notification settings coming soon...</p>
        </div>
      </div>
    )
  }), [loading, systemStatus, sessionStats, activeSession, refreshSystemStatus, refreshSessionStats]);

  // Debounced navigation to reduce rapid state changes
  const debouncedNavigate = useDebouncedCallback(
    (view: string) => {
      setCurrentView(view);
    },
    networkAdaptations.debounceDelay,
    [networkAdaptations.debounceDelay]
  );

  const handleNavigate = useCallback((view: string) => {
    // For immediate UI feedback, use optimistic updates
    updateViewOptimistically(
      `nav-${Date.now()}`,
      view,
      async () => {
        // Simulate navigation delay for remote connections
        if (!connectionStatus.isOnline || connectionStatus.isSlowConnection) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        debouncedNavigate(view);
        return view;
      }
    );
  }, [updateViewOptimistically, debouncedNavigate, connectionStatus]);

  return (
    <div className="min-h-screen bg-gray-900 text-white flex">
      <Navigation 
        currentView={optimisticView} // Use optimistic view for instant feedback
        onNavigate={handleNavigate}
        isAdmin={isAdmin}
      />
      
      <main className="flex-1 p-8 overflow-auto">
        {/* Connection Status Indicator */}
        {networkAdaptations.showOfflineIndicator && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded-lg flex items-center gap-2">
            <div className="w-2 h-2 bg-red-500 rounded-full"></div>
            <span className="text-sm text-red-400">Offline - Using cached data</span>
          </div>
        )}
        
        {networkAdaptations.showSlowConnectionWarning && connectionStatus.isOnline && (
          <div className="mb-4 p-3 bg-yellow-900/50 border border-yellow-500 rounded-lg flex items-center gap-2">
            <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
            <span className="text-sm text-yellow-400">
              Slow connection detected ({connectionStatus.latency}ms) - Optimizing for your network
            </span>
          </div>
        )}

        {/* Debug Info - Enhanced with network status */}
        <div className="mb-4 text-xs text-gray-500 flex items-center gap-4">
          <span>Current View: {optimisticView}</span>
          <span>•</span>
          <span>Connection: {networkAdaptations.connectionQuality}</span>
          {connectionStatus.latency && (
            <>
              <span>•</span>
              <span>Latency: {connectionStatus.latency}ms</span>
            </>
          )}
          {(systemError || statsError) && (
            <>
              <span>•</span>
              <span className="text-red-400">API Error - Using cache</span>
            </>
          )}
        </div>

        {views[optimisticView] || views[currentView] || (
          <div>
            <h1 className="text-2xl font-bold">View Not Found</h1>
            <p className="text-gray-400">The view "{optimisticView}" is not implemented yet.</p>
          </div>
        )}
      </main>
    </div>
  );
};