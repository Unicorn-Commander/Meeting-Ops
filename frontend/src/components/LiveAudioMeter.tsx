import React, { useEffect, useState, useRef } from 'react';
import { Volume2, VolumeX, Activity, Mic } from 'lucide-react';

export const LiveAudioMeter: React.FC = () => {
  const [level, setLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [db, setDb] = useState(-60);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const peakDecayTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const connect = () => {
      try {
        // Use relative URL for better proxy support
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//localhost:1950/ws/audio-levels`;
        
        console.log('Connecting to audio levels WebSocket:', wsUrl);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('Audio levels WebSocket connected');
          setIsConnected(true);
          setError(null);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'audio_level') {
              const newLevel = data.level || 0;
              const newDb = data.db || -60;
              
              setLevel(newLevel);
              setDb(newDb);
              
              // Update peak with decay
              if (newLevel > peak) {
                setPeak(newLevel);
                // Clear existing decay timeout
                if (peakDecayTimeoutRef.current) {
                  clearTimeout(peakDecayTimeoutRef.current);
                }
                // Start peak decay after 1 second
                peakDecayTimeoutRef.current = setTimeout(() => {
                  setPeak(0);
                }, 1000);
              }
            } else if (data.type === 'error') {
              setError(data.message);
            }
          } catch (e) {
            console.error('Error parsing audio level data:', e);
          }
        };

        ws.onerror = (error) => {
          console.error('Audio levels WebSocket error:', error);
          setError('Connection error');
        };

        ws.onclose = () => {
          console.log('Audio levels WebSocket disconnected');
          setIsConnected(false);
          wsRef.current = null;
          
          // Reconnect after 2 seconds
          reconnectTimeoutRef.current = setTimeout(connect, 2000);
        };
      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        setError('Failed to connect');
        // Retry connection
        reconnectTimeoutRef.current = setTimeout(connect, 2000);
      }
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (peakDecayTimeoutRef.current) {
        clearTimeout(peakDecayTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Convert level (0-1) to percentage
  const levelPercent = Math.min(100, level * 100);
  const peakPercent = Math.min(100, peak * 100);

  // Color based on level
  const getColor = (value: number) => {
    if (value > 0.8) return 'bg-red-500';
    if (value > 0.6) return 'bg-yellow-500';
    return 'bg-green-500';
  };

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
        </div>

        {/* dB readout */}
        <div className="flex justify-between items-center mt-2">
          <div className="text-xs text-gray-400">
            {isConnected ? (
              <>
                <span className="font-mono">{db.toFixed(1)} dB</span>
                <span className="ml-2">({(levelPercent).toFixed(0)}%)</span>
              </>
            ) : (
              <span>--.- dB</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Activity className="w-3 h-3 text-gray-400" />
            {level > 0.01 ? (
              <Volume2 className="w-3 h-3 text-green-400" />
            ) : (
              <VolumeX className="w-3 h-3 text-gray-600" />
            )}
          </div>
        </div>

        {/* Level indicators */}
        <div className="flex gap-1 mt-2">
          {[...Array(20)].map((_, i) => {
            const threshold = i / 20;
            const active = level > threshold;
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
          <p className="font-mono">ws://localhost:1950/ws/audio-levels</p>
        </div>
      )}
    </div>
  );
};

// Show peak indicator
const showPeak = true;