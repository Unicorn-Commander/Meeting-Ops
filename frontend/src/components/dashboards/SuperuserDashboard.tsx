import React, { useState, useEffect } from 'react';
import { SystemMonitor } from '../SystemMonitor';
import { NpuStatusIndicator } from '../NpuStatusIndicator';
import { NetworkStatus } from '../NetworkStatus';
import { LogViewer } from '../LogViewer';
import { 
  Cpu, 
  HardDrive, 
  Activity, 
  Network,
  Shield,
  Database,
  Building,
  AlertTriangle,
  CheckCircle,
  Terminal,
  Settings
} from 'lucide-react';

interface SystemHealth {
  cpu: { usage: number; temperature: number };
  memory: { used: number; total: number };
  disk: { used: number; total: number };
  npu: { status: string; model: string; usage: number };
  services: Array<{ name: string; status: string }>;
}

interface Organization {
  id: number;
  name: string;
  plan: string;
  users: number;
  storageUsed: number;
  storageQuota: number;
}

export const SuperuserDashboard: React.FC = () => {
  const [systemHealth, setSystemHealth] = useState<SystemHealth>({
    cpu: { usage: 0, temperature: 0 },
    memory: { used: 0, total: 0 },
    disk: { used: 0, total: 0 },
    npu: { status: 'unknown', model: '', usage: 0 },
    services: []
  });
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'hardware' | 'organizations' | 'maintenance'>('overview');
  const [selectedDevice, setSelectedDevice] = useState<string>('');

  useEffect(() => {
    // Fetch system information
    const fetchSystemInfo = async () => {
      try {
        const response = await fetch('/api/system-info');
        if (response.ok) {
          const data = await response.json();
          setSystemHealth({
            cpu: {
              usage: data.cpu?.percent || 0,
              temperature: data.cpu?.temperature || 0
            },
            memory: {
              used: data.memory?.used || 0,
              total: data.memory?.total || 0
            },
            disk: {
              used: data.disk?.used || 0,
              total: data.disk?.total || 0
            },
            npu: {
              status: data.npu?.available ? 'active' : 'inactive',
              model: data.npu?.model || 'Unknown',
              usage: data.npu?.usage || 0
            },
            services: data.services || []
          });
        }
      } catch (error) {
        console.error('Failed to fetch system info:', error);
      }
    };

    fetchSystemInfo();
    const interval = setInterval(fetchSystemInfo, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleRunCommand = async (command: string) => {
    // This would execute system commands via a secure API endpoint
    console.log('Execute command:', command);
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 mb-2">
          System Administration
        </h1>
        <p className="text-gray-400">
          Complete system control and monitoring
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-4 mb-6 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('overview')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'overview'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          System Overview
          {activeTab === 'overview' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('hardware')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'hardware'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Hardware Control
          {activeTab === 'hardware' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('organizations')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'organizations'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Organizations
          {activeTab === 'organizations' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('maintenance')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'maintenance'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Maintenance
          {activeTab === 'maintenance' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* System Health Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Cpu className="w-8 h-8 text-blue-400" />
                <span className="text-sm text-gray-400">
                  {systemHealth.cpu.temperature}°C
                </span>
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {systemHealth.cpu.usage}%
              </h3>
              <p className="text-sm text-gray-400 mt-1">CPU Usage</p>
              <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-blue-400 transition-all duration-300"
                  style={{ width: `${systemHealth.cpu.usage}%` }}
                />
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Activity className="w-8 h-8 text-green-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {Math.round((systemHealth.memory.used / systemHealth.memory.total) * 100)}%
              </h3>
              <p className="text-sm text-gray-400 mt-1">Memory Usage</p>
              <p className="text-xs text-gray-500 mt-1">
                {(systemHealth.memory.used / 1024 / 1024 / 1024).toFixed(1)} / 
                {(systemHealth.memory.total / 1024 / 1024 / 1024).toFixed(1)} GB
              </p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <HardDrive className="w-8 h-8 text-purple-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {Math.round((systemHealth.disk.used / systemHealth.disk.total) * 100)}%
              </h3>
              <p className="text-sm text-gray-400 mt-1">Disk Usage</p>
              <p className="text-xs text-gray-500 mt-1">
                {(systemHealth.disk.used / 1024 / 1024 / 1024).toFixed(1)} / 
                {(systemHealth.disk.total / 1024 / 1024 / 1024).toFixed(1)} GB
              </p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Cpu className="w-8 h-8 text-pink-400" />
                <span className={`text-xs px-2 py-1 rounded ${
                  systemHealth.npu.status === 'active' 
                    ? 'bg-green-500/20 text-green-400' 
                    : 'bg-red-500/20 text-red-400'
                }`}>
                  {systemHealth.npu.status}
                </span>
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {systemHealth.npu.usage}%
              </h3>
              <p className="text-sm text-gray-400 mt-1">NPU Usage</p>
              <p className="text-xs text-gray-500 mt-1">{systemHealth.npu.model}</p>
            </div>
          </div>

          {/* Services Status */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Service Status
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { name: 'Backend API', status: 'running' },
                { name: 'PostgreSQL', status: 'running' },
                { name: 'Redis', status: 'running' },
                { name: 'NPU Service', status: 'running' },
                { name: 'Audio Capture', status: 'running' },
                { name: 'WebSocket', status: 'running' },
                { name: 'Nginx', status: 'stopped' },
                { name: 'Backup Service', status: 'running' }
              ].map((service) => (
                <div 
                  key={service.name}
                  className="flex items-center gap-2 p-3 bg-gray-700 rounded-lg"
                >
                  {service.status === 'running' ? (
                    <CheckCircle className="w-4 h-4 text-green-400" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-red-400" />
                  )}
                  <span className="text-sm text-gray-200">{service.name}</span>
                </div>
              ))}
            </div>
          </div>

          {/* System Monitor */}
          <SystemMonitor />
        </div>
      )}

      {activeTab === 'hardware' && (
        <div className="space-y-6">
          {/* NPU Control */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              NPU Configuration
            </h2>
            <div className="space-y-4">
              <NpuStatusIndicator />
              
              <div className="pt-4 border-t border-gray-700">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  NPU Model Selection
                </label>
                <select 
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:ring-2 focus:ring-purple-500"
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                >
                  <option value="">Select NPU Model</option>
                  <option value="whisperx-npu-unified">WhisperX NPU Unified</option>
                  <option value="whisper-onnx-npu">Whisper ONNX NPU</option>
                  <option value="cpu-fallback">CPU Fallback</option>
                </select>
              </div>

              <button className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
                Apply NPU Configuration
              </button>
            </div>
          </div>

          {/* Audio Devices */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Audio Device Configuration
            </h2>
            <div className="space-y-3">
              <div className="p-4 bg-gray-700 rounded-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-medium text-gray-100">USB PnP Sound Device</h3>
                    <p className="text-sm text-gray-400">hw:0,0 - 44.1kHz, Mono</p>
                  </div>
                  <span className="px-3 py-1 bg-green-500/20 text-green-400 rounded text-sm">
                    Active
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Network Configuration */}
          <NetworkStatus />
        </div>
      )}

      {activeTab === 'organizations' && (
        <div className="space-y-6">
          <div className="bg-gray-800 rounded-lg p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-lg font-semibold text-gray-200">
                Organizations
              </h2>
              <button className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
                Add Organization
              </button>
            </div>

            <div className="space-y-4">
              {[
                { 
                  id: 1, 
                  name: 'Default Organization', 
                  plan: 'enterprise',
                  users: 25,
                  storageUsed: 45.2,
                  storageQuota: 100
                },
                { 
                  id: 2, 
                  name: 'Demo Organization', 
                  plan: 'free',
                  users: 3,
                  storageUsed: 2.1,
                  storageQuota: 10
                }
              ].map(org => (
                <div key={org.id} className="p-4 bg-gray-700 rounded-lg">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-medium text-gray-100">{org.name}</h3>
                      <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
                        <span className="capitalize">{org.plan} Plan</span>
                        <span>{org.users} Users</span>
                        <span>
                          {org.storageUsed}GB / {org.storageQuota}GB Storage
                        </span>
                      </div>
                    </div>
                    <button className="text-gray-400 hover:text-purple-400 transition-colors">
                      <Settings className="w-5 h-5" />
                    </button>
                  </div>
                  <div className="mt-3 h-2 bg-gray-600 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-purple-500 transition-all duration-300"
                      style={{ width: `${(org.storageUsed / org.storageQuota) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'maintenance' && (
        <div className="space-y-6">
          {/* Command Terminal */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4 flex items-center gap-2">
              <Terminal className="w-5 h-5" />
              System Terminal
            </h2>
            <div className="bg-black rounded p-4 font-mono text-sm">
              <div className="text-green-400 mb-2">root@meeting-ops:~#</div>
              <input
                type="text"
                className="w-full bg-transparent text-gray-100 outline-none"
                placeholder="Enter command..."
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleRunCommand((e.target as HTMLInputElement).value);
                    (e.target as HTMLInputElement).value = '';
                  }
                }}
              />
            </div>
          </div>

          {/* System Logs */}
          <LogViewer />

          {/* Maintenance Actions */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Maintenance Actions
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                <Database className="w-6 h-6 text-blue-400 mb-2" />
                <h3 className="font-medium text-gray-100">Backup Database</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Create full system backup
                </p>
              </button>
              <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                <Shield className="w-6 h-6 text-green-400 mb-2" />
                <h3 className="font-medium text-gray-100">Update SSL Certificate</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Renew or update SSL certs
                </p>
              </button>
              <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                <HardDrive className="w-6 h-6 text-purple-400 mb-2" />
                <h3 className="font-medium text-gray-100">Clean Storage</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Remove old recordings
                </p>
              </button>
              <button className="p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-left">
                <Activity className="w-6 h-6 text-red-400 mb-2" />
                <h3 className="font-medium text-gray-100">Restart Services</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Restart all system services
                </p>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};