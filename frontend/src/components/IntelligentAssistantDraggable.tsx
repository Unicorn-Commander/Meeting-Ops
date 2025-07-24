import React, { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, Settings, Sparkles, Clock, Lightbulb, 
  ChevronRight, User, CheckCircle, Target, TrendingUp,
  BookOpen, Send, X, Maximize2, Minimize2, Move
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Badge } from './ui/badge';

interface Position {
  x: number;
  y: number;
}

interface Size {
  width: number;
  height: number;
}

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
    response_time: number;
    accessible_sessions: number;
    context_used: Array<{type: string; count: number}>;
  };
}

export const IntelligentAssistantDraggable: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [userInsights, setUserInsights] = useState<UserInsight[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedResponse, setSelectedResponse] = useState<IntelligentResponse | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  
  // Dragging and resizing state
  const [position, setPosition] = useState<Position>({ x: window.innerWidth - 420, y: window.innerHeight - 650 });
  const [size, setSize] = useState<Size>({ width: 400, height: 600 });
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [dragStart, setDragStart] = useState<Position>({ x: 0, y: 0 });
  const [resizeStart, setResizeStart] = useState<{ width: number; height: number; x: number; y: number }>({ width: 0, height: 0, x: 0, y: 0 });
  
  const assistantRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadUserInsights();
    const savedConversations = localStorage.getItem('assistant_conversations');
    if (savedConversations) {
      setConversations(JSON.parse(savedConversations));
    }
  }, []);

  useEffect(() => {
    if (conversations.length > 0) {
      localStorage.setItem('assistant_conversations', JSON.stringify(conversations));
    }
  }, [conversations]);

  // Dragging logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging && !isMaximized) {
        const newX = e.clientX - dragStart.x;
        const newY = e.clientY - dragStart.y;
        
        // Keep within window bounds
        const maxX = window.innerWidth - size.width;
        const maxY = window.innerHeight - size.height;
        
        setPosition({
          x: Math.max(0, Math.min(newX, maxX)),
          y: Math.max(0, Math.min(newY, maxY))
        });
      } else if (isResizing && !isMaximized) {
        const newWidth = resizeStart.width + (e.clientX - resizeStart.x);
        const newHeight = resizeStart.height + (e.clientY - resizeStart.y);
        
        setSize({
          width: Math.max(300, Math.min(newWidth, window.innerWidth - position.x)),
          height: Math.max(400, Math.min(newHeight, window.innerHeight - position.y))
        });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(false);
    };

    if (isDragging || isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizing, dragStart, resizeStart, position, size, isMaximized]);

  const handleDragStart = (e: React.MouseEvent) => {
    if (isMaximized) return;
    const rect = assistantRef.current?.getBoundingClientRect();
    if (rect) {
      setDragStart({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      });
      setIsDragging(true);
    }
  };

  const handleResizeStart = (e: React.MouseEvent) => {
    if (isMaximized) return;
    e.stopPropagation();
    setResizeStart({
      width: size.width,
      height: size.height,
      x: e.clientX,
      y: e.clientY
    });
    setIsResizing(true);
  };

  const toggleMaximize = () => {
    setIsMaximized(!isMaximized);
  };

  const loadUserInsights = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/ai/assistant/insights', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setUserInsights(data.insights || []);
      }
    } catch (error) {
      console.error('Error loading user insights:', error);
    }
  };

  const quickActions: QuickAction[] = [
    { action: "Summary", query: "What were the key points from today's meetings?", icon: "📊" },
    { action: "Actions", query: "Show me all pending action items", icon: "✅" },
    { action: "Decisions", query: "What decisions were made this week?", icon: "🎯" },
    { action: "Trends", query: "What topics are trending in our meetings?", icon: "📈" }
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    const newConversation: Conversation = {
      timestamp: new Date().toISOString(),
      query,
      response: '',
      context: {}
    };

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/search/assistant/query', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query })
      });

      if (response.ok) {
        const data = await response.json();
        newConversation.response = data.formatted_response;
        newConversation.context = data;
        setSelectedResponse(data);
      }
    } catch (error) {
      console.error('Error querying assistant:', error);
      newConversation.response = 'Sorry, I encountered an error processing your request.';
    }

    setConversations([...conversations, newConversation]);
    setQuery('');
    setIsLoading(false);
    
    // Scroll to bottom
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  };

  const renderResponse = (response: IntelligentResponse) => {
    return (
      <div className="space-y-4">
        {/* Summary */}
        <div className="bg-blue-50 rounded-lg p-4">
          <p className="text-gray-800">{response.summary}</p>
          <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
            <Clock className="w-3 h-3" />
            <span>{response.metadata.response_time}ms</span>
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

        {/* Recommendations */}
        {response.recommendations.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-green-500" />
                Recommendations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1">
                {response.recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm text-gray-700">• {rec}</li>
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
        className="fixed bottom-6 right-6 bg-blue-600 text-white p-4 rounded-full shadow-lg hover:bg-blue-700 transition-colors z-50"
      >
        <MessageSquare className="w-6 h-6" />
      </button>
    );
  }

  const assistantStyle: React.CSSProperties = isMaximized
    ? {
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 50
      }
    : {
        position: 'fixed',
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
        zIndex: 50
      };

  return (
    <div
      ref={assistantRef}
      style={assistantStyle}
      className="bg-white rounded-lg shadow-xl flex flex-col"
    >
      {/* Header */}
      <div 
        className="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4 rounded-t-lg flex items-center justify-between cursor-move select-none"
        onMouseDown={handleDragStart}
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5" />
          <h3 className="font-semibold">AI Assistant</h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleMaximize}
            className="p-1 hover:bg-white/20 rounded transition-colors"
          >
            {isMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 hover:bg-white/20 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* User Insights */}
      {userInsights.length > 0 && (
        <div className="bg-gray-50 p-4 border-b">
          <div className="flex items-center gap-2 mb-2">
            <User className="w-4 h-4 text-gray-600" />
            <span className="text-sm font-medium text-gray-700">Your Insights</span>
          </div>
          <div className="space-y-2">
            {userInsights.slice(0, 3).map((insight, idx) => (
              <div key={idx} className="text-xs text-gray-600">
                {insight.type === 'meeting_frequency' && (
                  <span>You've attended {insight.count} meetings this week</span>
                )}
                {insight.type === 'top_topics' && (
                  <span>Your top topics: {insight.topics?.map(t => t.name).join(', ')}</span>
                )}
                {insight.type === 'action_completion' && (
                  <span>{insight.insight}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="p-4 border-b">
        <div className="grid grid-cols-2 gap-2">
          {quickActions.map((action, idx) => (
            <button
              key={idx}
              onClick={() => setQuery(action.query)}
              className="flex items-center gap-2 p-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors text-sm"
            >
              <span>{action.icon}</span>
              <span className="text-gray-700">{action.action}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div ref={chatRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {conversations.map((conv, idx) => (
          <div key={idx} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[80%] bg-blue-600 text-white p-3 rounded-lg">
                <p className="text-sm">{conv.query}</p>
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[80%] bg-gray-100 p-3 rounded-lg">
                {conv.context.formatted_response ? (
                  renderResponse(conv.context)
                ) : (
                  <p className="text-sm text-gray-700">{conv.response}</p>
                )}
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 p-3 rounded-lg">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-700"></div>
                <span className="text-sm text-gray-700">Thinking...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <form onSubmit={handleSubmit} className="p-4 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about meetings, decisions, or action items..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </form>

      {/* Resize Handle */}
      {!isMaximized && (
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
          onMouseDown={handleResizeStart}
        >
          <div className="absolute bottom-1 right-1 w-2 h-2 border-b-2 border-r-2 border-gray-400"></div>
        </div>
      )}
    </div>
  );
};