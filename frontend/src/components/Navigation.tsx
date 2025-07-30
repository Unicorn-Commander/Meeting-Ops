import React from 'react';
import {
  Mic,
  BarChart3,
  Folder,
  FileText,
  Settings,
  Search,
  Brain,
  Users as UsersIcon,
  Shield,
  Activity,
  Calendar,
  Webhook,
  Mail,
  Home,
  Sparkles,
  Command,
  Zap,
  Layers,
  Radio,
  HelpCircle,
  LogOut
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';

interface MenuItem {
  id: string;
  name: string;
  icon: any;
  description: string;
  badge?: string;
  badgeColor?: string;
}

interface MenuGroup {
  group: string;
  items: MenuItem[];
}

interface NavigationProps {
  currentView: string;
  onNavigate: (view: string) => void;
  isAdmin?: boolean;
}

export const Navigation: React.FC<NavigationProps> = ({ currentView, onNavigate, isAdmin }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const mainMenuItems: MenuGroup[] = [
    {
      group: 'Meeting Operations',
      items: [
        {
          id: 'command-center',
          name: 'Command Center',
          icon: Command,
          description: 'Real-time meeting control',
          badge: 'LIVE',
          badgeColor: 'bg-red-500'
        },
        {
          id: 'recording',
          name: 'Recording Studio',
          icon: Mic,
          description: 'Server-side recording & transcription'
        },
        {
          id: 'sessions',
          name: 'Meeting Sessions',
          icon: Radio,
          description: 'Recording history & management'
        },
        {
          id: 'library',
          name: 'Audio Library',
          icon: Folder,
          description: 'Recorded files & exports'
        },
        {
          id: 'insights',
          name: 'Meeting Insights',
          icon: BarChart3,
          description: 'Analytics & trends'
        },
        {
          id: 'transcripts',
          name: 'Transcripts',
          icon: FileText,
          description: 'Search & view transcriptions'
        }
      ]
    },
    {
      group: 'Intelligence Suite',
      items: [
        {
          id: 'smart-search',
          name: 'Smart Search',
          icon: Search,
          description: 'AI-powered semantic search',
          badge: 'AI',
          badgeColor: 'bg-purple-500'
        },
        {
          id: 'model-manager',
          name: 'Model Manager',
          icon: Brain,
          description: 'AI models & performance',
          badge: 'NPU',
          badgeColor: 'bg-green-500'
        },
        {
          id: 'assistants',
          name: 'Virtual Assistants',
          icon: Sparkles,
          description: 'AI-powered meeting helpers'
        }
      ]
    },
    {
      group: 'Integration Hub',
      items: [
        {
          id: 'calendar',
          name: 'Calendar Sync',
          icon: Calendar,
          description: 'Meeting scheduling & rooms'
        },
        {
          id: 'webhooks',
          name: 'Webhooks & API',
          icon: Webhook,
          description: 'External integrations'
        },
        {
          id: 'notifications',
          name: 'Notifications',
          icon: Mail,
          description: 'Email & alerts configuration'
        }
      ]
    }
  ];

  const adminMenuItems = isAdmin ? [
    {
      group: 'System Control',
      items: [
        {
          id: 'team',
          name: 'Team Management',
          icon: UsersIcon,
          description: 'Users & permissions'
        },
        {
          id: 'system',
          name: 'System Monitor',
          icon: Activity,
          description: 'Health & performance'
        },
        {
          id: 'security',
          name: 'Security Center',
          icon: Shield,
          description: 'Audit logs & policies'
        },
        {
          id: 'configuration',
          name: 'Configuration',
          icon: Settings,
          description: 'Advanced settings'
        }
      ]
    }
  ] : [];

  const allMenuItems = [...mainMenuItems, ...adminMenuItems];

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <aside className="w-80 bg-gray-800 border-r border-gray-700 flex flex-col h-screen">
      {/* Brand Header */}
      <div className="p-6 border-b border-gray-700 bg-gradient-to-r from-purple-600/10 to-pink-600/10">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
            <Command className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
              Unicorn Commander
            </h1>
            <p className="text-xs text-gray-400">Meeting Ops Edition</p>
          </div>
        </div>
        
        {/* Quick Record Button */}
        <button className="w-full mt-4 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-lg flex items-center justify-center gap-2 transition-all transform hover:scale-105">
          <Zap className="w-4 h-4" />
          <span className="font-medium">Quick Record</span>
        </button>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 overflow-y-auto p-4">
        {allMenuItems.map((group, groupIndex) => (
          <div key={group.group} className={groupIndex > 0 ? 'mt-6' : ''}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-3">
              {group.group}
            </h3>
            <div className="space-y-1">
              {group.items.map((item) => {
                const IconComponent = item.icon;
                const isActive = currentView === item.id;
                
                return (
                  <button
                    key={item.id}
                    onClick={() => onNavigate(item.id)}
                    className={`w-full text-left p-3 rounded-lg transition-all duration-200 group relative ${
                      isActive
                        ? 'bg-gradient-to-r from-purple-600/20 to-pink-600/20 text-white border-l-4 border-purple-500'
                        : 'hover:bg-gray-700/50 text-gray-300 hover:text-white'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <IconComponent className={`w-5 h-5 ${isActive ? 'text-purple-400' : 'text-gray-400 group-hover:text-gray-300'}`} />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{item.name}</span>
                          {'badge' in item && item.badge && (
                            <span className={`text-xs px-2 py-0.5 rounded-full text-white ${item.badgeColor} animate-pulse`}>
                              {item.badge}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 group-hover:text-gray-400">{item.description}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700 space-y-2">
        {/* Help */}
        <button
          onClick={() => onNavigate('help')}
          className="w-full text-left p-3 hover:bg-gray-700/50 rounded-lg transition-colors flex items-center gap-3 text-gray-400 hover:text-white"
        >
          <HelpCircle className="w-5 h-5" />
          <span>Help & Documentation</span>
        </button>

        {/* User Profile */}
        <div className="p-3 bg-gray-700/30 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center">
              <span className="text-sm font-bold text-white">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium">{user?.username}</p>
              <p className="text-xs text-gray-400">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 hover:bg-gray-600 rounded-lg transition-colors"
              title="Logout"
            >
              <LogOut className="w-4 h-4 text-gray-400" />
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};