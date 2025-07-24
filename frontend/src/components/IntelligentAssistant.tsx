import React, { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, Settings, Sparkles, Clock, Lightbulb, 
  ChevronRight, User, CheckCircle, Target, TrendingUp,
  BookOpen, Send, X
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Badge } from './ui/badge';

interface Conversation {
  timestamp: string;
  query: string;
  response: string;
  context: any;
}

interface QuickAction {
  action: string;
  query: string;
  icon: string;
}

interface UserInsight {
  type: string;
  insight: string;
  count?: number;
  sessions?: Array<{id: string; count: number}>;
  topics?: Array<{name: string; score: number}>;
}

interface IntelligentResponse {
  query: string;
  summary: string;
  key_insights: string[];
  action_items?: Array<{
    description: string;
    session_id: string;
    assigned_to?: string;
    status: string;
  }>;
  decisions?: Array<{
    description: string;
    session_id: string;
    made_by?: string;
    timestamp?: string;
  }>;
  recommendations: string[];
  formatted_response: string;
  metadata: {
    timestamp: string;
    search_type: string;
    result_count: number;
    accessible_sessions: number;
  };
}

export const IntelligentAssistant: React.FC = () => {
  const [isOpen, setIsOpen] = useState(true);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentResponse, setCurrentResponse] = useState<IntelligentResponse | null>(null);
  const [quickActions, setQuickActions] = useState<QuickAction[]>([]);
  const [userInsights, setUserInsights] = useState<UserInsight[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [preferences, setPreferences] = useState({
    summary_style: 'concise',
    focus_areas: [],
    formatting: {
      timestamps: true,
      speaker_names: true,
      confidence_scores: false
    },
    notification_settings: {
      email_summaries: false,
      action_items: true,
      decisions: true
    }
  });

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadQuickActions();
    loadUserInsights();
    loadConversationHistory();
    loadPreferences();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversations, currentResponse]);

  const loadQuickActions = async () => {
    try {
      const response = await fetch('/api/intelligence/quick-actions', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setQuickActions(data.quick_actions || []);
      }
    } catch (error) {
      console.error('Failed to load quick actions:', error);
    }
  };

  const loadUserInsights = async () => {
    try {
      const response = await fetch('/api/intelligence/insights', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setUserInsights(data.insights || []);
      }
    } catch (error) {
      console.error('Failed to load insights:', error);
    }
  };

  const loadConversationHistory = async () => {
    try {
      const response = await fetch('/api/intelligence/conversation-history?limit=10', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setConversations(data.conversations || []);
      }
    } catch (error) {
      console.error('Failed to load conversation history:', error);
    }
  };

  const loadPreferences = async () => {
    try {
      const response = await fetch('/api/intelligence/memory', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.preferences) {
          setPreferences(data.preferences);
        }
      }
    } catch (error) {
      console.error('Failed to load preferences:', error);
    }
  };

  const handleSubmit = async (queryText?: string) => {
    const finalQuery = queryText || query;
    if (!finalQuery.trim()) return;

    setLoading(true);
    setCurrentResponse(null);

    try {
      const response = await fetch('/api/intelligence/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          query: finalQuery,
          context: {
            view: 'assistant',
            previous_query: conversations[0]?.query
          }
        })
      });

      if (response.ok) {
        const data: IntelligentResponse = await response.json();
        setCurrentResponse(data);
        
        // Add to conversation history
        const newConversation: Conversation = {
          timestamp: data.metadata.timestamp,
          query: data.query,
          response: data.summary,
          context: {
            search_type: data.metadata.search_type,
            result_count: data.metadata.result_count
          }
        };
        
        setConversations([newConversation, ...conversations.slice(0, 9)]);
        setQuery('');
        
        // Reload quick actions and insights
        loadQuickActions();
        loadUserInsights();
      }
    } catch (error) {
      console.error('Query failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const updatePreferences = async (newPreferences: any) => {
    try {
      const response = await fetch('/api/intelligence/preferences', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          preferences: newPreferences
        })
      });

      if (response.ok) {
        setPreferences(newPreferences);
        setShowSettings(false);
      }
    } catch (error) {
      console.error('Failed to update preferences:', error);
    }
  };

  const renderResponse = (response: IntelligentResponse) => {
    return (
      <div className="space-y-4">
        {/* Summary */}
        <div className="bg-blue-50 rounded-lg p-4">
          <p className="text-gray-800">{response.summary}</p>
          <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
            <Badge variant="outline" className="text-xs">
              {response.metadata.search_type}
            </Badge>
            <span>{response.metadata.result_count} results</span>
            <span>•</span>
            <span>{response.metadata.accessible_sessions} sessions</span>
          </div>
        </div>

        {/* Key Insights */}
        {response.key_insights.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-yellow-500" />
                Key Insights
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1">
                {response.key_insights.map((insight, idx) => (
                  <li key={idx} className="text-sm text-gray-700 flex items-start gap-2">
                    <ChevronRight className="w-4 h-4 text-gray-400 mt-0.5" />
                    <span>{insight}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* Action Items */}
        {response.action_items && response.action_items.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Target className="w-4 h-4 text-red-500" />
                Action Items
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {response.action_items.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <CheckCircle className={`w-4 h-4 mt-0.5 ${
                      item.status === 'completed' ? 'text-green-500' : 'text-gray-400'
                    }`} />
                    <div className="flex-1">
                      <p className="text-sm text-gray-700">{item.description}</p>
                      {item.assigned_to && (
                        <p className="text-xs text-gray-500">Assigned to: {item.assigned_to}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Decisions */}
        {response.decisions && response.decisions.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-500" />
                Decisions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {response.decisions.map((decision, idx) => (
                  <li key={idx} className="text-sm text-gray-700">
                    • {decision.description}
                    {decision.made_by && (
                      <span className="text-xs text-gray-500 ml-2">by {decision.made_by}</span>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* Recommendations */}
        {response.recommendations.length > 0 && (
          <Card className="bg-purple-50 border-purple-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2 text-purple-800">
                <Sparkles className="w-4 h-4" />
                Recommendations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1">
                {response.recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm text-purple-700">
                    • {rec}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    );
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 bg-blue-600 text-white p-4 rounded-full shadow-lg hover:bg-blue-700 transition-colors"
      >
        <MessageSquare className="w-6 h-6" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 w-96 max-h-[600px] bg-white rounded-lg shadow-xl flex flex-col">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4 rounded-t-lg flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5" />
          <h3 className="font-semibold">Meeting Intelligence Assistant</h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-1 hover:bg-white/20 rounded transition-colors"
          >
            <Settings className="w-5 h-5" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 hover:bg-white/20 rounded transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="p-4 bg-gray-50 border-b">
          <h4 className="font-medium mb-3">Preferences</h4>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-gray-700">Summary Style</label>
              <select
                value={preferences.summary_style}
                onChange={(e) => updatePreferences({
                  ...preferences,
                  summary_style: e.target.value
                })}
                className="mt-1 w-full px-3 py-1 border border-gray-300 rounded text-sm"
              >
                <option value="concise">Concise</option>
                <option value="detailed">Detailed</option>
                <option value="bullet-points">Bullet Points</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Show in Responses</label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={preferences.notification_settings.action_items}
                  onChange={(e) => updatePreferences({
                    ...preferences,
                    notification_settings: {
                      ...preferences.notification_settings,
                      action_items: e.target.checked
                    }
                  })}
                />
                Action Items
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={preferences.notification_settings.decisions}
                  onChange={(e) => updatePreferences({
                    ...preferences,
                    notification_settings: {
                      ...preferences.notification_settings,
                      decisions: e.target.checked
                    }
                  })}
                />
                Decisions
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      {!showSettings && quickActions.length > 0 && !currentResponse && (
        <div className="p-3 bg-gray-50 border-b">
          <p className="text-xs text-gray-600 mb-2">Quick Actions</p>
          <div className="flex flex-wrap gap-2">
            {quickActions.map((action, idx) => (
              <button
                key={idx}
                onClick={() => handleSubmit(action.query)}
                className="px-3 py-1 bg-white border border-gray-200 rounded-full text-xs hover:bg-gray-100 transition-colors flex items-center gap-1"
              >
                <span>{action.icon}</span>
                <span>{action.action}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* User Insights */}
      {!showSettings && userInsights.length > 0 && !currentResponse && conversations.length === 0 && (
        <div className="p-4 bg-blue-50">
          <p className="text-sm font-medium text-blue-800 mb-2 flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            Your Patterns
          </p>
          <div className="space-y-2">
            {userInsights.map((insight, idx) => (
              <div key={idx} className="text-xs text-blue-700">
                • {insight.insight}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Previous Conversations */}
        {conversations.map((conv, idx) => (
          <div key={idx} className="space-y-2">
            <div className="flex justify-end">
              <div className="bg-blue-100 rounded-lg p-3 max-w-[80%]">
                <p className="text-sm text-gray-800">{conv.query}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {new Date(conv.timestamp).toLocaleTimeString()}
                </p>
              </div>
            </div>
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-lg p-3 max-w-[80%]">
                <p className="text-sm text-gray-800">{conv.response}</p>
              </div>
            </div>
          </div>
        ))}

        {/* Current Response */}
        {currentResponse && (
          <div className="space-y-2">
            <div className="flex justify-end">
              <div className="bg-blue-100 rounded-lg p-3 max-w-[80%]">
                <p className="text-sm text-gray-800">{currentResponse.query}</p>
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[80%]">
                {renderResponse(currentResponse)}
              </div>
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600"></div>
                <span className="text-sm text-gray-600">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t">
        <form onSubmit={(e) => { e.preventDefault(); handleSubmit(); }} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about your meetings..."
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};