import React, { useState, useEffect } from 'react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Calendar, Clock, Users, Mic, TrendingUp, FileText, Activity } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface AnalyticsData {
  summary: {
    totalMeetings: number;
    totalDuration: number;
    averageDuration: number;
    totalTranscriptions: number;
    totalSpeakers: number;
    npuUsage: number;
  };
  meetingsByDay: Array<{
    date: string;
    count: number;
    duration: number;
  }>;
  meetingsByType: Array<{
    type: string;
    count: number;
    percentage: number;
  }>;
  speakerStats: Array<{
    speaker: string;
    totalTime: number;
    percentage: number;
  }>;
  performanceMetrics: Array<{
    date: string;
    processingTime: number;
    rtf: number;
    npuAcceleration: boolean;
  }>;
  topKeywords: Array<{
    word: string;
    count: number;
  }>;
}

export const MeetingAnalytics: React.FC = () => {
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<'week' | 'month' | 'quarter' | 'year'>('month');
  const [selectedMetric, setSelectedMetric] = useState<'count' | 'duration'>('count');

  useEffect(() => {
    fetchAnalytics();
    
    // Refresh analytics every 30 seconds
    const interval = setInterval(fetchAnalytics, 30000);
    return () => clearInterval(interval);
  }, [timeRange]);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/analytics/meetings?range=${timeRange}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setAnalyticsData(data);
      } else if (response.status === 404) {
        // No analytics data available yet
        setAnalyticsData(null);
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      console.error('Failed to fetch analytics:', error);
      // Could show an error state here if needed
      setAnalyticsData(null);
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  if (!analyticsData) {
    return (
      <div className="text-center text-gray-400 py-8">
        <Activity className="w-16 h-16 mx-auto mb-4 opacity-50" />
        <p>No analytics data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Time Range Selector */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Meeting Analytics</h2>
        <div className="flex items-center space-x-4">
          <div className="flex bg-gray-800 rounded-lg p-1">
            {(['week', 'month', 'quarter', 'year'] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-4 py-2 rounded-md capitalize transition-colors ${
                  timeRange === range
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <Calendar className="w-8 h-8 text-blue-400" />
            <span className="text-2xl font-bold">{analyticsData.summary.totalMeetings}</span>
          </div>
          <p className="text-sm text-gray-400">Total Meetings</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <Clock className="w-8 h-8 text-green-400" />
            <span className="text-2xl font-bold">{formatDuration(analyticsData.summary.totalDuration)}</span>
          </div>
          <p className="text-sm text-gray-400">Total Duration</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <Activity className="w-8 h-8 text-purple-400" />
            <span className="text-2xl font-bold">{formatDuration(analyticsData.summary.averageDuration)}</span>
          </div>
          <p className="text-sm text-gray-400">Avg Duration</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <FileText className="w-8 h-8 text-yellow-400" />
            <span className="text-2xl font-bold">{analyticsData.summary.totalTranscriptions}</span>
          </div>
          <p className="text-sm text-gray-400">Transcriptions</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <Users className="w-8 h-8 text-pink-400" />
            <span className="text-2xl font-bold">{analyticsData.summary.totalSpeakers}</span>
          </div>
          <p className="text-sm text-gray-400">Unique Speakers</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <TrendingUp className="w-8 h-8 text-emerald-400" />
            <span className="text-2xl font-bold">{analyticsData.summary.npuUsage}%</span>
          </div>
          <p className="text-sm text-gray-400">NPU Usage</p>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Meetings Over Time */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold">Meetings Over Time</h3>
            <div className="flex bg-gray-700 rounded-lg p-1">
              <button
                onClick={() => setSelectedMetric('count')}
                className={`px-3 py-1 rounded text-sm ${
                  selectedMetric === 'count' ? 'bg-blue-600' : ''
                }`}
              >
                Count
              </button>
              <button
                onClick={() => setSelectedMetric('duration')}
                className={`px-3 py-1 rounded text-sm ${
                  selectedMetric === 'duration' ? 'bg-blue-600' : ''
                }`}
              >
                Duration
              </button>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={analyticsData.meetingsByDay}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="date" 
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
              />
              <Line 
                type="monotone" 
                dataKey={selectedMetric === 'count' ? 'count' : 'duration'} 
                stroke="#3b82f6" 
                strokeWidth={2}
                dot={{ fill: '#3b82f6', r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Meeting Types Distribution */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Meeting Types</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={analyticsData.meetingsByType}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={(entry) => `${entry.type} (${entry.percentage}%)`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="count"
              >
                {analyticsData.meetingsByType.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Speaker Time Distribution */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Speaker Time Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={analyticsData.speakerStats} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                type="number" 
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                dataKey="speaker" 
                type="category" 
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
                width={80}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
                formatter={(value: number) => `${formatDuration(value)}`}
              />
              <Bar dataKey="totalTime" fill="#10b981" radius={[0, 8, 8, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Performance Metrics */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Processing Performance</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={analyticsData.performanceMetrics}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="date" 
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
              />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="processingTime" 
                name="Processing Time (s)"
                stroke="#f59e0b" 
                strokeWidth={2}
              />
              <Line 
                type="monotone" 
                dataKey="rtf" 
                name="Real-time Factor"
                stroke="#8b5cf6" 
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top Keywords */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4">Top Keywords</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {analyticsData.topKeywords.map((keyword, index) => (
            <div
              key={keyword.word}
              className="bg-gray-700 rounded-lg px-4 py-2 text-center"
              style={{
                borderLeft: `4px solid ${COLORS[index % COLORS.length]}`
              }}
            >
              <p className="font-medium">{keyword.word}</p>
              <p className="text-sm text-gray-400">{keyword.count} times</p>
            </div>
          ))}
        </div>
      </div>

      {/* Export Options */}
      <div className="flex justify-end space-x-4">
        <button className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg transition-colors">
          Export CSV
        </button>
        <button className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg transition-colors">
          Generate Report
        </button>
      </div>
    </div>
  );
};