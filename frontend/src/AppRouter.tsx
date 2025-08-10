import React from 'react';
import { Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';

// Layouts
import { MainLayout } from './layouts/MainLayout';

// Auth
import { Login } from './components/Login';

// Dashboards
import { UltimateDashboard } from './components/dashboards/UltimateDashboard';
import { SuperuserDashboard } from './components/dashboards/SuperuserDashboard';
import { AdminDashboard } from './components/dashboards/AdminDashboard';
import { ManagerDashboard } from './components/dashboards/ManagerDashboard';
import { StandardUserDashboard } from './components/dashboards/StandardUserDashboard';
import { ViewerDashboard } from './components/dashboards/ViewerDashboard';

// Hubs
import { UnifiedRecordingInterface } from './components/UnifiedRecordingInterface';
import { TimeShiftRecording } from './components/TimeShiftRecording';

// Components
import { SessionList } from './components/SessionList';
import { SessionDetails } from './pages/SessionDetails';
import { LiveTranscription } from './components/LiveTranscription';
import { TranscriptionSettings } from './components/TranscriptionSettings';
import { FileManager } from './components/FileManager';
import { MeetingAnalytics } from './components/MeetingAnalytics';
import { MeetingInsights } from './components/MeetingInsights';
import { SpeakerAnalytics } from './components/SpeakerAnalytics';
import { KeywordTrends } from './components/KeywordTrends';
import { ExportCenter } from './components/ExportCenter';
import { FlaggedSegments } from './components/FlaggedSegments';
import { UserManagement } from './components/UserManagement';
import { SystemSettings } from './components/SystemSettings';
import { CalendarIntegration } from './components/CalendarIntegration';
import { WebhookManager } from './components/WebhookManager';
import { APIKeysManager } from './components/APIKeysManager';
import { EmailTemplates } from './components/EmailTemplates';
import { RealTimeCollaboration } from './components/RealTimeCollaboration';
import { CustomVocabulary } from './components/CustomVocabulary';
import { MeetingTemplates } from './components/MeetingTemplates';
import { AIChatInterface } from './components/AIChatInterface';
import { WorkingSystemSettings } from './components/WorkingSystemSettings';
import { SystemMonitor } from './components/SystemMonitor';
import { NpuStatusIndicator } from './components/NpuStatusIndicator';
import { NetworkStatus } from './components/NetworkStatus';
import { LogViewer } from './components/LogViewer';

// Protected Route Component
const ProtectedRoute: React.FC<{ 
  children: React.ReactNode; 
  requiredRoles?: string[] 
}> = ({ children, requiredRoles }) => {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRoles && user && !requiredRoles.includes(user.role || 'user')) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

// Dashboard Selector based on user role
const DashboardSelector: React.FC = () => {
  const { user } = useAuth();
  
  // Use the Ultimate Dashboard for all users now
  // It adapts based on role internally
  return <UltimateDashboard />;
  
  // Alternative: role-specific dashboards
  /*
  switch (user?.role) {
    case 'superuser':
      return <SuperuserDashboard />;
    case 'admin':
      return <AdminDashboard />;
    case 'manager':
      return <ManagerDashboard />;
    case 'viewer':
      return <ViewerDashboard />;
    default:
      return <StandardUserDashboard />;
  }
  */
};

export const AppRouter: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      {/* Auth Routes */}
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login />
      } />

      {/* Protected Routes */}
      <Route element={
        <ProtectedRoute>
          <MainLayout />
        </ProtectedRoute>
      }>
        {/* Dashboard */}
        <Route path="/dashboard" element={<DashboardSelector />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        {/* Recording Hub */}
        <Route path="/recording" element={<Outlet />}>
          <Route path="live" element={<UnifiedRecordingInterface />} />
          <Route path="timeshift" element={<TimeShiftRecording />} />
          <Route path="main" element={<UnifiedRecordingInterface />} />
          <Route path="sessions" element={<SessionList />} />
          <Route path="sessions/:sessionId" element={<SessionDetails />} />
        </Route>

        {/* Intelligence Center */}
        <Route path="/intelligence" element={<Outlet />}>
          <Route path="ai-chat" element={<AIChatInterface />} />
          <Route path="analytics" element={<MeetingAnalytics />} />
          <Route path="insights" element={
            <div className="p-6">
              <h2 className="text-2xl font-bold text-white mb-4">AI Meeting Insights</h2>
              <MeetingInsights className="mt-4" />
            </div>
          } />
          <Route path="speakers" element={
            <div className="p-6 text-white">
              <SpeakerAnalytics />
            </div>
          } />
          <Route path="keywords" element={
            <div className="p-6 text-white">
              <KeywordTrends />
            </div>
          } />
          <Route path="summaries" element={
            <div className="p-6 text-white">
              <h2 className="text-2xl font-bold mb-4">Meeting Summaries</h2>
              <p className="text-gray-400">AI-generated meeting summaries with action items</p>
            </div>
          } />
        </Route>

        {/* Content Manager */}
        <Route path="/content" element={<Outlet />}>
          <Route path="files" element={<FileManager />} />
          <Route path="flagged" element={
            <div className="p-6 text-white">
              <FlaggedSegments />
            </div>
          } />
          <Route path="export" element={
            <div className="p-6 text-white">
              <ExportCenter />
            </div>
          } />
          <Route path="storage" element={
            <div className="p-6 text-white">
              <h2 className="text-2xl font-bold mb-4">Storage Metrics</h2>
              <SystemMonitor />
            </div>
          } />
        </Route>

        {/* Integrations */}
        <Route path="/integrations" element={<Outlet />}>
          <Route path="calendar" element={
            <div className="p-6 text-white">
              <CalendarIntegration />
            </div>
          } />
          <Route path="email" element={
            <div className="p-6 text-white">
              <EmailTemplates />
            </div>
          } />
          <Route path="webhooks" element={
            <div className="p-6 text-white">
              <WebhookManager />
            </div>
          } />
          <Route path="api-keys" element={
            <div className="p-6 text-white">
              <APIKeysManager />
            </div>
          } />
        </Route>

        {/* System Control */}
        <Route path="/system" element={<Outlet />}>
          <Route path="npu" element={
            <div className="p-6">
              <h2 className="text-2xl font-bold text-white mb-4">NPU Monitor</h2>
              <NpuStatusIndicator />
            </div>
          } />
          <Route path="services" element={
            <div className="p-6">
              <h2 className="text-2xl font-bold text-white mb-4">Service Status</h2>
              <SystemMonitor />
            </div>
          } />
          <Route path="audio" element={
            <div className="p-6 text-white">
              <h2 className="text-2xl font-bold mb-4">Audio Devices</h2>
              <TranscriptionSettings userRole="superuser" />
            </div>
          } />
          <Route path="network" element={
            <div className="p-6">
              <h2 className="text-2xl font-bold text-white mb-4">Network Configuration</h2>
              <NetworkStatus />
            </div>
          } />
        </Route>

        {/* Organization */}
        <Route path="/org" element={<Outlet />}>
          <Route path="users" element={
            <ProtectedRoute requiredRoles={['admin', 'superuser', 'manager']}>
              <div className="p-6 text-white">
                <UserManagement />
              </div>
            </ProtectedRoute>
          } />
          <Route path="teams" element={
            <ProtectedRoute requiredRoles={['admin', 'superuser', 'manager']}>
              <div className="p-6 text-white">
                <h2 className="text-2xl font-bold mb-4">Team Settings</h2>
                <p className="text-gray-400">Configure team settings...</p>
              </div>
            </ProtectedRoute>
          } />
          <Route path="settings" element={
            <ProtectedRoute requiredRoles={['admin', 'superuser']}>
              <div className="p-6 text-white">
                <WorkingSystemSettings />
              </div>
            </ProtectedRoute>
          } />
          <Route path="access" element={
            <ProtectedRoute requiredRoles={['admin', 'superuser']}>
              <div className="p-6 text-white">
                <h2 className="text-2xl font-bold mb-4">Access Control</h2>
                <p className="text-gray-400">Manage role-based access...</p>
              </div>
            </ProtectedRoute>
          } />
          <Route path="audit" element={
            <ProtectedRoute requiredRoles={['admin', 'superuser']}>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-white mb-4">Audit Logs</h2>
                <LogViewer />
              </div>
            </ProtectedRoute>
          } />
        </Route>

        {/* Administration */}
        <Route path="/admin" element={<Outlet />}>
          <Route path="backup" element={
            <ProtectedRoute requiredRoles={['superuser']}>
              <div className="p-6 text-white">
                <h2 className="text-2xl font-bold mb-4">Backup & Restore</h2>
                <p className="text-gray-400">Database backup management...</p>
              </div>
            </ProtectedRoute>
          } />
          <Route path="ssl" element={
            <ProtectedRoute requiredRoles={['superuser']}>
              <div className="p-6 text-white">
                <h2 className="text-2xl font-bold mb-4">SSL Certificates</h2>
                <p className="text-gray-400">Manage SSL certificates...</p>
              </div>
            </ProtectedRoute>
          } />
          <Route path="logs" element={
            <ProtectedRoute requiredRoles={['superuser']}>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-white mb-4">System Logs</h2>
                <LogViewer />
              </div>
            </ProtectedRoute>
          } />
          <Route path="maintenance" element={
            <ProtectedRoute requiredRoles={['superuser']}>
              <div className="p-6 text-white">
                <h2 className="text-2xl font-bold mb-4">Maintenance Mode</h2>
                <p className="text-gray-400">System maintenance controls...</p>
              </div>
            </ProtectedRoute>
          } />
        </Route>

        {/* Advanced Features */}
        <Route path="/advanced" element={<Outlet />}>
          <Route path="collaboration" element={
            <div className="p-6 text-white">
              <RealTimeCollaboration />
            </div>
          } />
          <Route path="vocabulary" element={
            <div className="p-6 text-white">
              <CustomVocabulary />
            </div>
          } />
          <Route path="templates" element={
            <div className="p-6 text-white">
              <MeetingTemplates />
            </div>
          } />
          <Route path="mobile" element={
            <div className="p-6 text-white">
              <h2 className="text-2xl font-bold mb-4">Mobile Interface</h2>
              <p className="text-gray-400">Responsive mobile and tablet layouts</p>
            </div>
          } />
        </Route>
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};