import React, { createContext, useState, useContext, useEffect, type ReactNode } from 'react';
import { config } from '../config';

interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  role?: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser?: boolean;
  created_at: string;
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

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);

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
          const response = await fetch('/api/auth/me', {
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
              // Don't call logout here as refreshAccessToken already handled it
            }
          } else {
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
        const r = await fetch('/api/auth/me', {
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
      const response = await fetch('/api/auth/refresh', {
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

      const response = await fetch('/api/auth/login', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
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
      // Add auth header to API requests
      if (token && typeof url === 'string' && url.startsWith('/api/')) {
        init = init || {};
        init.headers = {
          ...init.headers,
          'Authorization': `Bearer ${token}`,
        };
      }

      const response = await originalFetch(url, init);

      // Handle 401 responses
      if (response.status === 401 && refreshToken && typeof url === 'string' && !url.includes('/auth/')) {
        const refreshSuccess = await refreshAccessToken();
        // Retry the original request if refresh was successful
        if (refreshSuccess && token) {
          init = init || {};
          init.headers = {
            ...init.headers,
            'Authorization': `Bearer ${token}`,
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
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};