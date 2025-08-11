import React, { useState, useEffect } from 'react';
import { 
  Mic, Download, Play, Trash2, Clock, Calendar, 
  FileText, Music, ChevronRight, MoreVertical,
  CheckCircle, AlertCircle, Loader2, Archive,
  Share2, Edit3, Flag
} from 'lucide-react';
import { config } from '../config';
import { useNavigate } from 'react-router-dom';

interface RecordingSession {
  id: string;
  name: string;
  description?: string;
  status: 'created' | 'recording' | 'processing_final' | 'completed';
  created_at: string;
  duration: number;
  file_size?: number;
  has_transcription?: boolean;
  has_final_transcription?: boolean;
  audio_file_path?: string;
}

export const RecordingSessionsList: React.FC = () => {
  const [sessions, setSessions] = useState<RecordingSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchSessions();
    // Refresh every 5 seconds to catch status updates
    const interval = setInterval(fetchSessions, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchSessions = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions`);
      if (response.ok) {
        const data = await response.json();
        setSessions(data.sort((a: RecordingSession, b: RecordingSession) => 
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ));
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSessionClick = (session: RecordingSession) => {
    // Navigate to session details page
    navigate(`/recording/sessions/${session.id}`);
  };

  const handleDownloadAudio = async (e: React.MouseEvent, session: RecordingSession) => {
    e.stopPropagation(); // Prevent row click
    
    if (!session.audio_file_path) return;
    
    // Create download link
    const link = document.createElement('a');
    link.href = `${config.apiBaseUrl}/api/files/download/${session.id}/audio`;
    link.download = `${session.name.replace(/[^a-z0-9]/gi, '_')}_audio.wav`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadTranscript = async (e: React.MouseEvent, session: RecordingSession) => {
    e.stopPropagation(); // Prevent row click
    
    // Fetch session with transcription
    const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}`);
    if (response.ok) {
      const data = await response.json();
      
      // Create transcript text
      let transcript = `Recording: ${session.name}\n`;
      transcript += `Date: ${new Date(session.created_at).toLocaleString()}\n`;
      transcript += `Duration: ${formatDuration(session.duration)}\n`;
      transcript += '\n--- TRANSCRIPT ---\n\n';
      
      if (data.final_transcription?.segments) {
        data.final_transcription.segments.forEach((seg: any) => {
          const speaker = seg.speaker || 'SPEAKER';
          const text = seg.text || '';
          transcript += `[${speaker}]: ${text}\n\n`;
        });
      } else if (data.transcription?.segments) {
        data.transcription.segments.forEach((seg: any) => {
          const speaker = seg.speaker || 'SPEAKER';
          const text = seg.text || '';
          transcript += `[${speaker}]: ${text}\n\n`;
        });
      } else if (data.transcription?.text) {
        transcript += data.transcription.text;
      }
      
      // Download as text file
      const blob = new Blob([transcript], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${session.name.replace(/[^a-z0-9]/gi, '_')}_transcript.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation(); // Prevent row click
    
    if (!confirm('Are you sure you want to delete this recording?')) return;
    
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        setSessions(sessions.filter(s => s.id !== sessionId));
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const formatDuration = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hrs > 0) {
      return `${hrs}h ${mins}m ${secs}s`;
    } else if (mins > 0) {
      return `${mins}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'N/A';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'recording':
        return (
          <div className="flex items-center gap-1 px-2 py-1 bg-red-500/20 text-red-400 rounded-full text-xs font-medium">
            <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
            Recording
          </div>
        );
      case 'processing_final':
        return (
          <div className="flex items-center gap-1 px-2 py-1 bg-purple-500/20 text-purple-400 rounded-full text-xs font-medium">
            <Loader2 className="w-3 h-3 animate-spin" />
            Processing
          </div>
        );
      case 'completed':
        return (
          <div className="flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-400 rounded-full text-xs font-medium">
            <CheckCircle className="w-3 h-3" />
            Complete
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-1 px-2 py-1 bg-gray-500/20 text-gray-400 rounded-full text-xs font-medium">
            <AlertCircle className="w-3 h-3" />
            {status}
          </div>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="bg-gray-950 rounded-xl shadow-2xl border border-gray-800">
      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-3">
              <Mic className="w-6 h-6 text-purple-400" />
              Recording Sessions
            </h2>
            <p className="text-gray-400 mt-1">
              {sessions.length} recording{sessions.length !== 1 ? 's' : ''} available
            </p>
          </div>
          
          <button
            onClick={() => navigate('/record')}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Mic className="w-4 h-4" />
            New Recording
          </button>
        </div>
      </div>

      {/* Sessions List */}
      <div className="divide-y divide-gray-800">
        {sessions.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
              <Mic className="w-10 h-10 text-gray-600" />
            </div>
            <p className="text-gray-400 text-lg mb-2">No recordings yet</p>
            <p className="text-gray-500 text-sm">Start your first recording to see it here</p>
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              onClick={() => handleSessionClick(session)}
              className="group hover:bg-gray-900/50 transition-all duration-200 cursor-pointer"
            >
              <div className="p-6">
                <div className="flex items-start justify-between">
                  {/* Left side - Main content */}
                  <div className="flex-1">
                    <div className="flex items-start gap-4">
                      {/* Icon */}
                      <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                        <Mic className="w-6 h-6 text-white" />
                      </div>
                      
                      {/* Content */}
                      <div className="flex-1">
                        <div className="flex items-center gap-3">
                          <h3 className="text-lg font-semibold text-white group-hover:text-purple-400 transition-colors">
                            {session.name}
                          </h3>
                          {getStatusBadge(session.status)}
                        </div>
                        
                        {session.description && (
                          <p className="text-gray-400 text-sm mt-1">{session.description}</p>
                        )}
                        
                        <div className="flex items-center gap-4 mt-3 text-sm text-gray-500">
                          <div className="flex items-center gap-1">
                            <Calendar className="w-4 h-4" />
                            {new Date(session.created_at).toLocaleDateString()}
                          </div>
                          <div className="flex items-center gap-1">
                            <Clock className="w-4 h-4" />
                            {formatDuration(session.duration)}
                          </div>
                          <div className="flex items-center gap-1">
                            <Archive className="w-4 h-4" />
                            {formatFileSize(session.file_size)}
                          </div>
                          {session.has_final_transcription && (
                            <div className="flex items-center gap-1 text-green-400">
                              <FileText className="w-4 h-4" />
                              Full transcript
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Right side - Actions */}
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    {session.status === 'completed' && (
                      <>
                        <button
                          onClick={(e) => handleDownloadTranscript(e, session)}
                          className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-white"
                          title="Download Transcript"
                        >
                          <FileText className="w-5 h-5" />
                        </button>
                        <button
                          onClick={(e) => handleDownloadAudio(e, session)}
                          className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-white"
                          title="Download Audio"
                        >
                          <Download className="w-5 h-5" />
                        </button>
                        <button
                          onClick={(e) => handleDeleteSession(e, session.id)}
                          className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-red-400"
                          title="Delete"
                        >
                          <Trash2 className="w-5 h-5" />
                        </button>
                      </>
                    )}
                    
                    <ChevronRight className="w-5 h-5 text-gray-600 group-hover:text-purple-400 transition-colors ml-2" />
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};