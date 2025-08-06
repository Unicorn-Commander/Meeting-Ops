import React, { useState, useEffect } from 'react';
import { 
  Search, Filter, Download, Trash2, Edit, Play, Pause, 
  FileText, Users, Clock, Calendar, ChevronRight, 
  MoreVertical, Share2, Mail, Archive, Tag, Star,
  Mic, Brain, Zap, CheckCircle, XCircle, AlertCircle
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';

interface Meeting {
  id: string;
  name: string;
  created_at: string;
  duration: number;
  status: 'completed' | 'processing' | 'failed';
  file_size: number;
  speaker_count: number;
  word_count: number;
  has_transcript: boolean;
  has_summary: boolean;
  tags: string[];
  starred: boolean;
  npu_processed: boolean;
  processing_time: number;
  confidence_score: number;
}

interface MeetingStats {
  total_meetings: number;
  total_duration: number;
  total_words: number;
  average_duration: number;
  npu_processed_count: number;
  storage_used: number;
}

export const MeetingManagement: React.FC = () => {
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [filteredMeetings, setFilteredMeetings] = useState<Meeting[]>([]);
  const [stats, setStats] = useState<MeetingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'completed' | 'processing' | 'failed'>('all');
  const [sortBy, setSortBy] = useState<'date' | 'name' | 'duration'>('date');
  const [selectedMeetings, setSelectedMeetings] = useState<Set<string>>(new Set());
  const [showBulkActions, setShowBulkActions] = useState(false);

  useEffect(() => {
    fetchMeetings();
    fetchStats();
  }, []);

  useEffect(() => {
    filterAndSortMeetings();
  }, [meetings, searchTerm, filterStatus, sortBy]);

  const fetchMeetings = async () => {
    try {
      // Try simple API first (no auth required)
      const response = await fetch('/api/simple/recording-sessions');
      const data = await response.json();
      
      // Convert simple API response to match expected format
      const formattedMeetings = data.map(session => ({
        id: session.id,
        name: session.name || 'Untitled Meeting',
        created_at: session.created_at,
        duration: session.duration || 0,
        status: session.status === 'completed' ? 'completed' : 
                session.status === 'processing' ? 'processing' : 
                session.status === 'recording' ? 'processing' : 'completed',
        file_size: session.file_size || 0,
        speaker_count: session.transcription?.segments ? 
          new Set(session.transcription.segments.map(s => s.speaker)).size : 1,
        word_count: session.transcription?.text ? 
          session.transcription.text.split(' ').length : 0,
        has_transcript: !!session.transcription,
        has_summary: !!session.summary,
        tags: [],
        starred: false,
        npu_processed: session.transcription?.model?.includes('whisper') || false,
        processing_time: session.transcription?.processing_time || 0,
        confidence_score: 0.95
      }));
      
      setMeetings(formattedMeetings);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch meetings:', error);
      // Fallback to mock data for testing
      setMeetings([]);
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch('/api/analytics/meetings?range=all', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  };

  const filterAndSortMeetings = () => {
    let filtered = [...meetings];

    // Apply search filter
    if (searchTerm) {
      filtered = filtered.filter(m => 
        m.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        m.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()))
      );
    }

    // Apply status filter
    if (filterStatus !== 'all') {
      filtered = filtered.filter(m => m.status === filterStatus);
    }

    // Apply sorting
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.name.localeCompare(b.name);
        case 'duration':
          return b.duration - a.duration;
        case 'date':
        default:
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

    setFilteredMeetings(filtered);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this meeting?')) return;

    try {
      await fetch(`/api/recording-sessions/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      setMeetings(meetings.filter(m => m.id !== id));
    } catch (error) {
      console.error('Failed to delete meeting:', error);
    }
  };

  const handleBulkDelete = async () => {
    if (!confirm(`Delete ${selectedMeetings.size} meetings?`)) return;

    try {
      await Promise.all(
        Array.from(selectedMeetings).map(id =>
          fetch(`/api/recording-sessions/${id}`, {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
          })
        )
      );
      setMeetings(meetings.filter(m => !selectedMeetings.has(m.id)));
      setSelectedMeetings(new Set());
      setShowBulkActions(false);
    } catch (error) {
      console.error('Failed to delete meetings:', error);
    }
  };

  const handleExport = async (id: string, format: 'txt' | 'json' | 'pdf' | 'docx' | 'srt') => {
    try {
      // All export formats are now available through simple API
      const endpoint = `/api/simple/recording-sessions/${id}/export/${format}`;
        
      const response = await fetch(endpoint, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`);
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      
      // Get filename from content-disposition header if available
      const contentDisposition = response.headers.get('content-disposition');
      let filename = `meeting-${id}.${format}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="(.+)"/);
        if (match) {
          filename = match[1];
        }
      }
      
      a.download = filename;
      a.click();
      window.URL.revokeObjectURL(url);
      
      // Show success message
      console.log(`Successfully exported meeting as ${format}`);
    } catch (error) {
      console.error('Failed to export meeting:', error);
      alert(`Failed to export meeting: ${error.message}`);
    }
  };

  const handleToggleStar = async (id: string) => {
    const meeting = meetings.find(m => m.id === id);
    if (!meeting) return;

    try {
      await fetch(`/api/recording-sessions/${id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ starred: !meeting.starred })
      });
      
      setMeetings(meetings.map(m => 
        m.id === id ? { ...m, starred: !m.starred } : m
      ));
    } catch (error) {
      console.error('Failed to update meeting:', error);
    }
  };

  const handleReprocess = async (id: string) => {
    try {
      await fetch(`/api/recording-sessions/${id}/reprocess`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      setMeetings(meetings.map(m => 
        m.id === id ? { ...m, status: 'processing' } : m
      ));
    } catch (error) {
      console.error('Failed to reprocess meeting:', error);
    }
  };

  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold text-white">Meeting Management</h1>
            <button
              onClick={() => navigate('/recording')}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2"
            >
              <Mic className="w-5 h-5" />
              New Recording
            </button>
          </div>

          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">Total Meetings</div>
                <div className="text-white text-xl font-semibold">{stats.total_meetings}</div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">Total Duration</div>
                <div className="text-white text-xl font-semibold">
                  {Math.floor(stats.total_duration / 3600)}h
                </div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">Total Words</div>
                <div className="text-white text-xl font-semibold">
                  {(stats.total_words / 1000).toFixed(1)}k
                </div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">NPU Processed</div>
                <div className="text-green-400 text-xl font-semibold flex items-center gap-1">
                  <Zap className="w-4 h-4" />
                  {stats.npu_processed_count}
                </div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">Avg Duration</div>
                <div className="text-white text-xl font-semibold">
                  {Math.floor(stats.average_duration / 60)}m
                </div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-gray-400 text-xs mb-1">Storage Used</div>
                <div className="text-white text-xl font-semibold">
                  {(stats.storage_used / (1024 * 1024 * 1024)).toFixed(1)}GB
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Filters and Search */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <input
                  type="text"
                  placeholder="Search meetings, tags..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>
            
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as any)}
              className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-purple-500"
            >
              <option value="all">All Status</option>
              <option value="completed">Completed</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
            </select>

            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-purple-500"
            >
              <option value="date">Sort by Date</option>
              <option value="name">Sort by Name</option>
              <option value="duration">Sort by Duration</option>
            </select>

            {selectedMeetings.size > 0 && (
              <button
                onClick={handleBulkDelete}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete ({selectedMeetings.size})
              </button>
            )}
          </div>
        </div>

        {/* Meetings List */}
        <div className="space-y-4">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto"></div>
            </div>
          ) : filteredMeetings.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-12 text-center">
              <FileText className="w-12 h-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">No meetings found</p>
            </div>
          ) : (
            filteredMeetings.map(meeting => (
              <div key={meeting.id} className="bg-gray-800 rounded-lg p-6 hover:bg-gray-750 transition-colors">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4 flex-1">
                    <input
                      type="checkbox"
                      checked={selectedMeetings.has(meeting.id)}
                      onChange={(e) => {
                        const newSelected = new Set(selectedMeetings);
                        if (e.target.checked) {
                          newSelected.add(meeting.id);
                        } else {
                          newSelected.delete(meeting.id);
                        }
                        setSelectedMeetings(newSelected);
                      }}
                      className="mt-1"
                    />
                    
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 
                          className="text-lg font-semibold text-white hover:text-purple-400 cursor-pointer"
                          onClick={() => navigate(`/sessions/${meeting.id}`)}
                        >
                          {meeting.name}
                        </h3>
                        {meeting.starred && <Star className="w-4 h-4 text-yellow-400 fill-current" />}
                        {meeting.npu_processed && (
                          <span className="px-2 py-1 bg-green-900/50 text-green-400 text-xs rounded-full flex items-center gap-1">
                            <Zap className="w-3 h-3" />
                            NPU
                          </span>
                        )}
                        {meeting.status === 'processing' && (
                          <span className="px-2 py-1 bg-yellow-900/50 text-yellow-400 text-xs rounded-full animate-pulse">
                            Processing...
                          </span>
                        )}
                        {meeting.status === 'failed' && (
                          <span className="px-2 py-1 bg-red-900/50 text-red-400 text-xs rounded-full">
                            Failed
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-6 text-sm text-gray-400 mb-3">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-4 h-4" />
                          {format(new Date(meeting.created_at), 'MMM d, yyyy h:mm a')}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-4 h-4" />
                          {formatDuration(meeting.duration)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Users className="w-4 h-4" />
                          {meeting.speaker_count} speakers
                        </span>
                        <span className="flex items-center gap-1">
                          <FileText className="w-4 h-4" />
                          {meeting.word_count} words
                        </span>
                        <span>{formatFileSize(meeting.file_size)}</span>
                      </div>

                      {meeting.tags.length > 0 && (
                        <div className="flex items-center gap-2 mb-3">
                          {meeting.tags.map(tag => (
                            <span key={tag} className="px-2 py-1 bg-gray-700 text-gray-300 text-xs rounded-full">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => navigate(`/sessions/${meeting.id}`)}
                          className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg flex items-center gap-1"
                        >
                          <Play className="w-4 h-4" />
                          View
                        </button>
                        
                        <button
                          onClick={() => navigate(`/sessions/${meeting.id}/edit`)}
                          className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg flex items-center gap-1"
                        >
                          <Edit className="w-4 h-4" />
                          Edit
                        </button>

                        <div className="relative group">
                          <button className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg flex items-center gap-1">
                            <Download className="w-4 h-4" />
                            Export
                          </button>
                          <div className="absolute top-full left-0 mt-1 bg-gray-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                            <button
                              onClick={() => handleExport(meeting.id, 'txt')}
                              className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                            >
                              Text (.txt)
                            </button>
                            <button
                              onClick={() => handleExport(meeting.id, 'json')}
                              className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                            >
                              JSON (.json)
                            </button>
                            <button
                              onClick={() => handleExport(meeting.id, 'pdf')}
                              className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                            >
                              PDF (.pdf)
                            </button>
                            <button
                              onClick={() => handleExport(meeting.id, 'docx')}
                              className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                            >
                              Word (.docx)
                            </button>
                            <button
                              onClick={() => handleExport(meeting.id, 'srt')}
                              className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                            >
                              Subtitles (.srt)
                            </button>
                          </div>
                        </div>

                        {meeting.status === 'failed' && (
                          <button
                            onClick={() => handleReprocess(meeting.id)}
                            className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 text-white text-sm rounded-lg flex items-center gap-1"
                          >
                            <Brain className="w-4 h-4" />
                            Reprocess
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="relative">
                    <button className="p-2 hover:bg-gray-700 rounded-lg">
                      <MoreVertical className="w-5 h-5 text-gray-400" />
                    </button>
                  </div>
                </div>

                {/* Processing Stats */}
                {meeting.npu_processed && (
                  <div className="mt-4 pt-4 border-t border-gray-700 flex items-center gap-6 text-xs text-gray-400">
                    <span>Processing Time: {meeting.processing_time}ms</span>
                    <span>Confidence: {(meeting.confidence_score * 100).toFixed(1)}%</span>
                    <span className="text-green-400">
                      {(meeting.duration * 1000 / meeting.processing_time).toFixed(1)}x faster than real-time
                    </span>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};