import React, { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, Send, Bot, User, Brain, Database,
  Network, Clock, Tag, Search, Filter, Trash2,
  Download, RefreshCw, Settings, Lightbulb,
  TrendingUp, BarChart, Users, Calendar,
  BookOpen, Archive, Star, Share2
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  context?: {
    sessionIds?: string[];
    topics?: string[];
    timeRange?: {
      start: string;
      end: string;
    };
    relevantMeetings?: string[];
    graphNodes?: string[];
  };
  sources?: Array<{
    type: 'meeting' | 'transcript' | 'insight' | 'document';
    id: string;
    title: string;
    relevance: number;
  }>;
  metadata?: {
    responseTime?: number;
    confidence?: number;
    tokensUsed?: number;
  };
}

interface ChatSession {
  id: string;
  name: string;
  description?: string;
  createdAt: string;
  lastMessage?: string;
  messageCount: number;
  topics: string[];
  isStarred: boolean;
}

interface ContextFilter {
  timeRange: 'all' | 'today' | 'week' | 'month' | 'quarter' | 'year' | 'custom';
  customStart?: string;
  customEnd?: string;
  categories: string[];
  participants: string[];
  meetingTypes: string[];
  includeTranscripts: boolean;
  includeInsights: boolean;
  includeDocuments: boolean;
}

interface KnowledgeGraph {
  nodes: Array<{
    id: string;
    label: string;
    type: 'meeting' | 'person' | 'topic' | 'decision' | 'action';
    size: number;
    color: string;
    metadata: any;
  }>;
  edges: Array<{
    source: string;
    target: string;
    weight: number;
    type: string;
    label?: string;
  }>;
}

