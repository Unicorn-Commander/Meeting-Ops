import React, { useState, useEffect } from 'react';
import {
  Server,
  HardDrive,
  Cpu,
  Zap,
  Activity,
  Settings,
  Database,
  Network,
  Shield,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  XCircle,
  Download,
  Upload,
  Trash2,
  FileText,
  Monitor,
  Users,
  Calendar,
  Mail
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
    performance?: {
      real_time_factor?: number;
      tokens_per_second?: number;
      processing_speed?: string;
    };
  };
  uptime_seconds: number;
  load_average: number[];
  platform: {
    system: string;
    release: string;
    machine: string;
  };
}

interface ServiceStatus {
  name: string;
  status: 'running' | 'stopped' | 'error';
  pid?: number;
  uptime?: string;
  description: string;
}

export const SystemAdminPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    fetchSystemData();
    if (autoRefresh) {
      const interval = setInterval(fetchSystemData, 5000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const fetchSystemData = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const headers = {
        'Authorization': `Bearer ${token}`
      };

      // Fetch system info
      const systemResponse = await fetch(`${API_BASE_URL}/api/system-info`, { headers });
      if (systemResponse.ok) {
        const data = await systemResponse.json();
        setSystemInfo(data);
      }

      // Mock service statuses - in real implementation, would come from backend
      setServices([
        {
          name: 'Meeting-Ops Backend',
          status: 'running',
          pid: 12345,
          uptime: '2h 15m',
          description: 'Main application server'
        },
        {
          name: 'NPU Service',
          status: systemInfo?.npu?.available ? 'running' : 'stopped',
          description: 'NPU acceleration service'
        },
        {
          name: 'PostgreSQL',
          status: 'running',
          pid: 98765,
          uptime: '5h 30m',
          description: 'Database server'
        },
        {
          name: 'Qdrant Vector DB',
          status: 'running',
          pid: 11111,
          uptime: '5h 29m',
          description: 'Vector search database'
        }
      ]);

      setError(null);
    } catch (err) {
      setError('Failed to fetch system data');
      console.error('System data fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) return `${days}d ${hours}h ${mins}m`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'text-green-400';
      case 'stopped': return 'text-red-400';
      case 'error': return 'text-orange-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <CheckCircle className="w-4 h-4" />;
      case 'stopped': return <XCircle className="w-4 h-4" />;
      case 'error': return <AlertCircle className="w-4 h-4" />;
      default: return <AlertCircle className="w-4 h-4" />;
    }
  };

  const tabs = [
    { id: 'overview', label: 'System Overview', icon: <Monitor className="w-4 h-4" /> },
    { id: 'services', label: 'Services', icon: <Server className="w-4 h-4" /> },
    { id: 'logs', label: 'System Logs', icon: <FileText className="w-4 h-4" /> },
    { id: 'storage', label: 'Storage', icon: <HardDrive className="w-4 h-4" /> },
    { id: 'network', label: 'Network', icon: <Network className="w-4 h-4" /> },
    { id: 'security', label: 'Security', icon: <Shield className="w-4 h-4" /> }
  ];

  if (loading && !systemInfo) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
        <span className="ml-2 text-gray-400">Loading system information...</span>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Quick Actions Bar */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">System Infrastructure</h2>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Auto-refresh:</span>
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
          <button
            onClick={fetchSystemData}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

        {/* System Status Banner */}
        {systemInfo && (
          <div className="bg-gray-800 rounded-lg p-4 mb-6 border border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 text-green-400" />
                  <span className="font-medium">System Operational</span>
                </div>
                <div className="text-sm text-gray-400">
                  Uptime: {formatUptime(systemInfo.uptime_seconds)}
                </div>
                <div className="text-sm text-gray-400">
                  Load: {systemInfo.load_average.map(l => l.toFixed(2)).join(', ')}
                </div>
              </div>
              <div className="flex items-center gap-4">
                {systemInfo.npu?.available && (
                  <div className="flex items-center gap-2 text-green-400">
                    <Zap className="w-4 h-4" />
                    <span className="text-sm">NPU Active</span>
                  </div>
                )}
                <div className="text-sm text-gray-400">
                  {systemInfo.platform.system} {systemInfo.platform.release}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error Banner */}
        {error && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-red-400">{error}</span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex space-x-1 bg-gray-800 rounded-lg p-1 mb-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="space-y-6">
          {activeTab === 'overview' && systemInfo && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {/* CPU Card */}
              <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Cpu className="w-5 h-5 text-blue-400" />
                    CPU
                  </h3>
                  <span className="text-2xl font-bold text-blue-400">
                    {systemInfo.cpu.usage_percent.toFixed(1)}%
                  </span>
                </div>
                <div className="space-y-2 text-sm text-gray-400">
                  <div>Cores: {systemInfo.cpu.cores}</div>
                  <div>Frequency: {systemInfo.cpu.frequency_mhz} MHz</div>
                  {systemInfo.cpu.temperature && (
                    <div>Temperature: {systemInfo.cpu.temperature}°C</div>
                  )}
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2 mt-4">
                  <div
                    className="bg-blue-400 h-2 rounded-full transition-all"
                    style={{ width: `${systemInfo.cpu.usage_percent}%` }}
                  />
                </div>
              </div>

              {/* Memory Card */}
              <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Database className="w-5 h-5 text-purple-400" />
                    Memory
                  </h3>
                  <span className="text-2xl font-bold text-purple-400">
                    {systemInfo.memory.percent.toFixed(1)}%
                  </span>
                </div>
                <div className="space-y-2 text-sm text-gray-400">
                  <div>Used: {systemInfo.memory.used_gb.toFixed(1)} GB</div>
                  <div>Total: {systemInfo.memory.total_gb.toFixed(1)} GB</div>
                  <div>Available: {systemInfo.memory.available_gb.toFixed(1)} GB</div>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2 mt-4">
                  <div
                    className="bg-purple-400 h-2 rounded-full transition-all"
                    style={{ width: `${systemInfo.memory.percent}%` }}
                  />
                </div>
              </div>

              {/* Storage Card */}
              <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <HardDrive className="w-5 h-5 text-green-400" />
                    Storage
                  </h3>
                  <span className="text-2xl font-bold text-green-400">
                    {systemInfo.disk.percent.toFixed(1)}%
                  </span>
                </div>
                <div className="space-y-2 text-sm text-gray-400">
                  <div>Used: {systemInfo.disk.used_gb.toFixed(1)} GB</div>
                  <div>Total: {systemInfo.disk.total_gb.toFixed(0)} GB</div>
                  <div>Free: {systemInfo.disk.free_gb.toFixed(1)} GB</div>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2 mt-4">
                  <div
                    className="bg-green-400 h-2 rounded-full transition-all"
                    style={{ width: `${systemInfo.disk.percent}%` }}
                  />
                </div>
              </div>

              {/* NPU Card */}
              <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Zap className="w-5 h-5 text-yellow-400" />
                    NPU
                  </h3>
                  {systemInfo.npu?.available ? (
                    <CheckCircle className="w-6 h-6 text-green-400" />
                  ) : (
                    <XCircle className="w-6 h-6 text-red-400" />
                  )}
                </div>
                {systemInfo.npu?.available ? (
                  <div className="space-y-2 text-sm text-gray-400">
                    <div>Device: {systemInfo.npu.device}</div>
                    <div>AIE: v{systemInfo.npu.aie_version}</div>
                    <div>Performance: {systemInfo.npu.performance?.processing_speed}</div>
                    <div className="text-green-400 font-medium">Hardware Mode</div>
                  </div>
                ) : (
                  <div className="text-red-400 text-sm">
                    NPU not available or not initialized
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'services' && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-6 border-b border-gray-700">
                <h3 className="text-xl font-semibold flex items-center gap-2">
                  <Server className="w-6 h-6 text-purple-400" />
                  System Services
                </h3>
              </div>
              <div className="divide-y divide-gray-700">
                {services.map((service, index) => (
                  <div key={index} className="p-6 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`flex items-center gap-2 ${getStatusColor(service.status)}`}>
                        {getStatusIcon(service.status)}
                        <span className="font-medium">{service.name}</span>
                      </div>
                      <span className="text-gray-400">{service.description}</span>
                    </div>
                    <div className="flex items-center gap-6 text-sm text-gray-400">
                      {service.pid && <div>PID: {service.pid}</div>}
                      {service.uptime && <div>Uptime: {service.uptime}</div>}
                      <div className="flex gap-2">
                        <button className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-white text-xs">
                          Start
                        </button>
                        <button className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-white text-xs">
                          Stop
                        </button>
                        <button className="px-3 py-1 bg-gray-600 hover:bg-gray-700 rounded text-white text-xs">
                          Restart
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-6 border-b border-gray-700">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-semibold flex items-center gap-2">
                    <FileText className="w-6 h-6 text-purple-400" />
                    System Logs
                  </h3>
                  <div className="flex gap-2">
                    <button className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded">
                      <Download className="w-4 h-4" />
                      Download
                    </button>
                    <button className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded">
                      <Trash2 className="w-4 h-4" />
                      Clear
                    </button>
                  </div>
                </div>
              </div>
              <div className="p-6">
                <div className="bg-gray-900 rounded p-4 h-96 overflow-y-auto font-mono text-sm">
                  <div className="text-gray-400">
                    [INFO] System logs will be displayed here
                  </div>
                  <div className="text-green-400">
                    [SUCCESS] NPU initialized successfully
                  </div>
                  <div className="text-blue-400">
                    [INFO] Backend server started on port 1950
                  </div>
                  <div className="text-yellow-400">
                    [WARN] High CPU usage detected: 87%
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'storage' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <div className="p-6 border-b border-gray-700">
                  <h3 className="text-xl font-semibold">Storage Management</h3>
                </div>
                <div className="p-6 space-y-4">
                  <button className="w-full flex items-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 rounded">
                    <Download className="w-4 h-4" />
                    Create Backup
                  </button>
                  <button className="w-full flex items-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded">
                    <Upload className="w-4 h-4" />
                    Restore Backup
                  </button>
                  <button className="w-full flex items-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 rounded">
                    <Trash2 className="w-4 h-4" />
                    Cleanup Old Files
                  </button>
                </div>
              </div>
              
              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <div className="p-6 border-b border-gray-700">
                  <h3 className="text-xl font-semibold">Recent Backups</h3>
                </div>
                <div className="p-6">
                  <div className="text-gray-400 text-center py-8">
                    No backups found
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'network' && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-6 border-b border-gray-700">
                <h3 className="text-xl font-semibold flex items-center gap-2">
                  <Network className="w-6 h-6 text-purple-400" />
                  Network Configuration
                </h3>
              </div>
              <div className="p-6 space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium mb-2">Frontend Port</label>
                    <input
                      type="number"
                      value="7777"
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Backend Port</label>
                    <input
                      type="number"
                      value="1950"
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                    />
                  </div>
                </div>
                <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded">
                  Save Configuration
                </button>
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <div className="p-6 border-b border-gray-700">
                  <h3 className="text-xl font-semibold flex items-center gap-2">
                    <Shield className="w-6 h-6 text-purple-400" />
                    Security Status
                  </h3>
                </div>
                <div className="p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <span>JWT Authentication</span>
                    <CheckCircle className="w-5 h-5 text-green-400" />
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Role-based Access Control</span>
                    <CheckCircle className="w-5 h-5 text-green-400" />
                  </div>
                  <div className="flex items-center justify-between">
                    <span>HTTPS Enabled</span>
                    <XCircle className="w-5 h-5 text-red-400" />
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Firewall Active</span>
                    <AlertCircle className="w-5 h-5 text-yellow-400" />
                  </div>
                </div>
              </div>

              <div className="bg-gray-800 rounded-lg border border-gray-700">
                <div className="p-6 border-b border-gray-700">
                  <h3 className="text-xl font-semibold">Access Management</h3>
                </div>
                <div className="p-6 space-y-4">
                  <button className="w-full flex items-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded">
                    <Users className="w-4 h-4" />
                    Manage Users
                  </button>
                  <button className="w-full flex items-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded">
                    <Shield className="w-4 h-4" />
                    API Keys
                  </button>
                  <button className="w-full flex items-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded">
                    <FileText className="w-4 h-4" />
                    Audit Logs
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
    </div>
  );
};