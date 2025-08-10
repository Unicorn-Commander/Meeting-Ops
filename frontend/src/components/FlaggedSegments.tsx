import React, { useState, useEffect } from 'react';
import { 
  Flag, Play, Share2, Trash2, Edit, Copy, Download,
  Clock, User, Tag, Search, Filter, ChevronRight,
  Bookmark, Star, AlertCircle, CheckCircle, Loader2
} from 'lucide-react';
import { toast } from 'react-toastify';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface FlaggedSegment {
  id: string;
  sessionId: string;
  sessionName: string;
  text: string;
  speaker: string;
  startTime: number;
  endTime: number;
  createdAt: string;
  tags: string[];
  priority: 'high' | 'medium' | 'low';
  category: 'action' | 'decision' | 'insight' | 'question' | 'other';
  notes?: string;
  shared: boolean;
  starred: boolean;
}

interface Session {
  id: string;
  name: string;
  date: string;
}

export const FlaggedSegments: React.FC = () => {
  const [segments, setSegments] = useState<FlaggedSegment[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(new Set());
  const [filterSession, setFilterSession] = useState<string>('all');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState<'recent' | 'priority' | 'session'>('recent');
  const [editingSegment, setEditingSegment] = useState<string | null>(null);
  const [editNotes, setEditNotes] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSegments();
    fetchSessions();
  }, []);

  const fetchSegments = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/flagged-segments`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSegments(data);
      } else {
        // Mock data
        setSegments([
          {
            id: '1',
            sessionId: '1',
            sessionName: 'Q1 Planning Meeting',
            text: 'We need to finalize the budget allocation for the new project by end of week. John will prepare the initial draft.',
            speaker: 'Sarah Wilson',
            startTime: 120,
            endTime: 145,
            createdAt: '2025-01-09T10:00:00',
            tags: ['budget', 'action-item', 'urgent'],
            priority: 'high',
            category: 'action',
            notes: 'Follow up with finance team',
            shared: false,
            starred: true
          },
          {
            id: '2',
            sessionId: '2',
            sessionName: 'Client Review',
            text: 'The client is very happy with the progress but wants to see more detailed analytics in the dashboard.',
            speaker: 'Mike Johnson',
            startTime: 450,
            endTime: 480,
            createdAt: '2025-01-08T14:30:00',
            tags: ['client-feedback', 'feature-request'],
            priority: 'medium',
            category: 'insight',
            notes: 'Add to product backlog',
            shared: true,
            starred: false
          },
          {
            id: '3',
            sessionId: '1',
            sessionName: 'Q1 Planning Meeting',
            text: 'Decision: We will proceed with Option B for the infrastructure upgrade, with a phased rollout starting March 1st.',
            speaker: 'David Brown',
            startTime: 890,
            endTime: 920,
            createdAt: '2025-01-09T11:00:00',
            tags: ['infrastructure', 'decision', 'q1-goals'],
            priority: 'high',
            category: 'decision',
            shared: true,
            starred: true
          },
          {
            id: '4',
            sessionId: '3',
            sessionName: 'Team Standup',
            text: 'What is our strategy for handling the increased load during the holiday season?',
            speaker: 'Jane Smith',
            startTime: 200,
            endTime: 210,
            createdAt: '2025-01-07T09:15:00',
            tags: ['planning', 'scalability'],
            priority: 'medium',
            category: 'question',
            notes: 'Schedule follow-up meeting with DevOps',
            shared: false,
            starred: false
          }
        ]);
      }
    } catch (error) {
      console.error('Failed to fetch segments:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchSessions = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/simple/recording-sessions`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSessions(data.map((s: any) => ({
          id: s.id,
          name: s.name || 'Untitled Session',
          date: s.created_at
        })));
      } else {
        // Mock data
        setSessions([
          { id: '1', name: 'Q1 Planning Meeting', date: '2025-01-09' },
          { id: '2', name: 'Client Review', date: '2025-01-08' },
          { id: '3', name: 'Team Standup', date: '2025-01-07' }
        ]);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const handleDeleteSegment = async (segmentId: string) => {
    if (!confirm('Are you sure you want to delete this flagged segment?')) return;

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE_URL}/api/flagged-segments/${segmentId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        setSegments(segments.filter(s => s.id !== segmentId));
        toast.success('Segment deleted');
      } else {
        // Demo mode
        setSegments(segments.filter(s => s.id !== segmentId));
        toast.success('Segment deleted (demo)');
      }
    } catch (error) {
      console.error('Failed to delete segment:', error);
      toast.error('Failed to delete segment');
    }
  };

  const handleToggleStar = async (segmentId: string) => {
    const segment = segments.find(s => s.id === segmentId);
    if (!segment) return;

    try {
      // Update locally first for immediate feedback
      setSegments(segments.map(s => 
        s.id === segmentId ? { ...s, starred: !s.starred } : s
      ));
      
      // API call would go here
      toast.success(segment.starred ? 'Removed from favorites' : 'Added to favorites');
    } catch (error) {
      console.error('Failed to toggle star:', error);
    }
  };

  const handleShare = async (segment: FlaggedSegment) => {
    try {
      // Create shareable link or copy to clipboard
      const shareText = `${segment.sessionName} - ${segment.speaker} (${formatTime(segment.startTime)})\n\n"${segment.text}"`;
      
      if (navigator.share) {
        await navigator.share({
          title: 'Meeting Highlight',
          text: shareText
        });
      } else {
        await navigator.clipboard.writeText(shareText);
        toast.success('Copied to clipboard');
      }
      
      // Update shared status
      setSegments(segments.map(s => 
        s.id === segment.id ? { ...s, shared: true } : s
      ));
    } catch (error) {
      console.error('Failed to share:', error);
    }
  };

  const handleSaveNotes = async (segmentId: string) => {
    try {
      // API call would go here
      setSegments(segments.map(s => 
        s.id === segmentId ? { ...s, notes: editNotes } : s
      ));
      setEditingSegment(null);
      toast.success('Notes updated');
    } catch (error) {
      console.error('Failed to save notes:', error);
      toast.error('Failed to save notes');
    }
  };

  const handleExportSelected = () => {
    if (selectedSegments.size === 0) {
      toast.error('Please select segments to export');
      return;
    }

    const selectedData = segments.filter(s => selectedSegments.has(s.id));
    const exportData = selectedData.map(s => ({
      session: s.sessionName,
      speaker: s.speaker,
      time: formatTime(s.startTime),
      text: s.text,
      priority: s.priority,
      category: s.category,
      tags: s.tags.join(', '),
      notes: s.notes || ''
    }));

    const csv = [
      Object.keys(exportData[0]).join(','),
      ...exportData.map(row => Object.values(row).map(v => `"${v}"`).join(','))
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flagged-segments-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    
    toast.success(`Exported ${selectedSegments.size} segments`);
    setSelectedSegments(new Set());
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'text-red-400 bg-red-400/20';
      case 'medium': return 'text-yellow-400 bg-yellow-400/20';
      case 'low': return 'text-green-400 bg-green-400/20';
      default: return 'text-gray-400 bg-gray-400/20';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'action': return <CheckCircle className="w-4 h-4" />;
      case 'decision': return <Flag className="w-4 h-4" />;
      case 'insight': return <AlertCircle className="w-4 h-4" />;
      case 'question': return <AlertCircle className="w-4 h-4" />;
      default: return <Tag className="w-4 h-4" />;
    }
  };

  const toggleSegmentSelection = (segmentId: string) => {
    const newSelection = new Set(selectedSegments);
    if (newSelection.has(segmentId)) {
      newSelection.delete(segmentId);
    } else {
      newSelection.add(segmentId);
    }
    setSelectedSegments(newSelection);
  };

  // Filter and sort segments
  let filteredSegments = segments.filter(segment => {
    const matchesSearch = segment.text.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         segment.speaker.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         segment.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesSession = filterSession === 'all' || segment.sessionId === filterSession;
    const matchesCategory = filterCategory === 'all' || segment.category === filterCategory;
    const matchesPriority = filterPriority === 'all' || segment.priority === filterPriority;
    
    return matchesSearch && matchesSession && matchesCategory && matchesPriority;
  });

  // Sort segments
  filteredSegments = [...filteredSegments].sort((a, b) => {
    switch (sortBy) {
      case 'priority':
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        return priorityOrder[a.priority] - priorityOrder[b.priority];
      case 'session':
        return a.sessionName.localeCompare(b.sessionName);
      default: // recent
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    }
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Flagged Segments</h2>
        <div className="flex items-center space-x-4">
          {selectedSegments.size > 0 && (
            <>
              <span className="text-sm text-gray-400">
                {selectedSegments.size} selected
              </span>
              <button
                onClick={handleExportSelected}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors flex items-center"
              >
                <Download className="w-4 h-4 mr-2" />
                Export Selected
              </button>
            </>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search segments..."
              className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
            />
          </div>

          <select
            value={filterSession}
            onChange={(e) => setFilterSession(e.target.value)}
            className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
          >
            <option value="all">All Sessions</option>
            {sessions.map(session => (
              <option key={session.id} value={session.id}>{session.name}</option>
            ))}
          </select>

          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
          >
            <option value="all">All Categories</option>
            <option value="action">Action Items</option>
            <option value="decision">Decisions</option>
            <option value="insight">Insights</option>
            <option value="question">Questions</option>
            <option value="other">Other</option>
          </select>

          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
          >
            <option value="all">All Priorities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
          >
            <option value="recent">Most Recent</option>
            <option value="priority">By Priority</option>
            <option value="session">By Session</option>
          </select>
        </div>
      </div>

      {/* Segments List */}
      <div className="space-y-4">
        {filteredSegments.map(segment => (
          <div
            key={segment.id}
            className={`bg-gray-800 rounded-lg border transition-all ${
              selectedSegments.has(segment.id) 
                ? 'border-purple-500 ring-2 ring-purple-500/20' 
                : 'border-gray-700 hover:border-gray-600'
            }`}
          >
            <div className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-start space-x-3">
                  <input
                    type="checkbox"
                    checked={selectedSegments.has(segment.id)}
                    onChange={() => toggleSegmentSelection(segment.id)}
                    className="mt-1 rounded border-gray-600 bg-gray-700 text-purple-600 focus:ring-purple-500"
                  />
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-2">
                      {getCategoryIcon(segment.category)}
                      <span className="font-semibold">{segment.sessionName}</span>
                      <span className="text-sm text-gray-400">•</span>
                      <span className="text-sm text-gray-400">{segment.speaker}</span>
                      <span className="text-sm text-gray-400">•</span>
                      <span className="text-sm text-gray-400">{formatTime(segment.startTime)}</span>
                      {segment.starred && <Star className="w-4 h-4 text-yellow-400 fill-current" />}
                    </div>
                    
                    <p className="text-lg mb-3">{segment.text}</p>
                    
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPriorityColor(segment.priority)}`}>
                        {segment.priority.toUpperCase()}
                      </span>
                      {segment.tags.map(tag => (
                        <span key={tag} className="px-2 py-1 bg-gray-700 rounded-full text-xs">
                          #{tag}
                        </span>
                      ))}
                    </div>
                    
                    {segment.notes && editingSegment !== segment.id && (
                      <div className="p-3 bg-gray-700/50 rounded-lg text-sm">
                        <strong>Notes:</strong> {segment.notes}
                      </div>
                    )}
                    
                    {editingSegment === segment.id && (
                      <div className="mt-3">
                        <textarea
                          value={editNotes}
                          onChange={(e) => setEditNotes(e.target.value)}
                          placeholder="Add notes..."
                          className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-purple-500"
                          rows={3}
                        />
                        <div className="flex items-center space-x-2 mt-2">
                          <button
                            onClick={() => handleSaveNotes(segment.id)}
                            className="px-3 py-1 bg-purple-600 hover:bg-purple-700 rounded text-sm"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingSegment(null)}
                            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleToggleStar(segment.id)}
                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                    title="Star"
                  >
                    <Star className={`w-4 h-4 ${segment.starred ? 'text-yellow-400 fill-current' : 'text-gray-400'}`} />
                  </button>
                  <button
                    onClick={() => {
                      setEditingSegment(segment.id);
                      setEditNotes(segment.notes || '');
                    }}
                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                    title="Edit notes"
                  >
                    <Edit className="w-4 h-4 text-gray-400" />
                  </button>
                  <button
                    onClick={() => handleShare(segment)}
                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                    title="Share"
                  >
                    <Share2 className="w-4 h-4 text-gray-400" />
                  </button>
                  <button
                    onClick={() => handleDeleteSegment(segment.id)}
                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4 text-gray-400" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {filteredSegments.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <Bookmark className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>No flagged segments found</p>
          <p className="text-sm mt-2">Flag important moments during meetings to see them here</p>
        </div>
      )}
    </div>
  );
};