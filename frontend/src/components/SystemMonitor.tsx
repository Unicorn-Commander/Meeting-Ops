import React, { useState, useEffect } from 'react';
import {
  Cpu,
  HardDrive,
  Activity,
  Zap,
  Server,
  Thermometer,
  Clock,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Minus
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface SystemInfo {
  cpu: {
    usage_percent: number;
    cores: number;
    frequency_mhz: number;
    temperature?: number;
  };
  memory: {
    total_gb: number;
    used_gb: number;
    available_gb: number;
    percent: number;
  };
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    percent: number;
  };
  npu?: {
    available: boolean;
    status: string;
    device?: string;
    aie_version?: string;
    hardware_mode?: boolean;
    utilization?: number;
    memory_used_mb?: number;
    power_watts?: number;
    temperature?: number;
    performance?: {
      real_time_factor?: number;
      tokens_per_second?: number;
      processing_speed?: string;
    };
  };
  gpu?: {
    name: string;
    memory_total_mb: number;
    memory_used_mb: number;
    utilization: number;
    temperature?: number;
  };
  network: {
    bytes_sent: number;
    bytes_recv: number;
    packets_sent: number;
    packets_recv: number;
  };
  processes: {
    total: number;
    running: number;
    sleeping: number;
  };
  uptime_seconds: number;
  load_average: number[];
}

