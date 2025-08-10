import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus, Search, Filter, Tag, Calendar, Download } from 'lucide-react';
import { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface Keyword {
  keyword: string;
  frequency: number;
  trend: 'up' | 'down' | 'stable';
  change: number;
  category?: string;
  sessions: number;
}

interface TrendData {
  date: string;
  [key: string]: any; // Dynamic keys for each keyword
}

export const KeywordTrends: React.FC = () => {
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [trendData, setTrendData] = useState<TrendData[]>([]);
  const [selectedKeywords, setSelectedKeywords] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [timeRange, setTimeRange] = useState<'week' | 'month' | 'quarter'>('month');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchKeywordTrends();
  }, [timeRange]);

  const fetchKeywordTrends = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/analytics/keywords?limit=50&range=${timeRange}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Transform data if needed
        const keywordsData = data.map((item: any) => ({
          keyword: item.keyword || item.word,
          frequency: item.frequency || item.count,
          trend: item.trend || 'stable',
          change: Math.random() * 20 - 10, // Mock change percentage
          category: categorizeKeyword(item.keyword || item.word),
          sessions: Math.floor(Math.random() * 20) + 1
        }));
        setKeywords(keywordsData);
        
        // Select top 5 keywords by default
        const topKeywords = keywordsData.slice(0, 5).map((k: Keyword) => k.keyword);
        setSelectedKeywords(new Set(topKeywords));
        
        // Generate trend data
        generateTrendData(keywordsData.slice(0, 10));
      } else {
        // Use mock data
        const mockKeywords = [
          { keyword: 'project', frequency: 145, trend: 'up' as const, change: 15.5, category: 'business', sessions: 12 },
          { keyword: 'deadline', frequency: 98, trend: 'up' as const, change: 8.2, category: 'business', sessions: 8 },
          { keyword: 'budget', frequency: 87, trend: 'stable' as const, change: 0.5, category: 'finance', sessions: 7 },
          { keyword: 'client', frequency: 76, trend: 'down' as const, change: -5.3, category: 'business', sessions: 6 },
          { keyword: 'development', frequency: 65, trend: 'up' as const, change: 12.1, category: 'technical', sessions: 9 },
          { keyword: 'testing', frequency: 54, trend: 'stable' as const, change: 1.2, category: 'technical', sessions: 5 },
          { keyword: 'release', frequency: 48, trend: 'up' as const, change: 18.7, category: 'technical', sessions: 4 },
          { keyword: 'meeting', frequency: 45, trend: 'down' as const, change: -3.2, category: 'general', sessions: 15 },
          { keyword: 'review', frequency: 42, trend: 'stable' as const, change: 0.8, category: 'process', sessions: 6 },
          { keyword: 'design', frequency: 38, trend: 'up' as const, change: 9.5, category: 'creative', sessions: 5 }
        ];
        setKeywords(mockKeywords);
        setSelectedKeywords(new Set(mockKeywords.slice(0, 5).map(k => k.keyword)));
        generateTrendData(mockKeywords);
      }
    } catch (error) {
      console.error('Failed to fetch keyword trends:', error);
    } finally {
      setLoading(false);
    }
  };

  const categorizeKeyword = (keyword: string): string => {
    const categories: { [key: string]: string[] } = {
      technical: ['api', 'code', 'bug', 'server', 'database', 'development', 'testing', 'release'],
      business: ['project', 'client', 'deadline', 'goal', 'strategy', 'market'],
      finance: ['budget', 'cost', 'revenue', 'profit', 'expense'],
      creative: ['design', 'ui', 'ux', 'brand', 'creative'],
      process: ['review', 'approval', 'workflow', 'process'],
      general: ['meeting', 'discussion', 'update', 'status']
    };

    for (const [category, words] of Object.entries(categories)) {
      if (words.some(word => keyword.toLowerCase().includes(word))) {
        return category;
      }
    }
    return 'general';
  };

  const generateTrendData = (keywordList: Keyword[]) => {
    const days = timeRange === 'week' ? 7 : timeRange === 'month' ? 30 : 90;
    const data: TrendData[] = [];
    
    for (let i = 0; i < days; i++) {
      const date = new Date();
      date.setDate(date.getDate() - (days - i - 1));
      const dataPoint: TrendData = {
        date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      };
      
      keywordList.forEach(keyword => {
        // Generate realistic trend data
        const baseValue = keyword.frequency / days;
        const variation = Math.sin(i / 5) * baseValue * 0.3;
        const trend = keyword.trend === 'up' ? i * 0.5 : keyword.trend === 'down' ? -i * 0.3 : 0;
        dataPoint[keyword.keyword] = Math.max(0, Math.round(baseValue + variation + trend));
      });
      
      data.push(dataPoint);
    }
    
    setTrendData(data);
  };

  const toggleKeywordSelection = (keyword: string) => {
    const newSelection = new Set(selectedKeywords);
    if (newSelection.has(keyword)) {
      newSelection.delete(keyword);
    } else {
      newSelection.add(keyword);
    }
    setSelectedKeywords(newSelection);
  };

  const getTrendIcon = (trend: 'up' | 'down' | 'stable') => {
    switch (trend) {
      case 'up': return <TrendingUp className="w-4 h-4 text-green-400" />;
      case 'down': return <TrendingDown className="w-4 h-4 text-red-400" />;
      default: return <Minus className="w-4 h-4 text-gray-400" />;
    }
  };

  const getChangeColor = (change: number) => {
    if (change > 0) return 'text-green-400';
    if (change < 0) return 'text-red-400';
    return 'text-gray-400';
  };

  const getCategoryColor = (category: string) => {
    const colors: { [key: string]: string } = {
      technical: '#3b82f6',
      business: '#8b5cf6',
      finance: '#10b981',
      creative: '#f59e0b',
      process: '#ef4444',
      general: '#6b7280'
    };
    return colors[category] || '#6b7280';
  };

  const filteredKeywords = keywords.filter(k => {
    const matchesSearch = k.keyword.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = categoryFilter === 'all' || k.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const categories = ['all', ...Array.from(new Set(keywords.map(k => k.category).filter(Boolean)))];

  const COLORS = ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#14b8a6', '#a855f7'];

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
        <h2 className="text-3xl font-bold">Keyword Trends</h2>
        <div className="flex items-center space-x-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search keywords..."
              className="pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
            />
          </div>

          {/* Category Filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
          >
            {categories.map(cat => (
              <option key={cat} value={cat}>
                {cat === 'all' ? 'All Categories' : cat.charAt(0).toUpperCase() + cat.slice(1)}
              </option>
            ))}
          </select>

          {/* Time Range */}
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
      </div>

      {/* Trend Chart */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4">Keyword Frequency Over Time</h3>
        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="date" stroke="#9ca3af" tick={{ fontSize: 12 }} />
            <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1f2937', 
                border: '1px solid #374151',
                borderRadius: '8px'
              }}
            />
            <Legend />
            {Array.from(selectedKeywords).map((keyword, index) => (
              <Area
                key={keyword}
                type="monotone"
                dataKey={keyword}
                stroke={COLORS[index % COLORS.length]}
                fill={COLORS[index % COLORS.length]}
                fillOpacity={0.3}
                strokeWidth={2}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Keywords Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredKeywords.map((keyword) => (
          <div
            key={keyword.keyword}
            onClick={() => toggleKeywordSelection(keyword.keyword)}
            className={`bg-gray-800 rounded-lg p-4 border cursor-pointer transition-all hover:border-purple-500 ${
              selectedKeywords.has(keyword.keyword) ? 'border-purple-500 ring-2 ring-purple-500/20' : 'border-gray-700'
            }`}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center">
                <Tag className="w-4 h-4 mr-2" style={{ color: getCategoryColor(keyword.category || 'general') }} />
                <h4 className="font-semibold text-lg">{keyword.keyword}</h4>
              </div>
              {getTrendIcon(keyword.trend)}
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">Frequency</span>
                <span className="font-bold">{keyword.frequency}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">Change</span>
                <span className={`font-bold ${getChangeColor(keyword.change)}`}>
                  {keyword.change > 0 ? '+' : ''}{keyword.change.toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">Sessions</span>
                <span className="font-bold">{keyword.sessions}</span>
              </div>
              {keyword.category && (
                <div className="pt-2 border-t border-gray-700">
                  <span 
                    className="text-xs px-2 py-1 rounded-full"
                    style={{ 
                      backgroundColor: getCategoryColor(keyword.category) + '20',
                      color: getCategoryColor(keyword.category)
                    }}
                  >
                    {keyword.category}
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Export Options */}
      <div className="flex justify-end">
        <button className="flex items-center bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg transition-colors">
          <Download className="w-4 h-4 mr-2" />
          Export Keyword Report
        </button>
      </div>
    </div>
  );
};