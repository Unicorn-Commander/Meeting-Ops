import React, { useState, useEffect } from 'react';
import { UserManagement } from '../UserManagement';
import { BackupManager } from '../BackupManager';
import { EmailNotifications } from '../EmailNotifications';
import { WebhookManager } from '../WebhookManager';
import { 
  Users, 
  Settings, 
  Database, 
  Mail,
  Webhook,
  Shield,
  Activity,
  HardDrive,
  TrendingUp,
  AlertCircle,
  CheckCircle,
  Clock
} from 'lucide-react';

interface OrgStats {
  totalUsers: number;
  activeUsers: number;
  storageUsed: number;
  storageTotal: number;
  sessionsToday: number;
  weeklyGrowth: number;
  systemHealth: 'healthy' | 'warning' | 'critical';
  pendingTasks: number;
}

export const OrganizationAdminDashboard: React.FC = () => {
  const [orgStats, setOrgStats] = useState<OrgStats>({
    totalUsers: 0,
    activeUsers: 0,
    storageUsed: 0,
    storageTotal: 100,
    sessionsToday: 0,
    weeklyGrowth: 0,
    systemHealth: 'healthy',
    pendingTasks: 0
  });
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'settings' | 'integrations' | 'maintenance'>('overview');
  const [recentActivity, setRecentActivity] = useState<any[]>([]);

  useEffect(() => {
    // Fetch organization statistics
    const fetchOrgStats = async () => {
      try {
        // This would fetch from multiple endpoints
        setOrgStats({
          totalUsers: 25,
          activeUsers: 18,
          storageUsed: 45.2,
          storageTotal: 100,
          sessionsToday: 12,
          weeklyGrowth: 15.3,
          systemHealth: 'healthy',
          pendingTasks: 3
        });

        setRecentActivity([
          { type: 'user_login', user: 'john.doe', time: '5 minutes ago' },
          { type: 'session_created', user: 'jane.smith', time: '15 minutes ago' },
          { type: 'backup_completed', time: '1 hour ago' },
          { type: 'user_added', user: 'new.user', time: '2 hours ago' }
        ]);
      } catch (error) {
        console.error('Failed to fetch org stats:', error);
      }
    };

    fetchOrgStats();
  }, []);

  const getHealthColor = (health: string) => {
    switch (health) {
      case 'healthy': return 'text-green-400';
      case 'warning': return 'text-yellow-400';
      case 'critical': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getHealthIcon = (health: string) => {
    switch (health) {
      case 'healthy': return <CheckCircle className="w-6 h-6" />;
      case 'warning': return <AlertCircle className="w-6 h-6" />;
      case 'critical': return <AlertCircle className="w-6 h-6" />;
      default: return <Activity className="w-6 h-6" />;
    }
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 mb-2">
          Organization Administration
        </h1>
        <p className="text-gray-400">
          Manage users, settings, and organization resources
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-4 mb-6 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('overview')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'overview'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Overview
          {activeTab === 'overview' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('users')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'users'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Users
          {activeTab === 'users' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('settings')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'settings'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Settings
          {activeTab === 'settings' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('integrations')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'integrations'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Integrations
          {activeTab === 'integrations' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('maintenance')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'maintenance'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Maintenance
          {orgStats.pendingTasks > 0 && (
            <span className="ml-2 px-2 py-0.5 bg-red-600 text-white text-xs rounded-full">
              {orgStats.pendingTasks}
            </span>
          )}
          {activeTab === 'maintenance' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Users className="w-8 h-8 text-purple-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {orgStats.activeUsers}/{orgStats.totalUsers}
              </h3>
              <p className="text-sm text-gray-400 mt-1">Active Users</p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <HardDrive className="w-8 h-8 text-blue-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {orgStats.storageUsed}GB
              </h3>
              <p className="text-sm text-gray-400 mt-1">Storage Used</p>
              <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-blue-400 transition-all duration-300"
                  style={{ width: `${(orgStats.storageUsed / orgStats.storageTotal) * 100}%` }}
                />
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <TrendingUp className="w-8 h-8 text-green-400" />
                <span className="text-sm font-medium text-green-400">
                  +{orgStats.weeklyGrowth}%
                </span>
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {orgStats.sessionsToday}
              </h3>
              <p className="text-sm text-gray-400 mt-1">Sessions Today</p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <div className={getHealthColor(orgStats.systemHealth)}>
                  {getHealthIcon(orgStats.systemHealth)}
                </div>
              </div>
              <h3 className="text-xl font-bold text-gray-100 capitalize">
                {orgStats.systemHealth}
              </h3>
              <p className="text-sm text-gray-400 mt-1">System Health</p>
            </div>
          </div>

          {/* Quick Actions and Activity */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Quick Actions */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-gray-200 mb-4">
                Quick Actions
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                  <Users className="w-6 h-6 text-purple-400 mb-2" />
                  <h3 className="font-medium text-gray-100">Add User</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Invite team member
                  </p>
                </button>
                <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                  <Database className="w-6 h-6 text-blue-400 mb-2" />
                  <h3 className="font-medium text-gray-100">Backup</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Create backup now
                  </p>
                </button>
                <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                  <Mail className="w-6 h-6 text-green-400 mb-2" />
                  <h3 className="font-medium text-gray-100">Email Report</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Send weekly digest
                  </p>
                </button>
                <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                  <Shield className="w-6 h-6 text-red-400 mb-2" />
                  <h3 className="font-medium text-gray-100">Security</h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Review permissions
                  </p>
                </button>
              </div>
            </div>

            {/* Recent Activity */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-gray-200 mb-4">
                Recent Activity
              </h2>
              <div className="space-y-3">
                {recentActivity.map((activity, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <div className="w-2 h-2 bg-purple-400 rounded-full mt-2" />
                    <div className="flex-1">
                      <p className="text-sm text-gray-300">
                        {activity.type === 'user_login' && `${activity.user} logged in`}
                        {activity.type === 'session_created' && `${activity.user} started a recording`}
                        {activity.type === 'backup_completed' && 'System backup completed'}
                        {activity.type === 'user_added' && `${activity.user} was added`}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        <Clock className="w-3 h-3 inline mr-1" />
                        {activity.time}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'users' && (
        <div>
          <UserManagement />
        </div>
      )}

      {activeTab === 'settings' && (
        <div className="space-y-6">
          {/* Organization Settings */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Organization Settings
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Organization Name
                </label>
                <input
                  type="text"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:ring-2 focus:ring-purple-500"
                  defaultValue="Default Organization"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Storage Quota (GB)
                </label>
                <input
                  type="number"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:ring-2 focus:ring-purple-500"
                  defaultValue="100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max Users
                </label>
                <input
                  type="number"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:ring-2 focus:ring-purple-500"
                  defaultValue="50"
                />
              </div>
              <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
                Save Settings
              </button>
            </div>
          </div>

          {/* Security Settings */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Security Settings
            </h2>
            <div className="space-y-4">
              <label className="flex items-center gap-3">
                <input type="checkbox" className="rounded" defaultChecked />
                <span className="text-gray-300">Require 2FA for all users</span>
              </label>
              <label className="flex items-center gap-3">
                <input type="checkbox" className="rounded" defaultChecked />
                <span className="text-gray-300">Enable session timeout (30 minutes)</span>
              </label>
              <label className="flex items-center gap-3">
                <input type="checkbox" className="rounded" />
                <span className="text-gray-300">Restrict login to specific IP ranges</span>
              </label>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'integrations' && (
        <div className="space-y-6">
          <EmailNotifications />
          <WebhookManager />
        </div>
      )}

      {activeTab === 'maintenance' && (
        <div className="space-y-6">
          <BackupManager />
          
          {/* Storage Cleanup */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Storage Management
            </h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-gray-700 rounded-lg">
                <div>
                  <h3 className="font-medium text-gray-100">Clean Old Recordings</h3>
                  <p className="text-sm text-gray-400 mt-1">
                    Remove recordings older than 90 days
                  </p>
                </div>
                <button className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors">
                  Clean Up
                </button>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-700 rounded-lg">
                <div>
                  <h3 className="font-medium text-gray-100">Optimize Database</h3>
                  <p className="text-sm text-gray-400 mt-1">
                    Vacuum and reindex database tables
                  </p>
                </div>
                <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors">
                  Optimize
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};