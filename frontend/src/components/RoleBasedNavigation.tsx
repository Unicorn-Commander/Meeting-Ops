import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { 
  LayoutDashboard, 
  Mic, 
  FileText, 
  Upload, 
  BarChart3, 
  Users, 
  Settings, 
  Shield, 
  Cpu, 
  Building,
  Database,
  HelpCircle,
  Activity,
  Brain
} from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  roles: string[];
  children?: NavItem[];
}

const navigationItems: NavItem[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: <LayoutDashboard className="w-5 h-5" />,
    roles: ['viewer', 'user', 'manager', 'admin', 'superuser']
  },
  {
    id: 'recording-new',
    label: '🎙️ Record Meeting',
    icon: <Mic className="w-5 h-5" />,
    roles: ['user', 'manager', 'admin', 'superuser']
  },
  {
    id: 'meetings',
    label: '📊 Recording Sessions',
    icon: <FileText className="w-5 h-5" />,
    roles: ['viewer', 'user', 'manager', 'admin', 'superuser']
    // Upload functionality integrated into Recording Sessions page
  },
  {
    id: 'ai-config',
    label: '🤖 AI Configuration',
    icon: <Brain className="w-5 h-5" />,
    roles: ['user', 'manager', 'admin', 'superuser'],
    children: [
      {
        id: 'templates',
        label: 'Summarization Templates',
        icon: <FileText className="w-4 h-4" />,
        roles: ['user', 'manager', 'admin', 'superuser']
      },
      {
        id: 'ai-settings',
        label: 'AI Provider Settings',
        icon: <Settings className="w-4 h-4" />,
        roles: ['manager', 'admin', 'superuser']
      }
    ]
  },
  {
    id: 'analytics',
    label: '📈 Analytics',
    icon: <BarChart3 className="w-5 h-5" />,
    roles: ['manager', 'admin', 'superuser']
  },
  {
    id: 'administration',
    label: 'Administration',
    icon: <Shield className="w-5 h-5" />,
    roles: ['admin', 'superuser'],
    children: [
      {
        id: 'users',
        label: 'Users',
        icon: <Users className="w-4 h-4" />,
        roles: ['admin', 'superuser']
      },
      {
        id: 'settings',
        label: 'Settings',
        icon: <Settings className="w-4 h-4" />,
        roles: ['admin', 'superuser']
      },
      {
        id: 'integrations',
        label: 'Integrations',
        icon: <Building className="w-4 h-4" />,
        roles: ['admin', 'superuser']
      },
      {
        id: 'audit-logs',
        label: 'Audit Logs',
        icon: <FileText className="w-4 h-4" />,
        roles: ['admin', 'superuser']
      }
    ]
  },
  {
    id: 'system',
    label: 'System',
    icon: <Cpu className="w-5 h-5" />,
    roles: ['superuser'],
    children: [
      {
        id: 'system-monitor',
        label: 'System Monitor',
        icon: <Activity className="w-4 h-4" />,
        roles: ['superuser']
      },
      {
        id: 'hardware',
        label: 'Hardware',
        icon: <Cpu className="w-4 h-4" />,
        roles: ['superuser']
      },
      {
        id: 'organizations',
        label: 'Organizations',
        icon: <Building className="w-4 h-4" />,
        roles: ['superuser']
      },
      {
        id: 'database',
        label: 'Database',
        icon: <Database className="w-4 h-4" />,
        roles: ['superuser']
      }
    ]
  },
  {
    id: 'help',
    label: 'Help',
    icon: <HelpCircle className="w-5 h-5" />,
    roles: ['viewer', 'user', 'manager', 'admin', 'superuser']
  }
];

interface RoleBasedNavigationProps {
  currentView: string;
  onNavigate: (viewId: string) => void;
}

export const RoleBasedNavigation: React.FC<RoleBasedNavigationProps> = ({
  currentView,
  onNavigate
}) => {
  const { user } = useAuth();
  const userRole = user?.role || 'viewer';
  const isSuperuser = user?.is_superuser || false;

  // Filter navigation items based on user role
  const filterNavItems = (items: NavItem[]): NavItem[] => {
    return items.filter(item => {
      const hasRole = item.roles.includes(userRole) || 
                     (isSuperuser && item.roles.includes('superuser'));
      if (!hasRole) return false;

      // Filter children if they exist
      if (item.children) {
        item.children = filterNavItems(item.children);
      }

      return true;
    });
  };

  const visibleItems = filterNavItems([...navigationItems]);

  return (
    <nav className="bg-gray-800 h-full">
      <div className="p-4">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
          Navigation
        </h2>
        
        <ul className="space-y-1">
          {visibleItems.map(item => (
            <li key={item.id}>
              <button
                onClick={() => onNavigate(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                  currentView === item.id
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
              
              {item.children && item.children.length > 0 && (
                <ul className="mt-1 ml-8 space-y-1">
                  {item.children.map(child => (
                    <li key={child.id}>
                      <button
                        onClick={() => onNavigate(child.id)}
                        className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                          currentView === child.id
                            ? 'bg-purple-600/20 text-purple-400'
                            : 'text-gray-400 hover:bg-gray-700 hover:text-white'
                        }`}
                      >
                        {child.icon}
                        <span>{child.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </div>
      
      {/* User Info Section */}
      <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-700">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-purple-600 rounded-full flex items-center justify-center text-white font-semibold">
            {user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-200">
              {user?.full_name || user?.username || 'User'}
            </p>
            <p className="text-xs text-gray-400 capitalize">
              {isSuperuser ? 'Superuser' : userRole}
            </p>
          </div>
        </div>
      </div>
    </nav>
  );
};