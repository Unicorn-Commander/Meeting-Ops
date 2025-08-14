import React, { useState, useEffect } from 'react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { SidebarNavigation } from './navigation/SidebarNavigation';
import { TopBar } from './navigation/TopBar';

// Import existing components
import { SessionList } from './SessionList';
import { SessionDetails } from './SessionDetails';
import { FileManager } from './FileManager';
import { SystemMonitor } from './SystemMonitor';
import { MeetingAnalytics } from './MeetingAnalytics';
import { CalendarIntegration } from './CalendarIntegration';
import { Configuration } from './ConfigurationSimple';
import { SecurityCenter } from './SecurityCenter';
import { UnifiedSearchInterface } from './UnifiedSearchInterface';
import { WebhookManager } from './WebhookManager';
import { ExportManager } from './ExportManager';
import { STTModelManager } from './STTModelManager';
import { UserManagement } from './UserManagement';
import { RecordingControls } from './RecordingControls';
import { LiveTranscriptionViewer } from './LiveTranscriptionViewer';
import { AudioLevelMeter } from './AudioLevelMeter';
import { EmailNotifications } from './EmailNotifications';
import { GitHubUpdater } from './GitHubUpdater';

// Quick Access Toolbar component
const QuickAccessToolbar: React.FC<{
  isRecording: boolean;
  onNewRecording: () => void;
  onQuickExport: () => void;
  onShowHelp: () => void;
}> = ({ isRecording, onNewRecording, onQuickExport, onShowHelp }) => {
  return (
    <div className="fixed bottom-6 right-6 flex flex-col space-y-2 z-40">
      {!isRecording && (
        <button
          onClick={onNewRecording}
          className="p-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-full shadow-lg transition-all duration-200 group"
          title="New Recording"
        >
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </button>
      )}
      <button
        onClick={onQuickExport}
        className="p-3 bg-gray-800 hover:bg-gray-700 rounded-full shadow-lg transition-all duration-200"
        title="Quick Export"
      >
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </button>
      <button
        onClick={onShowHelp}
        className="p-3 bg-gray-800 hover:bg-gray-700 rounded-full shadow-lg transition-all duration-200"
        title="Help"
      >
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </button>
    </div>
  );
};

