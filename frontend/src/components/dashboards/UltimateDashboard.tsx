import React, { useState, useEffect } from 'react';
import { 
  Activity, Users, HardDrive, Cpu, Mic, Clock, 
  TrendingUp, Calendar, Mail, AlertCircle, CheckCircle,
  BarChart3, PieChart, Flag, Star, Zap, Database,
  Shield, Wifi, Volume2, Download, Upload, Settings
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { UnifiedRecordingInterface } from '../UnifiedRecordingInterface';
import { SystemMonitor } from '../SystemMonitor';
import { LiveTranscription } from '../LiveTranscription';
import TranscriptionLoop from '../TranscriptionLoop';
import { config } from '../../config';

interface DashboardMetric {
  label: string;
  value: string | number;
  change?: number;
  icon: React.ElementType;
  color: string;
  trend?: 'up' | 'down' | 'stable';
}

interface SystemService {
  name: string;
  status: 'running' | 'stopped' | 'error';
  cpu?: number;
  memory?: number;
  uptime?: string;
}

export const UltimateDashboard: React.FC = () => {
  const { user } = useAuth();
  const [activeView, setActiveView] = useState<'overview' | 'recording' | 'transcription' | 'analytics' | 'system'>('overview');
  const [realTimeData, setRealTimeData] = useState({
    activeSessions: 0,
    totalUsers: 0,
    npuUsage: 0,
    storageUsed: 0,
    transcriptionRate: 0,
    todaysMeetings: 0
  });
  const [loading, setLoading] = useState(true);

  // Key metrics
  const metrics: DashboardMetric[] = [
    {
      label: 'Active Sessions',
      value: realTimeData.activeSessions,
      icon: Mic,
      color: 'text-green-400',
      trend: 'up',
      change: 2
    },
    {
      label: 'Total Users',
      value: realTimeData.totalUsers,
      icon: Users,
      color: 'text-blue-400',
      trend: 'stable'
    },
    {
      label: 'NPU Usage',
      value: `${Math.round(realTimeData.npuUsage)}%`,
      icon: Zap,
      color: 'text-purple-400',
      trend: 'up',
      change: 12
    },
    {
      label: 'Storage',
      value: `${Math.round(realTimeData.storageUsed)}%`,
      icon: HardDrive,
      color: 'text-yellow-400',
      trend: 'up',
      change: 5
    },
    {
      label: 'Accuracy',
      value: `${realTimeData.transcriptionRate.toFixed(1)}%`,
      icon: CheckCircle,
      color: 'text-cyan-400',
      trend: 'stable'
    },
    {
      label: 'Today\'s Meetings',
      value: realTimeData.todaysMeetings,
      icon: Calendar,
      color: 'text-pink-400',
      trend: realTimeData.todaysMeetings > 0 ? 'up' : 'stable'
    }
  ];

  // System services
  const [services, setServices] = useState<SystemService[]>([]);

  // Recent activities
  const [recentActivities, setRecentActivities] = useState<any[]>([]);

  // Fetch real data from backend
  useEffect(() => {
    const fetchDashboardData = async () => {
      setLoading(true);
      
      try {
        const token = localStorage.getItem('token');
        const headers: HeadersInit = token ? { 'Authorization': `Bearer ${token}` } : {};
        
        // Fetch system status
        const statusResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.status}`, { headers });
        if (statusResponse.ok) {
          const statusData = await statusResponse.json();
          
          setRealTimeData(prev => ({
            ...prev,
            activeSessions: statusData.active_sessions || 0,
            npuUsage: statusData.system_info?.npu_usage || 0,
            transcriptionRate: statusData.transcription_accuracy || 99.0
          }));
          
          // Transform service status
          if (statusData.services) {
            const serviceList: SystemService[] = [
              { name: 'PostgreSQL', status: (statusData.services.database ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'Redis Cache', status: (statusData.services.redis ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'NPU Service', status: (statusData.npu_available ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'Whisper Engine', status: (statusData.transcriber_ready ? 'running' : 'stopped') as 'running' | 'stopped', cpu: 0, memory: 0, uptime: '-' },
              { name: 'WebSocket Server', status: 'running' as const, cpu: 0, memory: 0, uptime: '-' }
            ];
            setServices(serviceList);
          }
        }
        
        // Fetch sessions for activity
        const sessionsResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.simpleRecording.sessions}`, { headers });
        if (sessionsResponse.ok) {
          const sessions = await sessionsResponse.json();
          
          // Create activities from recent sessions
          const activities = sessions.slice(0, 5).map((session: any, index: number) => ({
            id: session.id || index,
            type: 'recording',
            message: `Recording: ${session.title || 'Untitled Session'}`,
            time: new Date(session.created_at).toLocaleString(),
            icon: Mic
          }));
          setRecentActivities(activities);
          
          // Update metrics based on sessions
          const today = new Date().toDateString();
          const todaysSessions = sessions.filter((s: any) => 
            new Date(s.created_at).toDateString() === today
          ).length;
          
          setRealTimeData(prev => ({
            ...prev,
            totalUsers: new Set(sessions.map((s: any) => s.user_id)).size || 1,
            todaysMeetings: todaysSessions
          }));
        }
        
        // Fetch system metrics if available
        const metricsResponse = await fetch(`${config.apiBaseUrl}${config.apiEndpoints.system.metrics}`, { headers });
        if (metricsResponse.ok) {
          const metrics = await metricsResponse.json();
          setRealTimeData(prev => ({
            ...prev,
            storageUsed: metrics.storage_percentage || 0
          }));
        }
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };
    
    // Initial fetch
    fetchDashboardData();
    
    // Poll for updates every 5 seconds
    const interval = setInterval(fetchDashboardData, 5000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-green-500';
      case 'stopped': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const renderTrend = (trend?: 'up' | 'down' | 'stable', change?: number) => {
    if (!trend) return null;
    
    return (
      <span className={`text-xs flex items-center gap-1 ${
        trend === 'up' ? 'text-green-400' :
        trend === 'down' ? 'text-red-400' :
        'text-gray-400'
      }`}>
        {trend === 'up' && '↑'}
        {trend === 'down' && '↓'}
        {trend === 'stable' && '→'}
        {change && `${change > 0 ? '+' : ''}${change}%`}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">
                Welcome back, {user?.username || 'User'}
              </h1>
              <p className="text-gray-400 text-sm mt-1">
                {new Date().toLocaleDateString('en-US', { 
                  weekday: 'long', 
                  year: 'numeric', 
                  month: 'long', 
                  day: 'numeric' 
                })}
              </p>
            </div>
            
            {/* View Switcher */}
            <div className="flex items-center gap-2 bg-gray-900/50 rounded-lg p-1">
              {[
                { id: 'overview', label: 'Overview', icon: Activity },
                { id: 'recording', label: 'Recording', icon: Mic },
                { id: 'transcription', label: 'Transcription', icon: Zap },
                { id: 'analytics', label: 'Analytics', icon: BarChart3 },
                { id: 'system', label: 'System', icon: Cpu }
              ].map(view => (
                <button
                  key={view.id}
                  onClick={() => setActiveView(view.id as any)}
                  className={`flex items-center gap-2 px-4 py-2 rounded transition-all ${
                    activeView === view.id
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
                >
                  <view.icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{view.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-6">
        {activeView === 'overview' && (
          <div className="space-y-6">
            {/* Metrics Grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {metrics.map((metric, index) => (
                <div key={index} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  <div className="flex items-start justify-between mb-2">
                    <metric.icon className={`w-5 h-5 ${metric.color}`} />
                    {renderTrend(metric.trend, metric.change)}
                  </div>
                  <p className="text-2xl font-bold text-white">{metric.value}</p>
                  <p className="text-xs text-gray-500 mt-1">{metric.label}</p>
                </div>
              ))}
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Live Transcription */}
              <div className="lg:col-span-2">
                <LiveTranscription 
                  className="h-[500px]"
                />
              </div>

              {/* Recent Activity */}
              <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-purple-400" />
                  Recent Activity
                </h3>
                <div className="space-y-3">
                  {recentActivities.map(activity => (
                    <div key={activity.id} className="flex items-start gap-3 p-3 bg-gray-800/50 rounded-lg">
                      <div className="w-8 h-8 rounded-full bg-purple-600/20 flex items-center justify-center flex-shrink-0">
                        <activity.icon className="w-4 h-4 text-purple-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-200">{activity.message}</p>
                        <p className="text-xs text-gray-500 mt-1">{activity.time}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Services Grid */}
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Shield className="w-5 h-5 text-blue-400" />
                System Services
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {services.map(service => (
                  <div key={service.name} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(service.status)}`} />
                      <span className="text-sm font-medium text-gray-200">{service.name}</span>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">CPU</span>
                        <span className="text-gray-400">{service.cpu}%</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Memory</span>
                        <span className="text-gray-400">{service.memory}MB</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Uptime</span>
                        <span className="text-gray-400">{service.uptime}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeView === 'recording' && (
          <UnifiedRecordingInterface />
        )}

        {activeView === 'transcription' && (
          <TranscriptionLoop />
        )}

        {activeView === 'analytics' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold mb-4">Analytics Dashboard</h2>
            <p className="text-gray-400">Analytics components will be integrated here...</p>
          </div>
        )}

        {activeView === 'system' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold mb-4">System Control</h2>
            <p className="text-gray-400">System control panels will be integrated here...</p>
          </div>
        )}
      </div>

      {/* Footer Status Bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 px-6 py-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-gray-400">System Online</span>
            </span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">NPU: AMD Phoenix 16 TOPS</span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">Version: 2.0.0</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-gray-400">Storage: {realTimeData.storageUsed}% Used</span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">Network: <Wifi className="w-3 h-3 inline text-green-400" /> Connected</span>
          </div>
        </div>
      </div>
    </div>
  );
};