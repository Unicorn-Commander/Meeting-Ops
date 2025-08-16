import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Search, 
  Calendar, 
  Clock, 
  Mic, 
  Download, 
  Play,
  Trash2,
  Filter,
  ChevronRight
} from 'lucide-react';
import { config } from '../config';

interface Session {
  id: string;
  title: string;
  created_at: string;
  duration: number;
  transcript_text?: string;
  ai_insights?: any;
  status: 'completed' | 'processing' | 'failed';
}

export function Sessions() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [filteredSessions, setFilteredSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFilter, setDateFilter] = useState('all');

  useEffect(() => {
    fetchSessions();
  }, []);

  useEffect(() => {
    filterSessions();
  }, [sessions, searchTerm, dateFilter]);

  const fetchSessions = async () => {
    try {
      console.log('📋 Fetching sessions from:', `${config.apiUrl}/api/simple/recording-sessions`);
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions`);
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Sessions API response:', data);
        // API returns array directly, not wrapped in { sessions: [...] }
        const sessionsList = Array.isArray(data) ? data : (data.sessions || []);
        console.log('📊 Setting sessions:', sessionsList.length, 'sessions');
        setSessions(sessionsList);
      } else {
        console.error('❌ Failed to fetch sessions:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const filterSessions = () => {
    let filtered = [...sessions];

    // Search filter
    if (searchTerm) {
      filtered = filtered.filter(session => 
        session.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        session.transcript_text?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Date filter
    const now = new Date();
    if (dateFilter === 'today') {
      filtered = filtered.filter(session => {
        const sessionDate = new Date(session.created_at);
        return sessionDate.toDateString() === now.toDateString();
      });
    } else if (dateFilter === 'week') {
      const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      filtered = filtered.filter(session => 
        new Date(session.created_at) >= weekAgo
      );
    } else if (dateFilter === 'month') {
      const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      filtered = filtered.filter(session => 
        new Date(session.created_at) >= monthAgo
      );
    }

    setFilteredSessions(filtered);
  };

  const formatDuration = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const today = new Date();
    
    if (date.toDateString() === today.toDateString()) {
      return `Today, ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
      return `Yesterday, ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    
    return date.toLocaleDateString([], { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const downloadTranscript = async (session: Session) => {
    const content = `Meeting: ${session.title}\nDate: ${formatDate(session.created_at)}\nDuration: ${formatDuration(session.duration)}\n\n${session.transcript_text || 'No transcript available'}`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.title.replace(/[^a-z0-9]/gi, '_')}_transcript.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const deleteSession = async (sessionId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) return;
    
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions/${sessionId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        setSessions(prev => prev.filter(s => s.id !== sessionId));
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100 p-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Sessions</h1>
        <p className="text-zinc-400">Browse and manage your recorded meetings</p>
      </div>

      {/* Filters */}
      <div className="max-w-7xl mx-auto mb-6">
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-zinc-400" />
            <input
              type="text"
              placeholder="Search sessions, transcripts, or speakers..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-700"
            />
          </div>

          {/* Date Filter */}
          <div className="flex gap-2">
            {['all', 'today', 'week', 'month'].map(filter => (
              <button
                key={filter}
                onClick={() => setDateFilter(filter)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  dateFilter === filter
                    ? 'bg-zinc-800 text-white'
                    : 'bg-zinc-900 text-zinc-400 hover:text-white hover:bg-zinc-800'
                }`}
              >
                {filter.charAt(0).toUpperCase() + filter.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Results count */}
        <div className="mt-4 text-sm text-zinc-400">
          {filteredSessions.length} {filteredSessions.length === 1 ? 'session' : 'sessions'} found
        </div>
      </div>

      {/* Sessions Grid */}
      <div className="max-w-7xl mx-auto">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-zinc-400">Loading sessions...</div>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Mic className="w-16 h-16 text-zinc-700 mb-4" />
            <h3 className="text-xl font-semibold text-zinc-400 mb-2">No sessions found</h3>
            <p className="text-zinc-500 mb-6">
              {searchTerm || dateFilter !== 'all' 
                ? 'Try adjusting your filters' 
                : 'Start recording to create your first session'}
            </p>
            <button
              onClick={() => navigate('/record')}
              className="px-6 py-3 bg-gradient-to-r from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 text-white rounded-xl font-medium transition-colors"
            >
              Start Recording
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
            {filteredSessions.map(session => (
              <div
                key={session.id}
                className="group rounded-2xl bg-zinc-900/70 border border-zinc-800 hover:border-zinc-700 transition-all hover:shadow-xl hover:shadow-black/50"
              >
                {/* Session Card Header */}
                <div className="p-6 border-b border-zinc-800">
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-lg font-semibold text-white line-clamp-2">
                      {session.title}
                    </h3>
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      session.status === 'completed' 
                        ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                        : session.status === 'processing'
                        ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/30'
                        : 'bg-red-500/10 text-red-400 border border-red-500/30'
                    }`}>
                      {session.status}
                    </span>
                  </div>
                  
                  <div className="flex items-center gap-4 text-sm text-zinc-400">
                    <div className="flex items-center gap-1">
                      <Calendar className="w-4 h-4" />
                      {formatDate(session.created_at)}
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      {formatDuration(session.duration)}
                    </div>
                  </div>
                </div>

                {/* Session Preview */}
                <div className="p-6">
                  {session.ai_insights?.summary ? (
                    <p className="text-sm text-zinc-300 line-clamp-3 mb-4">
                      {session.ai_insights.summary}
                    </p>
                  ) : session.transcript_text ? (
                    <p className="text-sm text-zinc-300 line-clamp-3 mb-4">
                      {session.transcript_text.substring(0, 150)}...
                    </p>
                  ) : (
                    <p className="text-sm text-zinc-500 italic mb-4">
                      No transcript available
                    </p>
                  )}

                  {/* Action Items Preview */}
                  {session.ai_insights?.action_items?.length > 0 && (
                    <div className="mb-4">
                      <div className="text-xs text-zinc-400 mb-2">Action Items</div>
                      <div className="space-y-1">
                        {session.ai_insights.action_items.slice(0, 2).map((item: string, idx: number) => (
                          <div key={idx} className="text-xs text-zinc-300 flex items-start gap-2">
                            <span className="text-orange-400 mt-0.5">•</span>
                            <span className="line-clamp-1">{item}</span>
                          </div>
                        ))}
                        {session.ai_insights.action_items.length > 2 && (
                          <div className="text-xs text-zinc-500">
                            +{session.ai_insights.action_items.length - 2} more
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => navigate(`/sessions/${session.id}`)}
                      className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
                    >
                      <Play className="w-4 h-4" />
                      View
                    </button>
                    <button
                      onClick={() => downloadTranscript(session)}
                      className="p-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-zinc-200 transition-colors"
                      title="Download transcript"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => deleteSession(session.id)}
                      className="p-2 bg-zinc-800 hover:bg-red-900/50 rounded-lg text-zinc-200 hover:text-red-400 transition-colors"
                      title="Delete session"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}