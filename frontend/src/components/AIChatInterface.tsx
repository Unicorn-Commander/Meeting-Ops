import React, { useState, useEffect, useRef } from 'react';
import {
  MessageSquare, Send, Bot, User, Loader2, 
  Sparkles, Clock, ChevronRight, AlertCircle,
  Brain, Database, Globe, History, X
} from 'lucide-react';
import { config } from '../config';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  isLoading?: boolean;
}

interface AIChatInterfaceProps {
  sessionId?: string;  // If provided, chat is about specific meeting
  transcript?: string; // Meeting transcript for context
  className?: string;
  isGlobal?: boolean; // If true, uses global assistant across all meetings
}

export const AIChatInterface: React.FC<AIChatInterfaceProps> = ({
  sessionId,
  transcript,
  className = '',
  isGlobal = false
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Load chat history from localStorage
    const key = sessionId ? `chat_${sessionId}` : 'chat_global';
    const savedMessages = localStorage.getItem(key);
    if (savedMessages) {
      try {
        const parsed = JSON.parse(savedMessages);
        // Convert timestamp strings back to Date objects
        const messagesWithDates = parsed.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }));
        setMessages(messagesWithDates);
      } catch (e) {
        console.error('Failed to parse saved messages:', e);
        setMessages([getWelcomeMessage()]);
      }
    } else {
      // Add welcome message
      setMessages([getWelcomeMessage()]);
    }
  }, [sessionId, isGlobal]);

  const getWelcomeMessage = (): ChatMessage => ({
    id: Date.now().toString(),
    role: 'assistant',
    content: isGlobal 
      ? "Hello! I'm your AI assistant. I can help you with information across all your meetings. What would you like to know?"
      : "Hello! I can help you understand and extract insights from this meeting. What would you like to know?",
    timestamp: new Date()
  });

  useEffect(() => {
    // Save chat history
    const key = sessionId ? `chat_${sessionId}` : 'chat_global';
    if (messages.length > 0) {
      // Convert Date objects to strings for storage
      const messagesForStorage = messages.map(msg => ({
        ...msg,
        timestamp: msg.timestamp.toISOString()
      }));
      localStorage.setItem(key, JSON.stringify(messagesForStorage));
    }
  }, [messages, sessionId]);

  useEffect(() => {
    // Auto-scroll to bottom
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    const loadingMessage: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true
    };

    setMessages(prev => [...prev, userMessage, loadingMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const endpoint = isGlobal 
        ? `${config.apiBaseUrl}/api/ai/global-chat`
        : `${config.apiBaseUrl}/api/meeting-notes/chat`;

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          session_id: sessionId,
          query: inputMessage,
          transcript: transcript || '',
          history: messages.slice(-10).map(msg => ({
            role: msg.role,
            content: msg.content
          }))
        })
      });

      if (response.ok) {
        const data = await response.json();
        
        // Replace loading message with actual response
        setMessages(prev => prev.map(msg => 
          msg.id === loadingMessage.id 
            ? {
                ...msg,
                content: data.response || 'I apologize, but I was unable to generate a response.',
                isLoading: false
              }
            : msg
        ));
      } else {
        throw new Error('Failed to get response');
      }
    } catch (error) {
      console.error('Chat error:', error);
      
      // Replace loading message with error
      setMessages(prev => prev.map(msg => 
        msg.id === loadingMessage.id 
          ? {
              ...msg,
              content: 'I apologize, but I encountered an error. Please try again.',
              isLoading: false
            }
          : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const suggestedQuestions = isGlobal ? [
    "What were the main topics discussed this week?",
    "Show me all action items assigned to me",
    "What decisions were made in recent meetings?",
    "Find meetings where we discussed budget"
  ] : [
    "What are the key takeaways from this meeting?",
    "What action items were assigned?",
    "Who were the main participants?",
    "What decisions were made?"
  ];

  if (isMinimized) {
    return (
      <div className={`fixed bottom-4 right-4 z-50 ${className}`}>
        <button
          onClick={() => setIsMinimized(false)}
          className="bg-purple-600 hover:bg-purple-700 text-white rounded-full p-4 shadow-lg transition-all hover:scale-110"
        >
          <MessageSquare className="w-6 h-6" />
        </button>
      </div>
    );
  }

  return (
    <div className={`bg-gray-950 rounded-xl border border-gray-800 flex flex-col ${className}`}>
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-pink-900/30 border-b border-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Brain className="w-6 h-6 text-purple-400" />
              <Sparkles className="w-3 h-3 text-yellow-400 absolute -top-1 -right-1" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">
                {isGlobal ? 'Global AI Assistant' : 'Meeting AI Assistant'}
              </h3>
              <p className="text-xs text-gray-400">
                {isGlobal ? 'Ask about all your meetings' : 'Ask questions about this meeting'}
              </p>
            </div>
          </div>
          
          <button
            onClick={() => setIsMinimized(true)}
            className="p-1 hover:bg-gray-800 rounded transition-colors text-gray-400"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Context Indicators */}
        {isGlobal && (
          <div className="flex items-center gap-2 mt-3 text-xs">
            <span className="flex items-center gap-1 px-2 py-1 bg-blue-500/20 text-blue-300 rounded">
              <Database className="w-3 h-3" />
              All Meetings
            </span>
            <span className="flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-300 rounded">
              <History className="w-3 h-3" />
              Full History
            </span>
            <span className="flex items-center gap-1 px-2 py-1 bg-purple-500/20 text-purple-300 rounded">
              <Globe className="w-3 h-3" />
              Cross-Reference
            </span>
          </div>
        )}
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[400px] max-h-[600px]">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-3 ${
              message.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            {message.role === 'assistant' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-600/20 flex items-center justify-center">
                <Bot className="w-5 h-5 text-purple-400" />
              </div>
            )}
            
            <div
              className={`max-w-[70%] rounded-lg p-3 ${
                message.role === 'user'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-800 text-gray-200'
              }`}
            >
              {message.isLoading ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Thinking...</span>
                </div>
              ) : (
                <div className="whitespace-pre-wrap">{message.content}</div>
              )}
              <div className={`text-xs mt-2 ${
                message.role === 'user' ? 'text-purple-200' : 'text-gray-500'
              }`}>
                {message.timestamp.toLocaleTimeString()}
              </div>
            </div>
            
            {message.role === 'user' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600/20 flex items-center justify-center">
                <User className="w-5 h-5 text-blue-400" />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Questions */}
      {messages.length === 1 && (
        <div className="px-4 pb-2">
          <p className="text-xs text-gray-500 mb-2">Suggested questions:</p>
          <div className="flex flex-wrap gap-2">
            {suggestedQuestions.map((question, index) => (
              <button
                key={index}
                onClick={() => setInputMessage(question)}
                className="text-xs px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-full transition-colors flex items-center gap-1"
              >
                <ChevronRight className="w-3 h-3" />
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-gray-800 p-4">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isGlobal 
              ? "Ask about any of your meetings..." 
              : "Ask about this meeting..."
            }
            rows={2}
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-purple-500 resize-none"
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={!inputMessage.trim() || isLoading}
            className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 ${
              inputMessage.trim() && !isLoading
                ? 'bg-purple-600 hover:bg-purple-700 text-white'
                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
            }`}
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
        
        <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
          <span>Press Enter to send, Shift+Enter for new line</span>
          {isGlobal && (
            <span className="flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              Searching across all meetings
            </span>
          )}
        </div>
      </div>
    </div>
  );
};