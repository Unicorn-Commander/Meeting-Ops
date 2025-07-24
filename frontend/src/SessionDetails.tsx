import { useState, useEffect } from 'react';

interface Speaker {
  id: number;
  speaker_id: string;
  display_name: string;
  total_speaking_time: number;
  total_segments: number;
  confidence: number;
}

interface Transcription {
  id: number;
  text: string;
  timestamp: string;
  speaker_id: string | null;
  confidence: number;
  start_time_seconds: number;
  end_time_seconds: number;
  processing_time_ms: number;
  npu_accelerated: boolean;
}

interface Session {
  id: number;
  session_id: string;
  name: string;
  description?: string;
  start_time: string;
  end_time?: string;
  duration_seconds: number;
  status: string;
  total_transcriptions: number;
  total_speakers: number;
  meeting_type?: string;
  npu_accelerated: boolean;
}

interface SessionDetailsProps {
  sessionId: string;
  onClose: () => void;
}

function SessionDetails({ sessionId, onClose }: SessionDetailsProps) {
  const [session, setSession] = useState<Session | null>(null);
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null);

  useEffect(() => {
    fetchSessionDetails();
  }, [sessionId]);

  const fetchSessionDetails = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/recording-sessions/${sessionId}`);
      if (response.ok) {
        const data = await response.json();
        setSession(data.session);
        setTranscriptions(data.transcriptions || []);
        setSpeakers(data.speakers || []);
      }
    } catch (error) {
      console.error('Error fetching session details:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const exportSession = async (format: string) => {
    try {
      const response = await fetch(`/api/recording-sessions/${sessionId}/export?format=${format}`);
      if (response.ok) {
        const data = await response.json();
        
        if (format === 'txt') {
          // For text format, create a text file
          const blob = new Blob([data.content], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${sessionId}_transcript.txt`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        } else {
          // For JSON format
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${sessionId}_export.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      }
    } catch (error) {
      console.error('Error exporting session:', error);
    }
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const getSpeakerColor = (speakerId: string) => {
    const colors = [
      'bg-blue-500', 'bg-green-500', 'bg-purple-500', 'bg-yellow-500',
      'bg-pink-500', 'bg-indigo-500', 'bg-red-500', 'bg-orange-500'
    ];
    const index = parseInt(speakerId.replace(/\D/g, '')) % colors.length;
    return colors[index];
  };

  const filteredTranscriptions = transcriptions.filter(t => {
    const matchesSearch = t.text.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSpeaker = !selectedSpeaker || t.speaker_id === selectedSpeaker;
    return matchesSearch && matchesSpeaker;
  });

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-gray-800 rounded-lg p-8">
          <div className="animate-pulse">
            <div className="w-8 h-8 bg-purple-500 rounded-full mx-auto mb-4"></div>
            <p className="text-gray-300">Loading session details...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-lg w-full max-w-6xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white mb-2">{session?.name}</h2>
              <div className="flex items-center space-x-4 text-sm text-gray-400">
                <span>{new Date(session?.start_time || '').toLocaleString()}</span>
                <span>•</span>
                <span>{formatDuration(session?.duration_seconds || 0)}</span>
                <span>•</span>
                <span>{session?.total_transcriptions} transcriptions</span>
                <span>•</span>
                <span>{session?.total_speakers} speakers</span>
                {session?.npu_accelerated && (
                  <>
                    <span>•</span>
                    <span className="bg-green-600 text-xs px-2 py-1 rounded">NPU</span>
                  </>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Controls */}
        <div className="p-4 border-b border-gray-700 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4 flex-1">
              {/* Search */}
              <div className="relative flex-1 max-w-md">
                <input
                  type="text"
                  placeholder="Search transcription..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 pl-10"
                />
                <svg className="absolute left-3 top-2.5 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>

              {/* Speaker Filter */}
              <select
                value={selectedSpeaker || ''}
                onChange={(e) => setSelectedSpeaker(e.target.value || null)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2"
              >
                <option value="">All Speakers</option>
                {speakers.map(speaker => (
                  <option key={speaker.speaker_id} value={speaker.speaker_id}>
                    {speaker.display_name} ({formatDuration(Math.floor(speaker.total_speaking_time))})
                  </option>
                ))}
              </select>
            </div>

            {/* Export Buttons */}
            <div className="flex items-center space-x-2">
              <button
                onClick={() => exportSession('txt')}
                className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg text-sm font-medium transition-all"
              >
                Export TXT
              </button>
              <button
                onClick={() => exportSession('json')}
                className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg text-sm font-medium transition-all"
              >
                Export JSON
              </button>
            </div>
          </div>

          {/* Speaker Legend */}
          {speakers.length > 0 && (
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-400">Speakers:</span>
              {speakers.map(speaker => (
                <div key={speaker.speaker_id} className="flex items-center space-x-2">
                  <div className={`w-3 h-3 rounded-full ${getSpeakerColor(speaker.speaker_id)}`}></div>
                  <span className="text-sm">{speaker.display_name}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Transcription Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {filteredTranscriptions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-400">No transcriptions found</p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredTranscriptions.map((transcription, index) => (
                <div
                  key={transcription.id}
                  className="flex items-start space-x-4 hover:bg-gray-800/50 p-3 rounded-lg transition-colors"
                >
                  {/* Timestamp */}
                  <div className="text-sm text-gray-500 min-w-[60px]">
                    {formatTime(transcription.start_time_seconds)}
                  </div>

                  {/* Speaker Indicator */}
                  {transcription.speaker_id && (
                    <div className={`w-3 h-3 rounded-full mt-1.5 ${getSpeakerColor(transcription.speaker_id)}`}></div>
                  )}

                  {/* Transcription Text */}
                  <div className="flex-1">
                    <p className="text-white">{transcription.text}</p>
                    <div className="flex items-center space-x-4 mt-1 text-xs text-gray-500">
                      {transcription.speaker_id && (
                        <span>{speakers.find(s => s.speaker_id === transcription.speaker_id)?.display_name || transcription.speaker_id}</span>
                      )}
                      <span>Confidence: {(transcription.confidence * 100).toFixed(1)}%</span>
                      {transcription.npu_accelerated && <span className="text-green-400">NPU</span>}
                      <span>{transcription.processing_time_ms.toFixed(0)}ms</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 text-center text-sm text-gray-500">
          {filteredTranscriptions.length} of {transcriptions.length} transcriptions shown
        </div>
      </div>
    </div>
  );
}

export default SessionDetails;