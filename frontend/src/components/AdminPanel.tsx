import React, { useState } from 'react';
import { 
  Settings, 
  Network, 
  Users, 
  Brain, 
  HardDrive, 
  Shield, 
  Monitor,
  FileText,
  Upload,
  Lock
} from 'lucide-react';
import { useAuthentikAuth } from '../contexts/AuthentikAuthContext';
import { NetworkManagement } from './admin/NetworkManagement';
import { SystemDashboard } from './admin/SystemDashboard';
import { AIConfiguration } from './admin/AIConfiguration';
import { UserManagement } from '../components/UserManagement';
import { LogViewer } from './LogViewer';
import { BackupManager } from './BackupManager';
import { SSLManager } from './SSLManager';

interface AdminPanelProps {
  onClose?: () => void;
}

export const AdminPanel: React.FC<AdminPanelProps> = ({ onClose }) => {
  const { user } = useAuthentikAuth();
  const [currentSection, setCurrentSection] = useState('dashboard');
  // const [systemStatus, setSystemStatus] = useState<any>(null);

  // Check if user has admin access
  const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-8 flex items-center justify-center">
        <div className="text-center">
          <Shield className="mx-auto h-16 w-16 text-red-400 mb-4" />
          <h2 className="text-2xl font-bold mb-2">Access Denied</h2>
          <p className="text-gray-400">You need administrator privileges to access this panel.</p>
        </div>
      </div>
    );
  }

  const adminSections = [
    {
      id: 'dashboard',
      name: 'System Dashboard',
      icon: Monitor,
      description: 'System overview and health monitoring'
    },
    {
      id: 'network',
      name: 'Network & System',
      icon: Network,
      description: 'Network interfaces, IP configuration, firewall'
    },
    {
      id: 'ai-config',
      name: 'AI Configuration',
      icon: Brain,
      description: 'Models, NPU settings, transcription, diarization'
    },
    {
      id: 'users',
      name: 'User Management',
      icon: Users,
      description: 'User accounts, roles, permissions'
    },
    {
      id: 'storage',
      name: 'Storage & Files',
      icon: HardDrive,
      description: 'File management, storage, backup, archive'
    },
    {
      id: 'backup',
      name: 'Backup & Restore',
      icon: Upload,
      description: 'Create, list, and restore system backups'
    },
    {
      id: 'security',
      name: 'Security & Logging',
      icon: Shield,
      description: 'Security settings, audit logs, monitoring'
    },
    {
      id: 'ssl',
      name: 'SSL/HTTPS',
      icon: Lock,
      description: 'Manage SSL certificates and HTTPS configuration'
    },
    {
      id: 'logs',
      name: 'Log Management',
      icon: FileText,
      description: 'View and manage system logs'
    },
    {
      id: 'advanced',
      name: 'Advanced Settings',
      icon: Settings,
      description: 'Advanced configuration and integrations'
    }
  ];

  const renderCurrentSection = () => {
    switch (currentSection) {
      case 'dashboard':
        return <SystemDashboard />;
      case 'network':
        return <NetworkManagement />;
      case 'ai-config':
        return <AIConfiguration />;
      case 'users':
        return <UserManagement />;
      case 'storage':
        return <div className="p-6"><h2 className="text-2xl font-bold">Storage Management</h2><p className="text-gray-400 mt-2">Coming soon...</p></div>;
      case 'backup':
        return <BackupManager />;
      case 'security':
        return <div className="p-6"><h2 className="text-2xl font-bold">Security & Logging</h2><p className="text-gray-400 mt-2">Coming soon...</p></div>;
      case 'ssl':
        return <SSLManager />;
      case 'logs':
        return <LogViewer />;
      case 'advanced':
        return <div className="p-6"><h2 className="text-2xl font-bold">Advanced Settings</h2><p className="text-gray-400 mt-2">Coming soon...</p></div>;
      default:
        return <SystemDashboard />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex">
      {/* Admin Sidebar */}
      <aside className="w-80 bg-gray-800 border-r border-gray-700 flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold">Admin Panel</h1>
              <p className="text-sm text-gray-400">System Administration</p>
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          {adminSections.map((section) => {
            const IconComponent = section.icon;
            return (
              <button
                key={section.id}
                onClick={() => setCurrentSection(section.id)}
                className={`w-full text-left p-4 rounded-lg transition-all ${
                  currentSection === section.id
                    ? 'bg-blue-600 text-white'
                    : 'hover:bg-gray-700 text-gray-300'
                }`}
              >
                <div className="flex items-start gap-3">
                  <IconComponent className="h-5 w-5 mt-0.5 flex-shrink-0" />
                  <div>
                    <div className="font-medium">{section.name}</div>
                    <div className="text-xs text-gray-400 mt-1">
                      {section.description}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </nav>

        {/* Admin Info */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-3 p-3 bg-gray-700/50 rounded-lg">
            <div className="w-8 h-8 bg-gradient-to-r from-red-500 to-orange-500 rounded-full flex items-center justify-center">
              <Shield className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium">{user?.username}</p>
              <p className="text-xs text-gray-400">Administrator</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        {renderCurrentSection()}
      </main>
    </div>
  );
};