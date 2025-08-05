import React, { useState, useEffect } from 'react';
import { MeetingAnalytics } from '../MeetingAnalytics';
import { SessionList } from '../SessionList';
import { STTModelManager } from '../STTModelManager';
import { 
  Users, 
  BarChart3, 
  Calendar, 
  Download,
  Brain,
  Activity,
  TrendingUp,
  Clock
} from 'lucide-react';

interface TeamStats {
  totalSessions: number;
  totalDuration: number;
  activeUsers: number;
  weeklyGrowth: number;
  aiUsage: number;
  topSpeakers: Array<{ name: string; duration: number }>;
}

export const ManagerDashboard: React.FC = () => {
  const [teamStats, setTeamStats] = useState<TeamStats>({
    totalSessions: 0,
    totalDuration: 0,
    activeUsers: 0,
    weeklyGrowth: 0,
    aiUsage: 0,
    topSpeakers: []
  });
  const [dateRange, setDateRange] = useState('week');
  const [activeTab, setActiveTab] = useState<'overview' | 'sessions' | 'analytics' | 'ai'>('overview');

  useEffect(() => {
    // Fetch team statistics
    const fetchStats = async () => {
      try {
        const response = await fetch(`/api/analytics/meetings?range=${dateRange}`);
        if (response.ok) {
          const data = await response.json();
          setTeamStats({
            totalSessions: data.total_meetings || 0,
            totalDuration: data.total_duration || 0,
            activeUsers: data.unique_speakers || 0,
            weeklyGrowth: data.growth_percentage || 0,
            aiUsage: data.npu_usage_percentage || 0,
            topSpeakers: data.top_speakers || []
          });
        }
      } catch (error) {
        console.error('Failed to fetch team stats:', error);
      }
    };

    fetchStats();
  }, [dateRange]);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 mb-2">
          Team Dashboard
        </h1>
        <p className="text-gray-400">
          Manage team recordings and analyze meeting insights
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
          Overview
          {activeTab === 'overview' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('sessions')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'sessions'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Sessions
          {activeTab === 'sessions' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('analytics')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'analytics'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Analytics
          {activeTab === 'analytics' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('ai')}
          className={`pb-3 px-1 text-sm font-medium transition-colors relative ${
            activeTab === 'ai'
              ? 'text-purple-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          AI Models
          {activeTab === 'ai' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-400" />
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Calendar className="w-8 h-8 text-purple-400" />
                <span className={`text-sm font-medium ${
                  teamStats.weeklyGrowth >= 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {teamStats.weeklyGrowth >= 0 ? '+' : ''}{teamStats.weeklyGrowth}%
                </span>
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {teamStats.totalSessions}
              </h3>
              <p className="text-sm text-gray-400 mt-1">Total Sessions</p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Clock className="w-8 h-8 text-blue-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {Math.round(teamStats.totalDuration / 3600)}h
              </h3>
              <p className="text-sm text-gray-400 mt-1">Total Duration</p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Users className="w-8 h-8 text-green-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {teamStats.activeUsers}
              </h3>
              <p className="text-sm text-gray-400 mt-1">Active Team Members</p>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <Brain className="w-8 h-8 text-pink-400" />
              </div>
              <h3 className="text-2xl font-bold text-gray-100">
                {teamStats.aiUsage}%
              </h3>
              <p className="text-sm text-gray-400 mt-1">AI Usage</p>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Quick Actions
            </h2>
            <div className="flex flex-wrap gap-4">
              <button className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors">
                <Download className="w-4 h-4" />
                Export Team Report
              </button>
              <button className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors">
                <BarChart3 className="w-4 h-4" />
                View Detailed Analytics
              </button>
              <button className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors">
                <Users className="w-4 h-4" />
                Team Performance
              </button>
            </div>
          </div>

          {/* Top Speakers */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-200 mb-4">
              Most Active Team Members
            </h2>
            <div className="space-y-3">
              {teamStats.topSpeakers.slice(0, 5).map((speaker, index) => (
                <div key={index} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-purple-600 rounded-full flex items-center justify-center text-white text-sm font-semibold">
                      {index + 1}
                    </div>
                    <span className="text-gray-200">{speaker.name}</span>
                  </div>
                  <span className="text-gray-400 text-sm">
                    {Math.round(speaker.duration / 60)} min
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'sessions' && (
        <div>
          <div className="mb-4 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-200">
              Team Sessions
            </h2>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 focus:ring-2 focus:ring-purple-500"
            >
              <option value="day">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="quarter">This Quarter</option>
            </select>
          </div>
          <SessionList 
            onSelectSession={(session) => console.log('Selected:', session)}
          />
        </div>
      )}

      {activeTab === 'analytics' && (
        <div>
          <MeetingAnalytics />
        </div>
      )}

      {activeTab === 'ai' && (
        <div>
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-gray-200 mb-2">
              AI Model Configuration
            </h2>
            <p className="text-gray-400 text-sm">
              Configure transcription and AI models for your team
            </p>
          </div>
          <STTModelManager />
        </div>
      )}
    </div>
  );
};