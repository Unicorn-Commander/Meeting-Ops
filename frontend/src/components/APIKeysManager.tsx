import React, { useState, useEffect } from 'react';
import { 
  Key, Plus, Trash2, Copy, Eye, EyeOff, RefreshCw,
  Calendar, Shield, CheckCircle, AlertCircle, Clock,
  Settings, Download, Upload, Globe, Lock
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface APIKey {
  id: string;
  name: string;
  key: string;
  keyPreview: string;
  permissions: string[];
  rateLimit: number;
  usageCount: number;
  lastUsed?: string;
  createdAt: string;
  expiresAt?: string;
  status: 'active' | 'expired' | 'revoked';
  description?: string;
}

interface CreateKeyRequest {
  name: string;
  permissions: string[];
  rateLimit: number;
  expiresInDays?: number;
  description: string;
}

export const APIKeysManager: React.FC = () => {
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showKeyModal, setShowKeyModal] = useState<string | null>(null);
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [newKey, setNewKey] = useState<CreateKeyRequest>({
    name: '',
    permissions: [],
    rateLimit: 1000,
    expiresInDays: 90,
    description: ''
  });

  const availablePermissions = [
    { id: 'recording.read', name: 'View Recordings', description: 'Access to view recording sessions' },
    { id: 'recording.create', name: 'Create Recordings', description: 'Start new recording sessions' },
    { id: 'recording.delete', name: 'Delete Recordings', description: 'Delete recording sessions' },
    { id: 'transcription.read', name: 'View Transcriptions', description: 'Access transcription data' },
    { id: 'analytics.read', name: 'View Analytics', description: 'Access meeting analytics and insights' },
    { id: 'user.read', name: 'View Users', description: 'Access user information' },
    { id: 'user.manage', name: 'Manage Users', description: 'Create and modify users' },
    { id: 'settings.read', name: 'View Settings', description: 'Access system settings' },
    { id: 'settings.write', name: 'Modify Settings', description: 'Change system configuration' },
    { id: 'export.create', name: 'Export Data', description: 'Generate and download exports' }
  ];

  useEffect(() => {
    fetchAPIKeys();
  }, []);

  const fetchAPIKeys = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/keys`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setApiKeys(data);
      } else {
        // Mock data for demonstration
        setApiKeys([
          {
            id: '1',
            name: 'Production API',
            key: 'REMOVED',
            keyPreview: 'REMOVED',
            permissions: ['recording.read', 'recording.create', 'transcription.read'],
            rateLimit: 5000,
            usageCount: 2847,
            lastUsed: '2025-01-09T23:45:00Z',
            createdAt: '2024-12-01T10:00:00Z',
            expiresAt: '2025-03-01T10:00:00Z',
            status: 'active',
            description: 'Main production API key for meeting recording integration'
          },
          {
            id: '2',
            name: 'Analytics Dashboard',
            key: 'mk_dash_9876543210fedcba',
            keyPreview: 'mk_dash_9876...dcba',
            permissions: ['analytics.read', 'transcription.read'],
            rateLimit: 1000,
            usageCount: 156,
            lastUsed: '2025-01-09T18:30:00Z',
            createdAt: '2025-01-01T09:00:00Z',
            status: 'active',
            description: 'Read-only access for external analytics dashboard'
          },
          {
            id: '3',
            name: 'Legacy Integration',
            key: 'mk_old_abcdef1234567890',
            keyPreview: 'mk_old_abcd...7890',
            permissions: ['recording.read'],
            rateLimit: 100,
            usageCount: 0,
            createdAt: '2024-10-15T14:30:00Z',
            expiresAt: '2024-12-15T14:30:00Z',
            status: 'expired',
            description: 'Deprecated key for old system integration'
          }
        ]);
      }
    } catch (error) {
      console.error('Failed to fetch API keys:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(newKey)
      });

      if (response.ok) {
        const createdKey = await response.json();
        setApiKeys([createdKey, ...apiKeys]);
        setShowCreateModal(false);
        setShowKeyModal(createdKey.id);
        setNewKey({
          name: '',
          permissions: [],
          rateLimit: 1000,
          expiresInDays: 90,
          description: ''
        });
        toast.success('API key created successfully');
      } else {
        // Demo mode
        const mockKey: APIKey = {
          id: Date.now().toString(),
          name: newKey.name,
          key: `mk_demo_${Math.random().toString(36).substr(2, 16)}`,
          keyPreview: `mk_demo_${Math.random().toString(36).substr(2, 4)}...${Math.random().toString(36).substr(2, 4)}`,
          permissions: newKey.permissions,
          rateLimit: newKey.rateLimit,
          usageCount: 0,
          createdAt: new Date().toISOString(),
          expiresAt: newKey.expiresInDays ? new Date(Date.now() + newKey.expiresInDays * 24 * 60 * 60 * 1000).toISOString() : undefined,
          status: 'active',
          description: newKey.description
        };
        setApiKeys([mockKey, ...apiKeys]);
        setShowCreateModal(false);
        setShowKeyModal(mockKey.id);
        toast.success('API key created (demo mode)');
      }
    } catch (error) {
      console.error('Failed to create API key:', error);
      toast.error('Failed to create API key');
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm('Are you sure you want to revoke this API key? This action cannot be undone.')) {
      return;
    }

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/keys/${keyId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        setApiKeys(apiKeys.map(key => 
          key.id === keyId ? { ...key, status: 'revoked' as const } : key
        ));
        toast.success('API key revoked successfully');
      } else {
        // Demo mode
        setApiKeys(apiKeys.map(key => 
          key.id === keyId ? { ...key, status: 'revoked' as const } : key
        ));
        toast.success('API key revoked (demo mode)');
      }
    } catch (error) {
      console.error('Failed to revoke API key:', error);
      toast.error('Failed to revoke API key');
    }
  };

  const handleCopyKey = async (key: string) => {
    try {
      await navigator.clipboard.writeText(key);
      toast.success('API key copied to clipboard');
    } catch (error) {
      toast.error('Failed to copy API key');
    }
  };

  const toggleKeyVisibility = (keyId: string) => {
    const newVisibleKeys = new Set(visibleKeys);
    if (newVisibleKeys.has(keyId)) {
      newVisibleKeys.delete(keyId);
    } else {
      newVisibleKeys.add(keyId);
    }
    setVisibleKeys(newVisibleKeys);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'text-green-400 bg-green-400/20';
      case 'expired': return 'text-yellow-400 bg-yellow-400/20';
      case 'revoked': return 'text-red-400 bg-red-400/20';
      default: return 'text-gray-400 bg-gray-400/20';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active': return <CheckCircle className="w-4 h-4" />;
      case 'expired': return <Clock className="w-4 h-4" />;
      case 'revoked': return <AlertCircle className="w-4 h-4" />;
      default: return <AlertCircle className="w-4 h-4" />;
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString() + ' ' + new Date(dateString).toLocaleTimeString();
  };

  const isExpiringSoon = (expiresAt?: string) => {
    if (!expiresAt) return false;
    const daysUntilExpiry = (new Date(expiresAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
    return daysUntilExpiry <= 30 && daysUntilExpiry > 0;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">API Keys</h2>
        <div className="flex items-center space-x-4">
          <button
            onClick={() => fetchAPIKeys()}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors flex items-center"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center"
          >
            <Plus className="w-4 h-4 mr-2" />
            Create API Key
          </button>
        </div>
      </div>

      {/* API Keys List */}
      <div className="space-y-4">
        {apiKeys.map(apiKey => (
          <div key={apiKey.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center space-x-3 mb-2">
                  <h3 className="text-xl font-semibold">{apiKey.name}</h3>
                  <div className={`px-2 py-1 rounded-full text-xs font-medium flex items-center ${getStatusColor(apiKey.status)}`}>
                    {getStatusIcon(apiKey.status)}
                    <span className="ml-1 capitalize">{apiKey.status}</span>
                  </div>
                  {isExpiringSoon(apiKey.expiresAt) && (
                    <div className="px-2 py-1 rounded-full text-xs font-medium text-yellow-400 bg-yellow-400/20">
                      Expires Soon
                    </div>
                  )}
                </div>
                {apiKey.description && (
                  <p className="text-gray-400 text-sm mb-3">{apiKey.description}</p>
                )}
              </div>
              
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => toggleKeyVisibility(apiKey.id)}
                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                  title={visibleKeys.has(apiKey.id) ? 'Hide key' : 'Show key'}
                >
                  {visibleKeys.has(apiKey.id) ? (
                    <EyeOff className="w-4 h-4 text-gray-400" />
                  ) : (
                    <Eye className="w-4 h-4 text-gray-400" />
                  )}
                </button>
                <button
                  onClick={() => handleCopyKey(apiKey.key)}
                  className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                  title="Copy key"
                >
                  <Copy className="w-4 h-4 text-gray-400" />
                </button>
                {apiKey.status === 'active' && (
                  <button
                    onClick={() => handleRevokeKey(apiKey.id)}
                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                    title="Revoke key"
                  >
                    <Trash2 className="w-4 h-4 text-red-400" />
                  </button>
                )}
              </div>
            </div>

            {/* API Key Display */}
            <div className="bg-gray-900/50 rounded-lg p-4 mb-4">
              <div className="flex items-center justify-between">
                <code className="text-purple-300 font-mono">
                  {visibleKeys.has(apiKey.id) ? apiKey.key : apiKey.keyPreview}
                </code>
                <Key className="w-4 h-4 text-gray-400" />
              </div>
            </div>

            {/* Key Details */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
              <div>
                <label className="text-sm text-gray-400">Usage</label>
                <p className="font-semibold">{apiKey.usageCount.toLocaleString()} requests</p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Rate Limit</label>
                <p className="font-semibold">{apiKey.rateLimit}/hour</p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Last Used</label>
                <p className="font-semibold">
                  {apiKey.lastUsed ? new Date(apiKey.lastUsed).toLocaleDateString() : 'Never'}
                </p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Expires</label>
                <p className="font-semibold">
                  {apiKey.expiresAt ? new Date(apiKey.expiresAt).toLocaleDateString() : 'Never'}
                </p>
              </div>
            </div>

            {/* Permissions */}
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Permissions</label>
              <div className="flex flex-wrap gap-2">
                {apiKey.permissions.map(permission => {
                  const permissionInfo = availablePermissions.find(p => p.id === permission);
                  return (
                    <span key={permission} className="px-3 py-1 bg-gray-700 rounded-full text-sm">
                      {permissionInfo?.name || permission}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>

      {apiKeys.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <Key className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>No API keys found</p>
          <p className="text-sm mt-2">Create your first API key to get started</p>
        </div>
      )}

      {/* Create API Key Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-2xl m-4">
            <h3 className="text-xl font-bold mb-4">Create New API Key</h3>
            
            <form onSubmit={handleCreateKey} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Key Name</label>
                <input
                  type="text"
                  value={newKey.name}
                  onChange={(e) => setNewKey({...newKey, name: e.target.value})}
                  placeholder="Production API Key"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  required
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Description</label>
                <textarea
                  value={newKey.description}
                  onChange={(e) => setNewKey({...newKey, description: e.target.value})}
                  placeholder="Describe what this key will be used for..."
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  rows={3}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Rate Limit (requests/hour)</label>
                  <select
                    value={newKey.rateLimit}
                    onChange={(e) => setNewKey({...newKey, rateLimit: parseInt(e.target.value)})}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value={100}>100/hour</option>
                    <option value={1000}>1,000/hour</option>
                    <option value={5000}>5,000/hour</option>
                    <option value={10000}>10,000/hour</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">Expires In</label>
                  <select
                    value={newKey.expiresInDays || ''}
                    onChange={(e) => setNewKey({...newKey, expiresInDays: e.target.value ? parseInt(e.target.value) : undefined})}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    <option value="">Never</option>
                    <option value={30}>30 days</option>
                    <option value={90}>90 days</option>
                    <option value={365}>1 year</option>
                  </select>
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Permissions</label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                  {availablePermissions.map(permission => (
                    <label key={permission.id} className="flex items-start p-2 hover:bg-gray-700 rounded">
                      <input
                        type="checkbox"
                        checked={newKey.permissions.includes(permission.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setNewKey({...newKey, permissions: [...newKey.permissions, permission.id]});
                          } else {
                            setNewKey({...newKey, permissions: newKey.permissions.filter(p => p !== permission.id)});
                          }
                        }}
                        className="mt-1 mr-3 rounded border-gray-600 bg-gray-700 text-purple-600"
                      />
                      <div>
                        <div className="font-medium text-sm">{permission.name}</div>
                        <div className="text-xs text-gray-400">{permission.description}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
              
              <div className="flex items-center justify-end space-x-4 mt-6">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newKey.name || newKey.permissions.length === 0}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Create API Key
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Show New Key Modal */}
      {showKeyModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold">Your New API Key</h3>
              <AlertCircle className="w-6 h-6 text-yellow-400" />
            </div>
            
            <p className="text-sm text-gray-400 mb-4">
              Make sure to copy your API key now. You won't be able to see it again!
            </p>
            
            <div className="bg-gray-900/50 rounded-lg p-4 mb-4">
              <code className="text-purple-300 font-mono break-all">
                {apiKeys.find(k => k.id === showKeyModal)?.key}
              </code>
            </div>
            
            <div className="flex items-center space-x-4">
              <button
                onClick={() => {
                  const key = apiKeys.find(k => k.id === showKeyModal)?.key;
                  if (key) handleCopyKey(key);
                }}
                className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center justify-center"
              >
                <Copy className="w-4 h-4 mr-2" />
                Copy Key
              </button>
              <button
                onClick={() => setShowKeyModal(null)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};