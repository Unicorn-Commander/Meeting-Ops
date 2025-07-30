import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { ProductionDashboard } from './ProductionDashboard';
import { SystemAdminPanel } from './SystemAdminPanel';
import { ApplicationAdminPanel } from './ApplicationAdminPanel';
import { 
  User, 
  Settings, 
  Shield, 
  LogOut,
  ChevronRight
} from 'lucide-react';

export const UnifiedDashboard: React.FC = () => {
  const { user, logout } = useAuth();
  
  // Always use production dashboard for now
  const currentView = 'user';

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center space-x-6">
            {/* Logo */}
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-r from-purple-600 to-pink-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-lg">UC</span>
              </div>
              <h1 className="text-xl font-bold text-white">Meeting-Ops</h1>
            </div>
          </div>

          {/* User Info & Logout */}
          <div className="flex items-center space-x-4">
            <div className="text-right">
              <p className="text-sm font-medium text-white">{user?.username}</p>
              <p className="text-xs text-gray-400">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded-md transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        <ProductionDashboard />
      </main>

      {/* NPU Status Badge */}
      <div className="fixed bottom-4 left-4 bg-gray-800 rounded-lg px-3 py-2 border border-gray-700">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-xs text-gray-400">NPU Hardware Active</span>
        </div>
      </div>
    </div>
  );
};