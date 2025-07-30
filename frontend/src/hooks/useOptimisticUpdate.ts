import { useState, useCallback, useRef } from 'react';

interface OptimisticUpdate<T> {
  id: string;
  optimisticData: T;
  rollback: () => void;
  timestamp: number;
}

export function useOptimisticUpdate<T>(initialData: T) {
  const [data, setData] = useState<T>(initialData);
  const [isOptimistic, setIsOptimistic] = useState(false);
  const pendingUpdatesRef = useRef<Map<string, OptimisticUpdate<T>>>(new Map());
  const rollbackDataRef = useRef<T>(initialData);

  const applyOptimisticUpdate = useCallback((
    id: string,
    optimisticData: T,
    asyncOperation: () => Promise<T>
  ) => {
    // Store the current data for potential rollback
    const currentData = data;
    rollbackDataRef.current = currentData;

    // Apply optimistic update immediately
    setData(optimisticData);
    setIsOptimistic(true);

    const rollback = () => {
      setData(rollbackDataRef.current);
      setIsOptimistic(false);
      pendingUpdatesRef.current.delete(id);
    };

    // Store the update info
    pendingUpdatesRef.current.set(id, {
      id,
      optimisticData,
      rollback,
      timestamp: Date.now()
    });

    // Execute the async operation
    return asyncOperation()
      .then((result) => {
        // Success: apply the real data
        setData(result);
        setIsOptimistic(false);
        pendingUpdatesRef.current.delete(id);
        return result;
      })
      .catch((error) => {
        // Failure: rollback to previous state
        rollback();
        throw error;
      });
  }, [data]);

  const rollbackUpdate = useCallback((id: string) => {
    const update = pendingUpdatesRef.current.get(id);
    if (update) {
      update.rollback();
    }
  }, []);

  const rollbackAllUpdates = useCallback(() => {
    pendingUpdatesRef.current.forEach(update => update.rollback());
    pendingUpdatesRef.current.clear();
  }, []);

  const hasPendingUpdates = useCallback(() => {
    return pendingUpdatesRef.current.size > 0;
  }, []);

  const updateData = useCallback((newData: T) => {
    setData(newData);
    setIsOptimistic(false);
    rollbackDataRef.current = newData;
  }, []);

  return {
    data,
    isOptimistic,
    applyOptimisticUpdate,
    rollbackUpdate,
    rollbackAllUpdates,
    hasPendingUpdates,
    updateData
  };
}