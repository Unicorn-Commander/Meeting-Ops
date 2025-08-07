import React, { useState, useEffect } from 'react';
import { 
  Brain, TrendingUp, Users, Clock, MessageCircle, 
  Target, CheckCircle, AlertCircle, Lightbulb, 
  FileText, Search, Filter, Download, Share2,
  Zap, Activity, BarChart3, PieChart
} from 'lucide-react';

interface KeywordTrend {
  word: string;
  frequency: number;
  trend: 'up' | 'down' | 'stable';
  category: 'technical' | 'action' | 'sentiment' | 'topic';
}

interface ActionItem {
  id: string;
  text: string;
  assignee?: string;
  priority: 'high' | 'medium' | 'low';
  dueDate?: string;
  completed: boolean;
  category: string;
}

interface SpeakerInsight {
  speaker: string;
  talkTime: number;
  wordCount: number;
  sentiment: 'positive' | 'neutral' | 'negative';
  engagement: number;
  keyTopics: string[];
}

interface MeetingInsightsProps {
  sessionId?: string;
  className?: string;
}

export const MeetingInsights: React.FC<MeetingInsightsProps> = ({
  sessionId,
  className = ''
}) => {
  const [insights, setInsights] = useState<{
    summary: string;
    keywords: KeywordTrend[];
    actionItems: ActionItem[];
    speakers: SpeakerInsight[];
    sentiment: { positive: number; neutral: number; negative: number };
    duration: number;
    topicsDiscussed: string[];
  } | null>(null);

  const [activeTab, setActiveTab] = useState<'summary' | 'keywords' | 'actions' | 'speakers'>('summary');
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>('all');

  // Mock data for demonstration
  useEffect(() => {
    const mockInsights = {
      summary: "This meeting focused on Q4 planning and NPU transcription performance optimization. Key decisions included adopting INT8 quantization for better performance and implementing real-time waveform visualization. The team discussed budget allocation for hardware upgrades and timeline for feature rollout.",
      keywords: [
        { word: "NPU optimization", frequency: 15, trend: 'up' as const, category: 'technical' as const },
        { word: "performance", frequency: 12, trend: 'up' as const, category: 'technical' as const },
        { word: "budget", frequency: 8, trend: 'stable' as const, category: 'topic' as const },
        { word: "timeline", frequency: 6, trend: 'down' as const, category: 'action' as const },
        { word: "implementation", frequency: 10, trend: 'up' as const, category: 'action' as const },
      ],
      actionItems: [
        {
          id: '1',
          text: 'Implement INT8 quantization for NPU transcription',
          assignee: 'Engineering Team',
          priority: 'high' as const,
          dueDate: '2024-12-15',
          completed: false,
          category: 'Development'
        },
        {
          id: '2', 
          text: 'Create budget proposal for Q1 hardware upgrades',
          assignee: 'Finance Team',
          priority: 'medium' as const,
          dueDate: '2024-12-10',
          completed: false,
          category: 'Planning'
        },
        {
          id: '3',
          text: 'Review performance metrics for current NPU implementation',
          assignee: 'QA Team',
          priority: 'high' as const,
          dueDate: '2024-12-08',
          completed: true,
          category: 'Testing'
        }
      ],
      speakers: [
        {
          speaker: 'Sarah (Engineering)',
          talkTime: 45,
          wordCount: 1250,
          sentiment: 'positive' as const,
          engagement: 85,
          keyTopics: ['NPU optimization', 'performance metrics', 'technical implementation']
        },
        {
          speaker: 'Mike (Product)',
          talkTime: 35,
          wordCount: 980,
          sentiment: 'neutral' as const,
          engagement: 78,
          keyTopics: ['feature rollout', 'user requirements', 'timeline']
        },
        {
          speaker: 'Lisa (Finance)',
          talkTime: 20,
          wordCount: 540,
          sentiment: 'positive' as const,
          engagement: 72,
          keyTopics: ['budget allocation', 'cost analysis', 'ROI projections']
        }
      ],
      sentiment: { positive: 65, neutral: 25, negative: 10 },
      duration: 3600, // 1 hour
      topicsDiscussed: [
        'NPU Performance Optimization',
        'Q4 Budget Planning', 
        'Hardware Upgrade Timeline',
        'Feature Implementation Strategy',
        'Team Resource Allocation'
      ]
    };

    setInsights(mockInsights);
  }, [sessionId]);

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'text-red-400 bg-red-500/20';
      case 'medium': return 'text-yellow-400 bg-yellow-500/20';
      case 'low': return 'text-green-400 bg-green-500/20';
      default: return 'text-gray-400 bg-gray-500/20';
    }
  };

  const getCategoryColor = (category: string) => {
    const colors = {
      'technical': 'bg-purple-500/20 text-purple-400',
      'action': 'bg-blue-500/20 text-blue-400',
      'sentiment': 'bg-pink-500/20 text-pink-400',
      'topic': 'bg-green-500/20 text-green-400',
    };
    return colors[category as keyof typeof colors] || 'bg-gray-500/20 text-gray-400';
  };

  if (!insights) {
    return (
      <div className={`bg-gray-900 rounded-lg border border-gray-800 p-6 ${className}`}>
        <div className="text-center">
          <Brain className="w-8 h-8 text-purple-400 mx-auto mb-2" />
          <p className="text-gray-400">Generate AI insights by starting a meeting recording</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-800 ${className}`}>
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 p-6 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 rounded-lg">
              <Brain className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">AI Meeting Insights</h2>
              <p className="text-gray-400 text-sm">
                Powered by NPU + Large Language Models
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button className="p-2 text-gray-400 hover:text-white transition-colors">
              <Download className="w-5 h-5" />
            </button>
            <button className="p-2 text-gray-400 hover:text-white transition-colors">
              <Share2 className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-4 gap-4 mt-4">
          <div className="bg-gray-800/50 rounded-lg p-3 text-center">
            <Clock className="w-5 h-5 text-blue-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-white">
              {Math.floor(insights.duration / 60)}m
            </p>
            <p className="text-xs text-gray-500">Duration</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3 text-center">
            <Users className="w-5 h-5 text-green-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-white">{insights.speakers.length}</p>
            <p className="text-xs text-gray-500">Speakers</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3 text-center">
            <Target className="w-5 h-5 text-orange-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-white">{insights.actionItems.length}</p>
            <p className="text-xs text-gray-500">Action Items</p>
          </div>
          
          <div className="bg-gray-800/50 rounded-lg p-3 text-center">
            <TrendingUp className="w-5 h-5 text-purple-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-white">{insights.sentiment.positive}%</p>
            <p className="text-xs text-gray-500">Positive</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="px-6 border-b border-gray-800">
        <div className="flex space-x-0">
          {[
            { id: 'summary', label: 'Summary', icon: FileText },
            { id: 'keywords', label: 'Keywords', icon: Search },
            { id: 'actions', label: 'Actions', icon: CheckCircle },
            { id: 'speakers', label: 'Speakers', icon: Users }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab.id
                  ? 'text-purple-400 border-purple-400'
                  : 'text-gray-400 hover:text-gray-300 border-transparent'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === 'summary' && (
          <div className="space-y-6">
            {/* AI Summary */}
            <div>
              <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-yellow-400" />
                AI-Generated Summary
              </h3>
              <div className="bg-gray-800/50 rounded-lg p-4">
                <p className="text-gray-300 leading-relaxed">{insights.summary}</p>
              </div>
            </div>

            {/* Topics Discussed */}
            <div>
              <h3 className="text-white font-semibold mb-3">Key Topics</h3>
              <div className="flex flex-wrap gap-2">
                {insights.topicsDiscussed.map((topic, index) => (
                  <span
                    key={index}
                    className="px-3 py-1 bg-purple-500/20 text-purple-300 text-sm rounded-full"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>

            {/* Sentiment Analysis */}
            <div>
              <h3 className="text-white font-semibold mb-3">Overall Sentiment</h3>
              <div className="bg-gray-800/50 rounded-lg p-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-400">
                      {insights.sentiment.positive}%
                    </div>
                    <div className="text-xs text-gray-500">Positive</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-gray-400">
                      {insights.sentiment.neutral}%
                    </div>
                    <div className="text-xs text-gray-500">Neutral</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-red-400">
                      {insights.sentiment.negative}%
                    </div>
                    <div className="text-xs text-gray-500">Negative</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'keywords' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-white font-semibold">Trending Keywords</h3>
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-gray-400" />
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="bg-gray-800 text-white text-sm rounded px-2 py-1 border border-gray-700"
                >
                  <option value="all">All Categories</option>
                  <option value="technical">Technical</option>
                  <option value="action">Action Items</option>
                  <option value="topic">Topics</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              {insights.keywords
                .filter(kw => filter === 'all' || kw.category === filter)
                .map((keyword, index) => (
                <div key={index} className="bg-gray-800/50 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-white font-medium">{keyword.word}</span>
                      <span className={`text-xs px-2 py-1 rounded ${getCategoryColor(keyword.category)}`}>
                        {keyword.category}
                      </span>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400 text-sm">{keyword.frequency} mentions</span>
                      <div className={`flex items-center ${
                        keyword.trend === 'up' ? 'text-green-400' :
                        keyword.trend === 'down' ? 'text-red-400' : 'text-gray-400'
                      }`}>
                        <TrendingUp className={`w-4 h-4 ${
                          keyword.trend === 'down' ? 'rotate-180' : ''
                        }`} />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'actions' && (
          <div className="space-y-4">
            {insights.actionItems.map((item) => (
              <div key={item.id} className="bg-gray-800/50 rounded-lg p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className={`font-medium ${
                      item.completed ? 'text-gray-400 line-through' : 'text-white'
                    }`}>
                      {item.text}
                    </p>
                    
                    <div className="flex items-center gap-3 mt-2">
                      {item.assignee && (
                        <span className="text-sm text-purple-300">
                          {item.assignee}
                        </span>
                      )}
                      
                      <span className={`text-xs px-2 py-1 rounded ${getPriorityColor(item.priority)}`}>
                        {item.priority} priority
                      </span>
                      
                      <span className="text-xs text-gray-500">
                        {item.category}
                      </span>
                      
                      {item.dueDate && (
                        <span className="text-xs text-gray-500">
                          Due: {new Date(item.dueDate).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                  
                  <div className={`p-1 rounded ${
                    item.completed ? 'text-green-400' : 'text-gray-400'
                  }`}>
                    {item.completed ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'speakers' && (
          <div className="space-y-4">
            {insights.speakers.map((speaker, index) => (
              <div key={index} className="bg-gray-800/50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-white font-semibold">{speaker.speaker}</h4>
                  <div className={`px-2 py-1 rounded text-xs ${
                    speaker.sentiment === 'positive' ? 'bg-green-500/20 text-green-400' :
                    speaker.sentiment === 'negative' ? 'bg-red-500/20 text-red-400' :
                    'bg-gray-500/20 text-gray-400'
                  }`}>
                    {speaker.sentiment}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-3">
                  <div>
                    <p className="text-sm text-gray-500">Talk Time</p>
                    <p className="text-lg font-semibold text-blue-400">{speaker.talkTime}%</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Words</p>
                    <p className="text-lg font-semibold text-green-400">{speaker.wordCount}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Engagement</p>
                    <p className="text-lg font-semibold text-purple-400">{speaker.engagement}%</p>
                  </div>
                </div>

                <div>
                  <p className="text-sm text-gray-500 mb-2">Key Topics:</p>
                  <div className="flex flex-wrap gap-1">
                    {speaker.keyTopics.map((topic, i) => (
                      <span key={i} className="text-xs bg-purple-500/20 text-purple-300 px-2 py-1 rounded">
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};