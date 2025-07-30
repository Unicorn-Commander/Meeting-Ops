import { useState, useEffect, useCallback, useMemo } from 'react';

interface VirtualizationOptions {
  itemHeight: number;
  containerHeight: number;
  overscan?: number; // Number of items to render outside viewport
  scrollThreshold?: number; // Threshold for scroll-based updates
}

export function useVirtualization<T>(
  items: T[],
  options: VirtualizationOptions
) {
  const { itemHeight, containerHeight, overscan = 5, scrollThreshold = 100 } = options;
  
  const [scrollTop, setScrollTop] = useState(0);
  const [isScrolling, setIsScrolling] = useState(false);

  // Calculate visible range
  const visibleRange = useMemo(() => {
    const itemsInView = Math.ceil(containerHeight / itemHeight);
    const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    const endIndex = Math.min(
      items.length - 1,
      startIndex + itemsInView + overscan * 2
    );

    return { startIndex, endIndex, itemsInView };
  }, [scrollTop, itemHeight, containerHeight, items.length, overscan]);

  // Get visible items
  const visibleItems = useMemo(() => {
    return items.slice(visibleRange.startIndex, visibleRange.endIndex + 1);
  }, [items, visibleRange.startIndex, visibleRange.endIndex]);

  // Calculate scroll measurements
  const measurements = useMemo(() => {
    const totalHeight = items.length * itemHeight;
    const offsetY = visibleRange.startIndex * itemHeight;

    return {
      totalHeight,
      offsetY,
      visibleHeight: containerHeight
    };
  }, [items.length, itemHeight, visibleRange.startIndex, containerHeight]);

  // Throttled scroll handler
  const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const newScrollTop = event.currentTarget.scrollTop;
    
    // Only update if scroll change is significant
    if (Math.abs(newScrollTop - scrollTop) > scrollThreshold) {
      setScrollTop(newScrollTop);
    }

    // Set scrolling state
    if (!isScrolling) {
      setIsScrolling(true);
    }

    // Clear scrolling state after scroll ends
    const timeoutId = setTimeout(() => {
      setIsScrolling(false);
    }, 150);

    return () => clearTimeout(timeoutId);
  }, [scrollTop, scrollThreshold, isScrolling]);

  return {
    visibleItems,
    visibleRange,
    measurements,
    isScrolling,
    handleScroll,
    // Helper function to get item style
    getItemStyle: (index: number) => ({
      position: 'absolute' as const,
      top: (visibleRange.startIndex + index) * itemHeight,
      left: 0,
      right: 0,
      height: itemHeight
    })
  };
}

// Hook for performance monitoring
export function usePerformanceMonitor() {
  const [metrics, setMetrics] = useState({
    renderTime: 0,
    memoryUsage: 0,
    fps: 0
  });

  const measureRender = useCallback(<T extends any[], R>(
    renderFunction: (...args: T) => R,
    ...args: T
  ): R => {
    const startTime = performance.now();
    const result = renderFunction(...args);
    const endTime = performance.now();
    
    setMetrics(prev => ({
      ...prev,
      renderTime: endTime - startTime
    }));

    return result;
  }, []);

  // Monitor memory usage (when available)
  useEffect(() => {
    const updateMemoryUsage = () => {
      if ('memory' in performance) {
        const memory = (performance as any).memory;
        setMetrics(prev => ({
          ...prev,
          memoryUsage: memory.usedJSHeapSize / memory.jsHeapSizeLimit
        }));
      }
    };

    const interval = setInterval(updateMemoryUsage, 5000);
    return () => clearInterval(interval);
  }, []);

  // Monitor FPS
  useEffect(() => {
    let frameCount = 0;
    let lastTime = Date.now();
    
    const countFPS = () => {
      frameCount++;
      const currentTime = Date.now();
      
      if (currentTime - lastTime >= 1000) {
        setMetrics(prev => ({
          ...prev,
          fps: Math.round((frameCount * 1000) / (currentTime - lastTime))
        }));
        
        frameCount = 0;
        lastTime = currentTime;
      }
      
      requestAnimationFrame(countFPS);
    };

    const animationId = requestAnimationFrame(countFPS);
    return () => cancelAnimationFrame(animationId);
  }, []);

  return { metrics, measureRender };
}