import React, { useState, useEffect } from 'react';
import { SessionList } from '../SessionList';
import { TranscriptViewer } from '../TranscriptViewer';
import { AudioPlayer } from '../AudioPlayer';
import { Search, Play, FileText } from 'lucide-react';

interface Session {
  id: string;
  name: string;
  description?: string;
  date?: string;
  duration?: number;
  status?: string;
}

export const ViewerDashboard: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch sessions
    const fetchSessions = async () => {
      try {
        const response = await fetch('/api/sessions');
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

    fetchSessions();
  }, []);

  const filteredSessions = sessions.filter(session =>
    session.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    session.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 mb-2">
          Meeting Recordings
        </h1>
        <p className="text-gray-400">
          Browse and listen to recorded meetings
        </p>
      </div>

      {/* Search Bar */}
      <div className="mb-6">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search recordings..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-100 placeholder-gray-500"
          />
        </div>
      </div>

      {/* Sessions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-200 mb-4">
            Available Recordings
          </h2>
          {loading ? (
            <div className="text-center py-8 text-gray-400">
              Loading recordings...
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              No recordings found
            </div>
          ) : (
            <div className="space-y-3">
              {filteredSessions.map(session => (
                <div
                  key={session.id}
                  className={`p-4 bg-gray-800 rounded-lg cursor-pointer transition-colors hover:bg-gray-700 ${
                    selectedSession?.id === session.id ? 'ring-2 ring-purple-500' : ''
                  }`}
                  onClick={() => setSelectedSession(session)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-100">
                        {session.name}
                      </h3>
                      {session.description && (
                        <p className="text-sm text-gray-400 mt-1">
                          {session.description}
                        </p>
                      )}
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        {session.date && <span>{session.date}</span>}
                        {session.duration && (
                          <span>{Math.round(session.duration / 60)} min</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      <button
                        className="p-2 text-gray-400 hover:text-purple-400 transition-colors"
                        title="Play recording"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        className="p-2 text-gray-400 hover:text-purple-400 transition-colors"
                        title="View transcript"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedSession(session);
                          setShowTranscript(true);
                        }}
                      >
                        <FileText className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Session Details */}
        <div>
          {selectedSession ? (
            <div className="space-y-6">
              {/* Audio Player */}
              <div>
                <h2 className="text-lg font-semibold text-gray-200 mb-4">
                  Audio Playback
                </h2>
                <div className="bg-gray-800 rounded-lg p-4">
                  <h3 className="font-medium text-gray-100 mb-3">
                    {selectedSession.name}
                  </h3>
                  <AudioPlayer 
                    file={{
                      file_id: selectedSession.id,
                      filename: selectedSession.name,
                      duration_seconds: selectedSession.duration
                    }} 
                  />
                </div>
              </div>

              {/* Transcript Viewer */}
              {showTranscript && (
                <div>
                  <h2 className="text-lg font-semibold text-gray-200 mb-4">
                    Transcript
                  </h2>
                  <div className="bg-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto">
                    <TranscriptViewer sessionId={selectedSession.id} />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg p-8 text-center text-gray-400">
              <FileText className="w-12 h-12 mx-auto mb-4 text-gray-600" />
              <p>Select a recording to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};