export const ImprovedDashboard: React.FC = () => {
  const { user } = useAuthentikAuth();
  const [currentView, setCurrentView] = useState('dashboard');
  const [currentSubView, setCurrentSubView] = useState<string | undefined>();
  const [isRecording, setIsRecording] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

  // Debug navigation
  useEffect(() => {
    console.log('Current view changed to:', currentView, currentSubView);
  }, [currentView, currentSubView]);

  const handleNavigate = (view: string, subView?: string) => {
    console.log('Navigating to:', view, subView);
    setCurrentView(view);
    setCurrentSubView(subView);
  };

  const handleStartRecording = async () => {
    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || '';
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: `Meeting - ${new Date().toLocaleString()}`,
          description: 'Recording started from dashboard'
        })
      });

      if (response.ok) {
        const session = await response.json();
        setActiveSessionId(session.session_id);
        setIsRecording(true);
        handleNavigate('meetings', 'active-session');
      }
    } catch (error) {
      console.error('Failed to start recording:', error);
    }
  };

  const handleStopRecording = async () => {
    if (!activeSessionId) return;

    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || '';
      const token = localStorage.getItem('access_token');
      
      await fetch(`${API_BASE_URL}/api/recording-sessions/${activeSessionId}/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      setIsRecording(false);
      setActiveSessionId(null);
    } catch (error) {
      console.error('Failed to stop recording:', error);
    }
  };

  const renderDashboardOverview = () => (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-white">Dashboard Overview</h1>
      
      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-gray-400 text-sm mb-2">Total Meetings</h3>
          <p className="text-3xl font-bold text-white">142</p>
          <p className="text-sm text-green-400 mt-2">+12% this week</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-gray-400 text-sm mb-2">Hours Recorded</h3>
          <p className="text-3xl font-bold text-white">238.5</p>
          <p className="text-sm text-green-400 mt-2">+18% this week</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-gray-400 text-sm mb-2">NPU Usage</h3>
          <p className="text-3xl font-bold text-white">87%</p>
          <p className="text-sm text-blue-400 mt-2">Optimal performance</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-gray-400 text-sm mb-2">Storage Used</h3>
          <p className="text-3xl font-bold text-white">124GB</p>
          <p className="text-sm text-yellow-400 mt-2">56% capacity</p>
        </div>
      </div>

      {/* Live Monitor */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-semibold text-white mb-4">Live Monitor</h2>
          <AudioLevelMeter />
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-semibold text-white mb-4">System Status</h2>
          <SystemMonitor />
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold text-white mb-4">Recent Activity</h2>
        <SessionList onSelectSession={(session) => {
          setActiveSessionId(session.session_id);
          handleNavigate('meetings', 'sessions');
        }} />
      </div>
    </div>
  );

  const renderContent = () => {
    console.log('renderContent called with:', currentView, currentSubView);
    
    try {
      // Main view routing
      switch (currentView) {
        case 'dashboard':
          return renderDashboardOverview();

        case 'meetings':
          return (
            <div className="space-y-6">
              <h1 className="text-3xl font-bold text-white">Meetings</h1>
              {(() => {
                switch (currentSubView) {
                  case 'active-session':
                    return isRecording ? (
                      <div className="space-y-6">
                        <RecordingControls onSessionEnd={handleStopRecording} />
                        <LiveTranscriptionViewer sessionId={activeSessionId!} />
                      </div>
                    ) : (
                      <div className="flex items-center justify-center p-12">
                        <div className="text-center">
                          <p className="text-gray-400 mb-4">No active recording session</p>
                          <button
                            onClick={handleStartRecording}
                            className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 px-6 py-3 rounded-lg font-medium transition-all duration-200"
                          >
                            Start New Recording
                          </button>
                        </div>
                      </div>
                    );
                  case 'sessions':
                    return <SessionList onSelectSession={(session) => setActiveSessionId(session.session_id)} />;
                  case 'calendar':
                    return <CalendarIntegration />;
                  case 'analytics':
                    return <MeetingAnalytics />;
                  default:
                    return <SessionList onSelectSession={(session) => setActiveSessionId(session.session_id)} />;
                }
              })()}
            </div>
          );

      case 'intelligence':
        return (
          <div className="space-y-6">
            <h1 className="text-3xl font-bold text-white">Intelligence</h1>
            {currentSubView === 'search' ? <UnifiedSearchInterface /> : 
             currentSubView === 'insights' ? <MeetingAnalytics /> :
             <SessionList onSelectSession={(session) => setActiveSessionId(session.session_id)} />}
          </div>
        );

      case 'library':
        return (
          <div className="space-y-6">
            <h1 className="text-3xl font-bold text-white">Library</h1>
            {currentSubView === 'exports' ? <ExportManager /> :
             currentSubView === 'templates' ? <div className="text-white">Email Templates (Coming Soon)</div> :
             <FileManager />}
          </div>
        );

      case 'integrations':
        return (
          <div className="space-y-6">
            <h1 className="text-3xl font-bold text-white">Integrations</h1>
            {currentSubView === 'webhooks' ? <WebhookManager /> :
             currentSubView === 'email-settings' ? <EmailNotifications /> :
             currentSubView === 'api-access' ? <div className="text-white p-4">API Access Management (Coming Soon)</div> :
             <CalendarIntegration />}
          </div>
        );

      case 'settings':
        return (
          <div className="space-y-6">
            <h1 className="text-3xl font-bold text-white">Settings</h1>
            <Configuration />
          </div>
        );

      case 'admin':
        if (!isAdmin) {
          return (
            <div className="flex items-center justify-center h-full">
              <div className="text-white text-xl">Access Denied</div>
            </div>
          );
        }
        return (
          <div className="space-y-6">
            <h1 className="text-3xl font-bold text-white">Admin Panel</h1>
            {currentSubView === 'users' ? <UserManagement /> :
             currentSubView === 'system' ? <SystemMonitor /> :
             currentSubView === 'security' ? <SecurityCenter /> :
             currentSubView === 'storage' ? <FileManager /> :
             currentSubView === 'npu-config' ? <STTModelManager /> :
             <UserManagement />}
          </div>
        );

      default:
        return renderDashboardOverview();
      }
    } catch (error) {
      console.error('Error in renderContent:', error);
      return (
        <div className="text-white p-8">
          <h2 className="text-xl mb-4">Error rendering content</h2>
          <p className="text-gray-400">View: {currentView}, SubView: {currentSubView}</p>
          <p className="text-red-400 mt-2">{String(error)}</p>
        </div>
      );
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      {/* Top Bar */}
      <TopBar
        isRecording={isRecording}
        activeRoom="Conference Room A"
        onStartRecording={handleStartRecording}
        onStopRecording={handleStopRecording}
        onNavigate={handleNavigate}
      />

      {/* Main Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar Navigation */}
        <SidebarNavigation
          currentView={currentView}
          currentSubView={currentSubView}
          onNavigate={handleNavigate}
          isAdmin={isAdmin}
          isRecording={isRecording}
        />

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto bg-gray-900 p-6" key={`${currentView}-${currentSubView}`}>
          <div className="mb-4 text-xs text-gray-500">
            Debug: currentView={currentView}, currentSubView={currentSubView || 'none'}
          </div>
          {renderContent()}
        </main>
      </div>

      {/* Quick Access Toolbar */}
      <QuickAccessToolbar
        isRecording={isRecording}
        onNewRecording={handleStartRecording}
        onQuickExport={() => handleNavigate('library', 'exports')}
        onShowHelp={() => console.log('Show help')}
      />
      <GitHubUpdater />
    </div>
  );
};