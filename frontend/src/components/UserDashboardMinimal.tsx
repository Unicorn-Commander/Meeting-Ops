import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';

interface UserDashboardMinimalProps {
  onSwitchToAdmin?: () => void;
}

export const UserDashboardMinimal: React.FC<UserDashboardMinimalProps> = ({ onSwitchToAdmin }) => {
  const { user } = useAuth();
  const [currentView, setCurrentView] = useState('command-center');
  
  return (
    <div className="min-h-screen bg-gray-900 text-white flex">
      {/* Simple Sidebar */}
      <aside className="w-64 bg-gray-800 p-4">
        <h1 className="text-xl font-bold mb-4">Unicorn Commander</h1>
        <nav className="space-y-2">
          <button
            onClick={() => setCurrentView('command-center')}
            className={`w-full text-left p-3 rounded ${
              currentView === 'command-center' ? 'bg-purple-600' : 'hover:bg-gray-700'
            }`}
          >
            Command Center
          </button>
          <button
            onClick={() => setCurrentView('sessions')}
            className={`w-full text-left p-3 rounded ${
              currentView === 'sessions' ? 'bg-purple-600' : 'hover:bg-gray-700'
            }`}
          >
            Sessions
          </button>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8">
        <h1 className="text-3xl font-bold mb-4">
          {currentView === 'command-center' ? 'Command Center' : 'Sessions'}
        </h1>
        <div className="bg-gray-800 p-6 rounded">
          <p>Welcome, {user?.username || 'User'}!</p>
          <p className="mt-2 text-gray-400">This is a minimal dashboard for testing.</p>
        </div>
      </main>
    </div>
  );
};