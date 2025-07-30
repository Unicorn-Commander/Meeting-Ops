import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  Save,
  Download,
  FileText,
  Mic,
  Users,
  Clock,
  Calendar,
  AlertCircle,
  Loader2,
  Play,
  Pause,
  RefreshCw,
  Edit3,
  X,
  CheckCircle
} from 'lucide-react';
import { ExportManager } from './ExportManager';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

interface Session {
  id: number;
  session_id: string;
  name: string;
  description?: string;
  start_time: string;
  end_time?: string;
  duration_seconds?: number;
  status: string;
  total_speakers?: number;
  total_transcriptions?: number;
  summary?: string;
  key_points?: string[];
  action_items?: string[];
  meeting_type?: string;
  audio_file_path?: string;
  audio_format?: string;
  processing_completed?: boolean;
  npu_accelerated?: boolean;
}

interface Transcription {
  id: number;
  text: string;
  speaker_id?: string;
  start_time_seconds: number;
  end_time_seconds: number;
  confidence: number;
  timestamp: string;
}

interface SessionDetailsProps {
  sessionId: string;
  onBack?: () => void;
}

export const SessionDetails: React.FC<SessionDetailsProps> = ({ sessionId, onBack }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'transcription' | 'summary' | 'audio' | 'export'>('transcription');
  const [editMode, setEditMode] = useState(false);
  const [editedSummary, setEditedSummary] = useState('');
  const [editedTranscriptions, setEditedTranscriptions] = useState<Map<number, string>>(new Map());
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSessionDetails();
  }, [sessionId]);

  const fetchSessionDetails = async () => {
    try {
      setLoading(true);
      setError(null);
      const token = localStorage.getItem('access_token');
      
      // Fetch session details
      const sessionResponse = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!sessionResponse.ok) {
        throw new Error('Failed to fetch session details');
      }
      
      const sessionData = await sessionResponse.json();
      setSession(sessionData.session);
      setTranscriptions(sessionData.transcriptions || []);
      setEditedSummary(sessionData.session.summary || '');
    } catch (error) {
      console.error('Error fetching session details:', error);
      setError('Failed to load session details');
    } finally {
      setLoading(false);
    }
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

  const formatTimestamp = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleSaveSummary = async () => {
    try {
      setSaving(true);
      setError(null);
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionId}/summary`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ summary: editedSummary })
      });
      
      if (!response.ok) {
        throw new Error('Failed to save summary');
      }
      
      // Update local state
      if (session) {
        setSession({ ...session, summary: editedSummary });
      }
      setEditMode(false);
    } catch (error) {
      console.error('Error saving summary:', error);
      setError('Failed to save summary');
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateSummary = async () => {
    try {
      setGenerating(true);
      setError(null);
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_BASE_URL}/api/recording-sessions/${sessionId}/summarize`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to generate summary');
      }
      
      // Refresh session data
      await fetchSessionDetails();
    } catch (error) {
      console.error('Error generating summary:', error);
      setError('Failed to generate summary');
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveTranscription = async (transcriptionId: number) => {
    try {
      setSaving(true);
      setError(null);
      const token = localStorage.getItem('access_token');
      const newText = editedTranscriptions.get(transcriptionId);
      
      if (!newText) return;
      
      const response = await fetch(`${API_BASE_URL}/api/transcriptions/${transcriptionId}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ text: newText })
      });
      
      if (!response.ok) {
        throw new Error('Failed to save transcription');
      }
      
      // Update local state
      setTranscriptions(transcriptions.map(t => 
        t.id === transcriptionId ? { ...t, text: newText } : t
      ));
      
      // Clear edited state for this transcription
      const newEdited = new Map(editedTranscriptions);
      newEdited.delete(transcriptionId);
      setEditedTranscriptions(newEdited);
    } catch (error) {
      console.error('Error saving transcription:', error);
      setError('Failed to save transcription');
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async (format: 'txt' | 'json' | 'pdf' | 'wav') => {
    try {
      const token = localStorage.getItem('access_token');
      const url = `${API_BASE_URL}/api/recording-sessions/${sessionId}/export?format=${format}`;
      
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `${session?.name || 'session'}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
      } else {
        throw new Error('Export failed');
      }
    } catch (error) {
      console.error('Error exporting session:', error);
      setError('Failed to export session');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="bg-gray-800 rounded-lg shadow-sm p-8 text-center">
        <AlertCircle className="w-12 h-12 mx-auto mb-4 text-red-500" />
        <p className="text-gray-400">Session not found</p>
        <button
          onClick={onBack}
          className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Go Back
        </button>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg shadow-sm text-white">
      {/* Header */}
      <div className="p-6 border-b border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            {onBack && (
              <button
                onClick={onBack}
                className="p-2 hover:bg-gray-700 rounded transition-colors text-gray-300"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
            )}
            <h1 className="text-2xl font-semibold">{session.name}</h1>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleExport('txt')}
              className="px-3 py-1 text-sm border border-gray-600 rounded hover:bg-gray-700"
            >
              Export TXT
            </button>
            <button
              onClick={() => handleExport('pdf')}
              className="px-3 py-1 text-sm border border-gray-600 rounded hover:bg-gray-700"
            >
              Export PDF
            </button>
            <button
              onClick={fetchSessionDetails}
              className="p-2 hover:bg-gray-700 rounded transition-colors"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Session Info */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-gray-300">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-500" />
            <span>{new Date(session.start_time).toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-500" />
            <span>{formatDuration(session.duration_seconds)}</span>
          </div>
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-gray-500" />
            <span>{session.total_speakers || 0} speakers</span>
          </div>
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-gray-500" />
            <span>{session.total_transcriptions || 0} segments</span>
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-700">
        <button
          onClick={() => setActiveTab('transcription')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'transcription'
              ? 'border-b-2 border-blue-500 text-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Transcription
        </button>
        <button
          onClick={() => setActiveTab('summary')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'summary'
              ? 'border-b-2 border-blue-500 text-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Summary
        </button>
        <button
          onClick={() => setActiveTab('audio')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'audio'
              ? 'border-b-2 border-blue-500 text-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Audio
        </button>
        <button
          onClick={() => setActiveTab('export')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'export'
              ? 'border-b-2 border-blue-500 text-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Export
        </button>
      </div>

      {/* Tab Content */}
      <div className="p-6">
        {activeTab === 'transcription' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium">Transcription</h2>
              {transcriptions.length > 0 && (
                <span className="text-sm text-gray-500">
                  {transcriptions.length} segments
                </span>
              )}
            </div>
            
            {transcriptions.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <FileText className="w-12 h-12 mx-auto mb-4 text-gray-600" />
                <p>No transcription available</p>
                {session.status === 'completed' && (
                  <button
                    className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
                  >
                    Generate Transcription
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {transcriptions.map((transcript) => {
                  const isEditing = editedTranscriptions.has(transcript.id);
                  const currentText = isEditing
                    ? editedTranscriptions.get(transcript.id)!
                    : transcript.text;
                  
                  return (
                    <div
                      key={transcript.id}
                      className="border border-gray-700 rounded-lg p-4 hover:shadow-sm transition-shadow bg-gray-900"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-3 text-sm text-gray-400">
                          <span className="font-mono">
                            {formatTimestamp(transcript.start_time_seconds)}
                          </span>
                          {transcript.speaker_id && (
                            <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs">
                              {transcript.speaker_id}
                            </span>
                          )}
                          {transcript.confidence > 0 && (
                            <span className="text-xs">
                              {Math.round(transcript.confidence * 100)}% confidence
                            </span>
                          )}
                        </div>
                        
                        <div className="flex items-center gap-2">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => handleSaveTranscription(transcript.id)}
                                className="p-1 text-green-600 hover:bg-green-50 rounded"
                                disabled={saving}
                              >
                                {saving ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <CheckCircle className="w-4 h-4" />
                                )}
                              </button>
                              <button
                                onClick={() => {
                                  const newEdited = new Map(editedTranscriptions);
                                  newEdited.delete(transcript.id);
                                  setEditedTranscriptions(newEdited);
                                }}
                                className="p-1 text-red-600 hover:bg-red-50 rounded"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </>
                          ) : (
                            <button
                              onClick={() => {
                                const newEdited = new Map(editedTranscriptions);
                                newEdited.set(transcript.id, transcript.text);
                                setEditedTranscriptions(newEdited);
                              }}
                              className="p-1 text-gray-400 hover:bg-gray-700 rounded"
                            >
                              <Edit3 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                      
                      {isEditing ? (
                        <textarea
                          value={currentText}
                          onChange={(e) => {
                            const newEdited = new Map(editedTranscriptions);
                            newEdited.set(transcript.id, e.target.value);
                            setEditedTranscriptions(newEdited);
                          }}
                          className="w-full p-2 border border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-800 text-white"
                          rows={3}
                        />
                      ) : (
                        <p className="text-gray-100">{transcript.text}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === 'summary' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium">Summary</h2>
              <div className="flex items-center gap-2">
                {!session.summary && session.status === 'completed' && (
                  <button
                    onClick={handleGenerateSummary}
                    disabled={generating}
                    className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 flex items-center gap-2"
                  >
                    {generating && <Loader2 className="w-4 h-4 animate-spin" />}
                    Generate Summary
                  </button>
                )}
                {session.summary && !editMode && (
                  <button
                    onClick={() => setEditMode(true)}
                    className="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700"
                  >
                    Edit
                  </button>
                )}
                {editMode && (
                  <>
                    <button
                      onClick={handleSaveSummary}
                      disabled={saving}
                      className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50 flex items-center gap-2"
                    >
                      {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                      Save
                    </button>
                    <button
                      onClick={() => {
                        setEditMode(false);
                        setEditedSummary(session.summary || '');
                      }}
                      className="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700"
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </div>
            
            {!session.summary && !generating ? (
              <div className="text-center py-8 text-gray-400">
                <FileText className="w-12 h-12 mx-auto mb-4 text-gray-600" />
                <p>No summary available</p>
              </div>
            ) : (
              <div>
                {editMode ? (
                  <textarea
                    value={editedSummary}
                    onChange={(e) => setEditedSummary(e.target.value)}
                    className="w-full p-4 border border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-900 text-white"
                    rows={12}
                    placeholder="Enter meeting summary..."
                  />
                ) : (
                  <div className="prose max-w-none">
                    <p className="whitespace-pre-wrap">{session.summary}</p>
                  </div>
                )}
                
                {/* Key Points and Action Items */}
                {(session.key_points || session.action_items) && (
                  <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                    {session.key_points && session.key_points.length > 0 && (
                      <div>
                        <h3 className="font-medium mb-2">Key Points</h3>
                        <ul className="list-disc list-inside space-y-1">
                          {session.key_points.map((point, index) => (
                            <li key={index} className="text-gray-300">{point}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {session.action_items && session.action_items.length > 0 && (
                      <div>
                        <h3 className="font-medium mb-2">Action Items</h3>
                        <ul className="list-disc list-inside space-y-1">
                          {session.action_items.map((item, index) => (
                            <li key={index} className="text-gray-700">{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'audio' && (
          <div className="space-y-4">
            <h2 className="text-lg font-medium mb-4">Audio Playback</h2>
            
            {session.audio_file_path ? (
              <div className="space-y-4">
                <audio
                  controls
                  className="w-full"
                  src={`${API_BASE_URL}/api/files/session/${sessionId}/stream`}
                >
                  Your browser does not support the audio element.
                </audio>
                
                <div className="flex items-center justify-between p-4 bg-gray-900 rounded-lg border border-gray-700">
                  <div className="text-sm text-gray-400">
                    <p>Format: {session.audio_format?.toUpperCase() || 'WAV'}</p>
                    <p>Duration: {formatDuration(session.duration_seconds)}</p>
                  </div>
                  
                  <button
                    onClick={() => handleExport('wav')}
                    className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 flex items-center gap-2"
                  >
                    <Download className="w-4 h-4" />
                    Download Audio
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-400">
                <Mic className="w-12 h-12 mx-auto mb-4 text-gray-600" />
                <p>No audio file available</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'export' && (
          <div>
            <ExportManager 
              sessionId={sessionId}
              title="Export Session"
            />
          </div>
        )}
      </div>
    </div>
  );
};