import React, { useState, useEffect } from 'react';
import { 
  User, 
  LogOut, 
  Settings, 
  HelpCircle,
  Bell,
  Activity,
  Mic,
  Square,
  ChevronDown
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

interface TopBarProps {
  isRecording: boolean;
  activeRoom?: string;
  onStopRecording?: () => void;
  onStartRecording?: () => void;
  onNavigate: (view: string, subView?: string) => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  isRecording,
  activeRoom = 'None',
  onStopRecording,
  onStartRecording,
  onNavigate
}) => {
  const { user, logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [systemStatus, setSystemStatus] = useState<'online' | 'offline'>('online');

  // Check system status
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const API_BASE_URL = import.meta.env.VITE_API_URL || '';
        const response = await fetch(`${API_BASE_URL}/api/status`);
        setSystemStatus(response.ok ? 'online' : 'offline');
      } catch {
        setSystemStatus('offline');
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 30000); // Check every 30s
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="bg-gray-900 border-b border-gray-800 h-16 flex items-center justify-between px-6">
      {/* Left Section */}
      <div className="flex items-center space-x-6">
        {/* Logo */}
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">MO</span>
          </div>
          <h1 className="text-xl font-semibold text-white">Meeting-Ops</h1>
        </div>

        {/* Separator */}
        <div className="h-8 w-px bg-gray-700" />

        {/* Quick Record Button */}
        {isRecording ? (
          <button
            onClick={onStopRecording}
            className="flex items-center space-x-2 bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg transition-all duration-200 animate-pulse"
          >
            <Square className="w-4 h-4" />
            <span className="font-medium">Stop Recording</span>
          </button>
        ) : (
          <button
            onClick={onStartRecording}
            className="flex items-center space-x-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 px-4 py-2 rounded-lg transition-all duration-200"
          >
            <Mic className="w-4 h-4" />
            <span className="font-medium">Record</span>
          </button>
        )}

        {/* Active Room Status */}
        <div className="flex items-center space-x-2">
          <div className={`w-2 h-2 rounded-full ${isRecording ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
          <span className="text-gray-300">
            Active: <span className="text-white font-medium">{activeRoom}</span>
          </span>
        </div>
      </div>

      {/* Right Section */}
      <div className="flex items-center space-x-4">
        {/* System Status */}
        <div className="flex items-center space-x-2">
          <Activity className={`w-4 h-4 ${systemStatus === 'online' ? 'text-green-400' : 'text-red-400'}`} />
          <span className={`text-sm ${systemStatus === 'online' ? 'text-green-400' : 'text-red-400'}`}>
            {systemStatus === 'online' ? 'Online' : 'Offline'}
          </span>
        </div>

        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="p-2 hover:bg-gray-800 rounded-lg transition-colors duration-200 relative"
          >
            <Bell className="w-5 h-5 text-gray-300" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
          </button>

          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 bg-gray-800 rounded-lg shadow-xl border border-gray-700 z-50">
              <div className="p-4 border-b border-gray-700">
                <h3 className="font-semibold text-white">Notifications</h3>
              </div>
              <div className="max-h-96 overflow-y-auto">
                <div className="p-4 hover:bg-gray-700 cursor-pointer border-b border-gray-700/50">
                  <p className="text-sm text-white font-medium">Meeting completed</p>
                  <p className="text-xs text-gray-400 mt-1">Team Standup - 30 minutes ago</p>
                </div>
                <div className="p-4 hover:bg-gray-700 cursor-pointer">
                  <p className="text-sm text-white font-medium">Summary ready</p>
                  <p className="text-xs text-gray-400 mt-1">Client Review - 2 hours ago</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Help */}
        <button
          onClick={() => onNavigate('help')}
          className="p-2 hover:bg-gray-800 rounded-lg transition-colors duration-200"
        >
          <HelpCircle className="w-5 h-5 text-gray-300" />
        </button>

        {/* User Menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center space-x-2 p-2 hover:bg-gray-800 rounded-lg transition-colors duration-200"
          >
            <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center">
              <User className="w-4 h-4 text-white" />
            </div>
            <span className="text-white font-medium">{user?.username || 'User'}</span>
            <ChevronDown className="w-4 h-4 text-gray-400" />
          </button>

          {showUserMenu && (
            <div className="absolute right-0 mt-2 w-48 bg-gray-800 rounded-lg shadow-xl border border-gray-700 z-50">
              <div className="p-2">
                <button
                  onClick={() => {
                    setShowUserMenu(false);
                    onNavigate('settings', 'profile');
                  }}
                  className="w-full flex items-center space-x-2 px-3 py-2 hover:bg-gray-700 rounded-lg transition-colors duration-200"
                >
                  <User className="w-4 h-4 text-gray-400" />
                  <span className="text-white">Profile</span>
                </button>
                <button
                  onClick={() => {
                    setShowUserMenu(false);
                    onNavigate('settings');
                  }}
                  className="w-full flex items-center space-x-2 px-3 py-2 hover:bg-gray-700 rounded-lg transition-colors duration-200"
                >
                  <Settings className="w-4 h-4 text-gray-400" />
                  <span className="text-white">Settings</span>
                </button>
                <div className="my-2 border-t border-gray-700" />
                <button
                  onClick={() => {
                    setShowUserMenu(false);
                    logout();
                  }}
                  className="w-full flex items-center space-x-2 px-3 py-2 hover:bg-red-600/20 rounded-lg transition-colors duration-200"
                >
                  <LogOut className="w-4 h-4 text-red-400" />
                  <span className="text-red-400">Logout</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};