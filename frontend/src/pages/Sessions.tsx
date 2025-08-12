import React, { useState, useEffect } from 'react';
import {
  Plus, Search, Filter, Calendar, Mic, Clock, Users,
  FileText, Download, Trash2, Play, Eye, Tag,
  ChevronDown, Grid, List, SortAsc, SortDesc,
  Upload, FolderOpen, Star, Archive
} from 'lucide-react';
import { SessionCreator } from '../components/SessionCreator';
import { MeetingIntelligenceDashboard } from '../components/MeetingIntelligenceDashboard';
import { config } from '../config';
import { useNavigate } from 'react-router-dom';

interface Session {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  duration?: number;
  status: 'idle' | 'recording' | 'completed' | 'processing';
  participants?: string[];
  tags?: string[];
  audio_file?: string;
  transcript?: string;
  has_transcript: boolean;
  has_audio: boolean;
  session_type?: 'live' | 'upload';
}

export const Sessions: React.FC = () => {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [filteredSessions, setFilteredSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreator, setShowCreator] = useState(false);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'date' | 'name' | 'duration'>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    fetchSessions();
  }, []);

  useEffect(() => {
    filterSessions();
  }, [sessions, searchQuery, statusFilter, typeFilter, sortBy, sortOrder]);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setSessions(data);
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
    if (searchQuery) {
      filtered = filtered.filter(session =>
        session.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.participants?.some(p => p.toLowerCase().includes(searchQuery.toLowerCase()))
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(session => session.status === statusFilter);
    }

    // Type filter
    if (typeFilter !== 'all') {
      filtered = filtered.filter(session => session.session_type === typeFilter);
    }

    // Sort
    filtered.sort((a, b) => {
      let aValue: any, bValue: any;
      
      switch (sortBy) {
        case 'name':
          aValue = a.name.toLowerCase();
          bValue = b.name.toLowerCase();
          break;
        case 'duration':
          aValue = a.duration || 0;
          bValue = b.duration || 0;
          break;
        case 'date':
        default:
          aValue = new Date(a.created_at).getTime();
          bValue = new Date(b.created_at).getTime();
          break;
      }

      if (sortOrder === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });

    setFilteredSessions(filtered);
  };

  const handleSessionCreated = (sessionId: string) => {
    setShowCreator(false);
    fetchSessions();
    // Navigate to the new session
    navigate(`/sessions/${sessionId}`);
  };

  const deleteSession = async (sessionId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) return;

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        fetchSessions();
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
      alert('Failed to delete session');
    }
  };

  const downloadTranscript = async (session: Session) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}/transcript`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const blob = new Blob([data.transcript || 'No transcript available'], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${session.name}_transcript.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download transcript:', error);
    }
  };

  const downloadAudio = async (session: Session) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}/audio`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${session.name}_audio.wav`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download audio:', error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'recording': return 'text-red-400 bg-red-500/10 border-red-500';
      case 'completed': return 'text-green-400 bg-green-500/10 border-green-500';
      case 'processing': return 'text-yellow-400 bg-yellow-500/10 border-yellow-500';
      default: return 'text-gray-400 bg-gray-500/10 border-gray-500';
    }
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (selectedSession) {
    const meetingData = {
      transcript: selectedSession.transcript || '',
      notes: null,
      sessionId: selectedSession.id,
      duration: selectedSession.duration || 0,
      participants: selectedSession.participants || [],
      topics: []
    };

    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <div className="p-6">
          <button
            onClick={() => setSelectedSession(null)}
            className="mb-6 flex items-center gap-2 text-purple-400 hover:text-purple-300"
          >
            ← Back to Sessions
          </button>
          
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white">{selectedSession.name}</h1>
            <p className="text-gray-400">{selectedSession.description}</p>
          </div>

          <MeetingIntelligenceDashboard
            meetingData={meetingData}
            isRecording={selectedSession.status === 'recording'}
            className="w-full"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {showCreator && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
          <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <SessionCreator
              onClose={() => setShowCreator(false)}
              onSessionCreated={handleSessionCreated}
            />
          </div>
        </div>
      )}

      <div className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white">Sessions</h1>
            <p className="text-gray-400 mt-1">Manage your meeting recordings and transcriptions</p>
          </div>

          <button
            onClick={() => setShowCreator(true)}
            className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
          >
            <Plus className="w-5 h-5" />
            New Session
          </button>
        </div>

        {/* Controls */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 mb-6">
          <div className="flex items-center gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search sessions..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
              />
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center bg-gray-800 rounded-lg">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 rounded-l-lg ${viewMode === 'grid' ? 'bg-purple-600 text-white' : 'text-gray-400'}`}
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded-r-lg ${viewMode === 'list' ? 'bg-purple-600 text-white' : 'text-gray-400'}`}
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            {/* Filters */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
            >
              <Filter className="w-4 h-4" />
              Filters
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {/* Extended Filters */}
          {showFilters && (
            <div className="mt-4 pt-4 border-t border-gray-800">
              <div className="grid grid-cols-4 gap-4">
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="all">All Status</option>
                  <option value="idle">Idle</option>
                  <option value="recording">Recording</option>
                  <option value="processing">Processing</option>
                  <option value="completed">Completed</option>
                </select>

                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="all">All Types</option>
                  <option value="live">Live Recording</option>
                  <option value="upload">Uploaded Audio</option>
                </select>

                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'date' | 'name' | 'duration')}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="date">Sort by Date</option>
                  <option value="name">Sort by Name</option>
                  <option value="duration">Sort by Duration</option>
                </select>

                <button
                  onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
                  className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-white transition-colors"
                >
                  {sortOrder === 'asc' ? <SortAsc className="w-4 h-4" /> : <SortDesc className="w-4 h-4" />}
                  {sortOrder === 'asc' ? 'Ascending' : 'Descending'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Sessions */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="w-8 h-8 border-4 border-purple-400 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <p className="text-gray-400">Loading sessions...</p>
            </div>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="text-center py-12">
            <FolderOpen className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-300 mb-2">No Sessions Found</h3>
            <p className="text-gray-500 mb-6">
              {searchQuery || statusFilter !== 'all' || typeFilter !== 'all' 
                ? 'Try adjusting your filters or search query.'
                : 'Create your first session to get started.'
              }
            </p>
            {!searchQuery && statusFilter === 'all' && typeFilter === 'all' && (
              <button
                onClick={() => setShowCreator(true)}
                className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors mx-auto"
              >
                <Plus className="w-5 h-5" />
                Create First Session
              </button>
            )}
          </div>
        ) : (
          <div className={viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6' : 'space-y-4'}>
            {filteredSessions.map(session => (
              <div
                key={session.id}
                className={`bg-gray-900 border border-gray-800 rounded-lg hover:border-gray-700 transition-all ${
                  viewMode === 'list' ? 'flex items-center gap-6 p-4' : 'p-6'
                }`}
              >
                {viewMode === 'grid' ? (
                  <div className="space-y-4">
                    {/* Header */}
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-semibold text-white text-lg truncate">{session.name}</h3>
                        {session.description && (
                          <p className="text-gray-400 text-sm mt-1 line-clamp-2">{session.description}</p>
                        )}
                      </div>
                      <span className={`px-2 py-1 rounded-full text-xs border ${getStatusColor(session.status)}`}>
                        {session.status}
                      </span>
                    </div>

                    {/* Meta */}
                    <div className="space-y-2 text-sm text-gray-400">
                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4" />
                        {new Date(session.created_at).toLocaleDateString()}
                      </div>
                      {session.duration && (
                        <div className="flex items-center gap-2">
                          <Clock className="w-4 h-4" />
                          {formatDuration(session.duration)}
                        </div>
                      )}
                      {session.participants && session.participants.length > 0 && (
                        <div className="flex items-center gap-2">
                          <Users className="w-4 h-4" />
                          {session.participants.length} participant{session.participants.length !== 1 ? 's' : ''}
                        </div>
                      )}
                    </div>

                    {/* Tags */}
                    {session.tags && session.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {session.tags.slice(0, 3).map((tag, index) => (
                          <span key={index} className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded">
                            {tag}
                          </span>
                        ))}
                        {session.tags.length > 3 && (
                          <span className="px-2 py-1 bg-gray-600 text-gray-300 text-xs rounded">
                            +{session.tags.length - 3}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setSelectedSession(session)}
                        className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                      >
                        <Eye className="w-4 h-4" />
                        View
                      </button>
                      
                      {session.has_transcript && (
                        <button
                          onClick={() => downloadTranscript(session)}
                          className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                          title="Download Transcript"
                        >
                          <FileText className="w-4 h-4" />
                        </button>
                      )}
                      
                      {session.has_audio && (
                        <button
                          onClick={() => downloadAudio(session)}
                          className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                          title="Download Audio"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                      )}
                      
                      <button
                        onClick={() => deleteSession(session.id)}
                        className="p-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded transition-colors"
                        title="Delete Session"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ) : (
                  /* List View */
                  <>
                    <div className="flex-1">
                      <div className="flex items-center gap-4 mb-2">
                        <h3 className="font-semibold text-white text-lg">{session.name}</h3>
                        <span className={`px-2 py-1 rounded-full text-xs border ${getStatusColor(session.status)}`}>
                          {session.status}
                        </span>
                        {session.session_type === 'upload' && (
                          <span className="px-2 py-1 bg-blue-500/20 text-blue-300 text-xs rounded">
                            <Upload className="w-3 h-3 inline mr-1" />
                            Uploaded
                          </span>
                        )}
                      </div>
                      {session.description && (
                        <p className="text-gray-400 text-sm">{session.description}</p>
                      )}
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span>{new Date(session.created_at).toLocaleDateString()}</span>
                        {session.duration && <span>{formatDuration(session.duration)}</span>}
                        {session.participants && (
                          <span>{session.participants.length} participant{session.participants.length !== 1 ? 's' : ''}</span>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setSelectedSession(session)}
                        className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                      >
                        <Eye className="w-4 h-4" />
                        View
                      </button>
                      
                      {session.has_transcript && (
                        <button
                          onClick={() => downloadTranscript(session)}
                          className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                          title="Download Transcript"
                        >
                          <FileText className="w-4 h-4" />
                        </button>
                      )}
                      
                      {session.has_audio && (
                        <button
                          onClick={() => downloadAudio(session)}
                          className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                          title="Download Audio"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                      )}
                      
                      <button
                        onClick={() => deleteSession(session.id)}
                        className="p-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded transition-colors"
                        title="Delete Session"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};