import React, { useEffect, useState, useRef } from 'react';
import { Mic } from 'lucide-react';

export const LiveAudioMeter: React.FC = () => {
  const [level, setLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const peakHoldTime = useRef(0);
  const peakDecayRef = useRef<number | null>(null);

  useEffect(() => {
    let reconnectTimeout: NodeJS.Timeout;
    
    const connect = () => {
      try {
        // Direct connection to backend WebSocket
        const ws = new WebSocket('ws://localhost:8000/ws/audio-levels');
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('[LiveAudioMeter] WebSocket connected');
          setIsConnected(true);
          setError(null);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'audio_level') {
              const newLevel = data.level || 0;
              setLevel(newLevel);
              
              // Update peak
              if (newLevel > peak) {
                setPeak(newLevel);
                peakHoldTime.current = Date.now();
              }
            }
          } catch (e) {
            console.error('[LiveAudioMeter] Error parsing message:', e);
          }
        };

        ws.onerror = (error) => {
          console.error('[LiveAudioMeter] WebSocket error:', error);
          setError('Connection error');
          setIsConnected(false);
        };

        ws.onclose = () => {
          console.log('[LiveAudioMeter] WebSocket closed');
          setIsConnected(false);
          // Reconnect after 3 seconds
          reconnectTimeout = setTimeout(connect, 3000);
        };

      } catch (err) {
        console.error('[LiveAudioMeter] Failed to connect:', err);
        setError('Failed to connect');
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };

    connect();

    // Peak decay animation
    const animatePeakDecay = () => {
      const now = Date.now();
      const holdDuration = 1000; // Hold peak for 1 second
      const decayRate = 0.02;
      
      if (now - peakHoldTime.current > holdDuration && peak > level) {
        setPeak(prev => Math.max(level, prev - decayRate));
      }
      
      peakDecayRef.current = requestAnimationFrame(animatePeakDecay);
    };
    
    peakDecayRef.current = requestAnimationFrame(animatePeakDecay);

    return () => {
      clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (peakDecayRef.current) {
        cancelAnimationFrame(peakDecayRef.current);
      }
    };
  }, [peak, level]);

  // Convert level (0-1) to percentage
  const levelPercent = Math.min(100, level * 100);
  const peakPercent = Math.min(100, peak * 100);

  // Color based on level
  const getColor = (value: number) => {
    if (value > 0.8) return 'bg-red-500';
    if (value > 0.6) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  // Show peak indicator
  const showPeak = true;

  return (
    <div className="fixed top-20 right-6 bg-gray-900 border border-gray-700 rounded-lg p-4 shadow-lg">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-full ${isConnected ? 'bg-green-900' : 'bg-red-900'}`}>
          <Mic className={`w-5 h-5 ${isConnected ? 'text-green-400' : 'text-red-400'}`} />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Live Audio Input</h3>
          <p className="text-xs text-gray-400">
            {isConnected ? 'Monitoring microphone' : error || 'Connecting...'}
          </p>
        </div>
      </div>

      {/* Level meter */}
      <div className="w-64">
        <div className="relative h-8 bg-gray-800 rounded-lg overflow-hidden">
          {/* Background grid */}
          <div className="absolute inset-0 opacity-20">
            {[...Array(10)].map((_, i) => (
              <div
                key={i}
                className="absolute top-0 bottom-0 w-px bg-gray-600"
                style={{ left: `${i * 10}%` }}
              />
            ))}
          </div>

          {/* Level bar */}
          <div
            className={`absolute top-0 left-0 h-full transition-all duration-50 ${getColor(level)}`}
            style={{ width: `${levelPercent}%` }}
          />

          {/* Peak indicator */}
          {showPeak && peakPercent > 0 && (
            <div
              className="absolute top-0 w-1 h-full bg-white opacity-75"
              style={{ left: `${peakPercent}%` }}
            />
          )}

          {/* dB scale labels */}
          <div className="absolute inset-0 flex items-center justify-between px-1">
            <span className="text-xs text-gray-400">-60</span>
            <span className="text-xs text-gray-400">0 dB</span>
          </div>
        </div>

        {/* Level indicators */}
        <div className="flex gap-1 mt-2">
          {[...Array(20)].map((_, i) => {
            const threshold = i / 20;
            const active = level >= threshold;
            let color = 'bg-gray-700';
            if (active) {
              if (threshold > 0.8) color = 'bg-red-500';
              else if (threshold > 0.6) color = 'bg-yellow-500';
              else color = 'bg-green-500';
            }
            return (
              <div
                key={i}
                className={`flex-1 h-2 rounded-sm transition-colors ${color}`}
              />
            );
          })}
        </div>
      </div>

      {/* Debug info */}
      {!isConnected && (
        <div className="mt-3 text-xs text-gray-500">
          <p>Trying to connect to WebSocket...</p>
          <p className="font-mono">ws://localhost:9050/ws/audio-levels</p>
        </div>
      )}
    </div>
  );
};