export const SystemMonitor: React.FC = () => {
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(5000); // 5 seconds
  const [history, setHistory] = useState<{
    cpu: number[];
    memory: number[];
    timestamp: number[];
  }>({
    cpu: [],
    memory: [],
    timestamp: []
  });

  useEffect(() => {
    fetchSystemInfo();
    
    if (autoRefresh) {
      const interval = setInterval(fetchSystemInfo, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval]);

  const fetchSystemInfo = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/system-info`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setSystemInfo(data);
        
        // Update history (keep last 20 data points)
        setHistory(prev => ({
          cpu: [...prev.cpu.slice(-19), data.cpu.usage_percent],
          memory: [...prev.memory.slice(-19), data.memory.percent],
          timestamp: [...prev.timestamp.slice(-19), Date.now()]
        }));
        
        setError(null);
      } else {
        setError('Failed to fetch system info');
      }
    } catch (err) {
      setError('Error connecting to server');
      console.error('Error fetching system info:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    const gb = bytes / (1024 * 1024 * 1024);
    return gb.toFixed(2) + ' GB';
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) {
      return `${days}d ${hours}h ${mins}m`;
    } else if (hours > 0) {
      return `${hours}h ${mins}m`;
    } else {
      return `${mins}m`;
    }
  };

  const getUsageColor = (percent: number): string => {
    if (percent < 50) return 'text-green-400';
    if (percent < 80) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getUsageBgColor = (percent: number): string => {
    if (percent < 50) return 'bg-green-400';
    if (percent < 80) return 'bg-yellow-400';
    return 'bg-red-400';
  };

  const getTrend = (values: number[]): 'up' | 'down' | 'stable' => {
    if (values.length < 2) return 'stable';
    const recent = values.slice(-5);
    const avg = recent.reduce((a, b) => a + b, 0) / recent.length;
    const lastValue = values[values.length - 1];
    
    if (lastValue > avg + 5) return 'up';
    if (lastValue < avg - 5) return 'down';
    return 'stable';
  };

  if (loading && !systemInfo) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error && !systemInfo) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-6 text-center">
        <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
        <p className="text-red-400">{error}</p>
        <button
          onClick={fetchSystemInfo}
          className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 rounded transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!systemInfo) return null;

  const cpuTrend = getTrend(history.cpu);
  const memTrend = getTrend(history.memory);

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">System Resources</h2>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">Auto-refresh:</label>
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                autoRefresh 
                  ? 'bg-green-600 hover:bg-green-700' 
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              {autoRefresh ? 'ON' : 'OFF'}
            </button>
          </div>
          {autoRefresh && (
            <select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(Number(e.target.value))}
              className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm"
            >
              <option value={2000}>2s</option>
              <option value={5000}>5s</option>
              <option value={10000}>10s</option>
              <option value={30000}>30s</option>
            </select>
          )}
          <button
            onClick={fetchSystemInfo}
            className="p-2 hover:bg-gray-700 rounded transition-colors"
            title="Refresh now"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU Usage */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-blue-400" />
              <h3 className="font-medium">CPU Usage</h3>
            </div>
            {cpuTrend === 'up' ? (
              <TrendingUp className="w-4 h-4 text-red-400" />
            ) : cpuTrend === 'down' ? (
              <TrendingDown className="w-4 h-4 text-green-400" />
            ) : (
              <Minus className="w-4 h-4 text-gray-400" />
            )}
          </div>
          <div className="space-y-2">
            <div className="flex items-end justify-between">
              <span className={`text-2xl font-bold ${getUsageColor(systemInfo.cpu.usage_percent)}`}>
                {systemInfo.cpu.usage_percent.toFixed(1)}%
              </span>
              <span className="text-sm text-gray-400">
                {systemInfo.cpu.cores} cores
              </span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${getUsageBgColor(systemInfo.cpu.usage_percent)}`}
                style={{ width: `${systemInfo.cpu.usage_percent}%` }}
              />
            </div>
            <div className="text-xs text-gray-400">
              {systemInfo.cpu.frequency_mhz} MHz
              {systemInfo.cpu.temperature && ` • ${systemInfo.cpu.temperature}°C`}
            </div>
          </div>
        </div>

        {/* Memory Usage */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-purple-400" />
              <h3 className="font-medium">Memory</h3>
            </div>
            {memTrend === 'up' ? (
              <TrendingUp className="w-4 h-4 text-red-400" />
            ) : memTrend === 'down' ? (
              <TrendingDown className="w-4 h-4 text-green-400" />
            ) : (
              <Minus className="w-4 h-4 text-gray-400" />
            )}
          </div>
          <div className="space-y-2">
            <div className="flex items-end justify-between">
              <span className={`text-2xl font-bold ${getUsageColor(systemInfo.memory.percent)}`}>
                {systemInfo.memory.percent.toFixed(1)}%
              </span>
              <span className="text-sm text-gray-400">
                {systemInfo.memory.total_gb.toFixed(1)} GB
              </span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${getUsageBgColor(systemInfo.memory.percent)}`}
                style={{ width: `${systemInfo.memory.percent}%` }}
              />
            </div>
            <div className="text-xs text-gray-400">
              {systemInfo.memory.used_gb.toFixed(1)} / {systemInfo.memory.total_gb.toFixed(1)} GB used
            </div>
          </div>
        </div>

        {/* Disk Usage */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-green-400" />
              <h3 className="font-medium">Storage</h3>
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-end justify-between">
              <span className={`text-2xl font-bold ${getUsageColor(systemInfo.disk.percent)}`}>
                {systemInfo.disk.percent.toFixed(1)}%
              </span>
              <span className="text-sm text-gray-400">
                {systemInfo.disk.total_gb.toFixed(0)} GB
              </span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${getUsageBgColor(systemInfo.disk.percent)}`}
                style={{ width: `${systemInfo.disk.percent}%` }}
              />
            </div>
            <div className="text-xs text-gray-400">
              {systemInfo.disk.free_gb.toFixed(1)} GB free
            </div>
          </div>
        </div>

        {/* NPU Status */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-yellow-400" />
              <h3 className="font-medium">NPU Status</h3>
            </div>
            {systemInfo.npu?.available ? (
              <CheckCircle className="w-4 h-4 text-green-400" />
            ) : (
              <AlertCircle className="w-4 h-4 text-gray-400" />
            )}
          </div>
          {systemInfo.npu?.available ? (
            <div className="space-y-2">
              <div className="flex items-end justify-between">
                <span className="text-2xl font-bold text-green-400">
                  {systemInfo.npu.hardware_mode ? 'HW' : 'EMU'}
                </span>
                <span className="text-sm text-gray-400">
                  {systemInfo.npu.device || 'NPU Active'}
                </span>
              </div>
              {systemInfo.npu.aie_version && (
                <div className="text-xs text-green-400">
                  AIE v{systemInfo.npu.aie_version} • 16 TOPS INT8
                </div>
              )}
              {systemInfo.npu.utilization !== undefined && (
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className="h-2 rounded-full bg-green-400 transition-all"
                    style={{ width: `${systemInfo.npu.utilization || 0}%` }}
                  />
                </div>
              )}
              <div className="text-xs text-gray-400">
                {systemInfo.npu.performance?.real_time_factor && 
                  `${systemInfo.npu.performance.real_time_factor}x real-time`}
                {systemInfo.npu.performance?.processing_speed && 
                  ` • ${systemInfo.npu.performance.processing_speed}`}
              </div>
            </div>
          ) : (
            <div className="text-red-400 text-sm">
              <p className="font-bold">❌ NPU Required</p>
              <p className="text-xs mt-1">System requires NPU hardware</p>
            </div>
          )}
        </div>
      </div>

      {/* Additional Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Network Stats */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-5 h-5 text-cyan-400" />
            <h3 className="font-medium">Network Activity</h3>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-400">Sent</p>
              <p className="font-medium">{formatBytes(systemInfo.network.bytes_sent)}</p>
              <p className="text-xs text-gray-500">{systemInfo.network.packets_sent.toLocaleString()} packets</p>
            </div>
            <div>
              <p className="text-gray-400">Received</p>
              <p className="font-medium">{formatBytes(systemInfo.network.bytes_recv)}</p>
              <p className="text-xs text-gray-500">{systemInfo.network.packets_recv.toLocaleString()} packets</p>
            </div>
          </div>
        </div>

        {/* System Info */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-5 h-5 text-orange-400" />
            <h3 className="font-medium">System Info</h3>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Uptime</span>
              <span>{formatUptime(systemInfo.uptime_seconds)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Processes</span>
              <span>
                {systemInfo.processes.total} total, {systemInfo.processes.running} running
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Load Average</span>
              <span>{systemInfo.load_average.map(l => l.toFixed(2)).join(', ')}</span>
            </div>
          </div>
        </div>
      </div>

      {/* GPU Info (if available) */}
      {systemInfo.gpu && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-5 h-5 text-purple-400" />
            <h3 className="font-medium">GPU: {systemInfo.gpu.name}</h3>
          </div>
          <div className="grid grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-400">Utilization</p>
              <p className="text-xl font-bold">{systemInfo.gpu.utilization}%</p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Memory Used</p>
              <p className="text-xl font-bold">
                {(systemInfo.gpu.memory_used_mb / 1024).toFixed(1)} GB
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Memory Total</p>
              <p className="text-xl font-bold">
                {(systemInfo.gpu.memory_total_mb / 1024).toFixed(1)} GB
              </p>
            </div>
            {systemInfo.gpu.temperature && (
              <div>
                <p className="text-sm text-gray-400">Temperature</p>
                <p className="text-xl font-bold">{systemInfo.gpu.temperature}°C</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};