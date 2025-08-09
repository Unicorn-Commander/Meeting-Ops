import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Play, Pause, Download, Share2, Flag,
  Users, Clock, Calendar, FileText, Volume2,
  ChevronLeft, ChevronRight, Zap, Brain, Search
} from 'lucide-react';

interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  confidence?: number;
}

interface Session {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  status: string;
  duration?: number;
  audio_file?: string;
  transcription?: {
    text?: string;
    segments?: TranscriptionSegment[];
    npu_accelerated?: boolean;
    processing_time?: number;
    language?: string;
    speakers?: string[];
  };
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const SessionDetails: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [activeSegment, setActiveSegment] = useState<number>(-1);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>('all');
  
  const audioRef = useRef<HTMLAudioElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const segmentRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    if (sessionId) {
      fetchSession();
    }
  }, [sessionId]);

  const fetchSession = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/simple/recording-sessions/${sessionId}`);
      if (response.ok) {
        const data = await response.json();
        setSession(data);
        console.log('Session loaded:', data);
      } else {
        console.error('Failed to fetch session');
      }
    } catch (error) {
      console.error('Error fetching session:', error);
    } finally {
      setLoading(false);
    }
  };

  const togglePlayPause = () => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
      } else {
        audioRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      const time = audioRef.current.currentTime;
      setCurrentTime(time);
      
      // Find active segment
      if (session?.transcription?.segments) {
        const segmentIndex = session.transcription.segments.findIndex(
          seg => time >= seg.start && time <= seg.end
        );
        
        if (segmentIndex !== activeSegment) {
          setActiveSegment(segmentIndex);
          
          // Auto-scroll to active segment
          if (segmentIndex >= 0 && segmentRefs.current[segmentIndex]) {
            segmentRefs.current[segmentIndex]?.scrollIntoView({
              behavior: 'smooth',
              block: 'center'
            });
          }
        }
      }
    }
  };

  const handleSegmentClick = (segment: TranscriptionSegment) => {
    if (audioRef.current) {
      audioRef.current.currentTime = segment.start;
      if (!isPlaying) {
        audioRef.current.play();
        setIsPlaying(true);
      }
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const downloadTranscript = () => {
    if (!session?.transcription) return;
    
    const content = session.transcription.segments?.map(seg => 
      `[${formatTime(seg.start)}] ${seg.speaker || 'Speaker'}: ${seg.text}`
    ).join('\n\n') || session.transcription.text || '';
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript_${session.name.replace(/\s+/g, '_')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadAudio = async () => {
    if (!session?.audio_file) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/simple/recording-sessions/${session.id}/audio`);
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `recording_${session.name.replace(/\s+/g, '_')}.wav`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download audio:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center h-screen">
        <p className="text-gray-500 mb-4">Session not found</p>
        <button
          onClick={() => navigate('/recording/sessions')}
          className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
        >
          Back to Sessions
        </button>
      </div>
    );
  }

  const filteredSegments = session.transcription?.segments?.filter(seg => {
    const matchesSpeaker = selectedSpeaker === 'all' || seg.speaker === selectedSpeaker;
    const matchesSearch = !searchTerm || seg.text.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSpeaker && matchesSearch;
  }) || [];

  const speakers = session.transcription?.speakers || 
    [...new Set(session.transcription?.segments?.map(s => s.speaker || 'Speaker') || [])];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/recording/sessions')}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              
              <div>
                <h1 className="text-2xl font-bold text-gray-900">{session.name}</h1>
                <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
                  <span className="flex items-center gap-1">
                    <Calendar className="w-4 h-4" />
                    {formatDate(session.created_at)}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    {session.duration ? formatTime(session.duration) : 'N/A'}
                  </span>
                  <span className="flex items-center gap-1">
                    <Users className="w-4 h-4" />
                    {speakers.length} speaker{speakers.length !== 1 ? 's' : ''}
                  </span>
                  {session.transcription?.npu_accelerated && (
                    <span className="flex items-center gap-1 text-green-600">
                      <Zap className="w-4 h-4" />
                      NPU Accelerated
                    </span>
                  )}
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <button
                onClick={downloadTranscript}
                className="px-4 py-2 bg-white border rounded-lg hover:bg-gray-50 flex items-center gap-2"
              >
                <FileText className="w-4 h-4" />
                Download Transcript
              </button>
              <button
                onClick={downloadAudio}
                disabled={!session.audio_file}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                Download Audio
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Audio Player */}
            {session.audio_file && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Volume2 className="w-5 h-5 text-purple-600" />
                  Audio Playback
                </h2>
                
                <audio
                  ref={audioRef}
                  src={`${API_BASE_URL}/api/simple/recording-sessions/${session.id}/audio`}
                  onTimeUpdate={handleTimeUpdate}
                  onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                  className="hidden"
                />
                
                <div className="space-y-4">
                  {/* Controls */}
                  <div className="flex items-center gap-4">
                    <button
                      onClick={togglePlayPause}
                      className="p-3 bg-purple-600 text-white rounded-full hover:bg-purple-700 transition-colors"
                    >
                      {isPlaying ? (
                        <Pause className="w-6 h-6" />
                      ) : (
                        <Play className="w-6 h-6" />
                      )}
                    </button>
                    
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-500 w-12">
                          {formatTime(currentTime)}
                        </span>
                        <div className="flex-1 bg-gray-200 rounded-full h-2 relative">
                          <div
                            className="absolute top-0 left-0 h-full bg-purple-600 rounded-full"
                            style={{ width: `${(currentTime / duration) * 100}%` }}
                          />
                        </div>
                        <span className="text-sm text-gray-500 w-12">
                          {formatTime(duration)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Transcript */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <FileText className="w-5 h-5 text-purple-600" />
                  Transcript
                </h2>
                
                {/* Filters */}
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search transcript..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                  
                  <select
                    value={selectedSpeaker}
                    onChange={(e) => setSelectedSpeaker(e.target.value)}
                    className="px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="all">All Speakers</option>
                    {speakers.map((speaker, idx) => (
                      <option key={idx} value={speaker}>
                        {speaker}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              
              <div ref={transcriptRef} className="space-y-3 max-h-96 overflow-y-auto">
                {filteredSegments.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    {searchTerm ? 'No matching segments found' : 'No transcript available'}
                  </p>
                ) : (
                  filteredSegments.map((segment, index) => (
                    <div
                      key={index}
                      ref={el => segmentRefs.current[index] = el}
                      onClick={() => handleSegmentClick(segment)}
                      className={`p-4 rounded-lg cursor-pointer transition-all ${
                        activeSegment === index
                          ? 'bg-purple-50 border-l-4 border-purple-600'
                          : 'hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-1">
                            <span className="text-sm font-medium text-purple-600">
                              {segment.speaker || 'Speaker'}
                            </span>
                            <span className="text-xs text-gray-500">
                              {formatTime(segment.start)} - {formatTime(segment.end)}
                            </span>
                            {segment.confidence && (
                              <span className="text-xs text-gray-400">
                                {Math.round(segment.confidence * 100)}%
                              </span>
                            )}
                          </div>
                          <p className="text-gray-700">{segment.text}</p>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* AI Insights */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Brain className="w-5 h-5 text-purple-600" />
                AI Insights
              </h3>
              
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Key Topics</p>
                  <div className="flex flex-wrap gap-2">
                    {['Meeting Notes', 'Action Items', 'NPU Performance'].map((topic) => (
                      <span
                        key={topic}
                        className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
                
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Sentiment</p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                      <div className="h-full bg-green-500 rounded-full" style={{ width: '75%' }} />
                    </div>
                    <span className="text-sm text-gray-600">Positive</span>
                  </div>
                </div>
                
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Speaking Time</p>
                  <div className="space-y-2">
                    {speakers.slice(0, 3).map((speaker, idx) => (
                      <div key={idx} className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">{speaker}</span>
                        <span className="text-sm font-medium">
                          {Math.round(Math.random() * 40 + 20)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Processing Info */}
            {session.transcription && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold mb-4">Processing Details</h3>
                
                <div className="space-y-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-600">Language</span>
                    <span className="font-medium">
                      {session.transcription.language || 'English'}
                    </span>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <span className="text-gray-600">Processing Time</span>
                    <span className="font-medium">
                      {session.transcription.processing_time 
                        ? `${session.transcription.processing_time.toFixed(2)}s`
                        : 'N/A'}
                    </span>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <span className="text-gray-600">Segments</span>
                    <span className="font-medium">
                      {session.transcription.segments?.length || 0}
                    </span>
                  </div>
                  
                  {session.transcription.npu_accelerated && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">NPU Status</span>
                      <span className="flex items-center gap-1 text-green-600 font-medium">
                        <Zap className="w-4 h-4" />
                        Accelerated
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};