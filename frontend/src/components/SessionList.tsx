import React, { useState, useEffect } from 'react';
import {
  FileText,
  Search,
  Download,
  Trash2,
  Eye,
  Calendar,
  Clock,
  Users,
  Volume2,
  ChevronRight,
  Filter,
  RefreshCw,
  Zap
} from 'lucide-react';

interface Session {
  id: number;
  session_id: string;
  name: string;  // Changed from 'title' to match backend
  description?: string;
  start_time: string;
  end_time?: string;
  duration_seconds?: number;  // Changed from 'duration' to match backend
  status: string;
  total_speakers?: number;  // Changed from 'speaker_count' to match backend
  total_transcriptions?: number;  // Changed from 'transcription_count' to match backend
  summary?: string;  // Changed from 'has_summary' to match backend
  // Audio metadata
  audio_file_path?: string;
  audio_format?: string;
  sample_rate?: number;
  channels?: number;
  // Processing metadata
  processing_completed?: boolean;
  npu_accelerated?: boolean;
}

interface SessionListProps {
  onSelectSession?: (session: Session) => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const SessionList: React.FC<SessionListProps> = ({ onSelectSession }) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDate, setFilterDate] = useState('all');
  const [sortBy, setSortBy] = useState<'date' | 'duration' | 'size'>('date');
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchSessions = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setSessions(data.sessions || []);
      } else {
        console.error('Failed to fetch sessions:', response.statusText);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    if (diff < 3600000) return Math.floor(diff / 60000) + ' minutes ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + ' hours ago';
    if (diff < 604800000) return Math.floor(diff / 86400000) + ' days ago';
    
    return date.toLocaleDateString();
  };

  const formatDuration = (seconds?: number): string => {
    if (!seconds || seconds === 0) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleDelete = async (sessionId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) return;
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        await fetchSessions();
      } else {
        console.error('Failed to delete session:', response.statusText);
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const handleTranscribe = async (session: Session) => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${session.session_id}/transcribe`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        await fetchSessions();
      } else {
        console.error('Failed to transcribe session:', response.statusText);
      }
    } catch (error) {
      console.error('Failed to transcribe session:', error);
    }
  };

  const handleViewTranscript = (session: Session) => {
    setSelectedSession(session.session_id);
    if (onSelectSession) {
      onSelectSession(session);
    }
  };

  const handleDownload = async (session: Session) => {
    try {
      const token = localStorage.getItem('access_token');
      // First get the files for this session
      const response = await fetch(`${API_BASE_URL}/api/files/session/${session.session_id}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.files && data.files.length > 0) {
          // Download the first file
          const fileId = data.files[0].file_id;
          window.location.href = `${API_BASE_URL}/api/files/${fileId}/download`;
        } else {
          console.warn('No audio files found for session');
        }
      }
    } catch (error) {
      console.error('Failed to download session files:', error);
    }
  };

  const filteredSessions = sessions.filter(session => {
    const matchesSearch = !searchTerm || 
      session.session_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      session.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      session.description?.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesDate = filterDate === 'all' || (() => {
      const date = session.start_time ? new Date(session.start_time) : new Date();
      const age = Date.now() - date.getTime();
      switch (filterDate) {
        case 'today': return age < 86400000;
        case 'week': return age < 604800000;
        case 'month': return age < 2592000000;
        default: return true;
      }
    })();
    
    return matchesSearch && matchesDate;
  });

  const sortedSessions = [...filteredSessions].sort((a, b) => {
    switch (sortBy) {
      case 'duration':
        return (b.duration_seconds || 0) - (a.duration_seconds || 0);
      case 'size':
        return 0; // No file size in session model
      case 'date':
      default:
        const dateA = a.start_time ? new Date(a.start_time) : new Date();
        const dateB = b.start_time ? new Date(b.start_time) : new Date();
        return dateB.getTime() - dateA.getTime();
    }
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm">
      {/* Header */}
      <div className="p-4 border-b">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <FileText className="w-5 h-5" />
            Recording Sessions
          </h2>
          <button
            onClick={fetchSessions}
            className="p-2 hover:bg-gray-100 rounded transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Search and Filters */}
        <div className="flex gap-4 items-center">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search sessions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <select
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            className="px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Time</option>
            <option value="today">Today</option>
            <option value="week">This Week</option>
            <option value="month">This Month</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="date">Sort by Date</option>
            <option value="duration">Sort by Duration</option>
            <option value="size">Sort by Size</option>
          </select>
        </div>
      </div>

      {/* Session List */}
      <div className="divide-y">
        {sortedSessions.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <FileText className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>No recording sessions found</p>
          </div>
        ) : (
          sortedSessions.map((session) => (
            <div
              key={session.session_id}
              className={`p-4 hover:bg-gray-50 transition-colors ${
                selectedSession === session.session_id ? 'bg-blue-50' : ''
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-medium text-gray-900">
                    {session.name}
                  </h3>
                  
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {formatDate(session.start_time)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDuration(session.duration_seconds)}
                    </span>
                    {session.audio_file_path && (
                      <span className="flex items-center gap-1">
                        <Volume2 className="w-3 h-3" />
                        {session.audio_format || 'WAV'}
                      </span>
                    )}
                    {session.total_speakers !== undefined && session.total_speakers > 0 && (
                      <span className="flex items-center gap-1">
                        <Users className="w-3 h-3" />
                        {session.total_speakers} speakers
                      </span>
                    )}
                  </div>

                  {session.description && (
                    <p className="mt-2 text-sm text-gray-600 line-clamp-2">
                      {session.description}
                    </p>
                  )}

                  <div className="flex items-center gap-2 mt-2">
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      session.status === 'completed' ? 'bg-green-100 text-green-800' :
                      session.status === 'recording' ? 'bg-red-100 text-red-800' :
                      session.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {session.status}
                    </span>
                    {session.total_transcriptions && session.total_transcriptions > 0 && (
                      <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                        Transcribed ({session.total_transcriptions})
                      </span>
                    )}
                    {session.summary && (
                      <span className="px-2 py-1 text-xs bg-purple-100 text-purple-800 rounded-full">
                        Summary
                      </span>
                    )}
                    {session.npu_accelerated && (
                      <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full flex items-center gap-1">
                        <Zap className="w-3 h-3" />
                        NPU
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 ml-4">
                  {session.status === 'completed' && (!session.total_transcriptions || session.total_transcriptions === 0) && (
                    <button
                      onClick={() => handleTranscribe(session)}
                      className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
                    >
                      Transcribe
                    </button>
                  )}
                  
                  <button
                    onClick={() => handleViewTranscript(session)}
                    className="p-2 hover:bg-gray-200 rounded transition-colors"
                    title="View details"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  
                  {session.audio_file_path && (
                    <button
                      onClick={() => handleDownload(session)}
                      className="p-2 hover:bg-gray-200 rounded transition-colors"
                      title="Download audio"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  )}
                  
                  <button
                    onClick={() => handleDelete(session.session_id)}
                    className="p-2 hover:bg-red-100 text-red-600 rounded transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};