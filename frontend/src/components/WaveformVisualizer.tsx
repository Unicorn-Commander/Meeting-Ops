import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Volume2, VolumeX, Activity, Zap } from 'lucide-react';

interface WaveformVisualizerProps {
  className?: string;
  showControls?: boolean;
  animate?: boolean;
}

interface AudioData {
  level: number;
  peak: number;
  timestamp: number;
  mic_active: boolean;
  quality: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const WaveformVisualizer: React.FC<WaveformVisualizerProps> = ({
  className = '',
  showControls = true,
  animate = true
}) => {
  const [audioData, setAudioData] = useState<AudioData[]>([]);
  const [currentLevel, setCurrentLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const [quality, setQuality] = useState<'excellent' | 'good' | 'low'>('good');
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const animationFrameRef = useRef<number>(0);
  const dataBufferRef = useRef<number[]>([]);
  
  const MAX_BUFFER_SIZE = 128; // Keep last 128 samples for waveform

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/ws/audio-levels`;
    console.log('[Waveform] Connecting to:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Waveform] Connected to audio levels WebSocket');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'audio_level' && data.data) {
          const audioLevel = data.data as AudioData;
          
          setCurrentLevel(audioLevel.level);
          setPeak(audioLevel.peak);
          setMicActive(audioLevel.mic_active);
          setQuality(audioLevel.quality);
          
          // Add to buffer for waveform
          dataBufferRef.current.push(audioLevel.level);
          if (dataBufferRef.current.length > MAX_BUFFER_SIZE) {
            dataBufferRef.current.shift();
          }
          
          // Update audio data array
          setAudioData(prev => {
            const newData = [...prev, audioLevel];
            return newData.slice(-50); // Keep last 50 data points
          });
        }
      } catch (err) {
        console.error('[Waveform] Parse error:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('[Waveform] WebSocket error:', error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('[Waveform] WebSocket closed');
      setIsConnected(false);
      
      // Auto-reconnect after 3 seconds
      setTimeout(connectWebSocket, 3000);
    };
  }, []);

  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvas;
    const buffer = dataBufferRef.current;
    
    // Clear canvas
    ctx.fillStyle = '#111827'; // bg-gray-900
    ctx.fillRect(0, 0, width, height);
    
    if (buffer.length < 2) {
      // Show idle state
      ctx.strokeStyle = '#374151'; // gray-700
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
      return;
    }

    // Draw waveform
    const stepX = width / (MAX_BUFFER_SIZE - 1);
    
    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    if (quality === 'excellent') {
      gradient.addColorStop(0, '#10b981'); // green-500
      gradient.addColorStop(1, '#059669'); // green-600
    } else if (quality === 'good') {
      gradient.addColorStop(0, '#8b5cf6'); // purple-500
      gradient.addColorStop(1, '#7c3aed'); // purple-600
    } else {
      gradient.addColorStop(0, '#f59e0b'); // yellow-500
      gradient.addColorStop(1, '#d97706'); // yellow-600
    }

    // Draw filled waveform
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(0, height);
    
    for (let i = 0; i < buffer.length; i++) {
      const x = i * stepX;
      const normalizedLevel = Math.min(buffer[i] / 100, 1);
      const y = height - (normalizedLevel * height);
      
      if (i === 0) {
        ctx.lineTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    
    ctx.lineTo(width, height);
    ctx.closePath();
    ctx.fill();

    // Draw peak line
    ctx.strokeStyle = '#ec4899'; // pink-500
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    const peakY = height - ((peak / 100) * height);
    ctx.beginPath();
    ctx.moveTo(0, peakY);
    ctx.lineTo(width, peakY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw current level indicator (moving line)
    if (animate && micActive) {
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.8;
      const currentX = ((Date.now() / 50) % width);
      ctx.beginPath();
      ctx.moveTo(currentX, 0);
      ctx.lineTo(currentX, height);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }, [peak, quality, animate, micActive]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [connectWebSocket]);

  useEffect(() => {
    if (animate) {
      const animateWaveform = () => {
        drawWaveform();
        animationFrameRef.current = requestAnimationFrame(animateWaveform);
      };
      animateWaveform();
      
      return () => {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
      };
    } else {
      drawWaveform();
    }
  }, [animate, drawWaveform]);

  const getQualityColor = () => {
    switch (quality) {
      case 'excellent': return 'text-green-400';
      case 'good': return 'text-blue-400';
      case 'low': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getQualityBg = () => {
    switch (quality) {
      case 'excellent': return 'bg-green-500/20';
      case 'good': return 'bg-blue-500/20';
      case 'low': return 'bg-yellow-500/20';
      default: return 'bg-gray-500/20';
    }
  };

  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-800 p-4 ${className}`}>
      {showControls && (
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${micActive ? 'bg-green-500/20' : 'bg-gray-500/20'}`}>
              {micActive ? (
                <Volume2 className={`w-5 h-5 ${micActive ? 'text-green-400' : 'text-gray-400'}`} />
              ) : (
                <VolumeX className="w-5 h-5 text-gray-400" />
              )}
            </div>
            <div>
              <h3 className="text-white font-semibold">Audio Waveform</h3>
              <div className="flex items-center gap-2 text-xs">
                <span className={`flex items-center gap-1 ${
                  isConnected ? 'text-green-400' : 'text-red-400'
                }`}>
                  <Activity className="w-3 h-3" />
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
                <span className={`px-2 py-0.5 rounded ${getQualityBg()} ${getQualityColor()}`}>
                  {quality}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-gray-500">Current</p>
              <p className={`text-lg font-bold ${getQualityColor()}`}>
                {currentLevel.toFixed(0)}%
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500">Peak</p>
              <p className="text-lg font-bold text-pink-400">
                {peak.toFixed(0)}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Waveform Canvas */}
      <div className="relative bg-gray-800 rounded-lg overflow-hidden" style={{ height: '200px' }}>
        <canvas
          ref={canvasRef}
          width={800}
          height={200}
          className="w-full h-full"
          style={{ imageRendering: 'crisp-edges' }}
        />
        
        {!isConnected && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-800/90">
            <div className="text-center">
              <Activity className="w-8 h-8 text-gray-500 mx-auto mb-2" />
              <p className="text-gray-400 text-sm">Connecting to audio stream...</p>
            </div>
          </div>
        )}
      </div>

      {/* Level Meters */}
      <div className="mt-4 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 w-16">Level</span>
          <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-100 ${
                quality === 'excellent' ? 'bg-gradient-to-r from-green-500 to-green-400' :
                quality === 'good' ? 'bg-gradient-to-r from-purple-500 to-blue-400' :
                'bg-gradient-to-r from-yellow-500 to-orange-400'
              }`}
              style={{ width: `${currentLevel}%` }}
            />
          </div>
          <span className="text-xs text-gray-400 w-10 text-right">
            {currentLevel.toFixed(0)}%
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 w-16">Peak</span>
          <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-pink-500 to-red-400 transition-all duration-300"
              style={{ width: `${peak}%` }}
            />
          </div>
          <span className="text-xs text-gray-400 w-10 text-right">
            {peak.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* NPU Processing Indicator */}
      {micActive && (
        <div className="mt-3 flex items-center gap-2 text-xs text-purple-400">
          <Zap className="w-3 h-3" />
          <span>NPU processing audio at 16 TOPS</span>
        </div>
      )}
    </div>
  );
};