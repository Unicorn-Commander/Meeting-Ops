import React, { useState, useEffect, useRef } from 'react';
import { 
  Save, Undo, Redo, Users, Clock, Search, Download,
  Play, Pause, SkipBack, SkipForward, Volume2,
  Edit2, Check, X, Mic, ChevronDown, ChevronUp,
  Brain, Zap, FileText, Share2, Trash2, Plus
} from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';

interface TranscriptSegment {
  id: string;
  speaker: string;
  text: string;
  start_time: number;
  end_time: number;
  confidence: number;
  is_final: boolean;
  words: Word[];
}

interface Word {
  text: string;
  start: number;
  end: number;
  confidence: number;
}

interface Speaker {
  id: string;
  name: string;
  color: string;
  segments: number;
  totalTime: number;
}

interface Session {
  id: string;
  name: string;
  created_at: string;
  duration: number;
  audio_url: string;
  transcript: TranscriptSegment[];
  speakers: Speaker[];
  npu_processed: boolean;
  processing_time: number;
}

export const TranscriptEditor: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  
  const [session, setSession] = useState<Session | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [editingSegment, setEditingSegment] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>('all');
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [showTimestamps, setShowTimestamps] = useState(true);
  const [showConfidence, setShowConfidence] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [undoStack, setUndoStack] = useState<TranscriptSegment[][]>([]);
  const [redoStack, setRedoStack] = useState<TranscriptSegment[][]>([]);
  
  const audioRef = useRef<HTMLAudioElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sessionId) {
      loadSession();
    }
  }, [sessionId]);

  useEffect(() => {
    // Auto-scroll to current segment during playback
    if (isPlaying && currentTime > 0) {
      const currentSegment = transcript.find(
        s => s.start_time <= currentTime && s.end_time >= currentTime
      );
      if (currentSegment) {
        const element = document.getElementById(`segment-${currentSegment.id}`);
        element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentTime, isPlaying]);

  const loadSession = async () => {
    try {
      const response = await fetch(`/api/recording-sessions/${sessionId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      const data = await response.json();
      
      setSession(data);
      setTranscript(data.transcript || []);
      
      // Extract unique speakers
      const speakerMap = new Map<string, Speaker>();
      data.transcript?.forEach((segment: TranscriptSegment) => {
        if (!speakerMap.has(segment.speaker)) {
          speakerMap.set(segment.speaker, {
            id: segment.speaker,
            name: segment.speaker,
            color: getSpeakerColor(segment.speaker),
            segments: 0,
            totalTime: 0
          });
        }
        const speaker = speakerMap.get(segment.speaker)!;
        speaker.segments++;
        speaker.totalTime += (segment.end_time - segment.start_time);
      });
      
      setSpeakers(Array.from(speakerMap.values()));
    } catch (error) {
      console.error('Failed to load session:', error);
    }
  };

  const getSpeakerColor = (speaker: string): string => {
    const colors = [
      'text-blue-400', 'text-green-400', 'text-purple-400', 
      'text-yellow-400', 'text-pink-400', 'text-cyan-400'
    ];
    const index = parseInt(speaker.replace(/\D/g, ''), 10) % colors.length;
    return colors[index];
  };

  const handleEdit = (segmentId: string, text: string) => {
    setEditingSegment(segmentId);
    setEditText(text);
  };

  const saveEdit = (segmentId: string) => {
    // Save to undo stack
    setUndoStack([...undoStack, [...transcript]]);
    setRedoStack([]);
    
    // Update transcript
    setTranscript(transcript.map(s => 
      s.id === segmentId ? { ...s, text: editText } : s
    ));
    
    setEditingSegment(null);
    setHasChanges(true);
  };

  const cancelEdit = () => {
    setEditingSegment(null);
    setEditText('');
  };

  const handleUndo = () => {
    if (undoStack.length > 0) {
      const previous = undoStack[undoStack.length - 1];
      setRedoStack([...redoStack, [...transcript]]);
      setTranscript(previous);
      setUndoStack(undoStack.slice(0, -1));
    }
  };

  const handleRedo = () => {
    if (redoStack.length > 0) {
      const next = redoStack[redoStack.length - 1];
      setUndoStack([...undoStack, [...transcript]]);
      setTranscript(next);
      setRedoStack(redoStack.slice(0, -1));
    }
  };

  const mergeSpeakers = (speaker1: string, speaker2: string) => {
    setUndoStack([...undoStack, [...transcript]]);
    setTranscript(transcript.map(s => 
      s.speaker === speaker2 ? { ...s, speaker: speaker1 } : s
    ));
    setHasChanges(true);
    loadSession(); // Reload to update speaker list
  };

  const splitSegment = (segmentId: string, position: number) => {
    const segment = transcript.find(s => s.id === segmentId);
    if (!segment) return;

    const words = segment.text.split(' ');
    const firstPart = words.slice(0, position).join(' ');
    const secondPart = words.slice(position).join(' ');
    
    const midTime = segment.start_time + ((segment.end_time - segment.start_time) * (position / words.length));
    
    const newSegments = [
      { ...segment, text: firstPart, end_time: midTime },
      { 
        ...segment, 
        id: `${segment.id}-split`, 
        text: secondPart, 
        start_time: midTime 
      }
    ];
    
    setUndoStack([...undoStack, [...transcript]]);
    setTranscript(transcript.flatMap(s => 
      s.id === segmentId ? newSegments : [s]
    ));
    setHasChanges(true);
  };

  const deleteSegment = (segmentId: string) => {
    if (!confirm('Delete this segment?')) return;
    
    setUndoStack([...undoStack, [...transcript]]);
    setTranscript(transcript.filter(s => s.id !== segmentId));
    setHasChanges(true);
  };

  const saveTranscript = async () => {
    try {
      await fetch(`/api/recording-sessions/${sessionId}/transcript`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ transcript })
      });
      setHasChanges(false);
    } catch (error) {
      console.error('Failed to save transcript:', error);
    }
  };

  const exportTranscript = async (format: 'txt' | 'srt' | 'json' | 'docx') => {
    try {
      const response = await fetch(`/api/recording-sessions/${sessionId}/export?format=${format}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transcript-${sessionId}.${format}`;
      a.click();
    } catch (error) {
      console.error('Failed to export transcript:', error);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleAudioTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const seekTo = (time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setCurrentTime(time);
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

  const filteredTranscript = transcript.filter(segment => {
    const matchesSpeaker = selectedSpeaker === 'all' || segment.speaker === selectedSpeaker;
    const matchesSearch = !searchTerm || segment.text.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSpeaker && matchesSearch;
  });

  if (!session) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <div className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-semibold text-white">{session.name}</h1>
            {session.npu_processed && (
              <span className="px-2 py-1 bg-green-900/50 text-green-400 text-xs rounded-full flex items-center gap-1">
                <Zap className="w-3 h-3" />
                NPU Processed
              </span>
            )}
            {hasChanges && (
              <span className="px-2 py-1 bg-yellow-900/50 text-yellow-400 text-xs rounded-full">
                Unsaved Changes
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={handleUndo}
              disabled={undoStack.length === 0}
              className="p-2 hover:bg-gray-700 rounded-lg disabled:opacity-50"
            >
              <Undo className="w-5 h-5 text-gray-400" />
            </button>
            <button
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              className="p-2 hover:bg-gray-700 rounded-lg disabled:opacity-50"
            >
              <Redo className="w-5 h-5 text-gray-400" />
            </button>
            
            <div className="h-6 w-px bg-gray-600 mx-2" />
            
            <button
              onClick={saveTranscript}
              disabled={!hasChanges}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              Save
            </button>
            
            <div className="relative group">
              <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg flex items-center gap-2">
                <Download className="w-4 h-4" />
                Export
              </button>
              <div className="absolute top-full right-0 mt-1 bg-gray-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                <button
                  onClick={() => exportTranscript('txt')}
                  className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                >
                  Text (.txt)
                </button>
                <button
                  onClick={() => exportTranscript('srt')}
                  className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                >
                  Subtitles (.srt)
                </button>
                <button
                  onClick={() => exportTranscript('json')}
                  className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                >
                  JSON (.json)
                </button>
                <button
                  onClick={() => exportTranscript('docx')}
                  className="block w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-gray-600"
                >
                  Word (.docx)
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Audio Player */}
      <div className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="max-w-7xl mx-auto">
          <audio
            ref={audioRef}
            src={session.audio_url}
            onTimeUpdate={handleAudioTimeUpdate}
            onEnded={() => setIsPlaying(false)}
          />
          
          <div className="flex items-center gap-4">
            <button
              onClick={togglePlayPause}
              className="p-2 bg-purple-600 hover:bg-purple-700 rounded-full"
            >
              {isPlaying ? <Pause className="w-5 h-5 text-white" /> : <Play className="w-5 h-5 text-white" />}
            </button>
            
            <button
              onClick={() => seekTo(Math.max(0, currentTime - 10))}
              className="p-2 hover:bg-gray-700 rounded-lg"
            >
              <SkipBack className="w-5 h-5 text-gray-400" />
            </button>
            
            <button
              onClick={() => seekTo(Math.min(session.duration, currentTime + 10))}
              className="p-2 hover:bg-gray-700 rounded-lg"
            >
              <SkipForward className="w-5 h-5 text-gray-400" />
            </button>
            
            <div className="flex-1">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <span>{formatTime(currentTime)}</span>
                <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-purple-500"
                    style={{ width: `${(currentTime / session.duration) * 100}%` }}
                  />
                </div>
                <span>{formatTime(session.duration)}</span>
              </div>
            </div>
            
            <select
              value={playbackRate}
              onChange={(e) => {
                const rate = parseFloat(e.target.value);
                setPlaybackRate(rate);
                if (audioRef.current) {
                  audioRef.current.playbackRate = rate;
                }
              }}
              className="px-3 py-1 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm"
            >
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1">1x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2x</option>
            </select>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar */}
        <div className="lg:col-span-1 space-y-4">
          {/* Search */}
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
              <input
                type="text"
                placeholder="Search transcript..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
              />
            </div>
          </div>

          {/* Speakers */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Users className="w-5 h-5" />
              Speakers
            </h3>
            
            <div className="space-y-2">
              <button
                onClick={() => setSelectedSpeaker('all')}
                className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                  selectedSpeaker === 'all' ? 'bg-purple-600 text-white' : 'hover:bg-gray-700 text-gray-300'
                }`}
              >
                All Speakers
              </button>
              
              {speakers.map(speaker => (
                <div key={speaker.id} className="flex items-center justify-between">
                  <button
                    onClick={() => setSelectedSpeaker(speaker.id)}
                    className={`flex-1 text-left px-3 py-2 rounded-lg transition-colors ${
                      selectedSpeaker === speaker.id ? 'bg-purple-600 text-white' : 'hover:bg-gray-700 text-gray-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={speaker.color}>{speaker.name}</span>
                      <span className="text-xs opacity-75">{speaker.segments}</span>
                    </div>
                    <div className="text-xs opacity-75 mt-1">
                      {formatTime(speaker.totalTime)}
                    </div>
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Options */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-white mb-4">Display Options</h3>
            
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-gray-300">
                <input
                  type="checkbox"
                  checked={showTimestamps}
                  onChange={(e) => setShowTimestamps(e.target.checked)}
                  className="rounded"
                />
                Show timestamps
              </label>
              
              <label className="flex items-center gap-2 text-gray-300">
                <input
                  type="checkbox"
                  checked={showConfidence}
                  onChange={(e) => setShowConfidence(e.target.checked)}
                  className="rounded"
                />
                Show confidence scores
              </label>
            </div>
          </div>
        </div>

        {/* Transcript */}
        <div className="lg:col-span-3">
          <div className="bg-gray-800 rounded-lg p-6">
            <div ref={transcriptRef} className="space-y-4 max-h-[70vh] overflow-y-auto">
              {filteredTranscript.map((segment, index) => (
                <div
                  key={segment.id}
                  id={`segment-${segment.id}`}
                  className={`p-4 rounded-lg transition-all ${
                    currentTime >= segment.start_time && currentTime <= segment.end_time
                      ? 'bg-purple-900/30 ring-2 ring-purple-500'
                      : 'bg-gray-700 hover:bg-gray-650'
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className={`font-medium ${getSpeakerColor(segment.speaker)}`}>
                        {segment.speaker}
                      </span>
                      {showTimestamps && (
                        <button
                          onClick={() => seekTo(segment.start_time)}
                          className="text-xs text-gray-400 hover:text-purple-400"
                        >
                          {formatTime(segment.start_time)}
                        </button>
                      )}
                      {showConfidence && (
                        <span className="text-xs text-gray-400">
                          {(segment.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleEdit(segment.id, segment.text)}
                        className="p-1 hover:bg-gray-600 rounded"
                      >
                        <Edit2 className="w-4 h-4 text-gray-400" />
                      </button>
                      <button
                        onClick={() => deleteSegment(segment.id)}
                        className="p-1 hover:bg-gray-600 rounded"
                      >
                        <Trash2 className="w-4 h-4 text-red-400" />
                      </button>
                    </div>
                  </div>
                  
                  {editingSegment === segment.id ? (
                    <div>
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white"
                        rows={3}
                        autoFocus
                      />
                      <div className="flex items-center gap-2 mt-2">
                        <button
                          onClick={() => saveEdit(segment.id)}
                          className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-1"
                        >
                          <Check className="w-4 h-4" />
                          Save
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-3 py-1 bg-gray-600 hover:bg-gray-500 text-white rounded-lg flex items-center gap-1"
                        >
                          <X className="w-4 h-4" />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-gray-100 leading-relaxed">{segment.text}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};