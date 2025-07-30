import React, { useState, useEffect } from 'react';
import {
  Shield,
  Activity,
  AlertTriangle,
  User,
  Clock,
  Search,
  Filter,
  Download,
  RefreshCw,
  Eye,
  Lock,
  Unlock,
  UserX,
  Settings,
  FileText,
  Trash2,
  ChevronDown,
  ChevronRight,
  Calendar
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface AuditLogEntry {
  id: string;
  timestamp: string;
  user_id: string;
  username: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  ip_address: string;
  user_agent: string;
  status: 'success' | 'failure' | 'warning';
  details?: any;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
}

interface SecurityPolicy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  severity: 'info' | 'warning' | 'error';
  last_triggered?: string;
  trigger_count: number;
}

interface SecurityMetrics {
  total_events_24h: number;
  failed_logins_24h: number;
  suspicious_activities: number;
  active_sessions: number;
  blocked_ips: string[];
  security_score: number;
}

export const SecurityCenter: React.FC = () => {
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [securityPolicies, setSecurityPolicies] = useState<SecurityPolicy[]>([]);
  const [securityMetrics, setSecurityMetrics] = useState<SecurityMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterAction, setFilterAction] = useState('all');
  const [filterRisk, setFilterRisk] = useState('all');
  const [filterTimeRange, setFilterTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h');
  const [selectedLog, setSelectedLog] = useState<AuditLogEntry | null>(null);
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadSecurityData();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadSecurityData, 30000);
    return () => clearInterval(interval);
  }, [filterTimeRange]);

  const loadSecurityData = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Load audit logs
      const auditResponse = await fetch(
        `${API_BASE_URL}/api/security/audit-logs?range=${filterTimeRange}`,
        { headers }
      );
      
      if (auditResponse.ok) {
        const auditData = await auditResponse.json();
        setAuditLogs(auditData);
      } else {
        // Mock data for testing
        setAuditLogs([
          {
            id: '1',
            timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
            user_id: 'admin-123',
            username: 'admin',
            action: 'login_success',
            resource_type: 'authentication',
            ip_address: '192.168.1.100',
            user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            status: 'success',
            risk_level: 'low'
          },
          {
            id: '2',
            timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
            user_id: 'user-456',
            username: 'john.doe',
            action: 'session_create',
            resource_type: 'recording_session',
            resource_id: 'session-789',
            ip_address: '192.168.1.105',
            user_agent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            status: 'success',
            risk_level: 'low'
          },
          {
            id: '3',
            timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
            user_id: 'unknown',
            username: 'unknown',
            action: 'login_failure',
            resource_type: 'authentication',
            ip_address: '203.0.113.42',
            user_agent: 'curl/7.68.0',
            status: 'failure',
            risk_level: 'high',
            details: { reason: 'Invalid credentials', attempts: 5 }
          },
          {
            id: '4',
            timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
            user_id: 'admin-123',
            username: 'admin',
            action: 'user_create',
            resource_type: 'user',
            resource_id: 'user-999',
            ip_address: '192.168.1.100',
            user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            status: 'success',
            risk_level: 'medium'
          }
        ]);
      }

      // Load security policies
      const policiesResponse = await fetch(`${API_BASE_URL}/api/security/policies`, { headers });
      
      if (policiesResponse.ok) {
        const policiesData = await policiesResponse.json();
        setSecurityPolicies(policiesData);
      } else {
        // Mock data for testing
        setSecurityPolicies([
          {
            id: 'failed_login_attempts',
            name: 'Failed Login Attempts',
            description: 'Monitor and block IPs after 5 failed login attempts',
            enabled: true,
            severity: 'warning',
            last_triggered: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
            trigger_count: 3
          },
          {
            id: 'suspicious_user_agents',
            name: 'Suspicious User Agents',
            description: 'Flag requests from automated tools and bots',
            enabled: true,
            severity: 'info',
            trigger_count: 12
          },
          {
            id: 'privilege_escalation',
            name: 'Privilege Escalation',
            description: 'Alert on attempts to access admin functions',
            enabled: true,
            severity: 'error',
            trigger_count: 0
          },
          {
            id: 'data_export_anomaly',
            name: 'Data Export Anomaly',
            description: 'Monitor unusual data export patterns',
            enabled: false,
            severity: 'warning',
            trigger_count: 1
          }
        ]);
      }

      // Load security metrics
      const metricsResponse = await fetch(`${API_BASE_URL}/api/security/metrics`, { headers });
      
      if (metricsResponse.ok) {
        const metricsData = await metricsResponse.json();
        setSecurityMetrics(metricsData);
      } else {
        // Mock data for testing
        setSecurityMetrics({
          total_events_24h: 1247,
          failed_logins_24h: 8,
          suspicious_activities: 3,
          active_sessions: 12,
          blocked_ips: ['203.0.113.42', '198.51.100.123'],
          security_score: 85
        });
      }
    } catch (error) {
      console.error('Failed to load security data:', error);
    } finally {
      setLoading(false);
    }
  };

  const exportAuditLogs = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${API_BASE_URL}/api/security/audit-logs/export?format=csv&range=${filterTimeRange}`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `audit-logs-${filterTimeRange}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to export audit logs:', error);
    }
  };

  const toggleLogExpansion = (logId: string) => {
    const newExpanded = new Set(expandedLogs);
    if (newExpanded.has(logId)) {
      newExpanded.delete(logId);
    } else {
      newExpanded.add(logId);
    }
    setExpandedLogs(newExpanded);
  };

  const getActionIcon = (action: string) => {
    switch (action) {
      case 'login_success':
      case 'login_failure':
        return <Lock className="w-4 h-4" />;
      case 'session_create':
      case 'session_delete':
        return <FileText className="w-4 h-4" />;
      case 'user_create':
      case 'user_delete':
        return <User className="w-4 h-4" />;
      case 'settings_change':
        return <Settings className="w-4 h-4" />;
      default:
        return <Activity className="w-4 h-4" />;
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'critical':
        return 'text-red-400 bg-red-900/20';
      case 'high':
        return 'text-orange-400 bg-orange-900/20';
      case 'medium':
        return 'text-yellow-400 bg-yellow-900/20';
      case 'low':
        return 'text-green-400 bg-green-900/20';
      default:
        return 'text-gray-400 bg-gray-900/20';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'text-green-400';
      case 'failure':
        return 'text-red-400';
      case 'warning':
        return 'text-yellow-400';
      default:
        return 'text-gray-400';
    }
  };

  const filteredLogs = auditLogs.filter(log => {
    const matchesSearch = searchTerm === '' || 
      log.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.ip_address.includes(searchTerm);
    
    const matchesAction = filterAction === 'all' || log.action.includes(filterAction);
    const matchesRisk = filterRisk === 'all' || log.risk_level === filterRisk;
    
    return matchesSearch && matchesAction && matchesRisk;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Shield className="w-8 h-8 text-blue-400" />
            Security Center
          </h1>
          <p className="text-gray-400">Audit logs & security monitoring</p>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={exportAuditLogs}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
          >
            <Download className="w-4 h-4" />
            Export Logs
          </button>
          <button
            onClick={loadSecurityData}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Security Metrics */}
      {securityMetrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <Activity className="w-6 h-6 text-blue-400" />
              <span className="text-2xl font-bold">{securityMetrics.total_events_24h}</span>
            </div>
            <p className="text-sm text-gray-400">Total Events (24h)</p>
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <Lock className="w-6 h-6 text-red-400" />
              <span className="text-2xl font-bold text-red-400">{securityMetrics.failed_logins_24h}</span>
            </div>
            <p className="text-sm text-gray-400">Failed Logins (24h)</p>
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <AlertTriangle className="w-6 h-6 text-yellow-400" />
              <span className="text-2xl font-bold text-yellow-400">{securityMetrics.suspicious_activities}</span>
            </div>
            <p className="text-sm text-gray-400">Suspicious Activities</p>
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <User className="w-6 h-6 text-green-400" />
              <span className="text-2xl font-bold">{securityMetrics.active_sessions}</span>
            </div>
            <p className="text-sm text-gray-400">Active Sessions</p>
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <UserX className="w-6 h-6 text-red-400" />
              <span className="text-2xl font-bold">{securityMetrics.blocked_ips.length}</span>
            </div>
            <p className="text-sm text-gray-400">Blocked IPs</p>
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <Shield className="w-6 h-6 text-purple-400" />
              <span className={`text-2xl font-bold ${securityMetrics.security_score >= 80 ? 'text-green-400' : securityMetrics.security_score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                {securityMetrics.security_score}%
              </span>
            </div>
            <p className="text-sm text-gray-400">Security Score</p>
          </div>
        </div>
      )}

      {/* Security Policies */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5 text-orange-400" />
          Security Policies
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {securityPolicies.map((policy) => (
            <div key={policy.id} className="bg-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-medium">{policy.name}</h3>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs ${
                    policy.severity === 'error' ? 'bg-red-900/20 text-red-400' :
                    policy.severity === 'warning' ? 'bg-yellow-900/20 text-yellow-400' :
                    'bg-blue-900/20 text-blue-400'
                  }`}>
                    {policy.severity}
                  </span>
                  <button
                    className={`w-8 h-4 rounded-full transition-colors ${
                      policy.enabled ? 'bg-green-600' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-3 h-3 bg-white rounded-full transition-transform ${
                      policy.enabled ? 'translate-x-4' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
              </div>
              <p className="text-sm text-gray-400 mb-2">{policy.description}</p>
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Triggered: {policy.trigger_count} times</span>
                {policy.last_triggered && (
                  <span>Last: {new Date(policy.last_triggered).toLocaleDateString()}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Audit Logs */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <FileText className="w-5 h-5 text-green-400" />
              Audit Logs
            </h2>
            <div className="flex items-center gap-2">
              <select
                value={filterTimeRange}
                onChange={(e) => setFilterTimeRange(e.target.value as any)}
                className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm"
              >
                <option value="1h">Last Hour</option>
                <option value="24h">Last 24 Hours</option>
                <option value="7d">Last 7 Days</option>
                <option value="30d">Last 30 Days</option>
              </select>
            </div>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search logs..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm w-64"
              />
            </div>
            
            <select
              value={filterAction}
              onChange={(e) => setFilterAction(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm"
            >
              <option value="all">All Actions</option>
              <option value="login">Login Events</option>
              <option value="session">Session Events</option>
              <option value="user">User Events</option>
              <option value="settings">Settings</option>
            </select>

            <select
              value={filterRisk}
              onChange={(e) => setFilterRisk(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm"
            >
              <option value="all">All Risk Levels</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        {/* Log Entries */}
        <div className="divide-y divide-gray-700">
          {filteredLogs.map((log) => (
            <div key={log.id} className="p-4 hover:bg-gray-750 transition-colors">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 flex-1">
                  <button
                    onClick={() => toggleLogExpansion(log.id)}
                    className="text-gray-400 hover:text-white"
                  >
                    {expandedLogs.has(log.id) ? (
                      <ChevronDown className="w-4 h-4" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    )}
                  </button>

                  <div className={`p-2 rounded ${getStatusColor(log.status)}`}>
                    {getActionIcon(log.action)}
                  </div>

                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">{log.username}</span>
                      <span className="text-gray-400">•</span>
                      <span className="text-sm text-gray-400">{log.action.replace('_', ' ')}</span>
                      <span className={`px-2 py-1 rounded text-xs ${getRiskColor(log.risk_level)}`}>
                        {log.risk_level}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <Clock className="w-3 h-3" />
                      <span>{new Date(log.timestamp).toLocaleString()}</span>
                      <span>•</span>
                      <span>{log.ip_address}</span>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedLog(log)}
                  className="p-2 text-gray-400 hover:text-white transition-colors"
                  title="View Details"
                >
                  <Eye className="w-4 h-4" />
                </button>
              </div>

              {expandedLogs.has(log.id) && (
                <div className="mt-4 ml-12 p-4 bg-gray-700 rounded-lg">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">Resource Type:</span>
                      <span className="ml-2">{log.resource_type}</span>
                    </div>
                    {log.resource_id && (
                      <div>
                        <span className="text-gray-400">Resource ID:</span>
                        <span className="ml-2 font-mono text-xs">{log.resource_id}</span>
                      </div>
                    )}
                    <div>
                      <span className="text-gray-400">User Agent:</span>
                      <span className="ml-2 text-xs">{log.user_agent.substring(0, 50)}...</span>
                    </div>
                    <div>
                      <span className="text-gray-400">Status:</span>
                      <span className={`ml-2 ${getStatusColor(log.status)}`}>{log.status}</span>
                    </div>
                  </div>
                  {log.details && (
                    <div className="mt-3">
                      <span className="text-gray-400">Details:</span>
                      <pre className="mt-2 p-2 bg-gray-800 rounded text-xs overflow-auto">
                        {JSON.stringify(log.details, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {filteredLogs.length === 0 && (
          <div className="p-8 text-center text-gray-400">
            <FileText className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>No audit logs found matching your criteria</p>
          </div>
        )}
      </div>
    </div>
  );
};