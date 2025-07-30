import React, { useState } from 'react';
import { 
  Home, 
  Mic, 
  Brain, 
  BookOpen, 
  Link2, 
  Settings, 
  ShieldCheck,
  ChevronDown,
  ChevronRight,
  Activity,
  Calendar,
  BarChart3,
  FileText,
  Sparkles,
  Search,
  FileAudio,
  Download,
  File,
  Trash2,
  Users,
  Monitor,
  HardDrive,
  Key,
  Radio
} from 'lucide-react';

interface MenuItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  children?: MenuItem[];
  adminOnly?: boolean;
}

interface SidebarNavigationProps {
  currentView: string;
  currentSubView?: string;
  onNavigate: (view: string, subView?: string) => void;
  isAdmin: boolean;
  isRecording?: boolean;
}

export const SidebarNavigation: React.FC<SidebarNavigationProps> = ({
  currentView,
  currentSubView,
  onNavigate,
  isAdmin,
  isRecording = false
}) => {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['meetings', 'intelligence', 'library'])
  );

  const toggleSection = (sectionId: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionId)) {
      newExpanded.delete(sectionId);
    } else {
      newExpanded.add(sectionId);
    }
    setExpandedSections(newExpanded);
  };

  const menuItems: MenuItem[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: <Home className="w-5 h-5" />
    },
    {
      id: 'meetings',
      label: 'Meetings',
      icon: <Mic className="w-5 h-5" />,
      children: [
        {
          id: 'active-session',
          label: 'Active Session',
          icon: <Radio className={`w-4 h-4 ${isRecording ? 'text-red-500 animate-pulse' : ''}`} />
        },
        {
          id: 'sessions',
          label: 'Sessions',
          icon: <FileText className="w-4 h-4" />
        },
        {
          id: 'calendar',
          label: 'Calendar',
          icon: <Calendar className="w-4 h-4" />
        },
        {
          id: 'analytics',
          label: 'Analytics',
          icon: <BarChart3 className="w-4 h-4" />
        }
      ]
    },
    {
      id: 'intelligence',
      label: 'Intelligence',
      icon: <Brain className="w-5 h-5" />,
      children: [
        {
          id: 'transcripts',
          label: 'Transcripts',
          icon: <FileText className="w-4 h-4" />
        },
        {
          id: 'summaries',
          label: 'Summaries',
          icon: <Sparkles className="w-4 h-4" />
        },
        {
          id: 'insights',
          label: 'Insights',
          icon: <Activity className="w-4 h-4" />
        },
        {
          id: 'search',
          label: 'Search',
          icon: <Search className="w-4 h-4" />
        }
      ]
    },
    {
      id: 'library',
      label: 'Library',
      icon: <BookOpen className="w-5 h-5" />,
      children: [
        {
          id: 'audio-files',
          label: 'Audio Files',
          icon: <FileAudio className="w-4 h-4" />
        },
        {
          id: 'exports',
          label: 'Exports',
          icon: <Download className="w-4 h-4" />
        },
        {
          id: 'templates',
          label: 'Templates',
          icon: <File className="w-4 h-4" />
        },
        {
          id: 'trash',
          label: 'Trash',
          icon: <Trash2 className="w-4 h-4" />
        }
      ]
    },
    {
      id: 'integrations',
      label: 'Integrations',
      icon: <Link2 className="w-5 h-5" />,
      children: [
        {
          id: 'calendar-sync',
          label: 'Calendar Sync',
          icon: <Calendar className="w-4 h-4" />
        },
        {
          id: 'webhooks',
          label: 'Webhooks',
          icon: <Link2 className="w-4 h-4" />
        },
        {
          id: 'email-settings',
          label: 'Email Settings',
          icon: <FileText className="w-4 h-4" />
        },
        {
          id: 'api-access',
          label: 'API Access',
          icon: <Key className="w-4 h-4" />
        }
      ]
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: <Settings className="w-5 h-5" />,
      children: [
        {
          id: 'audio-devices',
          label: 'Audio Devices',
          icon: <Mic className="w-4 h-4" />
        },
        {
          id: 'notifications',
          label: 'Notifications',
          icon: <Activity className="w-4 h-4" />
        },
        {
          id: 'export-preferences',
          label: 'Export Preferences',
          icon: <Download className="w-4 h-4" />
        },
        {
          id: 'profile',
          label: 'Profile',
          icon: <Users className="w-4 h-4" />
        }
      ]
    },
    {
      id: 'admin',
      label: 'Admin',
      icon: <ShieldCheck className="w-5 h-5" />,
      adminOnly: true,
      children: [
        {
          id: 'users',
          label: 'Users',
          icon: <Users className="w-4 h-4" />
        },
        {
          id: 'system',
          label: 'System',
          icon: <Monitor className="w-4 h-4" />
        },
        {
          id: 'security',
          label: 'Security',
          icon: <ShieldCheck className="w-4 h-4" />
        },
        {
          id: 'storage',
          label: 'Storage',
          icon: <HardDrive className="w-4 h-4" />
        },
        {
          id: 'npu-config',
          label: 'NPU Config',
          icon: <Brain className="w-4 h-4" />
        }
      ]
    }
  ];

  const filteredMenuItems = menuItems.filter(item => !item.adminOnly || isAdmin);

  const renderMenuItem = (item: MenuItem, isChild = false) => {
    const hasChildren = item.children && item.children.length > 0;
    const isExpanded = expandedSections.has(item.id);
    const isActive = currentView === item.id || 
                    (hasChildren && item.children?.some(child => currentView === item.id && currentSubView === child.id));

    return (
      <div key={item.id}>
        <button
          onClick={() => {
            if (hasChildren) {
              toggleSection(item.id);
              // Navigate to first child if expanding
              if (!isExpanded && item.children && item.children[0]) {
                onNavigate(item.id, item.children[0].id);
              }
            } else {
              onNavigate(isChild ? currentView : item.id, isChild ? item.id : undefined);
            }
          }}
          className={`
            w-full flex items-center justify-between px-4 py-2.5 rounded-lg
            transition-all duration-200 group
            ${isActive 
              ? 'bg-gradient-to-r from-purple-600/20 to-pink-600/20 text-white border-l-4 border-purple-500' 
              : 'hover:bg-gray-800 text-gray-300 hover:text-white'
            }
            ${isChild ? 'pl-12 py-2' : ''}
          `}
        >
          <div className="flex items-center space-x-3">
            {item.icon}
            <span className={`font-medium ${isChild ? 'text-sm' : ''}`}>{item.label}</span>
          </div>
          {hasChildren && !isChild && (
            <div className="transition-transform duration-200">
              {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </div>
          )}
        </button>
        
        {hasChildren && isExpanded && (
          <div className="mt-1 space-y-0.5">
            {item.children!.map(child => renderMenuItem(child, true))}
          </div>
        )}
      </div>
    );
  };

  return (
    <nav className="w-64 bg-gray-900 h-full overflow-y-auto border-r border-gray-800">
      <div className="p-4">
        {/* Logo/Branding */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
            Meeting-Ops
          </h1>
          <p className="text-xs text-gray-500 mt-1">Unicorn Commander Suite</p>
        </div>

        {/* Quick Record Button */}
        <button
          onClick={() => onNavigate('meetings', 'active-session')}
          className={`
            w-full mb-6 py-3 px-4 rounded-lg font-medium
            flex items-center justify-center space-x-2
            transition-all duration-300 shadow-lg
            ${isRecording 
              ? 'bg-red-600 hover:bg-red-700 animate-pulse' 
              : 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700'
            }
          `}
        >
          <Mic className="w-5 h-5" />
          <span>{isRecording ? 'Recording...' : 'Start Recording'}</span>
        </button>

        {/* Menu Items */}
        <div className="space-y-1">
          {filteredMenuItems.map(item => renderMenuItem(item))}
        </div>
      </div>
    </nav>
  );
};