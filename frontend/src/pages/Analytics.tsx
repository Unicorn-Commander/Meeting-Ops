import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  TrendingUp, Clock, Users, FileText, Calendar, Target,
  Activity, Zap, Filter, Download, RefreshCw, ChevronRight
} from 'lucide-react';

interface AnalyticsData {
  speakingTime: Array<{ name: string; time: number; percentage: number }>;
  keywords: Array<{ word: string; frequency: number }>;
  meetingTrends: Array<{ date: string; duration: number; sessions: number }>;
  actionItems: {
    total: number;
    completed: number;
    pending: number;
    overdue: number;
  };
  sessionStats: {
    totalSessions: number;
    totalDuration: number;
    averageDuration: number;
    totalSpeakers: number;
  };
}

const COLORS = ['#8B5CF6', '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#EC4899'];

export const Analytics: React.FC = () => {
  const [timeRange, setTimeRange] = useState<'week' | 'month' | 'quarter' | 'year'>('month');
  const [loading, setLoading] = useState(true);
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData>({
    speakingTime: [
      { name: 'John Smith', time: 1250, percentage: 35 },
      { name: 'Jane Doe', time: 980, percentage: 28 },
      { name: 'Mike Johnson', time: 750, percentage: 21 },
      { name: 'Sarah Wilson', time: 570, percentage: 16 }
    ],
    keywords: [
      { word: 'project', frequency: 45 },
      { word: 'deadline', frequency: 38 },
      { word: 'budget', frequency: 32 },
      { word: 'meeting', frequency: 28 },
      { word: 'review', frequency: 25 },
      { word: 'milestone', frequency: 22 },
      { word: 'strategy', frequency: 20 },
      { word: 'customer', frequency: 18 }
    ],
    meetingTrends: [
      { date: 'Mon', duration: 125, sessions: 4 },
      { date: 'Tue', duration: 180, sessions: 6 },
      { date: 'Wed', duration: 210, sessions: 7 },
      { date: 'Thu', duration: 165, sessions: 5 },
      { date: 'Fri', duration: 145, sessions: 5 },
      { date: 'Sat', duration: 30, sessions: 1 },
      { date: 'Sun', duration: 0, sessions: 0 }
    ],
    actionItems: {
      total: 24,
      completed: 15,
      pending: 7,
      overdue: 2
    },
    sessionStats: {
      totalSessions: 28,
      totalDuration: 855,
      averageDuration: 30.5,
      totalSpeakers: 12
    }
  });

  useEffect(() => {
    // Simulate loading data
    setTimeout(() => {
      setLoading(false);
    }, 1000);
  }, [timeRange]);

  const formatDuration = (minutes: number): string => {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    }
    return `${mins}m`;
  };

  const actionItemsData = [
    { name: 'Completed', value: analyticsData.actionItems.completed, color: '#10B981' },
    { name: 'Pending', value: analyticsData.actionItems.pending, color: '#F59E0B' },
    { name: 'Overdue', value: analyticsData.actionItems.overdue, color: '#EF4444' }
  ];

  const completionRate = Math.round((analyticsData.actionItems.completed / analyticsData.actionItems.total) * 100);

  const exportAnalytics = () => {
    const data = {
      timeRange,
      exportDate: new Date().toISOString(),
      ...analyticsData
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `analytics_${timeRange}_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
                <Activity className="w-8 h-8 text-purple-600" />
                Meeting Analytics
              </h1>
              <p className="text-gray-600 mt-2">
                Insights and trends from your meeting recordings
              </p>
            </div>
            
            <div className="flex items-center gap-3">
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value as any)}
                className="px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="week">This Week</option>
                <option value="month">This Month</option>
                <option value="quarter">This Quarter</option>
                <option value="year">This Year</option>
              </select>
              
              <button
                onClick={() => setLoading(true)}
                className="p-2 bg-white border rounded-lg hover:bg-gray-50"
                title="Refresh"
              >
                <RefreshCw className="w-5 h-5" />
              </button>
              
              <button
                onClick={exportAnalytics}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                Export
              </button>
            </div>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <FileText className="w-8 h-8 text-purple-600" />
              <span className="text-2xl font-bold">{analyticsData.sessionStats.totalSessions}</span>
            </div>
            <p className="text-gray-600 text-sm">Total Sessions</p>
            <p className="text-xs text-green-600 mt-1">+12% from last period</p>
          </div>
          
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <Clock className="w-8 h-8 text-blue-600" />
              <span className="text-2xl font-bold">{formatDuration(analyticsData.sessionStats.totalDuration)}</span>
            </div>
            <p className="text-gray-600 text-sm">Total Duration</p>
            <p className="text-xs text-green-600 mt-1">+8% from last period</p>
          </div>
          
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <Users className="w-8 h-8 text-green-600" />
              <span className="text-2xl font-bold">{analyticsData.sessionStats.totalSpeakers}</span>
            </div>
            <p className="text-gray-600 text-sm">Unique Speakers</p>
            <p className="text-xs text-green-600 mt-1">+3 new this period</p>
          </div>
          
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-2">
              <Target className="w-8 h-8 text-orange-600" />
              <span className="text-2xl font-bold">{completionRate}%</span>
            </div>
            <p className="text-gray-600 text-sm">Action Items Completed</p>
            <p className="text-xs text-gray-500 mt-1">{analyticsData.actionItems.completed} of {analyticsData.actionItems.total}</p>
          </div>
        </div>

        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Speaking Time Distribution */}
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-purple-600" />
              Speaking Time Distribution
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={analyticsData.speakingTime}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percentage }) => `${name}: ${percentage}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="time"
                >
                  {analyticsData.speakingTime.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatDuration(value)} />
              </PieChart>
            </ResponsiveContainer>
            
            {/* Legend */}
            <div className="mt-4 space-y-2">
              {analyticsData.speakingTime.map((speaker, index) => (
                <div key={speaker.name} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full" 
                      style={{ backgroundColor: COLORS[index % COLORS.length] }}
                    />
                    <span>{speaker.name}</span>
                  </div>
                  <span className="text-gray-600">{formatDuration(speaker.time)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Keywords Frequency */}
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-purple-600" />
              Top Keywords
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={analyticsData.keywords}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="word" angle={-45} textAnchor="end" height={60} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="frequency" fill="#8B5CF6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Meeting Duration Trends */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-purple-600" />
            Meeting Duration Trends
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={analyticsData.meetingTrends}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis yAxisId="left" label={{ value: 'Duration (min)', angle: -90, position: 'insideLeft' }} />
              <YAxis yAxisId="right" orientation="right" label={{ value: 'Sessions', angle: 90, position: 'insideRight' }} />
              <Tooltip />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="duration" stroke="#8B5CF6" name="Total Duration" strokeWidth={2} />
              <Line yAxisId="right" type="monotone" dataKey="sessions" stroke="#3B82F6" name="Number of Sessions" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Action Items Completion */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Target className="w-5 h-5 text-purple-600" />
              Action Items Status
            </h2>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={actionItemsData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  fill="#8884d8"
                  paddingAngle={5}
                  dataKey="value"
                >
                  {actionItemsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            
            <div className="mt-4 space-y-2">
              {actionItemsData.map((item) => (
                <div key={item.name} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full" 
                      style={{ backgroundColor: item.color }}
                    />
                    <span>{item.name}</span>
                  </div>
                  <span className="font-semibold">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-white rounded-lg shadow-sm p-6 lg:col-span-2">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-purple-600" />
              Recent Activity
            </h2>
            <div className="space-y-3">
              {[
                { time: '2 hours ago', event: 'Weekly Team Standup', duration: '15m', speakers: 5 },
                { time: '5 hours ago', event: 'Client Review Meeting', duration: '45m', speakers: 3 },
                { time: 'Yesterday', event: 'Product Planning Session', duration: '1h 20m', speakers: 8 },
                { time: 'Yesterday', event: 'One-on-One Check-in', duration: '30m', speakers: 2 },
                { time: '2 days ago', event: 'Department All-Hands', duration: '1h', speakers: 15 }
              ].map((activity, index) => (
                <div key={index} className="flex items-center justify-between py-2 border-b last:border-0">
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">{activity.event}</p>
                    <p className="text-sm text-gray-500">{activity.time}</p>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-gray-600">
                    <span className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      {activity.duration}
                    </span>
                    <span className="flex items-center gap-1">
                      <Users className="w-4 h-4" />
                      {activity.speakers}
                    </span>
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* NPU Performance Card */}
        <div className="bg-gradient-to-r from-purple-600 to-indigo-600 rounded-lg shadow-sm p-6 mt-8 text-white">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-semibold flex items-center gap-2">
                <Zap className="w-6 h-6" />
                NPU Acceleration Active
              </h3>
              <p className="mt-2 text-purple-100">
                Processing meetings 220x faster with AMD Phoenix NPU
              </p>
              <div className="mt-4 grid grid-cols-3 gap-4">
                <div>
                  <p className="text-2xl font-bold">0.0045</p>
                  <p className="text-sm text-purple-200">RTF (Real-time Factor)</p>
                </div>
                <div>
                  <p className="text-2xl font-bold">4,789</p>
                  <p className="text-sm text-purple-200">Tokens/second</p>
                </div>
                <div>
                  <p className="text-2xl font-bold">16.2s</p>
                  <p className="text-sm text-purple-200">to process 1 hour</p>
                </div>
              </div>
            </div>
            <div className="text-6xl opacity-20">
              <Zap />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};