export const AIChatInterface: React.FC = () => {
  const [currentSession, setCurrentSession] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'chat' | 'graph' | 'memory'>('chat');
  const [contextFilter, setContextFilter] = useState<ContextFilter>({
    timeRange: 'month',
    categories: [],
    participants: [],
    meetingTypes: [],
    includeTranscripts: true,
    includeInsights: true,
    includeDocuments: false
  });
  const [knowledgeGraph, setKnowledgeGraph] = useState<KnowledgeGraph | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadChatData();
    loadSuggestedQuestions();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (currentSession) {
      loadMessages(currentSession);
    }
  }, [currentSession]);

  const loadChatData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Load chat sessions
      const sessionsResponse = await fetch(`${API_BASE_URL}/api/ai-chat/sessions`, { headers });
      if (sessionsResponse.ok) {
        const sessionsData = await sessionsResponse.json();
        setSessions(sessionsData);
        if (sessionsData.length > 0) {
          setCurrentSession(sessionsData[0].id);
        }
      } else {
        // Mock data for demonstration
        const mockSessions: ChatSession[] = [
          {
            id: 'session-1',
            name: 'Q4 Strategy Discussion',
            description: 'Analysis of Q4 planning meetings and strategic decisions',
            createdAt: '2025-01-09T10:00:00Z',
            lastMessage: 'What were the key outcomes from our Q4 planning sessions?',
            messageCount: 12,
            topics: ['strategy', 'planning', 'Q4', 'budget'],
            isStarred: true
          },
          {
            id: 'session-2',
            name: 'Team Performance Analysis',
            description: 'Insights from standup meetings and team dynamics',
            createdAt: '2025-01-08T14:30:00Z',
            lastMessage: 'Show me trends in team velocity over the past quarter',
            messageCount: 8,
            topics: ['performance', 'team', 'velocity', 'analytics'],
            isStarred: false
          },
          {
            id: 'session-3',
            name: 'Technical Architecture Review',
            description: 'Discussion about system design and technical decisions',
            createdAt: '2025-01-07T09:15:00Z',
            lastMessage: 'What are the main technical risks we discussed?',
            messageCount: 15,
            topics: ['architecture', 'technical', 'risks', 'design'],
            isStarred: false
          }
        ];
        setSessions(mockSessions);
        setCurrentSession(mockSessions[0].id);
      }

      // Load knowledge graph
      const graphResponse = await fetch(`${API_BASE_URL}/api/ai-chat/knowledge-graph`, { headers });
      if (graphResponse.ok) {
        const graphData = await graphResponse.json();
        setKnowledgeGraph(graphData);
      } else {
        // Mock graph data
        setKnowledgeGraph({
          nodes: [
            { id: 'meeting-1', label: 'Q4 Planning', type: 'meeting', size: 20, color: '#3B82F6', metadata: { date: '2025-01-05', attendees: 8 } },
            { id: 'meeting-2', label: 'Team Standup', type: 'meeting', size: 15, color: '#3B82F6', metadata: { date: '2025-01-09', attendees: 6 } },
            { id: 'person-1', label: 'John Doe', type: 'person', size: 18, color: '#10B981', metadata: { role: 'Manager' } },
            { id: 'person-2', label: 'Sarah Wilson', type: 'person', size: 16, color: '#10B981', metadata: { role: 'Tech Lead' } },
            { id: 'topic-1', label: 'Budget Planning', type: 'topic', size: 12, color: '#F59E0B', metadata: { mentions: 15 } },
            { id: 'topic-2', label: 'Performance Metrics', type: 'topic', size: 10, color: '#F59E0B', metadata: { mentions: 8 } },
            { id: 'decision-1', label: 'Hire 2 Developers', type: 'decision', size: 14, color: '#8B5CF6', metadata: { priority: 'high' } },
            { id: 'action-1', label: 'Prepare Budget Proposal', type: 'action', size: 12, color: '#EF4444', metadata: { assignee: 'John Doe', dueDate: '2025-01-15' } }
          ],
          edges: [
            { source: 'meeting-1', target: 'person-1', weight: 0.8, type: 'attended' },
            { source: 'meeting-1', target: 'person-2', weight: 0.7, type: 'attended' },
            { source: 'meeting-1', target: 'topic-1', weight: 0.9, type: 'discussed' },
            { source: 'meeting-1', target: 'decision-1', weight: 0.8, type: 'decided' },
            { source: 'decision-1', target: 'action-1', weight: 0.9, type: 'resulted_in' },
            { source: 'person-1', target: 'action-1', weight: 0.8, type: 'assigned' },
            { source: 'meeting-2', target: 'person-2', weight: 0.9, type: 'attended' },
            { source: 'meeting-2', target: 'topic-2', weight: 0.7, type: 'discussed' }
          ]
        });
      }
    } catch (error) {
      console.error('Failed to load chat data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadMessages = async (sessionId: string) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/ai-chat/sessions/${sessionId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const messagesData = await response.json();
        setMessages(messagesData);
      } else {
        // Mock messages for demonstration
        const mockMessages: ChatMessage[] = [
          {
            id: 'msg-1',
            role: 'system',
            content: 'AI Assistant initialized with access to 45 meeting transcripts, 156 insights, and contextual memory spanning the last 6 months.',
            timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          },
          {
            id: 'msg-2',
            role: 'user',
            content: 'What were the key outcomes from our Q4 planning sessions?',
            timestamp: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
            context: {
              sessionIds: ['session-123', 'session-124'],
              topics: ['Q4', 'planning', 'budget'],
              timeRange: { start: '2024-10-01', end: '2024-12-31' }
            }
          },
          {
            id: 'msg-3',
            role: 'assistant',
            content: `Based on analysis of 3 Q4 planning meetings from October-December 2024, here are the key outcomes:

**Strategic Decisions:**
• Approved 23% budget increase for engineering team
• Decided to expand into European markets in Q2 2025
• Prioritized API modernization as top technical initiative

**Action Items Identified:**
• Hire 2 senior developers by January 15th (Assigned: John Doe)
• Complete market research for EU expansion (Assigned: Sarah Wilson)
• Draft technical roadmap for API v2.0 (Assigned: Mike Chen)

**Key Metrics & Targets:**
• Revenue target: $2.4M for Q4 (achieved $2.6M - 108% of goal)
• Customer acquisition: 150 new clients (achieved 167 - 111% of goal)
• Team growth: Expand from 28 to 35 employees

**Risk Mitigation:**
• Identified dependency on key client contracts
• Established backup hiring pipeline for critical roles
• Created contingency budget allocation of $50K

Would you like me to dive deeper into any specific area or analyze the follow-through on these decisions?`,
            timestamp: new Date(Date.now() - 7 * 60 * 1000).toISOString(),
            sources: [
              { type: 'meeting', id: 'session-123', title: 'Q4 Planning - Strategic Review', relevance: 0.95 },
              { type: 'meeting', id: 'session-124', title: 'Q4 Planning - Budget Discussion', relevance: 0.88 },
              { type: 'insight', id: 'insight-45', title: 'Revenue Performance Analysis', relevance: 0.82 }
            ],
            metadata: {
              responseTime: 2340,
              confidence: 0.92,
              tokensUsed: 445
            }
          }
        ];
        setMessages(mockMessages);
      }
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const loadSuggestedQuestions = () => {
    setSuggestedQuestions([
      "What are the recurring themes across our team meetings?",
      "Show me decision patterns from the past quarter",
      "Which action items are overdue and who's responsible?",
      "Analyze the sentiment trends in our board meetings",
      "What topics correlate with longer meeting durations?",
      "Who are the most active contributors in technical discussions?",
      "Compare team velocity metrics across different quarters",
      "What are the emerging risks mentioned in recent meetings?"
    ]);
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || !currentSession) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputMessage.trim(),
      timestamp: new Date().toISOString(),
      context: {
        sessionIds: [], // Will be populated based on context filter
        topics: extractTopics(inputMessage),
        timeRange: getTimeRangeFromFilter()
      }
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsTyping(true);

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/ai-chat/sessions/${currentSession}/messages`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: inputMessage.trim(),
          context: contextFilter,
          useMemoryDatabase: true,
          includeGraphContext: true
        })
      });

      if (response.ok) {
        const aiResponse = await response.json();
        const assistantMessage: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          role: 'assistant',
          content: aiResponse.content,
          timestamp: new Date().toISOString(),
          sources: aiResponse.sources || [],
          metadata: aiResponse.metadata || {}
        };
        setMessages(prev => [...prev, assistantMessage]);
      } else {
        // Mock AI response for demonstration
        setTimeout(() => {
          const mockResponse: ChatMessage = {
            id: `msg-${Date.now() + 1}`,
            role: 'assistant',
            content: generateMockAIResponse(inputMessage),
            timestamp: new Date().toISOString(),
            sources: [
              { type: 'meeting', id: 'session-recent', title: 'Recent Team Meeting', relevance: 0.85 }
            ],
            metadata: {
              responseTime: 1500,
              confidence: 0.88,
              tokensUsed: 320
            }
          };
          setMessages(prev => [...prev, mockResponse]);
        }, 2000);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      toast.error('Failed to send message');
    } finally {
      setIsTyping(false);
    }
  };

  const generateMockAIResponse = (question: string): string => {
    const responses = [
      `Based on analysis of recent meetings and memory database context, I can provide insights about "${question}". The data shows interesting patterns across your meeting history with contextual connections to previous discussions.`,
      `From the graph database analysis, I've identified key relationships between participants, topics, and decisions related to your query. The memory system reveals temporal patterns that might be relevant.`,
      `Analyzing the historical context and categorical patterns, here are the insights from your meeting database. The AI has cross-referenced multiple sessions to provide comprehensive context.`
    ];
    return responses[Math.floor(Math.random() * responses.length)];
  };

  const extractTopics = (text: string): string[] => {
    const commonTopics = ['meeting', 'planning', 'budget', 'team', 'strategy', 'technical', 'performance'];
    return commonTopics.filter(topic => text.toLowerCase().includes(topic));
  };

  const getTimeRangeFromFilter = () => {
    const now = new Date();
    const ranges = {
      today: { start: new Date(now.setHours(0,0,0,0)), end: new Date() },
      week: { start: new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000), end: new Date() },
      month: { start: new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000), end: new Date() },
      quarter: { start: new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000), end: new Date() },
      year: { start: new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000), end: new Date() }
    };
    
    const range = ranges[contextFilter.timeRange as keyof typeof ranges];
    return range ? {
      start: range.start.toISOString(),
      end: range.end.toISOString()
    } : { start: '', end: '' };
  };

  const createNewSession = () => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      name: `New Chat ${sessions.length + 1}`,
      createdAt: new Date().toISOString(),
      messageCount: 0,
      topics: [],
      isStarred: false
    };
    setSessions([newSession, ...sessions]);
    setCurrentSession(newSession.id);
    setMessages([]);
  };

  const deleteSession = (sessionId: string) => {
    if (!confirm('Delete this chat session?')) return;
    setSessions(sessions.filter(s => s.id !== sessionId));
    if (currentSession === sessionId) {
      const remaining = sessions.filter(s => s.id !== sessionId);
      setCurrentSession(remaining.length > 0 ? remaining[0].id : null);
    }
    toast.success('Session deleted');
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const exportChat = () => {
    const chatData = {
      session: sessions.find(s => s.id === currentSession),
      messages: messages,
      exportedAt: new Date().toISOString()
    };
    
    const blob = new Blob([JSON.stringify(chatData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat-export-${currentSession}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="h-screen flex bg-gray-900 text-white">
      {/* Sidebar - Chat Sessions */}
      <div className="w-80 bg-gray-800 border-r border-gray-700 flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold flex items-center">
              <Brain className="w-6 h-6 text-purple-400 mr-2" />
              AI Assistant
            </h2>
            <button
              onClick={createNewSession}
              className="p-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors"
              title="New Chat"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </div>
          
          {/* Context Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center w-full p-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            <Filter className="w-4 h-4 mr-2" />
            Context: {contextFilter.timeRange} • {contextFilter.includeTranscripts ? 'T' : ''}
            {contextFilter.includeInsights ? 'I' : ''}
          </button>
        </div>

        {/* Context Filters */}
        {showFilters && (
          <div className="p-4 bg-gray-750 border-b border-gray-700 space-y-3">
            <div>
              <label className="block text-sm font-medium mb-1">Time Range</label>
              <select
                value={contextFilter.timeRange}
                onChange={(e) => setContextFilter({...contextFilter, timeRange: e.target.value as any})}
                className="w-full px-3 py-1 bg-gray-600 border border-gray-500 rounded text-sm"
              >
                <option value="today">Today</option>
                <option value="week">Past Week</option>
                <option value="month">Past Month</option>
                <option value="quarter">Past Quarter</option>
                <option value="year">Past Year</option>
                <option value="all">All Time</option>
              </select>
            </div>
            
            <div className="flex flex-wrap gap-2">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={contextFilter.includeTranscripts}
                  onChange={(e) => setContextFilter({...contextFilter, includeTranscripts: e.target.checked})}
                  className="mr-1"
                />
                <span className="text-xs">Transcripts</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={contextFilter.includeInsights}
                  onChange={(e) => setContextFilter({...contextFilter, includeInsights: e.target.checked})}
                  className="mr-1"
                />
                <span className="text-xs">AI Insights</span>
              </label>
            </div>
          </div>
        )}

        {/* Chat Sessions List */}
        <div className="flex-1 overflow-y-auto">
          {sessions.map(session => (
            <div
              key={session.id}
              className={`p-3 border-b border-gray-700 cursor-pointer transition-colors ${
                currentSession === session.id ? 'bg-gray-700' : 'hover:bg-gray-750'
              }`}
              onClick={() => setCurrentSession(session.id)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center">
                    <h3 className="font-medium truncate">{session.name}</h3>
                    {session.isStarred && <Star className="w-4 h-4 text-yellow-400 ml-1" />}
                  </div>
                  {session.description && (
                    <p className="text-xs text-gray-400 truncate mt-1">{session.description}</p>
                  )}
                  <div className="flex items-center text-xs text-gray-500 mt-2">
                    <span>{session.messageCount} messages</span>
                    <span className="mx-2">•</span>
                    <span>{new Date(session.createdAt).toLocaleDateString()}</span>
                  </div>
                </div>
                
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(session.id);
                  }}
                  className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
              
              {session.topics.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {session.topics.slice(0, 3).map(topic => (
                    <span key={topic} className="px-2 py-1 bg-gray-600 rounded-full text-xs">
                      {topic}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Chat Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between bg-gray-800">
          <div className="flex items-center">
            <h3 className="font-semibold">
              {sessions.find(s => s.id === currentSession)?.name || 'Select a Chat'}
            </h3>
            {currentSession && (
              <div className="ml-4 flex items-center space-x-2 text-sm text-gray-400">
                <Database className="w-4 h-4" />
                <span>Memory DB</span>
                <Network className="w-4 h-4" />
                <span>Graph Context</span>
              </div>
            )}
          </div>
          
          <div className="flex items-center space-x-2">
            {/* Tab Controls */}
            <div className="flex space-x-1 bg-gray-700 rounded-lg p-1">
              {[
                { id: 'chat', label: 'Chat', icon: MessageSquare },
                { id: 'graph', label: 'Graph', icon: Network },
                { id: 'memory', label: 'Memory', icon: Database }
              ].map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`flex items-center gap-1 px-3 py-1 rounded-md transition-colors text-sm ${
                      activeTab === tab.id
                        ? 'bg-purple-600 text-white'
                        : 'text-gray-400 hover:text-white hover:bg-gray-600'
                    }`}
                  >
                    <Icon className="w-3 h-3" />
                    {tab.label}
                  </button>
                );
              })}
            </div>
            
            <button
              onClick={exportChat}
              className="p-2 text-gray-400 hover:text-white transition-colors"
              title="Export Chat"
            >
              <Download className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Chat Content */}
        {activeTab === 'chat' && (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && suggestedQuestions.length > 0 && (
                <div className="text-center">
                  <div className="mb-6">
                    <Brain className="w-16 h-16 mx-auto text-purple-400 mb-4" />
                    <h3 className="text-xl font-semibold mb-2">AI Assistant Ready</h3>
                    <p className="text-gray-400">
                      Ask me anything about your meetings, analyze patterns, or explore the knowledge graph
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3 max-w-4xl mx-auto">
                    {suggestedQuestions.slice(0, 6).map((question, index) => (
                      <button
                        key={index}
                        onClick={() => setInputMessage(question)}
                        className="p-3 bg-gray-800 hover:bg-gray-700 rounded-lg text-left text-sm transition-colors border border-gray-700"
                      >
                        <Lightbulb className="w-4 h-4 text-yellow-400 mb-2" />
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              
              {messages.map(message => (
                <div
                  key={message.id}
                  className={`flex items-start space-x-3 ${
                    message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''
                  }`}
                >
                  <div className={`p-2 rounded-full ${
                    message.role === 'user' 
                      ? 'bg-purple-600' 
                      : message.role === 'assistant'
                      ? 'bg-blue-600'
                      : 'bg-gray-600'
                  }`}>
                    {message.role === 'user' ? (
                      <User className="w-4 h-4" />
                    ) : message.role === 'assistant' ? (
                      <Bot className="w-4 h-4" />
                    ) : (
                      <Settings className="w-4 h-4" />
                    )}
                  </div>
                  
                  <div className={`flex-1 max-w-4xl ${
                    message.role === 'user' ? 'text-right' : ''
                  }`}>
                    <div className={`rounded-lg p-4 ${
                      message.role === 'user'
                        ? 'bg-purple-600/20 border border-purple-600/30'
                        : message.role === 'assistant'
                        ? 'bg-gray-800 border border-gray-700'
                        : 'bg-gray-700/50 border border-gray-600'
                    }`}>
                      <div className="whitespace-pre-wrap">{message.content}</div>
                      
                      {message.sources && message.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-600">
                          <p className="text-xs text-gray-400 mb-2">Sources:</p>
                          <div className="space-y-1">
                            {message.sources.map((source, index) => (
                              <div key={index} className="flex items-center justify-between text-xs">
                                <span className="text-blue-400">{source.title}</span>
                                <span className="text-gray-500">{Math.round(source.relevance * 100)}%</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      <div className="flex items-center justify-between text-xs text-gray-500 mt-2">
                        <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
                        {message.metadata && (
                          <span>
                            {message.metadata.responseTime}ms • {message.metadata.confidence && Math.round(message.metadata.confidence * 100)}% confidence
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              
              {isTyping && (
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-blue-600 rounded-full">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                    </div>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="p-4 border-t border-gray-700 bg-gray-800">
              <div className="flex items-center space-x-2">
                <div className="flex-1 relative">
                  <input
                    type="text"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                    placeholder="Ask me about your meetings, analyze patterns, explore relationships..."
                    className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500 pr-12"
                    disabled={isTyping}
                  />
                  <div className="absolute right-3 top-1/2 transform -translate-y-1/2 flex items-center space-x-1 text-xs text-gray-500">
                    <Database className="w-3 h-3" />
                    <Network className="w-3 h-3" />
                  </div>
                </div>
                <button
                  onClick={sendMessage}
                  disabled={!inputMessage.trim() || isTyping}
                  className="p-3 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
              
              <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
                <span>Context: {contextFilter.timeRange} • Memory & Graph enabled</span>
                <span>Press Enter to send</span>
              </div>
            </div>
          </>
        )}

        {/* Graph View */}
        {activeTab === 'graph' && (
          <div className="flex-1 p-6 bg-gray-850">
            <div className="text-center">
              <Network className="w-16 h-16 mx-auto text-blue-400 mb-4" />
              <h3 className="text-xl font-semibold mb-2">Knowledge Graph Visualization</h3>
              <p className="text-gray-400 mb-6">
                Interactive visualization of meetings, people, topics, and relationships
              </p>
              
              {knowledgeGraph && (
                <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-400">
                        {knowledgeGraph.nodes.filter(n => n.type === 'meeting').length}
                      </div>
                      <div className="text-sm text-gray-400">Meetings</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-400">
                        {knowledgeGraph.nodes.filter(n => n.type === 'person').length}
                      </div>
                      <div className="text-sm text-gray-400">People</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-yellow-400">
                        {knowledgeGraph.nodes.filter(n => n.type === 'topic').length}
                      </div>
                      <div className="text-sm text-gray-400">Topics</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-purple-400">
                        {knowledgeGraph.nodes.filter(n => n.type === 'decision').length}
                      </div>
                      <div className="text-sm text-gray-400">Decisions</div>
                    </div>
                  </div>
                  
                  <div className="text-center text-gray-400">
                    Interactive graph visualization would be rendered here using D3.js or similar
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Memory Database View */}
        {activeTab === 'memory' && (
          <div className="flex-1 p-6 bg-gray-850">
            <div className="text-center">
              <Database className="w-16 h-16 mx-auto text-green-400 mb-4" />
              <h3 className="text-xl font-semibold mb-2">Memory Database</h3>
              <p className="text-gray-400 mb-6">
                Persistent context and learning from all meeting interactions
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <BarChart className="w-8 h-8 text-blue-400 mx-auto mb-3" />
                  <h4 className="font-semibold mb-2">Context Memory</h4>
                  <div className="text-2xl font-bold text-blue-400 mb-1">45</div>
                  <div className="text-sm text-gray-400">Stored sessions</div>
                </div>
                
                <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <TrendingUp className="w-8 h-8 text-green-400 mx-auto mb-3" />
                  <h4 className="font-semibold mb-2">Pattern Learning</h4>
                  <div className="text-2xl font-bold text-green-400 mb-1">156</div>
                  <div className="text-sm text-gray-400">Behavioral patterns</div>
                </div>
                
                <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <Archive className="w-8 h-8 text-purple-400 mx-auto mb-3" />
                  <h4 className="font-semibold mb-2">Long-term Memory</h4>
                  <div className="text-2xl font-bold text-purple-400 mb-1">2.3K</div>
                  <div className="text-sm text-gray-400">Concepts learned</div>
                </div>
              </div>
              
              <div className="mt-6 bg-gray-800 rounded-lg p-4 border border-gray-700 text-left">
                <h4 className="font-semibold mb-3">Recent Learning Events</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span>Learned: "Budget planning patterns"</span>
                    <span className="text-gray-400">2 hours ago</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Updated: "Team communication style"</span>
                    <span className="text-gray-400">1 day ago</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Associated: "John Doe → Strategic planning"</span>
                    <span className="text-gray-400">2 days ago</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};