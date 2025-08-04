import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { LoginWithAuth } from './components/LoginWithAuth';
import { RoleBasedNavigation } from './components/RoleBasedNavigation';
import { RoleGuard } from './components/RoleGuard';

// Dashboard imports
import { ViewerDashboard } from './components/dashboards/ViewerDashboard';
import { StandardUserDashboard } from './components/dashboards/StandardUserDashboard';
import { ManagerDashboard } from './components/dashboards/ManagerDashboard';
import { OrganizationAdminDashboard } from './components/dashboards/OrganizationAdminDashboard';
import { SuperuserDashboard } from './components/dashboards/SuperuserDashboard';

// Component imports
import { RecordingInterface } from './components/RecordingInterface';
import { SessionList } from './components/SessionList';
import { MeetingAnalytics } from './components/MeetingAnalytics';
import { STTModelManager } from './components/STTModelManager';
import { UserManagement } from './components/UserManagement';
import { Configuration } from './components/Configuration';
import { CalendarIntegration } from './components/CalendarIntegration';
import { LogViewer } from './components/LogViewer';
import { SystemMonitor } from './components/SystemMonitor';
import { FileManager } from './components/FileManager';
import { HelpContent } from './components/HelpContent';
import { AdminDashboard } from './components/AdminDashboard';
import { UserDashboard } from './components/UserDashboard';

// Icons
import { LogOut, User, Shield } from 'lucide-react';

function AppContent() {
  const { user, logout, isAuthenticated, isLoading } = useAuth();
  const [currentView, setCurrentView] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Get user role
  const userRole = user?.role || 'viewer';
  const isSuperuser = user?.is_superuser || false;

  // Role-based dashboard selection
  const getDashboardComponent = () => {
    if (isSuperuser) return <SuperuserDashboard />;
    
    switch (userRole) {
      case 'admin':
        return <OrganizationAdminDashboard />;
      case 'manager':
        return <ManagerDashboard />;
      case 'user':
        return <StandardUserDashboard />;
      case 'viewer':
      default:
        return <ViewerDashboard />;
    }
  };

  // View component mapping
  const getViewComponent = () => {
    switch (currentView) {
      case 'dashboard':
        return getDashboardComponent();
      
      case 'record':
        return (
          <RoleGuard allowedRoles={['user', 'manager', 'admin', 'superuser']}>
            <RecordingInterface token={''} apiBaseUrl={''} />
          </RoleGuard>
        );
      
      case 'my-sessions':
        return (
          <RoleGuard allowedRoles={['user', 'manager', 'admin', 'superuser']}>
            <SessionList onSelectSession={() => {}} showUserSessionsOnly={true} />
          </RoleGuard>
        );
      
      case 'team-sessions':
        return (
          <RoleGuard allowedRoles={['manager', 'admin', 'superuser']}>
            <SessionList onSelectSession={() => {}} showAllSessions={true} />
          </RoleGuard>
        );
      
      case 'sessions':
        return <SessionList onSelectSession={() => {}} />;
      
      case 'upload':
        return (
          <RoleGuard allowedRoles={['user', 'manager', 'admin', 'superuser']}>
            <FileManager />
          </RoleGuard>
        );
      
      case 'analytics':
        return (
          <RoleGuard allowedRoles={['manager', 'admin', 'superuser']}>
            <MeetingAnalytics />
          </RoleGuard>
        );
      
      case 'ai-models':
        return (
          <RoleGuard allowedRoles={['manager', 'admin', 'superuser']}>
            <STTModelManager />
          </RoleGuard>
        );
      
      case 'users':
        return (
          <RoleGuard allowedRoles={['admin', 'superuser']}>
            <UserManagement />
          </RoleGuard>
        );
      
      case 'settings':
        return (
          <RoleGuard allowedRoles={['admin', 'superuser']}>
            <Configuration />
          </RoleGuard>
        );
      
      case 'integrations':
        return (
          <RoleGuard allowedRoles={['admin', 'superuser']}>
            <CalendarIntegration />
          </RoleGuard>
        );
      
      case 'audit-logs':
        return (
          <RoleGuard allowedRoles={['admin', 'superuser']}>
            <LogViewer />
          </RoleGuard>
        );
      
      case 'system-monitor':
        return (
          <RoleGuard allowedRoles={['superuser']}>
            <SystemMonitor />
          </RoleGuard>
        );
      
      case 'hardware':
        return (
          <RoleGuard allowedRoles={['superuser']}>
            <div className="p-6">
              <h1 className="text-2xl font-bold text-gray-100 mb-6">
                Hardware Configuration
              </h1>
              {/* Hardware control components would go here */}
            </div>
          </RoleGuard>
        );
      
      case 'organizations':
        return (
          <RoleGuard allowedRoles={['superuser']}>
            <div className="p-6">
              <h1 className="text-2xl font-bold text-gray-100 mb-6">
                Organization Management
              </h1>
              {/* Organization management would go here */}
            </div>
          </RoleGuard>
        );
      
      case 'database':
        return (
          <RoleGuard allowedRoles={['superuser']}>
            <div className="p-6">
              <h1 className="text-2xl font-bold text-gray-100 mb-6">
                Database Administration
              </h1>
              {/* Database tools would go here */}
            </div>
          </RoleGuard>
        );
      
      case 'help':
        return <HelpContent />;
      
      case 'simple':
        return <UserDashboard />;
      
      default:
        return getDashboardComponent();
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white text-xl">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <LoginWithAuth />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white flex">
      {/* Sidebar Navigation */}
      <div className={`${
        sidebarCollapsed ? 'w-16' : 'w-64'
      } transition-all duration-300 bg-gray-800 border-r border-gray-700 flex flex-col`}>
        {/* Logo Section */}
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center justify-between">
            <h1 className={`font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent transition-all duration-300 ${
              sidebarCollapsed ? 'text-xl' : 'text-xl'
            }`}>
              {sidebarCollapsed ? '🦄' : '🦄 Meeting-Ops'}
            </h1>
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="p-1 text-gray-400 hover:text-gray-200 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                  d={sidebarCollapsed ? "M13 5l7 7-7 7" : "M11 19l-7-7 7-7"} 
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex-1 overflow-y-auto">
          {!sidebarCollapsed && (
            <RoleBasedNavigation 
              currentView={currentView}
              onNavigate={setCurrentView}
            />
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Top Bar */}
        <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-100">
                {user?.full_name || user?.username || 'User'}
              </h2>
              <div className="flex items-center gap-2 mt-1">
                <Shield className="w-4 h-4 text-purple-400" />
                <span className="text-sm text-gray-400 capitalize">
                  {isSuperuser ? 'Superuser' : userRole} Access
                </span>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <button
                onClick={() => setCurrentView('simple')}
                className="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded transition-colors"
              >
                Simple View
              </button>
              <button
                onClick={() => setCurrentView('settings')}
                className="p-2 text-gray-400 hover:text-gray-200 transition-colors"
              >
                <User className="w-5 h-5" />
              </button>
              <button
                onClick={logout}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto bg-gray-900">
          {getViewComponent()}
        </main>
      </div>
    </div>
  );
}

function AppRoleBased() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default AppRoleBased;