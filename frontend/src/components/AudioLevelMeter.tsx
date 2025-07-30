import React, { useEffect, useState, useRef } from 'react';
import { Volume2, VolumeX, Activity } from 'lucide-react';

interface AudioLevelMeterProps {
  wsUrl?: string;
  height?: number;
  showDb?: boolean;
  showPeak?: boolean;
  orientation?: 'horizontal' | 'vertical';
}

const WS_BASE_URL = (import.meta.env.VITE_API_URL || 'ws://localhost:1950').replace('http', 'ws');

export const AudioLevelMeter: React.FC<AudioLevelMeterProps> = ({
  wsUrl = `${WS_BASE_URL}/ws/audio-levels`,
  height = 20,
  showDb = true,
  showPeak = true,
  orientation = 'horizontal'
}) => {
  const [level, setLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [db, setDb] = useState(-60);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const peakDecayRef = useRef<number | null>(null);
  const peakHoldTime = useRef(0);

  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          setError(null);
        };

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          
          if (data.type === 'audio_level') {
            setLevel(data.level || 0);
            setDb(data.db || -60);
            
            // Peak hold logic
            if (data.peak > peak) {
              setPeak(data.peak);
              peakHoldTime.current = Date.now();
            }
          } else if (data.type === 'error') {
            setError(data.message);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          setError('Connection error');
        };

        ws.onclose = () => {
          setIsConnected(false);
          // Reconnect after 3 seconds
          setTimeout(connect, 3000);
        };

      } catch (err) {
        console.error('Failed to connect:', err);
        setError('Failed to connect');
      }
    };

    connect();

    // Peak decay animation
    const animatePeakDecay = () => {
      const now = Date.now();
      const holdDuration = 1000; // Hold peak for 1 second
      const decayRate = 0.05;
      
      if (now - peakHoldTime.current > holdDuration && peak > level) {
        setPeak(prev => Math.max(level, prev - decayRate));
      }
      
      peakDecayRef.current = requestAnimationFrame(animatePeakDecay);
    };
    
    peakDecayRef.current = requestAnimationFrame(animatePeakDecay);

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (peakDecayRef.current) {
        cancelAnimationFrame(peakDecayRef.current);
      }
    };
  }, [wsUrl]);

  // Calculate colors based on level
  const getColor = (value: number) => {
    if (value > 0.9) return '#ef4444'; // Red - clipping
    if (value > 0.7) return '#f59e0b'; // Amber - high
    if (value > 0.3) return '#10b981'; // Green - normal
    return '#6b7280'; // Gray - low
  };

  const levelPercent = Math.min(100, level * 100);
  const peakPercent = Math.min(100, peak * 100);
  const levelColor = getColor(level);

  if (orientation === 'vertical') {
    return (
      <div className="flex flex-col items-center space-y-2">
        <div className="relative w-8 h-48 bg-gray-800 rounded-full overflow-hidden">
          <div 
            className="absolute bottom-0 w-full transition-all duration-100 ease-out"
            style={{
              height: `${levelPercent}%`,
              backgroundColor: levelColor
            }}
          />
          {showPeak && (
            <div 
              className="absolute w-full h-1 bg-white opacity-75"
              style={{ bottom: `${peakPercent}%` }}
            />
          )}
        </div>
        {showDb && (
          <div className="text-xs text-gray-500 font-mono">
            {db.toFixed(1)} dB
          </div>
        )}
        <div className="text-xs text-gray-500">
          {isConnected ? (
            <Volume2 className="w-4 h-4 text-green-500" />
          ) : (
            <VolumeX className="w-4 h-4 text-red-500" />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center space-x-2">
        <div className={`relative flex-1 bg-gray-200 rounded-full overflow-hidden`} style={{ height }}>
          {/* Level bar */}
          <div 
            className="absolute left-0 top-0 h-full transition-all duration-100 ease-out"
            style={{
              width: `${levelPercent}%`,
              backgroundColor: levelColor
            }}
          />
          
          {/* Peak indicator */}
          {showPeak && (
            <div 
              className="absolute top-0 w-1 h-full bg-gray-600"
              style={{ left: `${peakPercent}%` }}
            />
          )}
          
          {/* Scale marks */}
          <div className="absolute inset-0 flex items-center">
            {[0, -6, -12, -18, -24, -30, -40, -50].map((dbMark) => {
              const percent = Math.pow(10, dbMark / 20) * 100;
              return (
                <div
                  key={dbMark}
                  className="absolute w-px h-full bg-gray-400 opacity-50"
                  style={{ left: `${percent}%` }}
                />
              );
            })}
          </div>
        </div>
        
        {/* Status indicator */}
        <div className="flex items-center space-x-1">
          {isConnected ? (
            <Activity className="w-4 h-4 text-green-500" />
          ) : (
            <VolumeX className="w-4 h-4 text-red-500" />
          )}
        </div>
      </div>
      
      {showDb && (
        <div className="flex justify-between text-xs text-gray-500">
          <span className="font-mono">{db.toFixed(1)} dB</span>
          <span>{error || (isConnected ? 'Connected' : 'Connecting...')}</span>
        </div>
      )}
    </div>
  );
};

// Spectrum Analyzer Component
export const SpectrumAnalyzer: React.FC<{ wsUrl?: string }> = ({ 
  wsUrl = 'ws://localhost:9050/ws/audio-spectrum' 
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [spectrum] = useState<number[]>([]);
  
  useEffect(() => {
    if (!canvasRef.current) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Set canvas size
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    
    // Draw spectrum
    const draw = () => {
      ctx.fillStyle = '#1f2937';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      if (spectrum.length === 0) return;
      
      const barWidth = canvas.width / spectrum.length;
      const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
      gradient.addColorStop(0, '#10b981');
      gradient.addColorStop(0.5, '#f59e0b');
      gradient.addColorStop(1, '#ef4444');
      
      spectrum.forEach((value, index) => {
        const barHeight = value * canvas.height;
        const x = index * barWidth;
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
      });
    };
    
    draw();
  }, [spectrum]);
  
  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <h3 className="text-sm font-medium text-gray-300 mb-2">Frequency Spectrum</h3>
      <canvas
        ref={canvasRef}
        className="w-full h-32 rounded"
      />
    </div>
  );
};