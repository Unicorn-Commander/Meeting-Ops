import React, { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import { useOrg } from './contexts/OrgContext';
import { useRecording } from './contexts/RecordingContext';
import { redirectToLogin } from './utils/loginRedirect';
import { Login } from './components/Login';
import LiveRecording from './pages/LiveRecording';
import Dashboard from './pages/Dashboard';
import RAGChat from './pages/RAGChat';
import DigestsPage from './pages/Digests';
import { Sessions } from './pages/Sessions';
import { SessionDetails } from './pages/SessionDetails';
import { SpeakerLibrary } from './pages/SpeakerLibrary';
import SettingsEnhanced from './pages/SettingsEnhanced';
import { AgentConfiguration } from './pages/admin/AgentConfiguration';
import { SharedSessionRedirect } from './components/SharedSessionRedirect';
import { AgentDashboard } from './pages/admin/AgentDashboard';
import Rooms from './pages/Rooms';
import RoomSetupWizard from './pages/RoomSetupWizard';
import RoomDetail from './pages/RoomDetail';
import { Menu, X, Circle, Clock, DoorOpen, ShieldCheck } from 'lucide-react';

/**
 * Admin detection used across the layout. Mirrors the pattern from
 * SpeakerLibrary / RoomDetail so a single shape covers superusers
 * (system-wide) plus per-org admin/superuser roles. Crucially we read
 * `activeOrganization.role` not user.role, so a user who is admin in
 * one org and member in another sees admin nav only when the admin
 * org is currently selected — exactly what Aaron asked for.
 */
function isAdminRole(role?: string, isSuperuser?: boolean): boolean {
  if (isSuperuser) return true;
  return role === 'admin' || role === 'superuser';
}

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
  const { logout, user } = useAuth();
  const { activeOrganization } = useOrg();
  const { isRecording, recordingTime } = useRecording();
  const location = window.location.hash.replace('#', '');

  // Admin visibility is derived from the ACTIVE org's role + the
  // global superuser flag. Switching org rebinds this immediately —
  // a user who's admin in Magic Unicorn but member in Aaron-personal
  // sees the Admin section only when Magic Unicorn is active.
  const isAdmin = isAdminRole(activeOrganization?.role, user?.is_superuser);

  // navItems supports either an emoji string or a lucide-react icon
  // component. The Rooms entry uses the lucide DoorOpen glyph so it
  // stays visually anchored to the actions sidebar style; everything
  // else keeps its existing emoji to avoid a global cosmetic change.
  type NavItem = {
    path: string;
    label: string;
    icon: string | React.ComponentType<{ className?: string }>;
  };
  // Workspace-level nav — visible to everyone. Aaron's directive is
  // that admin items move OUT of the main list and into their own
  // section, so Speakers / Rooms (the multi-tenant configuration
  // surfaces) get pushed to the admin section below.
  const navItems: NavItem[] = [
    { path: '/dashboard', label: 'Dashboard', icon: '🏠' },
    { path: '/record', label: 'Record', icon: '🎙️' },
    { path: '/sessions', label: 'Sessions', icon: '📁' },
    { path: '/rag', label: 'AI Chat', icon: '💬' },
    { path: '/digests', label: 'Digests', icon: '📊' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ];
  // Admin-only nav — entirely hidden for non-admin users. Even the
  // section heading goes away when isAdmin is false; an empty
  // labeled bucket is noisy and Aaron wants the cleaner non-admin
  // view to land for regular users.
  const adminNavItems: NavItem[] = [
    { path: '/rooms', label: 'Rooms', icon: DoorOpen },
    { path: '/speakers', label: 'Speakers', icon: '🗣️' },
    { path: '/admin/agents', label: 'Agents', icon: '🤖' },
  ];

  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const renderNavItem = (item: NavItem) => {
    const Icon = typeof item.icon === 'string' ? null : item.icon;
    return (
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
        {Icon ? <Icon className="w-5 h-5" /> : <span>{item.icon as string}</span>}
        <span>{item.label}</span>
      </a>
    );
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
        {navItems.map(renderNavItem)}
      </div>

      {/* Admin-only section. Renders only when the current user is an
          admin in the active organization (or a global superuser). The
          subtle divider + section heading visually separates these
          items per Aaron's "labeled as such" directive. Non-admin
          users see exactly the workspace nav with no admin signal. */}
      {isAdmin && (
        <div className="mt-6">
          <div className="mt-2 border-t border-zinc-800/70" />
          <div className="mt-4 mb-2 flex items-center gap-2 px-3">
            <ShieldCheck className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">Admin</span>
          </div>
          <div className="space-y-2">
            {adminNavItems.map(renderNavItem)}
          </div>
        </div>
      )}

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
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;
  redirectToLogin('/');
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
    redirectToLogin();
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Redirecting to sign-in…</div></div>;
  }

  if (!hasAccess) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">No organization access.</div></div>;
  }

  return <AppLayout>{children}</AppLayout>;
}

