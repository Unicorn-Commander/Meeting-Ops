import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import {
  Home, Mic, BarChart3, FolderOpen, Link2, Cpu,
  Users, Settings, Shield, ChevronDown, ChevronRight,
  Activity, Calendar, Mail, Webhook, Database, Lock,
  HardDrive, Wifi, Bell, Search, Menu, X, LogOut,
  Star, Flag, Save, Download, Upload, Clock,
  Zap, AlertCircle, CheckCircle, Info, Volume2, Brain
} from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
  path?: string;
  badge?: string | number;
  badgeType?: 'success' | 'warning' | 'error' | 'info';
  children?: NavItem[];
  requiredRoles?: string[];
}

const navigationStructure: NavItem[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: Home,
    path: '/dashboard',
    badge: 'Live',
    badgeType: 'success'
  },
  {
    id: 'recording',
    label: 'Recording Hub',
    icon: Mic,
    children: [
      { id: 'live-recording', label: 'Record Meeting', icon: Activity, path: '/recording/live' },
      { id: 'sessions', label: 'Session Library', icon: Clock, path: '/recording/sessions' }
    ]
  },
  {
    id: 'intelligence',
    label: 'Intelligence Center',
    icon: BarChart3,
    children: [
      { id: 'analytics', label: 'Analytics Dashboard', icon: BarChart3, path: '/intelligence/analytics' },
      { id: 'insights', label: 'AI Insights', icon: Brain, path: '/intelligence/insights', badge: 'NEW', badgeType: 'info' },
      { id: 'speakers', label: 'Speaker Insights', icon: Users, path: '/intelligence/speakers' },
      { id: 'keywords', label: 'Keyword Trends', icon: Search, path: '/intelligence/keywords' },
      { id: 'summaries', label: 'Meeting Summaries', icon: Save, path: '/intelligence/summaries' }
    ]
  },
  {
    id: 'content',
    label: 'Content Manager',
    icon: FolderOpen,
    children: [
      { id: 'files', label: 'File Browser', icon: FolderOpen, path: '/content/files' },
      { id: 'flagged', label: 'Flagged Segments', icon: Flag, path: '/content/flagged', badge: 5, badgeType: 'warning' },
      { id: 'export', label: 'Export Center', icon: Download, path: '/content/export' },
      { id: 'storage', label: 'Storage Metrics', icon: HardDrive, path: '/content/storage' }
    ]
  },
  {
    id: 'integrations',
    label: 'Integrations',
    icon: Link2,
    children: [
      { id: 'calendar', label: 'Calendar Sync', icon: Calendar, path: '/integrations/calendar' },
      { id: 'email', label: 'Email Templates', icon: Mail, path: '/integrations/email' },
      { id: 'webhooks', label: 'Webhooks', icon: Webhook, path: '/integrations/webhooks' },
      { id: 'api-keys', label: 'API Keys', icon: Lock, path: '/integrations/api-keys' }
    ],
    requiredRoles: ['admin', 'superuser']
  },
  {
    id: 'system',
    label: 'System Control',
    icon: Cpu,
    children: [
      { id: 'npu', label: 'NPU Monitor', icon: Zap, path: '/system/npu', badge: '16 TOPS', badgeType: 'success' },
      { id: 'services', label: 'Service Status', icon: Activity, path: '/system/services' },
      { id: 'audio', label: 'Audio Devices', icon: Volume2, path: '/system/audio' },
      { id: 'network', label: 'Network Config', icon: Wifi, path: '/system/network' }
    ],
    requiredRoles: ['admin', 'superuser']
  },
  {
    id: 'organization',
    label: 'Organization',
    icon: Users,
    children: [
      { id: 'users', label: 'User Management', icon: Users, path: '/org/users' },
      { id: 'teams', label: 'Team Settings', icon: Shield, path: '/org/teams' },
      { id: 'access', label: 'Access Control', icon: Lock, path: '/org/access' },
      { id: 'audit', label: 'Audit Logs', icon: Database, path: '/org/audit' }
    ],
    requiredRoles: ['admin', 'superuser', 'manager']
  },
  {
    id: 'administration',
    label: 'Administration',
    icon: Shield,
    children: [
      { id: 'backup', label: 'Backup/Restore', icon: Database, path: '/admin/backup' },
      { id: 'ssl', label: 'SSL Certificates', icon: Lock, path: '/admin/ssl' },
      { id: 'logs', label: 'System Logs', icon: Activity, path: '/admin/logs' },
      { id: 'maintenance', label: 'Maintenance', icon: Settings, path: '/admin/maintenance' }
    ],
    requiredRoles: ['superuser']
  }
];

