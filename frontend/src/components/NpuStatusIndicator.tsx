import React, { useState, useEffect } from 'react';
import { Zap, Cpu, Activity, CheckCircle, AlertCircle, Loader2, Info } from 'lucide-react';

interface NpuStatus {
  available: boolean;
  device: string;
  usage_percent: number;
  model: string;
  tops: number;
  status: string;
  hardware_mode: boolean;
  aie_version: string;
}

interface TranscriberStatus {
  ready: boolean;
  model: string;
  optimization: string;
  backend: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const NpuStatusIndicator: React.FC = () => {
  const [npuStatus, setNpuStatus] = useState<NpuStatus | null>(null);
  const [transcriberStatus, setTranscriberStatus] = useState<TranscriberStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchNpuStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setError('Authentication required');
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/system/npu-status`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setNpuStatus(data.npu);
      setTranscriberStatus(data.transcriber);
      setError(null);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch NPU status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNpuStatus();
    const interval = setInterval(fetchNpuStatus, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-purple-400 animate-spin" />
          <span className="ml-2 text-gray-400">Loading NPU status...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg border border-red-800 p-6">
        <div className="flex items-center gap-3">
          <AlertCircle className="w-6 h-6 text-red-400 flex-shrink-0" />
          <div>
            <h3 className="text-red-400 font-semibold">NPU Status Error</h3>
            <p className="text-gray-400 text-sm">{error}</p>
            <button
              onClick={fetchNpuStatus}
              className="mt-2 text-xs text-purple-400 hover:text-purple-300 underline"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!npuStatus || !transcriberStatus) {
    return (
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <div className="text-center text-gray-400">
          <Info className="w-6 h-6 mx-auto mb-2" />
          <p>NPU status unavailable</p>
        </div>
      </div>
    );
  }

  const getStatusColor = (status: string, available: boolean) => {
    if (!available) return 'text-red-400';
    switch (status) {
      case 'ready': return 'text-green-400';
      case 'initializing': return 'text-yellow-400';
      case 'error': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status: string, available: boolean) => {
    if (!available) return <AlertCircle className="w-5 h-5" />;
    switch (status) {
      case 'ready': return <CheckCircle className="w-5 h-5" />;
      case 'initializing': return <Loader2 className="w-5 h-5 animate-spin" />;
      case 'error': return <AlertCircle className="w-5 h-5" />;
      default: return <Info className="w-5 h-5" />;
    }
  };

  return (
    <div className="space-y-4">
      {/* NPU Hardware Status */}
      <div className="bg-gradient-to-r from-purple-900/20 to-pink-900/20 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${
              npuStatus.available ? 'bg-green-500/20' : 'bg-red-500/20'
            }`}>
              <Zap className={`w-6 h-6 ${
                npuStatus.available ? 'text-green-400' : 'text-red-400'
              }`} />
            </div>
            <div>
              <h3 className="text-white font-bold">NPU Hardware</h3>
              <p className="text-gray-400 text-sm">{npuStatus.model}</p>
            </div>
          </div>
          
          <div className={`flex items-center gap-2 ${getStatusColor(npuStatus.status, npuStatus.available)}`}>
            {getStatusIcon(npuStatus.status, npuStatus.available)}
            <span className="font-semibold capitalize">{npuStatus.status}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">Performance</p>
            <p className="text-lg font-bold text-purple-400">{npuStatus.tops} TOPS</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">Utilization</p>
            <p className="text-lg font-bold text-blue-400">{npuStatus.usage_percent}%</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">Device</p>
            <p className="text-sm text-gray-300">{npuStatus.device}</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">AIE Version</p>
            <p className="text-sm text-gray-300">v{npuStatus.aie_version}</p>
          </div>
        </div>

        {/* Usage Bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-500">NPU Usage</span>
            <span className="text-xs text-gray-400">{npuStatus.usage_percent}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-500"
              style={{ width: `${npuStatus.usage_percent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Transcriber Status */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${
              transcriberStatus.ready ? 'bg-green-500/20' : 'bg-yellow-500/20'
            }`}>
              <Activity className={`w-6 h-6 ${
                transcriberStatus.ready ? 'text-green-400' : 'text-yellow-400'
              }`} />
            </div>
            <div>
              <h3 className="text-white font-bold">AI Transcriber</h3>
              <p className="text-gray-400 text-sm">{transcriberStatus.backend}</p>
            </div>
          </div>
          
          <div className={`flex items-center gap-2 ${
            transcriberStatus.ready ? 'text-green-400' : 'text-yellow-400'
          }`}>
            {transcriberStatus.ready ? (
              <CheckCircle className="w-5 h-5" />
            ) : (
              <Loader2 className="w-5 h-5 animate-spin" />
            )}
            <span className="font-semibold">
              {transcriberStatus.ready ? 'Ready' : 'Initializing'}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">Model</p>
            <p className="text-sm font-semibold text-cyan-400">{transcriberStatus.model}</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-500 mb-1">Optimization</p>
            <p className="text-sm font-semibold text-green-400">{transcriberStatus.optimization.toUpperCase()}</p>
          </div>
        </div>
        
        {transcriberStatus.ready && (
          <div className="mt-4 flex items-center gap-2 text-xs text-green-400">
            <CheckCircle className="w-3 h-3" />
            <span>Ready for real-time transcription</span>
          </div>
        )}
      </div>

      {/* Performance Indicators */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h4 className="text-white font-semibold mb-3">Performance Metrics</h4>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <p className="text-2xl font-bold text-green-400">220x</p>
            <p className="text-xs text-gray-500">Min Speedup</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-purple-400">&lt;100ms</p>
            <p className="text-xs text-gray-500">Latency</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-400">4.8k</p>
            <p className="text-xs text-gray-500">Tokens/sec</p>
          </div>
        </div>
      </div>

      {/* Last Update */}
      {lastUpdate && (
        <div className="text-center">
          <p className="text-xs text-gray-500">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
};