import React, { createContext, useState, useContext, useEffect, type ReactNode } from 'react';
import { config } from '../config';
import { setReconnectingState } from '../components/ReconnectingOverlay';
import { redirectToLogin } from '../utils/loginRedirect';
import {
  buildOrgHeaders,
  clearStoredOrgSlug,
  getStoredOrgSlug,
  isMeetingOpsApiRequest,
  type OrganizationMembership,
} from '../utils/organization';
import { clearAllHydratedCaches, HYDRATED_CACHE_CLEAR_EVENT } from '../utils/cachedState';

/**
 * Wipe every hydrated-state cache and let live components know to
 * reset to defaults. Called on login (new user might be a different
 * person) and logout (clear all data from the device).
 */
function broadcastHydratedCacheClear(): void {
  clearAllHydratedCaches();
  try {
    window.dispatchEvent(new Event(HYDRATED_CACHE_CLEAR_EVENT));
  } catch {
    /* SSR or restricted env — caches already cleared above */
  }
}

export type Tier = 'free' | 'pro' | 'enterprise';

export interface TierFeatures {
  server_live: boolean;
  diarization: boolean;
  qwen36_summary: boolean;
  speaker_library: boolean;
  retention_controls: boolean;
  brigade_byok: boolean;
  hipaa: boolean;
  // Server-processing gates (v3.0.0). Free tier is browser-only — these are
  // all false for free, true for pro/enterprise. Mirrors backend
  // TIER_FEATURES in backend/auth/tier.py.
  canonical_reprocess: boolean;
  brigade_integration: boolean;
  cross_device_sync: boolean;
  bulk_import: boolean;
  max_sessions_per_month: number | null;
  max_session_minutes: number | null;
}

/**
 * Default capability dict matching backend `TIER_FEATURES.free` in
 * `backend/auth/tier.py`. Used by `useTierFeatures()` as the fallback
 * while `/api/auth/me` is in flight so disabled buttons don't flash
 * "enabled" briefly on first paint.
 */
export const DEFAULT_TIER_FEATURES: TierFeatures = {
  server_live: false,
  diarization: false,
  qwen36_summary: false,
  speaker_library: false,
  retention_controls: false,
  brigade_byok: false,
  hipaa: false,
  canonical_reprocess: false,
  brigade_integration: false,
  cross_device_sync: false,
  bulk_import: false,
  max_sessions_per_month: 50,
  max_session_minutes: 60,
};

export interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  role?: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser?: boolean;
  created_at: string;
  organizations?: OrganizationMembership[];
  active_organization?: OrganizationMembership | null;
  tier?: Tier;
  tier_features?: TierFeatures;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  // Resolved tier + capability dict. Falls back to free + DEFAULT_TIER_FEATURES
  // while /api/auth/me is in flight or for anonymous callers.
  tier: Tier;
  tierFeatures: TierFeatures;
  /**
   * True when a 401 was observed during an active recording. The forced
   * logout/redirect was suppressed so the recording UI stays alive. UI
   * surfaces a non-blocking banner; user re-authenticates after stop.
   */
  authStaleDuringRecording: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

