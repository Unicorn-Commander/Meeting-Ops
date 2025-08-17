import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import { Login } from './components/Login';
import LiveRecording from './pages/LiveRecording';
import { Sessions } from './pages/Sessions';  // Use the correct Sessions component, not the wrapper
import { SessionDetails } from './pages/SessionDetails';
import SettingsEnhanced from './pages/SettingsEnhanced';
import { AgentConfiguration } from './pages/admin/AgentConfiguration';
import { AgentDashboard } from './pages/admin/AgentDashboard';

// Layout wrapper with simplified navigation
function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gradient-to-b from-zinc-950 to-black">
      <SimplifiedNavigation />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

// Simplified Navigation Component
function SimplifiedNavigation() {
  const { logout } = useAuth();
  const location = window.location.hash.replace('#', '');
  
  const navItems = [
    { path: '/record', label: 'Record', icon: '🎙️' },
    { path: '/sessions', label: 'Sessions', icon: '📁' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
    { path: '/admin/agents', label: 'AI Agents', icon: '🤖' },
  ];

  return (
    <nav className="w-64 bg-zinc-950 border-r border-zinc-800 p-4">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fuchsia-500 to-indigo-500 flex items-center justify-center">
            <span className="text-white text-xl">✨</span>
          </div>
          <div>
            <div className="text-white font-semibold">Meeting-Ops</div>
            <div className="text-xs text-zinc-400">AI Recording Suite</div>
          </div>
        </div>
      </div>
      
      <div className="space-y-2">
        {navItems.map(item => (
          <a
            key={item.path}
            href={`#${item.path}`}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
              location === item.path 
                ? 'bg-zinc-800 text-white' 
                : 'text-zinc-400 hover:text-white hover:bg-zinc-900'
            }`}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </a>
        ))}
      </div>
      
      <div className="absolute bottom-4 left-4 right-4">
        <button
          onClick={logout}
          className="w-full px-3 py-2 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded-lg transition-colors text-sm"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}

// Protected Route Component
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  return <AppLayout>{children}</AppLayout>;
}

// Main Router
export function AppRouterSimplified() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/record" replace /> : <Login />
      } />
      
      <Route path="/" element={<Navigate to="/record" replace />} />
      
      <Route path="/record" element={
        <ProtectedRoute>
          <LiveRecording />
        </ProtectedRoute>
      } />
      
      <Route path="/sessions" element={
        <ProtectedRoute>
          <Sessions />
        </ProtectedRoute>
      } />
      
      <Route path="/sessions/:id" element={
        <ProtectedRoute>
          <SessionDetails />
        </ProtectedRoute>
      } />
      
      <Route path="/settings" element={
        <ProtectedRoute>
          <SettingsEnhanced />
        </ProtectedRoute>
      } />
      
      <Route path="/admin/agents" element={
        <ProtectedRoute>
          <AgentDashboard />
        </ProtectedRoute>
      } />
      
      <Route path="/admin/agents-old" element={
        <ProtectedRoute>
          <AgentConfiguration />
        </ProtectedRoute>
      } />
      
      <Route path="*" element={<Navigate to="/record" replace />} />
    </Routes>
  );
}