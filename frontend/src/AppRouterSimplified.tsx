import React, { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import { useOrg } from './contexts/OrgContext';
import { useRecording } from './contexts/RecordingContext';
import { Login } from './components/Login';
import LiveRecording from './pages/LiveRecording';
import RAGChat from './pages/RAGChat';
import DigestsPage from './pages/Digests';
import { Sessions } from './pages/Sessions';
import { SessionDetails } from './pages/SessionDetails';
import { SpeakerLibrary } from './pages/SpeakerLibrary';
import SettingsEnhanced from './pages/SettingsEnhanced';
import { AgentConfiguration } from './pages/admin/AgentConfiguration';
import { AgentDashboard } from './pages/admin/AgentDashboard';
import { Menu, X, Circle, Clock } from 'lucide-react';

// Layout wrapper with simplified navigation
function AppLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { organizations, activeOrganization, switchOrganization } = useOrg();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen bg-gradient-to-b from-zinc-950 to-black">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile hamburger button */}
      <button
        onClick={() => setSidebarOpen(true)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors md:hidden"
        aria-label="Open menu"
      >
        <Menu className="w-6 h-6" />
      </button>

      <SimplifiedNavigation isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="flex-1 overflow-y-auto">
        <header className="sticky top-0 z-30 flex items-center justify-end gap-3 border-b border-zinc-800 bg-black/80 px-4 py-3 backdrop-blur">
          <div className="mr-auto pl-12 text-sm text-zinc-500 md:pl-0">
            {activeOrganization ? `Workspace: ${activeOrganization.name}` : 'Workspace'}
          </div>
          <div className="min-w-0">
            <label className="sr-only" htmlFor="org-switcher">Organization</label>
            <select
              id="org-switcher"
              value={activeOrganization?.slug ?? ''}
              onChange={(event) => switchOrganization(event.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
            >
              {organizations.map((organization) => (
                <option key={organization.slug} value={organization.slug}>
                  {organization.name} ({organization.role})
                </option>
              ))}
            </select>
          </div>
          <div className="hidden text-right md:block">
            <div className="text-sm text-zinc-100">{user?.full_name || user?.email || user?.username}</div>
            <div className="text-xs text-zinc-500">{activeOrganization?.role || user?.role || 'user'}</div>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}

// Simplified Navigation Component
function SimplifiedNavigation({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { logout } = useAuth();
  const { isRecording, recordingTime } = useRecording();
  const location = window.location.hash.replace('#', '');

  const navItems = [
    { path: '/record', label: 'Record', icon: '🎙️' },
    { path: '/sessions', label: 'Sessions', icon: '📁' },
    { path: '/speakers', label: 'Speakers', icon: '🗣️' },
    { path: '/rag', label: 'AI Chat', icon: '💬' },
    { path: '/digests', label: 'Digests', icon: '📊' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ];

  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <nav
      className={`fixed top-0 left-0 h-full w-64 bg-zinc-950 border-r border-zinc-800 p-4 z-50 transform transition-transform duration-200 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        md:relative md:translate-x-0 md:flex md:flex-col`}
    >
      {/* Close button for mobile */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors md:hidden"
        aria-label="Close menu"
      >
        <X className="w-5 h-5" />
      </button>

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

      {/* Recording indicator in nav */}
      {isRecording && (
        <div className="mb-4 px-3 py-2 bg-red-600/20 border border-red-500/30 rounded-lg">
          <a
            href="#/record"
            onClick={onClose}
            className="flex items-center gap-2 text-red-400 hover:text-red-300 transition-colors"
          >
            <Circle className="w-3 h-3 fill-red-400 animate-pulse" />
            <span className="text-sm font-medium">Recording</span>
            <span className="ml-auto text-xs font-mono flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatTime(recordingTime)}
            </span>
          </a>
        </div>
      )}

      <div className="space-y-2">
        {navItems.map(item => (
          <a
            key={item.path}
            href={`#${item.path}`}
            onClick={onClose}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors min-h-[44px] ${
              (item.path === '/' ? location === item.path : location.startsWith(item.path))
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
          onClick={() => { logout(); onClose(); }}
          className="w-full px-3 py-2 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded-lg transition-colors text-sm min-h-[44px]"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}

function SsoLoginRedirect({ isAuthenticated }: { isAuthenticated: boolean }) {
  if (isAuthenticated) return <Navigate to="/record" replace />;
  // Kick to Keycloak via oauth2-proxy
  window.location.href = `/oauth2/start?rd=${encodeURIComponent('/')}`;
  return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Redirecting to sign-in…</div></div>;
}

// Protected Route Component
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const { hasAccess, isLoading: isOrgLoading } = useOrg();

  // Wait for SSO probe before deciding
  if (isLoading || isOrgLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Authenticating…</div></div>;
  }

  // Not authed → kick to oauth2-proxy SSO sign-in (Keycloak)
  if (!isAuthenticated) {
    const target = encodeURIComponent(window.location.pathname + window.location.hash);
    window.location.href = `/oauth2/start?rd=${target}`;
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Redirecting to sign-in…</div></div>;
  }

  if (!hasAccess) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">No organization access.</div></div>;
  }

  return <AppLayout>{children}</AppLayout>;
}

// Main Router
export function AppRouterSimplified() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isLoading: isOrgLoading } = useOrg();

  if (isLoading || isOrgLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Authenticating…</div></div>;
  }

  return (
    <Routes>
      <Route path="/login" element={<SsoLoginRedirect isAuthenticated={isAuthenticated} />} />

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

      <Route path="/speakers" element={
        <ProtectedRoute>
          <SpeakerLibrary />
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

            <Route path="/rag" element={
        <ProtectedRoute>
          <RAGChat />
        </ProtectedRoute>
      } />

      <Route path="/digests" element={
        <ProtectedRoute>
          <DigestsPage />
        </ProtectedRoute>
      } />

      <Route path="*" element={<Navigate to="/record" replace />} />
    </Routes>
  );
}