export const MeetingOpsNavigation: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [notifications, setNotifications] = useState(3);
  
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Filter navigation based on user role
  const filterNavigation = (items: NavItem[]): NavItem[] => {
    return items.filter(item => {
      if (item.requiredRoles && user) {
        const hasRole = item.requiredRoles.includes(user.role || 'user');
        if (!hasRole) return false;
      }
      if (item.children) {
        item.children = filterNavigation(item.children);
      }
      return true;
    });
  };

  const visibleNavigation = filterNavigation(navigationStructure);

  const toggleExpanded = (itemId: string) => {
    setExpandedItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  const isActive = (path?: string) => {
    if (!path) return false;
    return location.pathname.startsWith(path);
  };

  const renderNavItem = (item: NavItem, depth = 0) => {
    const hasChildren = item.children && item.children.length > 0;
    const isExpanded = expandedItems.has(item.id);
    const active = isActive(item.path);

    return (
      <div key={item.id}>
        <button
          onClick={() => {
            if (hasChildren) {
              toggleExpanded(item.id);
            } else if (item.path) {
              navigate(item.path);
            }
          }}
          className={`
            w-full flex items-center justify-between px-3 py-2 rounded-lg
            transition-all duration-200 group
            ${active 
              ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg' 
              : 'hover:bg-gray-800 text-gray-300 hover:text-white'
            }
            ${depth > 0 ? 'ml-4' : ''}
          `}
        >
          <div className="flex items-center gap-3">
            <item.icon className={`w-5 h-5 ${active ? 'text-white' : 'text-gray-400 group-hover:text-purple-400'}`} />
            {!collapsed && (
              <>
                <span className="font-medium">{item.label}</span>
                {item.badge && (
                  <span className={`
                    px-2 py-0.5 text-xs rounded-full font-semibold
                    ${item.badgeType === 'success' ? 'bg-green-500/20 text-green-400' :
                      item.badgeType === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                      item.badgeType === 'error' ? 'bg-red-500/20 text-red-400' :
                      'bg-blue-500/20 text-blue-400'
                    }
                  `}>
                    {item.badge}
                  </span>
                )}
              </>
            )}
          </div>
          {!collapsed && hasChildren && (
            <div className="transition-transform duration-200">
              {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </div>
          )}
        </button>
        
        {!collapsed && hasChildren && isExpanded && (
          <div className="mt-1 space-y-1">
            {item.children!.map(child => renderNavItem(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={`
      bg-gray-900 border-r border-gray-800 flex flex-col h-full
      transition-all duration-300 ${collapsed ? 'w-16' : 'w-64'}
    `}>
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          {!collapsed && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
                <Mic className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-white font-bold text-sm">Meeting-Ops</h1>
                <p className="text-xs text-gray-400">Control Center</p>
              </div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-gray-400 hover:text-white transition-colors"
          >
            {collapsed ? <Menu className="w-5 h-5" /> : <X className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Search Bar */}
      {!collapsed && (
        <div className="p-3 border-b border-gray-800">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Quick search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
        </div>
      )}

      {/* Status Indicators */}
      <div className={`p-3 border-b border-gray-800 ${collapsed ? 'px-2' : ''}`}>
        <div className={`grid ${collapsed ? 'grid-cols-1 gap-2' : 'grid-cols-3'} gap-2`}>
          <div className="flex items-center justify-center p-2 bg-green-500/10 rounded-lg" title="NPU Active">
            <Zap className="w-4 h-4 text-green-400" />
            {!collapsed && <span className="ml-2 text-xs text-green-400">NPU</span>}
          </div>
          <div className="flex items-center justify-center p-2 bg-blue-500/10 rounded-lg" title="3 Active Sessions">
            <Activity className="w-4 h-4 text-blue-400" />
            {!collapsed && <span className="ml-2 text-xs text-blue-400">3</span>}
          </div>
          <div className="flex items-center justify-center p-2 bg-yellow-500/10 rounded-lg" title="3 Notifications">
            <Bell className="w-4 h-4 text-yellow-400" />
            {!collapsed && <span className="ml-2 text-xs text-yellow-400">{notifications}</span>}
          </div>
        </div>
      </div>

      {/* Navigation Items */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {visibleNavigation.map(item => renderNavItem(item))}
      </div>

      {/* User Section */}
      <div className="p-3 border-t border-gray-800">
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between'}`}>
          {!collapsed && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-500 rounded-full flex items-center justify-center">
                <span className="text-white text-xs font-bold">
                  {user?.username?.[0]?.toUpperCase() || 'U'}
                </span>
              </div>
              <div>
                <p className="text-sm text-white font-medium">{user?.username || 'User'}</p>
                <p className="text-xs text-gray-400 capitalize">{user?.role || 'user'}</p>
              </div>
            </div>
          )}
          <button
            onClick={logout}
            className="text-gray-400 hover:text-red-400 transition-colors"
            title="Logout"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};