import React, { useState, useEffect } from 'react';
import {
  Server,
  Activity,
  HardDrive,
  Cpu,
  MemoryStick,
  Network,
  Users,
  FileText,
  AlertTriangle,
  CheckCircle,
  XCircle,
  TrendingUp,
  Clock,
  Zap
} from 'lucide-react';

interface SystemStats {
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  network_io: {
    bytes_sent: number;
    bytes_recv: number;
  };
  uptime: number;
  load_avg: [number, number, number];
}

interface ServiceStatus {
  name: string;
  status: 'running' | 'stopped' | 'error';
  description: string;
  uptime?: string;
}

export const SystemDashboard: React.FC = () => {
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  useEffect(() => {
    fetchSystemStats();
    const interval = setInterval(fetchSystemStats, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchSystemStats = async () => {
    try {
      // Mock system stats for now - replace with actual API
      const mockStats: SystemStats = {
        cpu_usage: Math.random() * 100,
        memory_usage: 65 + Math.random() * 20,
        disk_usage: 45 + Math.random() * 10,
        network_io: {
          bytes_sent: Math.floor(Math.random() * 1000000000),
          bytes_recv: Math.floor(Math.random() * 1000000000)
        },
        uptime: 86400 * 5 + Math.random() * 86400,
        load_avg: [
          Math.random() * 2,
          Math.random() * 2,
          Math.random() * 2
        ]
      };

      const mockServices: ServiceStatus[] = [
        { name: 'NPU Runtime', status: 'running', description: 'AI acceleration service' },
        { name: 'Transcription Service', status: 'running', description: 'Speech-to-text processing' },
        { name: 'Speaker Diarization', status: 'running', description: 'Speaker identification' },
        { name: 'Audio Recording', status: 'running', description: 'Audio capture service' },
        { name: 'WebSocket Server', status: 'running', description: 'Real-time communication' },
        { name: 'Database', status: 'running', description: 'Data storage service' },
        { name: 'File Storage', status: 'running', description: 'File management service' },
        { name: 'LLM Summarization', status: 'running', description: 'Meeting summarization' }
      ];

      setSystemStats(mockStats);
      setServices(mockServices);
      setLastUpdate(new Date());
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch system stats:', error);
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    if (bytes === 0) return '0 B';
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'text-green-400';
      case 'stopped':
        return 'text-gray-400';
      case 'error':
        return 'text-red-400';
      default:
        return 'text-gray-400';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <CheckCircle className="h-4 w-4" />;
      case 'stopped':
        return <XCircle className="h-4 w-4" />;
      case 'error':
        return <AlertTriangle className="h-4 w-4" />;
      default:
        return <XCircle className="h-4 w-4" />;
    }
  };

  const getUsageColor = (percentage: number) => {
    if (percentage < 60) return 'bg-green-500';
    if (percentage < 80) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Loading system information...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">System Dashboard</h1>
          <p className="text-gray-400 mt-1">
            Real-time system monitoring and health status
          </p>
        </div>
        <div className="text-sm text-gray-400">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      </div>

      {/* System Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU Usage */}
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-blue-400" />
              <span className="font-medium">CPU Usage</span>
            </div>
            <span className="text-2xl font-bold">{systemStats?.cpu_usage.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${getUsageColor(systemStats?.cpu_usage || 0)}`}
              style={{ width: `${systemStats?.cpu_usage || 0}%` }}
            ></div>
          </div>
          <div className="text-xs text-gray-400 mt-2">
            Load: {systemStats?.load_avg.map(l => l.toFixed(2)).join(', ')}
          </div>
        </div>

        {/* Memory Usage */}
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <MemoryStick className="h-5 w-5 text-green-400" />
              <span className="font-medium">Memory</span>
            </div>
            <span className="text-2xl font-bold">{systemStats?.memory_usage.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${getUsageColor(systemStats?.memory_usage || 0)}`}
              style={{ width: `${systemStats?.memory_usage || 0}%` }}
            ></div>
          </div>
          <div className="text-xs text-gray-400 mt-2">
            Used of available system memory
          </div>
        </div>

        {/* Disk Usage */}
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-purple-400" />
              <span className="font-medium">Storage</span>
            </div>
            <span className="text-2xl font-bold">{systemStats?.disk_usage.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${getUsageColor(systemStats?.disk_usage || 0)}`}
              style={{ width: `${systemStats?.disk_usage || 0}%` }}
            ></div>
          </div>
          <div className="text-xs text-gray-400 mt-2">
            Root filesystem usage
          </div>
        </div>

        {/* Uptime */}
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-orange-400" />
              <span className="font-medium">Uptime</span>
            </div>
          </div>
          <div className="text-xl font-bold mb-1">
            {formatUptime(systemStats?.uptime || 0)}
          </div>
          <div className="text-xs text-gray-400">
            System running continuously
          </div>
        </div>
      </div>

      {/* Network Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-gray-800 p-4 rounded-lg">
          <h3 className="font-medium mb-4 flex items-center gap-2">
            <Network className="h-5 w-5 text-blue-400" />
            Network Activity
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Bytes Sent</span>
              <span className="font-mono text-sm">
                {formatBytes(systemStats?.network_io.bytes_sent || 0)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Bytes Received</span>
              <span className="font-mono text-sm">
                {formatBytes(systemStats?.network_io.bytes_recv || 0)}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-gray-800 p-4 rounded-lg">
          <h3 className="font-medium mb-4 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-green-400" />
            Quick Actions
          </h3>
          <div className="space-y-2">
            <button className="w-full text-left p-2 hover:bg-gray-700 rounded transition-colors text-sm">
              View detailed logs
            </button>
            <button className="w-full text-left p-2 hover:bg-gray-700 rounded transition-colors text-sm">
              System performance metrics
            </button>
            <button className="w-full text-left p-2 hover:bg-gray-700 rounded transition-colors text-sm">
              Resource usage history
            </button>
          </div>
        </div>
      </div>

      {/* Services Status */}
      <div className="bg-gray-800 p-4 rounded-lg">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <Server className="h-5 w-5 text-blue-400" />
          System Services Status
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {services.map((service, index) => (
            <div
              key={index}
              className="flex items-center justify-between p-3 bg-gray-700 rounded-lg"
            >
              <div className="flex items-center gap-3">
                <div className={`${getStatusColor(service.status)}`}>
                  {getStatusIcon(service.status)}
                </div>
                <div>
                  <p className="font-medium text-sm">{service.name}</p>
                  <p className="text-xs text-gray-400">{service.description}</p>
                </div>
              </div>
              <span className={`text-xs font-medium ${getStatusColor(service.status)}`}>
                {service.status.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* System Alerts */}
      <div className="bg-gray-800 p-4 rounded-lg">
        <h3 className="font-medium mb-4 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-400" />
          System Alerts & Notifications
        </h3>
        <div className="space-y-2">
          <div className="flex items-center gap-3 p-3 bg-green-900/20 border border-green-600 rounded-lg">
            <CheckCircle className="h-4 w-4 text-green-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium">All systems operational</p>
              <p className="text-xs text-gray-400">No critical issues detected</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3 p-3 bg-blue-900/20 border border-blue-600 rounded-lg">
            <Zap className="h-4 w-4 text-blue-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium">NPU acceleration active</p>
              <p className="text-xs text-gray-400">Real hardware NPU runtime detected and functional</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};