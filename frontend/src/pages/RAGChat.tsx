import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Trash2, ExternalLink } from 'lucide-react';
import { useOrg } from '../contexts/OrgContext';
import { config } from '../config';

interface Citation {
  meeting_id: string;
  chunk_idx: number;
  snippet: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  metadata?: any;
}

export default function RAGChatPanel() {
  const { activeOrganization } = useOrg();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  useEffect(() => {
    if (activeOrganization) {
      loadHistory();
    }
  }, [activeOrganization?.slug]);

  const getHeaders = () => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (activeOrganization?.slug) {
      headers['X-MeetingOps-Org'] = activeOrganization.slug;
    }
    return headers;
  };

  const loadHistory = async () => {
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/rag/chat/history`, {
        headers: getHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setMessages(data.map((m: any) => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
          })));
        }
      }
    } catch { /* skip */ }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setLoading(true);
    setStreaming('');

    try {
      const res = await fetch(`${config.apiBaseUrl}/api/rag/chat`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          question,
          scope: {},
          history: messages.map(m => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Error: Unable to reach RAG service.' }]);
        setLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setLoading(false);
        return;
      }

      const decoder = new TextDecoder();
      let fullContent = '';
      let finalCitations: Citation[] = [];
      let finalMetadata: any = {};

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.token) {
                fullContent += data.token;
                setStreaming(fullContent);
              } else if (data.done) {
                finalCitations = data.sources || [];
                finalMetadata = data.metadata || {};
              } else if (data.error) {
                fullContent += `\n[Error: ${data.error}]`;
              }
            } catch { /* skip malformed JSON */ }
          }
        }
      }

      setStreaming('');
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: fullContent,
        citations: finalCitations,
        metadata: finalMetadata,
      }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: Failed to connect to RAG service.' }]);
    }
    setLoading(false);
  };

  const clearHistory = async () => {
    try {
      await fetch(`${config.apiBaseUrl}/api/rag/chat/history`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
    } catch { /* skip */ }
    setMessages([]);
    setStreaming('');
  };

  return (
    <div className="flex flex-col h-full bg-zinc-950">
      <div className="flex items-center justify-between p-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-fuchsia-400" />
          <span className="text-sm font-medium text-zinc-100">Meeting RAG Chat</span>
        </div>
        <button
          onClick={clearHistory}
          className="p-2 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors"
          title="Clear history"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-zinc-500 py-8">
            <Bot className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>Ask questions about your meetings across time.</p>
            <p className="text-xs mt-1">E.g. "What were the key decisions from last month?"</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role === 'assistant' && (
              <Bot className="w-5 h-5 mt-1 text-fuchsia-400 flex-shrink-0" />
            )}
            <div className={`max-w-[80%] rounded-lg px-3 py-2 ${
              msg.role === 'user'
                ? 'bg-fuchsia-600 text-white'
                : 'bg-zinc-800 text-zinc-100'
            }`}>
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700">
                  <p className="text-xs text-zinc-400 mb-1">Sources:</p>
                  {msg.citations.map((c, j) => (
                    <a
                      key={j}
                      href={`#/sessions/${c.meeting_id}`}
                      className="flex items-center gap-1 text-xs text-fuchsia-400 hover:text-fuchsia-300 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      Meeting {c.meeting_id} chunk {c.chunk_idx}: {c.snippet?.slice(0, 60)}...
                    </a>
                  ))}
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <User className="w-5 h-5 mt-1 text-zinc-400 flex-shrink-0" />
            )}
          </div>
        ))}
        {streaming && (
          <div className="flex gap-3">
            <Bot className="w-5 h-5 mt-1 text-fuchsia-400 flex-shrink-0" />
            <div className="max-w-[80%] rounded-lg px-3 py-2 bg-zinc-800 text-zinc-100">
              <p className="text-sm whitespace-pre-wrap">{streaming}<span className="animate-pulse">|</span></p>
            </div>
          </div>
        )}
        {loading && !streaming && (
          <div className="flex gap-3">
            <Bot className="w-5 h-5 mt-1 text-fuchsia-400 flex-shrink-0" />
            <div className="rounded-lg px-3 py-2 bg-zinc-800 text-zinc-400">
              <span className="text-sm animate-pulse">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div className="p-3 border-t border-zinc-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder="Ask a question about your meetings..."
            className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-fuchsia-500 outline-none"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="p-2 rounded-lg bg-fuchsia-600 hover:bg-fuchsia-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