// Returns true iff the user is mid-recording (always-on or live) per
// localStorage. Used to short-circuit forced-logout-on-401 paths so a
// transient backend hiccup (deploy, network blip, oauth2-proxy session
// refresh) doesn't tear down a live meeting UI. Aaron 2026-05-30:
// "page refreshed and interrupted my recording. Not the first time."
function isRecordingActiveLocally(): boolean {
  try {
    const raw = localStorage.getItem('activeRecordingSession');
    if (raw) {
      const s = JSON.parse(raw);
      if (s && s.isRecording && s.id) return true;
    }
    // AlwaysOnContext persists its own state under this key.
    const aoRaw = localStorage.getItem('alwaysOnRecorderState');
    if (aoRaw) {
      const ao = JSON.parse(aoRaw);
      // Any non-idle / non-stopped state counts as "do not yank the UI".
      const live = ao && typeof ao.state === 'string' &&
        !['idle', 'stopped', 'paused', undefined, null].includes(ao.state);
      if (live) return true;
    }
  } catch { /* ignore */ }
  return false;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);
  // Becomes true when a 401 arrived during a recording — we suppress
  // the forced redirect and surface a non-blocking banner instead so
  // the user can finish the meeting before re-authing.
  const [authStaleDuringRecording, setAuthStaleDuringRecording] = useState(false);
  const authApi = (path: string) => `${config.apiUrl}${path}`;

  // Initialize tokens from localStorage safely
  useEffect(() => {
    try {
      const storedToken = localStorage.getItem('access_token');
      const storedRefreshToken = localStorage.getItem('refresh_token');
      setToken(storedToken);
      setRefreshToken(storedRefreshToken);
      setInitialLoadComplete(true);
    } catch (err) {
      console.error('Failed to read from localStorage:', err);
      setInitialLoadComplete(true);
    }
  }, []);

  // Check if user is authenticated on mount
  useEffect(() => {
    const checkAuth = async () => {
      if (token) {
        try {
          const response = await fetch(authApi('/api/auth/me'), {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });

          if (response.ok) {
            try {
              const userData = await response.json();
              setUser(userData);
            } catch (jsonError) {
              console.error('Failed to parse user data:', jsonError);
              logout();
            }
          } else if (response.status === 401 && refreshToken) {
            // Try to refresh the token
            const refreshSuccess = await refreshAccessToken();
            if (!refreshSuccess) {
              console.warn('Token refresh failed during auth check');
              // Don't call logout here as refreshAccessToken already handled it.
              // BUT: if a recording is live, also surface a non-blocking
              // banner so the user knows re-auth is needed at stop-time.
              if (isRecordingActiveLocally()) {
                setAuthStaleDuringRecording(true);
                console.warn('[auth] 401 during active recording — deferred logout');
                return;
              }
            }
          } else {
            // 401 with no refresh token (or worse) would normally force a
            // logout + redirect. If a recording is in progress that wipes
            // the user's live meeting UI and the chunks-flush state — see
            // Aaron's 2026-05-30 ticket. Defer instead.
            if (response.status === 401 && isRecordingActiveLocally()) {
              setAuthStaleDuringRecording(true);
              console.warn('[auth] 401 during active recording — deferred logout');
              return;
            }
            // Clear invalid tokens
            logout();
          }
        } catch (err) {
          console.error('Auth check failed:', err);
          // Only logout if it's not a network connectivity issue
          if (err instanceof TypeError && err.message.includes('fetch')) {
            console.warn('Network connectivity issue during auth check - keeping current state');
            // Don't set loading to false immediately on network errors to prevent flashing
            setTimeout(() => setIsLoading(false), 1000);
            return;
          } else {
            logout();
          }
        }
      }
      setIsLoading(false);
    };

    // Always probe /api/auth/me on mount so SSO sessions (oauth2-proxy
    // injects X-Auth-Request-Email server-side) are picked up even without
    // a JWT in localStorage.
    const probeSso = async () => {
      try {
        const r = await fetch(authApi('/api/auth/me'), {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' },
        });
        const ct = r.headers.get('content-type') || '';
        if (r.ok && ct.includes('application/json')) {
          try { setUser(await r.json()); } catch {}
        }
      } catch {}
      setIsLoading(false);
    };

    if (initialLoadComplete) {
      if (token || refreshToken) {
        checkAuth();
      } else {
        probeSso();
      }
    }
  }, [initialLoadComplete, token, refreshToken]); // Depend on initial load and token changes

  const refreshAccessToken = async () => {
    if (!refreshToken) {
      console.warn('No refresh token available for token refresh');
      return false;
    }

    try {
      const response = await fetch(authApi('/api/auth/refresh'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        try {
          const data = await response.json();
          setToken(data.access_token);
          setRefreshToken(data.refresh_token);
          setUser(data.user);
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          return true;
        } catch (jsonError) {
          console.error('Failed to parse refresh token response:', jsonError);
          logout();
          return false;
        }
      } else {
        console.warn('Token refresh failed:', response.status, response.statusText);
        logout();
        return false;
      }
    } catch (err) {
      console.error('Token refresh request failed:', err);
      // Don't logout on network errors, let the calling code handle it
      if (err instanceof TypeError && err.message.includes('fetch')) {
        console.warn('Network error during token refresh - keeping current state');
        return false;
      }
      logout();
      return false;
    }
  };

  const login = async (username: string, password: string) => {
    setError(null);
    setIsLoading(true);

    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);

      const response = await fetch(authApi('/api/auth/login'), {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        // Fresh login: wipe any leftover hydrated caches from a
        // previous user on this device before storing new auth state.
        broadcastHydratedCacheClear();
        setToken(data.access_token);
        setRefreshToken(data.refresh_token);
        setUser(data.user);
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        setError(null);
      } else {
        // Handle error response more robustly
        let errorMessage = 'Login failed';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorMessage;
        } catch (jsonError) {
          // If JSON parsing fails, use status text or default message
          errorMessage = response.statusText || `HTTP ${response.status}`;
        }
        throw new Error(errorMessage);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    // Try to stop any active recording before clearing auth
    const activeSession = localStorage.getItem('activeRecordingSession');
    if (activeSession) {
      try {
        const session = JSON.parse(activeSession);
        if (session.isRecording && session.id) {
          const apiBase = config.apiUrl;
          await fetch(`${apiBase}/api/simple/recording-sessions/${session.id}/stop`, {
            method: 'POST',
          });
        }
      } catch { /* best-effort */ }
    }

    // Clear recording state
    localStorage.removeItem('activeRecordingSession');
    localStorage.removeItem('lastMeetingSummary');
    localStorage.removeItem('lastMeetingTimestamp');

    // Clear auth
    setUser(null);
    setToken(null);
    setRefreshToken(null);
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    clearStoredOrgSlug();
    // Wipe hydrated state caches so the next user (or login bounce)
    // doesn't see this user's data flash on screen first.
    broadcastHydratedCacheClear();
    setError(null);

    // SSO sign-out: clear oauth2-proxy session, then Keycloak session,
    // then bounce back to root (which will redirect to fresh SSO login).
    const rd = encodeURIComponent(
      'https://auth.magicunicorn.dev/realms/uchub/protocol/openid-connect/logout' +
      '?post_logout_redirect_uri=' + encodeURIComponent('https://meetingops.magicunicorn.dev/') +
      '&client_id=meeting-ops'
    );
    window.location.href = `/oauth2/sign_out?rd=${rd}`;
  };

  // Set up axios-like interceptor for fetch
  useEffect(() => {
    const originalFetch = window.fetch;
    
    window.fetch = async (url: RequestInfo | URL, init?: RequestInit) => {
      const rawUrl = typeof url === 'string' ? url : url.toString();
      const orgSlug = getStoredOrgSlug();
      const shouldDecorate = isMeetingOpsApiRequest(url, config.apiBaseUrl);

      if (shouldDecorate) {
        const headers = buildOrgHeaders(init?.headers, orgSlug);
        if (token && !headers.has('Authorization')) {
          headers.set('Authorization', `Bearer ${token}`);
        }
        init = {
          ...init,
          headers,
        };
      }

      const response = await originalFetch(url, init);

      // Detect stale oauth2-proxy session: 302 redirect or HTML response
      // when we expected JSON. This happens when the oauth2-proxy cookie
      // expires but the SPA tab is still open.
      const isApiCall = rawUrl.startsWith('/api/') || rawUrl.includes('/api/');
      const headersInit = init?.headers;
      const headersObj = headersInit instanceof Headers ? headersInit : new Headers(headersInit);
      const wantsJson = headersObj.get('accept')?.includes('application/json') ||
        (isApiCall && !headersObj.has('Accept'));
      if (isApiCall && wantsJson && response.status === 302) {
        const loc = response.headers.get('location') || '';
        if (/\/oauth2\/(start|sign_out)|\/realms\/uchub/i.test(loc)) {
          setReconnectingState(true);
          redirectToLogin();
          return new Response(null, { status: 302 });
        }
      }
      if (isApiCall && wantsJson && response.headers.get('content-type')?.startsWith('text/html')) {
        setReconnectingState(true);
        redirectToLogin();
        return new Response(null, { status: 401 });
      }

      // Handle 401 responses
      if (response.status === 401 && refreshToken && !rawUrl.includes('/auth/')) {
        const refreshSuccess = await refreshAccessToken();
        // Retry the original request if refresh was successful
        const refreshedToken = localStorage.getItem('access_token');
        if (refreshSuccess && refreshedToken && shouldDecorate) {
          const retryHeaders = buildOrgHeaders(init?.headers, orgSlug);
          retryHeaders.set('Authorization', `Bearer ${refreshedToken}`);
          init = {
            ...init,
            headers: retryHeaders,
          };
          return originalFetch(url, init);
        }
      }

      return response;
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, [token, refreshToken]);

  const tier: Tier = user?.tier ?? 'free';
  const tierFeatures: TierFeatures = user?.tier_features ?? DEFAULT_TIER_FEATURES;

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        refreshToken: refreshAccessToken,
        isAuthenticated: !!user,
        isLoading,
        error,
        tier,
        tierFeatures,
        authStaleDuringRecording,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
