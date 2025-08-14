import React, { createContext, useState, useContext, useEffect, type ReactNode } from 'react';
import { config } from '../config';

interface AuthentikUser {
  username: string;
  email: string;
  name: string;
  uid: string;
  groups: string[];
  is_admin: boolean;
  is_active: boolean;
  authenticated_at: string;
}

interface AuthentikAuthContextType {
  user: AuthentikUser | null;
  login: () => void;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  checkUserStatus: () => Promise<void>;
}

const AuthentikAuthContext = createContext<AuthentikAuthContextType | undefined>(undefined);

export const useAuthentikAuth = () => {
  const context = useContext(AuthentikAuthContext);
  if (!context) {
    throw new Error('useAuthentikAuth must be used within an AuthentikAuthProvider');
  }
  return context;
};

interface AuthentikAuthProviderProps {
  children: ReactNode;
}

// Use the config for URL management
const getAuthUrls = () => {
  return {
    loginUrl: config.apiEndpoints.auth.login(),
    logoutUrl: config.apiEndpoints.auth.logout(),
    profileUrl: config.apiEndpoints.auth.profile(),
    apiUrl: config.apiBaseUrl
  };
};

export const AuthentikAuthProvider: React.FC<AuthentikAuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<AuthentikUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Extract user from Authentik headers (set by Traefik/Authentik)
  const extractUserFromHeaders = async (): Promise<AuthentikUser | null> => {
    try {
      // In production, headers are set by Traefik/Authentik
      // In development, we need to make a request to get them
      const urls = getAuthUrls();
      
      const response = await fetch(`${urls.apiUrl}${config.apiEndpoints.auth.me}`, {
        method: 'GET',
        credentials: 'include', // Important for SSO cookies
        headers: {
          'Accept': 'application/json',
        }
      });

      if (response.ok) {
        const userData = await response.json();
        
        // Convert backend user format to our Authentik format
        return {
          username: userData.username,
          email: userData.email,
          name: userData.full_name || userData.username,
          uid: userData.id || userData.username,
          groups: userData.role === 'admin' ? ['admin', 'Meeting-Ops-Admins'] : ['Meeting-Ops-Users'],
          is_admin: userData.is_superuser || userData.role === 'admin',
          is_active: userData.is_active,
          authenticated_at: new Date().toISOString()
        };
      }

      // Check for Authentik headers directly (fallback for direct header access)
      const headers = ['X-authentik-username', 'X-authentik-email', 'X-authentik-name', 'X-authentik-uid', 'X-authentik-groups'];
      const hasHeaders = headers.some(header => {
        // Check meta tags (might be set by server-side rendering)
        const meta = document.querySelector(`meta[name="${header}"]`);
        return meta && meta.getAttribute('content');
      });

      if (hasHeaders) {
        const username = document.querySelector('meta[name="X-authentik-username"]')?.getAttribute('content') || '';
        const email = document.querySelector('meta[name="X-authentik-email"]')?.getAttribute('content') || '';
        const name = document.querySelector('meta[name="X-authentik-name"]')?.getAttribute('content') || username;
        const uid = document.querySelector('meta[name="X-authentik-uid"]')?.getAttribute('content') || username;
        const groupsStr = document.querySelector('meta[name="X-authentik-groups"]')?.getAttribute('content') || '';
        const groups = groupsStr ? groupsStr.split(',').map(g => g.trim()) : ['Meeting-Ops-Users'];

        if (username && email) {
          return {
            username,
            email,
            name,
            uid,
            groups,
            is_admin: groups.includes('admin') || groups.includes('Meeting-Ops-Admins'),
            is_active: true,
            authenticated_at: new Date().toISOString()
          };
        }
      }

      return null;
    } catch (err) {
      console.error('Failed to extract user from headers:', err);
      return null;
    }
  };

  // Check user authentication status
  const checkUserStatus = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const userData = await extractUserFromHeaders();
      setUser(userData);
    } catch (err) {
      console.error('Failed to check user status:', err);
      setError(err instanceof Error ? err.message : 'Authentication check failed');
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  // Initialize authentication on mount
  useEffect(() => {
    checkUserStatus();
  }, []);

  // Login - redirect to Authentik
  const login = () => {
    const urls = getAuthUrls();
    const currentUrl = window.location.href;
    window.location.href = `${urls.loginUrl}&next=${encodeURIComponent(currentUrl)}`;
  };

  // Logout - redirect to Authentik logout
  const logout = () => {
    const urls = getAuthUrls();
    setUser(null);
    setError(null);
    window.location.href = urls.logoutUrl;
  };

  // Set up API request interceptor for authentication
  useEffect(() => {
    const originalFetch = window.fetch;
    
    window.fetch = async (url: RequestInfo | URL, init?: RequestInit) => {
      // For API requests, ensure credentials are included for SSO cookies
      if (typeof url === 'string' && (url.startsWith('/api/') || url.includes('api.'))) {
        init = init || {};
        init.credentials = 'include'; // Important for SSO session cookies
        
        // Add content type for JSON requests
        if (init.method && ['POST', 'PUT', 'PATCH'].includes(init.method.toUpperCase())) {
          init.headers = {
            'Content-Type': 'application/json',
            ...init.headers,
          };
        }
      }

      const response = await originalFetch(url, init);

      // Handle 401 responses - redirect to login
      if (response.status === 401 && typeof url === 'string' && !url.includes('/auth/')) {
        console.warn('Received 401 response, redirecting to login');
        login();
        return response;
      }

      return response;
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  return (
    <AuthentikAuthContext.Provider
      value={{
        user,
        login,
        logout,
        isAuthenticated: !!user,
        isLoading,
        error,
        checkUserStatus,
      }}
    >
      {children}
    </AuthentikAuthContext.Provider>
  );
};