/**
 * Admin-only wrapper. Same gating as the sidebar — if the user isn't
 * an admin in the active org (and not a global superuser), bounce
 * them to /dashboard. Prevents direct-URL access to /rooms,
 * /speakers, and /admin/* for regular users. Pages still apply their
 * own internal admin checks for finer-grained controls (e.g. only
 * enroll speakers as admin), but this is the route-level gate.
 */
function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const { activeOrganization, hasAccess, isLoading: isOrgLoading } = useOrg();

  if (isLoading || isOrgLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Authenticating…</div></div>;
  }
  if (!isAuthenticated) {
    redirectToLogin();
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">Redirecting to sign-in…</div></div>;
  }
  if (!hasAccess) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="text-gray-500">No organization access.</div></div>;
  }
  if (!isAdminRole(activeOrganization?.role, user?.is_superuser)) {
    // Silently bounce, no flash of forbidden content.
    return <Navigate to="/dashboard" replace />;
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

      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      <Route path="/dashboard" element={
        <ProtectedRoute>
          <Dashboard />
        </ProtectedRoute>
      } />

      {/*
        /record is preserved as a redirect to /record/personal so any
        existing bookmarks, recording-indicator hash links, and
        notification surfaces keep working. The personal/browser
        recording page lives under /record/personal; future room-host
        UIs can land under /record/<roomid>.
       */}
      <Route path="/record" element={<Navigate to="/record/personal" replace />} />
      <Route path="/record/personal" element={
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

      {/* Magic-link landing: post-login redemption -> navigates to /sessions/:id */}
      <Route path="/shared/sessions" element={
        <ProtectedRoute>
          <SharedSessionRedirect />
        </ProtectedRoute>
      } />

      {/* Admin-gated surfaces. Speakers + Rooms + Agents are all
          workspace-configuration features Aaron flagged as "admin
          stuff"; route-level guard bounces non-admin direct links to
          /dashboard so the sidebar gating + URL gating stay in sync. */}
      <Route path="/speakers" element={
        <AdminRoute>
          <SpeakerLibrary />
        </AdminRoute>
      } />

      <Route path="/rooms" element={
        <AdminRoute>
          <Rooms />
        </AdminRoute>
      } />

      <Route path="/rooms/new" element={
        <AdminRoute>
          <RoomSetupWizard />
        </AdminRoute>
      } />

      <Route path="/rooms/:id" element={
        <AdminRoute>
          <RoomDetail />
        </AdminRoute>
      } />

      <Route path="/settings" element={
        <ProtectedRoute>
          <SettingsEnhanced />
        </ProtectedRoute>
      } />

      <Route path="/admin/agents" element={
        <AdminRoute>
          <AgentDashboard />
        </AdminRoute>
      } />

      <Route path="/admin/agents-old" element={
        <AdminRoute>
          <AgentConfiguration />
        </AdminRoute>
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

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
