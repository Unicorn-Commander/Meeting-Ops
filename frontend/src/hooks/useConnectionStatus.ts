import { useState, useEffect, useCallback } from 'react';

interface ConnectionStatus {
  isOnline: boolean;
  isSlowConnection: boolean;
  latency: number | null;
  lastCheck: number;
}

export function useConnectionStatus() {
  const [status, setStatus] = useState<ConnectionStatus>({
    isOnline: navigator.onLine,
    isSlowConnection: false,
    latency: null,
    lastCheck: Date.now()
  });

  const checkConnection = useCallback(async () => {
    const startTime = Date.now();
    
    try {
      // Use a small request to check connectivity and measure latency
      const response = await fetch('/api/health', {
        method: 'GET',
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      
      const endTime = Date.now();
      const latency = endTime - startTime;
      
      setStatus({
        isOnline: response.ok,
        isSlowConnection: latency > 2000, // Consider slow if > 2 seconds
        latency,
        lastCheck: endTime
      });
      
      return { isOnline: response.ok, latency };
    } catch (error) {
      const endTime = Date.now();
      const latency = endTime - startTime;
      
      setStatus({
        isOnline: false,
        isSlowConnection: latency > 2000,
        latency,
        lastCheck: endTime
      });
      
      return { isOnline: false, latency };
    }
  }, []);

  // Listen to browser online/offline events
  useEffect(() => {
    const handleOnline = () => {
      setStatus(prev => ({ ...prev, isOnline: true }));
      checkConnection();
    };

    const handleOffline = () => {
      setStatus(prev => ({
        ...prev,
        isOnline: false,
        latency: null
      }));
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [checkConnection]);

  // Periodic connection check
  useEffect(() => {
    // Initial check
    checkConnection();

    // Check every 30 seconds
    const interval = setInterval(checkConnection, 30000);
    
    return () => clearInterval(interval);
  }, [checkConnection]);

  const getNetworkAdaptations = useCallback(() => {
    const { isOnline, isSlowConnection, latency } = status;
    
    return {
      // Increase timeouts for slow connections
      timeout: isSlowConnection ? 15000 : 5000,
      
      // Reduce polling frequency for slow connections
      pollInterval: isSlowConnection ? 60000 : 30000,
      
      // Disable real-time features if offline
      enableRealtime: isOnline,
      
      // Use different debounce delays based on connection
      debounceDelay: isSlowConnection ? 1000 : 300,
      
      // Retry configuration
      maxRetries: isOnline ? 3 : 1,
      retryDelay: isSlowConnection ? 2000 : 1000,
      
      // UI adaptations
      showOfflineIndicator: !isOnline,
      showSlowConnectionWarning: isSlowConnection,
      
      // Connection quality indicator
      connectionQuality: !isOnline ? 'offline' : 
                        isSlowConnection ? 'slow' : 
                        (latency && latency < 500) ? 'excellent' : 'good'
    };
  }, [status]);

  return {
    ...status,
    checkConnection,
    getNetworkAdaptations
  };
}