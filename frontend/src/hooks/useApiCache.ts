import { useState, useEffect, useCallback, useRef } from 'react';

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  expiry: number;
}

interface UseApiCacheOptions {
  cacheDuration?: number; // milliseconds
  refetchInterval?: number; // milliseconds
  retryCount?: number;
  retryDelay?: number;
}

export function useApiCache<T>(
  key: string,
  fetcher: () => Promise<T>,
  options: UseApiCacheOptions = {}
) {
  const {
    cacheDuration = 30000, // 30 seconds default
    refetchInterval = 0, // no auto-refetch by default
    retryCount = 3,
    retryDelay = 1000
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(0);
  
  const cacheRef = useRef<Map<string, CacheEntry<T>>>(new Map());
  const abortControllerRef = useRef<AbortController | null>(null);
  const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const isExpired = useCallback((entry: CacheEntry<T>) => {
    return Date.now() > entry.timestamp + entry.expiry;
  }, []);

  const getCachedData = useCallback(() => {
    const entry = cacheRef.current.get(key);
    if (entry && !isExpired(entry)) {
      return entry.data;
    }
    return null;
  }, [key, isExpired]);

  const setCachedData = useCallback((newData: T) => {
    cacheRef.current.set(key, {
      data: newData,
      timestamp: Date.now(),
      expiry: cacheDuration
    });
  }, [key, cacheDuration]);

  const fetchWithRetry = useCallback(async (attempt = 1): Promise<T> => {
    try {
      // Cancel previous request if still pending
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      abortControllerRef.current = new AbortController();
      const result = await fetcher();
      
      return result;
    } catch (err) {
      if (attempt < retryCount && (err as Error).name !== 'AbortError') {
        // Wait before retrying
        await new Promise(resolve => {
          retryTimeoutRef.current = setTimeout(resolve, retryDelay * attempt);
        });
        return fetchWithRetry(attempt + 1);
      }
      throw err;
    }
  }, [fetcher, retryCount, retryDelay]);

  const fetchData = useCallback(async (forceRefresh = false) => {
    // Check cache first
    if (!forceRefresh) {
      const cached = getCachedData();
      if (cached) {
        setData(cached);
        return cached;
      }
    }

    // Avoid duplicate requests
    if (loading) return;

    setLoading(true);
    setError(null);

    try {
      const result = await fetchWithRetry();
      setCachedData(result);
      setData(result);
      setLastFetch(Date.now());
      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Fetch failed');
      setError(error);
      
      // On error, try to use stale cache data if available
      const staleData = cacheRef.current.get(key)?.data;
      if (staleData) {
        setData(staleData);
      }
      
      throw error;
    } finally {
      setLoading(false);
    }
  }, [getCachedData, loading, fetchWithRetry, setCachedData, key]);

  const refresh = useCallback(() => {
    return fetchData(true);
  }, [fetchData]);

  const clearCache = useCallback(() => {
    cacheRef.current.delete(key);
  }, [key]);

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, [key]); // Only depend on key, not fetchData to avoid infinite loops

  // Auto-refetch interval
  useEffect(() => {
    if (refetchInterval > 0) {
      const interval = setInterval(() => {
        fetchData();
      }, refetchInterval);
      
      return () => clearInterval(interval);
    }
  }, [refetchInterval, fetchData]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, []);

  return {
    data,
    loading,
    error,
    refresh,
    clearCache,
    lastFetch,
    isStale: lastFetch > 0 && Date.now() - lastFetch > cacheDuration
  };
}