import React, { useState, useEffect } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

import {
  Network,
  Wifi,
  Globe,
  Shield,
  Activity,
  AlertCircle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Edit,
  Save,
  X
} from 'lucide-react';

interface NetworkInterface {
  name: string;
  state: string;
  type: string;
  addresses: Array<{
    ip: string;
    prefix: string;
    type: string;
  }>;
  mac_address: string;
  stats: {
    rx_bytes: number;
    tx_bytes: number;
    rx_packets: number;
    tx_packets: number;
  };
}

interface FirewallRule {
  to: string;
  action: string;
  from: string;
  raw: string;
}

interface NetworkStatus {
  hostname: string;
  domain: string;
  interfaces: NetworkInterface[];
  dns: {
    nameservers: string[];
    search_domains: string[];
  };
  firewall: {
    enabled: boolean;
    default_policy: {
      incoming: string;
      outgoing: string;
    };
    rules: FirewallRule[];
  };
}

export const NetworkManagement: React.FC = () => {
  const [networkStatus, setNetworkStatus] = useState<NetworkStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('interfaces');
  const [editingInterface, setEditingInterface] = useState<string | null>(null);
  const [connectivityTest, setConnectivityTest] = useState<any>(null);

  useEffect(() => {
    fetchNetworkStatus();
  }, []);

  const fetchNetworkStatus = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/network/status`);
      if (response.ok) {
        const data = await response.json();
        setNetworkStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch network status:', error);
    } finally {
      setLoading(false);
    }
  };

  const testConnectivity = async (target: string = '8.8.8.8') => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/network/connectivity/test?target=${target}`);
      if (response.ok) {
        const data = await response.json();
        setConnectivityTest(data);
      }
    } catch (error) {
      console.error('Failed to test connectivity:', error);
    }
  };

  const toggleFirewall = async (enable: boolean) => {
    try {
      const endpoint = enable ? `${API_BASE_URL}/api/network/firewall/enable` : `${API_BASE_URL}/api/network/firewall/disable`;
      const response = await fetch(endpoint, { method: 'POST' });
      if (response.ok) {
        fetchNetworkStatus(); // Refresh status
      }
    } catch (error) {
      console.error('Failed to toggle firewall:', error);
    }
  };

  const formatBytes = (bytes: number): string => {
    const sizes = ['B', 'KB', 'MB', 'GB'];
    if (bytes === 0) return '0 B';
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  };

  const getInterfaceIcon = (type: string) => {
    switch (type) {
      case 'ethernet':
        return <Network className="h-5 w-5" />;
      case 'wireless':
        return <Wifi className="h-5 w-5" />;
      case 'loopback':
        return <Activity className="h-5 w-5" />;
      default:
        return <Globe className="h-5 w-5" />;
    }
  };

  const getStateColor = (state: string) => {
    return state === 'UP' ? 'text-green-400' : 'text-red-400';
  };

  const getStateIcon = (state: string) => {
    return state === 'UP' ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />;
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Loading network information...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Network & System Management</h1>
          <p className="text-gray-400 mt-1">Configure network interfaces, DNS, and firewall settings</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => testConnectivity()}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
          >
            <Activity className="h-4 w-4" />
            Test Connectivity
          </button>
          <button
            onClick={fetchNetworkStatus}
            className="flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* System Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Globe className="h-5 w-5 text-blue-400" />
            <div>
              <p className="text-sm text-gray-400">Hostname</p>
              <p className="font-medium">{networkStatus?.hostname || 'Unknown'}</p>
            </div>
          </div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Network className="h-5 w-5 text-green-400" />
            <div>
              <p className="text-sm text-gray-400">Active Interfaces</p>
              <p className="font-medium">
                {networkStatus?.interfaces?.filter(i => i.state === 'UP').length || 0}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <Shield className={`h-5 w-5 ${networkStatus?.firewall?.enabled ? 'text-green-400' : 'text-red-400'}`} />
            <div>
              <p className="text-sm text-gray-400">Firewall</p>
              <p className="font-medium">{networkStatus?.firewall?.enabled ? 'Enabled' : 'Disabled'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Connectivity Test Results */}
      {connectivityTest && (
        <div className="bg-gray-800 p-4 rounded-lg">
          <h3 className="font-medium mb-3">Connectivity Test Results</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className={`p-3 rounded border ${connectivityTest.ping.success ? 'border-green-600 bg-green-900/20' : 'border-red-600 bg-red-900/20'}`}>
              <div className="flex items-center gap-2 mb-2">
                {connectivityTest.ping.success ? 
                  <CheckCircle className="h-4 w-4 text-green-400" /> : 
                  <XCircle className="h-4 w-4 text-red-400" />
                }
                <span className="font-medium">Ping Test to {connectivityTest.target}</span>
              </div>
              <pre className="text-xs text-gray-400 bg-gray-900 p-2 rounded overflow-x-auto">
                {connectivityTest.ping.output}
              </pre>
            </div>
            <div className={`p-3 rounded border ${connectivityTest.dns.success ? 'border-green-600 bg-green-900/20' : 'border-red-600 bg-red-900/20'}`}>
              <div className="flex items-center gap-2 mb-2">
                {connectivityTest.dns.success ? 
                  <CheckCircle className="h-4 w-4 text-green-400" /> : 
                  <XCircle className="h-4 w-4 text-red-400" />
                }
                <span className="font-medium">DNS Resolution</span>
              </div>
              <pre className="text-xs text-gray-400 bg-gray-900 p-2 rounded overflow-x-auto">
                {connectivityTest.dns.output}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="border-b border-gray-700">
        <nav className="flex space-x-8">
          {[
            { id: 'interfaces', name: 'Network Interfaces', icon: Network },
            { id: 'dns', name: 'DNS Settings', icon: Globe },
            { id: 'firewall', name: 'Firewall', icon: Shield },
            { id: 'routes', name: 'Routing', icon: Activity }
          ].map((tab) => {
            const IconComponent = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-gray-400 hover:text-gray-300'
                }`}
              >
                <IconComponent className="h-4 w-4" />
                {tab.name}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="space-y-4">
        {activeTab === 'interfaces' && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium">Network Interfaces</h3>
            {networkStatus?.interfaces?.map((networkInterface) => (
              <div key={networkInterface.name} className="bg-gray-800 p-4 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {getInterfaceIcon(networkInterface.type)}
                    <div>
                      <h4 className="font-medium">{networkInterface.name}</h4>
                      <p className="text-sm text-gray-400">{networkInterface.type}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className={`flex items-center gap-1 ${getStateColor(networkInterface.state)}`}>
                      {getStateIcon(networkInterface.state)}
                      <span className="text-sm font-medium">{networkInterface.state}</span>
                    </div>
                    <button
                      onClick={() => setEditingInterface(networkInterface.name)}
                      className="p-2 hover:bg-gray-700 rounded transition-colors"
                    >
                      <Edit className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <p className="text-sm text-gray-400 mb-1">IP Addresses</p>
                    {networkInterface.addresses?.length > 0 ? (
                      networkInterface.addresses.map((addr, idx) => (
                        <p key={idx} className="text-sm font-mono">
                          {addr.ip}/{addr.prefix} ({addr.type})
                        </p>
                      ))
                    ) : (
                      <p className="text-sm text-gray-500">No addresses configured</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-gray-400 mb-1">MAC Address</p>
                    <p className="text-sm font-mono">{networkInterface.mac_address || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-400 mb-1">Traffic</p>
                    <p className="text-sm">
                      ↓ {formatBytes(networkInterface.stats?.rx_bytes || 0)} / 
                      ↑ {formatBytes(networkInterface.stats?.tx_bytes || 0)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'dns' && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium">DNS Configuration</h3>
            <div className="bg-gray-800 p-4 rounded-lg">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h4 className="font-medium mb-2">DNS Servers</h4>
                  {networkStatus?.dns?.nameservers && networkStatus.dns.nameservers.length > 0 ? (
                    <ul className="space-y-1">
                      {networkStatus?.dns?.nameservers?.map((server, idx) => (
                        <li key={idx} className="text-sm font-mono bg-gray-900 px-2 py-1 rounded">
                          {server}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-gray-500">No DNS servers configured</p>
                  )}
                </div>
                <div>
                  <h4 className="font-medium mb-2">Search Domains</h4>
                  {networkStatus?.dns?.search_domains && networkStatus.dns.search_domains.length > 0 ? (
                    <ul className="space-y-1">
                      {networkStatus?.dns?.search_domains?.map((domain, idx) => (
                        <li key={idx} className="text-sm font-mono bg-gray-900 px-2 py-1 rounded">
                          {domain}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-gray-500">No search domains configured</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'firewall' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium">Firewall Management</h3>
              <button
                onClick={() => toggleFirewall(!networkStatus?.firewall?.enabled)}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  networkStatus?.firewall?.enabled
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-green-600 hover:bg-green-700'
                }`}
              >
                {networkStatus?.firewall?.enabled ? 'Disable Firewall' : 'Enable Firewall'}
              </button>
            </div>

            <div className="bg-gray-800 p-4 rounded-lg">
              <h4 className="font-medium mb-3">Firewall Status</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div>
                  <p className="text-sm text-gray-400">Status</p>
                  <p className={`font-medium ${networkStatus?.firewall?.enabled ? 'text-green-400' : 'text-red-400'}`}>
                    {networkStatus?.firewall?.enabled ? 'Active' : 'Inactive'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Incoming Default</p>
                  <p className="font-medium">{networkStatus?.firewall?.default_policy?.incoming || 'Unknown'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Outgoing Default</p>
                  <p className="font-medium">{networkStatus?.firewall?.default_policy?.outgoing || 'Unknown'}</p>
                </div>
              </div>

              {networkStatus?.firewall?.rules && networkStatus.firewall.rules.length > 0 && (
                <div>
                  <h5 className="font-medium mb-2">Active Rules</h5>
                  <div className="space-y-2">
                    {networkStatus?.firewall?.rules?.map((rule, idx) => (
                      <div key={idx} className="bg-gray-900 p-2 rounded text-sm font-mono">
                        {rule.raw}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'routes' && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium">Routing Table</h3>
            <div className="bg-gray-800 p-4 rounded-lg">
              <p className="text-sm text-gray-400 mb-3">Current routing configuration:</p>
              <div className="text-sm text-gray-500">
                Routing table management coming soon...
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};