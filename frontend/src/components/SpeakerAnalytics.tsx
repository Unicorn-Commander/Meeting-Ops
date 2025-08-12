import React, { useState, useEffect } from 'react';
import { Users, Clock, MessageSquare, TrendingUp, Calendar, Award, Activity, BarChart3 } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface Speaker {
  id: string;
  name: string;
  totalTime: number;
  totalWords: number;
  sessions: number;
  averageSpeed: number;
  sentiment: 'positive' | 'neutral' | 'negative';
  lastActive: string;
}

interface SpeakerDetail {
  speaker_id: string;
  total_segments: number;
  total_speaking_time: number;
  total_words: number;
  average_segment_length: number;
  sessions_participated: number;
  first_appearance: string;
  last_appearance: string;
}

interface InteractionData {
  speakerA: string;
  speakerB: string;
  interactions: number;
  totalTime: number;
}

export const SpeakerAnalytics: React.FC = () => {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null);
  const [speakerDetail, setSpeakerDetail] = useState<SpeakerDetail | null>(null);
  const [interactions, setInteractions] = useState<InteractionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<'week' | 'month' | 'quarter'>('month');

  useEffect(() => {
    fetchSpeakers();
  }, [timeRange]);

  useEffect(() => {
    if (selectedSpeaker) {
      fetchSpeakerDetail(selectedSpeaker);
    }
  }, [selectedSpeaker]);

  const fetchSpeakers = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/analytics/speakers?range=${timeRange}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSpeakers(data.speakers || []);
        setInteractions(data.interactions || []);
      } else {
        console.warn('Speaker analytics data not available');
        setSpeakers([]);
        setInteractions([]);
      }
    } catch (error) {
      console.error('Failed to fetch speakers:', error);
      setSpeakers([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchSpeakerDetail = async (speakerId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/analytics/speaker/${speakerId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSpeakerDetail(data);
      }
    } catch (error) {
      console.error('Failed to fetch speaker detail:', error);
    }
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'positive': return '#10b981';
      case 'negative': return '#ef4444';
      default: return '#6b7280';
    }
  };

  // Prepare data for charts
  const speakingTimeData = speakers.map(s => ({
    name: s.name,
    time: s.totalTime / 60, // Convert to minutes
    sessions: s.sessions
  }));

  const speedData = speakers.map(s => ({
    name: s.name,
    speed: s.averageSpeed,
    words: s.totalWords
  }));

  const sentimentData = [
    { name: 'Positive', value: speakers.filter(s => s.sentiment === 'positive').length, color: '#10b981' },
    { name: 'Neutral', value: speakers.filter(s => s.sentiment === 'neutral').length, color: '#6b7280' },
    { name: 'Negative', value: speakers.filter(s => s.sentiment === 'negative').length, color: '#ef4444' }
  ];

  // Radar chart data for selected speaker
  const getRadarData = (speaker: Speaker) => [
    { subject: 'Speaking Time', value: (speaker.totalTime / Math.max(...speakers.map(s => s.totalTime))) * 100 },
    { subject: 'Word Count', value: (speaker.totalWords / Math.max(...speakers.map(s => s.totalWords))) * 100 },
    { subject: 'Sessions', value: (speaker.sessions / Math.max(...speakers.map(s => s.sessions))) * 100 },
    { subject: 'Speed', value: (speaker.averageSpeed / 200) * 100 },
    { subject: 'Engagement', value: Math.random() * 100 } // Mock engagement score
  ];

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
        <h2 className="text-3xl font-bold">Speaker Analytics</h2>
        <div className="flex bg-gray-800 rounded-lg p-1">
          {(['week', 'month', 'quarter'] as const).map((range) => (
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

      {/* Top Speakers Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {speakers.slice(0, 6).map((speaker) => (
          <div
            key={speaker.id}
            onClick={() => setSelectedSpeaker(speaker.id)}
            className={`bg-gray-800 rounded-lg p-6 border cursor-pointer transition-all hover:border-purple-500 ${
              selectedSpeaker === speaker.id ? 'border-purple-500 ring-2 ring-purple-500/20' : 'border-gray-700'
            }`}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center text-white font-bold text-lg">
                  {speaker.name.split(' ').map(n => n[0]).join('')}
                </div>
                <div className="ml-3">
                  <h3 className="font-semibold text-lg">{speaker.name}</h3>
                  <p className="text-sm text-gray-400">Last active: {speaker.lastActive}</p>
                </div>
              </div>
              <div className={`px-2 py-1 rounded-full text-xs font-medium`} style={{ backgroundColor: getSentimentColor(speaker.sentiment) + '20', color: getSentimentColor(speaker.sentiment) }}>
                {speaker.sentiment}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-400 mb-1">Speaking Time</p>
                <p className="text-xl font-bold">{formatDuration(speaker.totalTime)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">Words Spoken</p>
                <p className="text-xl font-bold">{speaker.totalWords.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">Sessions</p>
                <p className="text-xl font-bold">{speaker.sessions}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">Avg Speed</p>
                <p className="text-xl font-bold">{speaker.averageSpeed} wpm</p>
              </div>
            </div>

            {selectedSpeaker === speaker.id && speakerDetail && (
              <div className="mt-4 pt-4 border-t border-gray-700">
                <p className="text-sm text-gray-400">
                  First seen: {new Date(speakerDetail.first_appearance).toLocaleDateString()}
                </p>
                <p className="text-sm text-gray-400">
                  Avg segment: {formatDuration(speakerDetail.average_segment_length)}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Speaking Time Distribution */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Speaking Time Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={speakingTimeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 12 }} />
              <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
                formatter={(value: number) => `${Math.round(value)} min`}
              />
              <Bar dataKey="time" fill="#8b5cf6" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Speaking Speed Comparison */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Speaking Speed Analysis</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={speedData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 12 }} />
              <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
              />
              <Line type="monotone" dataKey="speed" stroke="#10b981" strokeWidth={2} dot={{ fill: '#10b981', r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Sentiment Distribution */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold mb-4">Sentiment Analysis</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={sentimentData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={(entry) => `${entry.name} (${entry.value})`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {sentimentData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
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

        {/* Speaker Performance Radar */}
        {selectedSpeaker && (
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 className="text-xl font-bold mb-4">
              Performance Profile: {speakers.find(s => s.id === selectedSpeaker)?.name}
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={getRadarData(speakers.find(s => s.id === selectedSpeaker)!)}>
                <PolarGrid stroke="#374151" />
                <PolarAngleAxis dataKey="subject" stroke="#9ca3af" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} stroke="#374151" />
                <Radar name="Performance" dataKey="value" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.6} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#1f2937', 
                    border: '1px solid #374151',
                    borderRadius: '8px'
                  }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Interaction Matrix */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4">Speaker Interactions</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left py-3 px-4">Speaker A</th>
                <th className="text-left py-3 px-4">Speaker B</th>
                <th className="text-right py-3 px-4">Interactions</th>
                <th className="text-right py-3 px-4">Total Time</th>
              </tr>
            </thead>
            <tbody>
              {interactions.map((interaction, index) => (
                <tr key={index} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                  <td className="py-3 px-4">{interaction.speakerA}</td>
                  <td className="py-3 px-4">{interaction.speakerB}</td>
                  <td className="text-right py-3 px-4">{interaction.interactions}</td>
                  <td className="text-right py-3 px-4">{formatDuration(interaction.totalTime)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Export Options */}
      <div className="flex justify-end space-x-4">
        <button className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg transition-colors">
          Export Speaker Report
        </button>
        <button className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg transition-colors">
          Generate Insights
        </button>
      </div>
    </div>
  );
};