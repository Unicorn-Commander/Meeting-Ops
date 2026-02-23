import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Play, Pause, Download, Share2, Flag,
  Users, Clock, Calendar, FileText, Volume2,
  ChevronLeft, ChevronRight, Zap, Brain, Search,
  FileDown, FileAudio, FileSpreadsheet, BookOpen,
  Upload, Mail, Sparkles, RefreshCw, MessageCircle, Send
} from 'lucide-react';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { ErrorMessage } from '../components/ErrorMessage';
import { config } from '../config';

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
  title?: string;              // AI-generated title
  description?: string;
  created_at: string;
  started_at?: string;
  ended_at?: string;
  status: string;
  duration?: number;
  audio_file?: string;
  transcript?: string;         // Full transcript text
  transcript_simple?: string;  // Simple transcript without speakers
  transcript_diarized?: {      // Transcript with speaker info
    text: string;
    segments: TranscriptionSegment[];
    speakers: string[];
  };
  summary?: any;               // AI-generated summary JSON (legacy)
  final_summary?: {            // Comprehensive final summary
    executive?: string;
    bullets?: string[];
    actions?: Array<{action: string; owner?: string; priority?: string}>;
    decisions?: string[];
    tasks?: Array<{task: string; assignee?: string}>;
    minutes?: string;
    title?: string;
  };
  progressive_summaries?: Array<{  // All summaries during recording
    timestamp: string;
    word_count_at_summary: number;
    interval_used: number;
    processing_time_ms?: number;
    text?: string;                   // New plain text format
    sections?: {                     // Legacy structured format (optional)
      executive?: string;
      bullets?: string[];
      actions?: Array<{action: string; owner?: string; priority?: string}>;
      decisions?: string[];
      title?: string;
    };
  }>;
  ai_insights?: any;           // Legacy field
  metadata?: {                 // Processing metadata
    word_count?: number;
    speaker_count?: number;
    npu_accelerated?: boolean;
    processing_time_ms?: number;
    model_used?: string;
    last_progressive_summary?: string;
    total_progressive_summaries?: number;
  };
  generated_emails?: Array<{    // Generated follow-up emails
    subject: string;
    to?: string;
    cc?: string;
    body: string;
    attachments?: string[];
    type?: string;              // follow-up, action-items, summary, etc.
  }>;
  transcription?: {
    text?: string;
    segments?: TranscriptionSegment[];
    npu_accelerated?: boolean;
    processing_time?: number;
    language?: string;
    speakers?: string[];
  };
  transcription_segments?: TranscriptionSegment[];
}

export const SessionDetails: React.FC = () => {
  const { id: sessionId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [activeSegment, setActiveSegment] = useState<number>(-1);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>('all');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [generatingEmail, setGeneratingEmail] = useState(false);
  const [generatedEmails, setGeneratedEmails] = useState<any[]>([]);
  
  const audioRef = useRef<HTMLAudioElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const segmentRefs = useRef<(HTMLDivElement | null)[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // AI Chat state
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessage, setChatMessage] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{role: string; content: string}>>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatHistoryLoaded, setChatHistoryLoaded] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // AI Insights state
  const [insights, setInsights] = useState<any>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);

  useEffect(() => {
    console.log('🔍 SessionDetails useEffect - sessionId:', sessionId);
    if (sessionId) {
      fetchSession();
    } else {
      console.error('❌ No sessionId found in URL params');
      setError('No session ID provided in URL');
      setLoading(false);
    }
  }, [sessionId]);

  // Load persisted chat history from server when chat panel is opened
  useEffect(() => {
    if (!chatOpen || chatHistoryLoaded || !sessionId || !session) return;
    const loadChatHistory = async () => {
      try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(
          `${config.apiUrl}/api/ai-chat/sessions/${session.id || sessionId}/messages`,
          {
            headers: {
              ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
          }
        );
        if (response.ok) {
          const data = await response.json();
          // Validate that we got actual chat messages (not other data)
          if (Array.isArray(data) && data.length > 0 && data[0].role && data[0].content) {
            setChatMessages(data.map((msg: any) => ({
              role: msg.role,
              content: msg.content,
            })));
          }
        }
      } catch (err) {
        console.warn('Failed to load chat history:', err);
      } finally {
        setChatHistoryLoaded(true);
      }
    };
    loadChatHistory();
  }, [chatOpen, chatHistoryLoaded, sessionId, session]);

  // Fetch AI insights from the real backend endpoint
  useEffect(() => {
    if (!sessionId) return;
    const fetchInsights = async () => {
      setInsightsLoading(true);
      try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(
          `${config.apiUrl}/api/simple/recording-sessions/${sessionId}/insights`,
          {
            headers: {
              ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
          }
        );
        if (response.ok) {
          const data = await response.json();
          setInsights(data);
        } else {
          console.warn('Failed to fetch AI insights:', response.status);
          setInsights(null);
        }
      } catch (err) {
        console.warn('AI insights fetch error:', err);
        setInsights(null);
      } finally {
        setInsightsLoading(false);
      }
    };
    fetchInsights();
  }, [sessionId]);

  const fetchSession = async () => {
    try {
      setError(null);
      console.log('📋 Fetching session details for:', sessionId);
      const url = `${config.apiUrl}/api/simple/recording-sessions/${sessionId}`;
      console.log('🔗 Fetching from URL:', url);
      
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Session data received:', data);
        
        // Normalize transcription data - prefer transcription_segments, then diarized segments
        if (!data.transcription) {
          data.transcription = {};
        }

        if (data.transcription_segments && data.transcription_segments.length > 0) {
          data.transcription.segments = data.transcription_segments;
          console.log('📝 Found', data.transcription_segments.length, 'transcription segments');
        } else if (data.transcript_diarized?.segments?.length) {
          data.transcription.segments = data.transcript_diarized.segments;
          console.log('📝 Found', data.transcript_diarized.segments.length, 'diarized segments');
        }

        if (!data.transcription.text && data.transcript_simple) {
          data.transcription.text = data.transcript_simple;
        }
        
        // Check if we have transcript text
        if (data.transcript || data.transcription?.text) {
          console.log('✅ Transcript text available');
        } else {
          console.log('⚠️ No transcript text found');
        }
        
        setSession(data);
        console.log('✅ Session loaded successfully');
      } else {
        const errorText = await response.text();
        console.error('❌ Failed to fetch session:', response.status, errorText);
        setError(`Failed to fetch session: ${response.status} ${errorText}`);
      }
    } catch (error) {
      console.error('❌ Error fetching session:', error);
      setError(`Network error: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
    if (!session?.transcription && !session?.transcript && !session?.transcript_simple) return;
    
    let content = '';
    
    // Try segments first, then full transcript text
    if (session.transcription?.segments && session.transcription.segments.length > 0) {
      content = session.transcription.segments.map(seg => 
        `[${formatTime(seg.start)}] ${seg.speaker || 'Speaker'}: ${seg.text}`
      ).join('\n\n');
    } else if (session.transcript) {
      content = session.transcript;
    } else if (session.transcript_simple) {
      content = session.transcript_simple;
    } else if (session.transcription?.text) {
      content = session.transcription.text;
    }
    
    if (!content) {
      alert('No transcript available for download');
      return;
    }
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript_${(session.title || session.name || 'session').replace(/\s+/g, '_')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadSummary = () => {
    if (!session?.summary && !session?.final_summary) {
      alert('No summary available for download');
      return;
    }
    
    let content = `MEETING SUMMARY\n`;
    content += `===============\n\n`;
    content += `Meeting: ${session.title || session.name || 'Untitled'}\n`;
    content += `Date: ${formatDate(session.created_at)}\n`;
    content += `Duration: ${session.duration ? formatTime(session.duration) : 'N/A'}\n\n`;
    
    const summarySource = session.final_summary || session.summary?.analysis || session.summary || {};

    if ((summarySource as Session['final_summary'])?.executive) {
      content += `EXECUTIVE SUMMARY\n`;
      content += `-----------------\n`;
      content += `${(summarySource as Session['final_summary'])?.executive}\n\n`;
    }
    
    const bullets = (summarySource as Session['final_summary'])?.bullets || [];
    if (bullets.length > 0) {
      content += `KEY DISCUSSION POINTS\n`;
      content += `---------------------\n`;
      bullets.forEach((bullet: string) => {
        content += `• ${bullet}\n`;
      });
      content += '\n';
    }
    
    const decisions = (summarySource as Session['final_summary'])?.decisions || [];
    if (decisions.length > 0) {
      content += `IMPORTANT DECISIONS\n`;
      content += `-------------------\n`;
      decisions.forEach((decision: string) => {
        content += `✓ ${decision}\n`;
      });
      content += '\n';
    }
    
    const actions = (summarySource as Session['final_summary'])?.actions || [];
    if (actions.length > 0) {
      content += `ACTION ITEMS\n`;
      content += `------------\n`;
      actions.forEach((action: any) => {
        const actionText = typeof action === 'string' ? action : action.action;
        content += `□ ${actionText}\n`;
        if (action.owner) content += `  Owner: ${action.owner}\n`;
        if (action.priority) content += `  Priority: ${action.priority}\n`;
        content += '\n';
      });
    }
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `summary_${(session.title || session.name || 'session').replace(/\s+/g, '_')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadAudio = async () => {
    if (!sessionId) return;
    
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions/${session?.id || sessionId}/download/audio`);
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `recording_${(session?.name || session?.title || session?.id || sessionId).toString().replace(/\s+/g, '_')}.wav`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download audio:', error);
    }
  };

  const handleAudioUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !session) return;
    
    // Validate file type
    if (!file.type.startsWith('audio/')) {
      alert('Please select an audio file');
      return;
    }
    
    // Validate file size (max 500MB)
    if (file.size > 500 * 1024 * 1024) {
      alert('Audio file is too large. Please select a file under 500MB.');
      return;
    }
    
    setUploading(true);
    
    try {
      const formData = new FormData();
      formData.append('audio', file);
      
      const response = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${session.id}/upload-audio`,
        {
          method: 'POST',
          body: formData
        }
      );
      
      if (response.ok) {
        alert('Audio uploaded successfully! Processing will begin shortly.');
        // Refresh session data
        await fetchSession();
        setShowUploadModal(false);
      } else {
        const error = await response.text();
        alert(`Failed to upload audio: ${error}`);
      }
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Failed to upload audio file');
    } finally {
      setUploading(false);
    }
  };

  const sendChatMessage = async () => {
    if (!chatMessage.trim() || chatLoading || !session) return;
    
    const userMsg = chatMessage.trim();
    setChatMessage('');
    setChatMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatLoading(true);
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${config.apiUrl}/api/ai-chat/sessions/${session.id || sessionId}/messages`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          },
          body: JSON.stringify({ message: userMsg })
        }
      );
      
      if (response.ok) {
        const data = await response.json();
        setChatMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
      } else {
        setChatMessages(prev => [...prev, { role: 'assistant', content: 'Failed to get a response. Please try again.' }]);
      }
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Network error. Please check your connection.' }]);
    } finally {
      setChatLoading(false);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  };

  const generateEmails = async () => {
    if (!session) return;
    
    setGeneratingEmail(true);
    
    try {
      const response = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${session.id}/generate-emails`,
        { method: 'POST' }
      );
      
      if (response.ok) {
        const emails = await response.json();
        setGeneratedEmails(emails);
        
        // Store emails in session data
        setSession({
          ...session,
          generated_emails: emails
        });
      } else {
        alert('Failed to generate emails');
      }
    } catch (error) {
      console.error('Email generation failed:', error);
      alert('Failed to generate emails');
    } finally {
      setGeneratingEmail(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="text-center">
          <LoadingSpinner size="lg" message="Loading session details..." />
          <div className="mt-4 text-sm text-gray-400">
            Session ID: {sessionId}
            <br />
            Check browser console for debug logs
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="max-w-md w-full">
          <ErrorMessage 
            message={error}
            onRetry={fetchSession}
            variant="banner"
          />
          <div className="text-center mt-6">
            <button
              onClick={() => navigate('/sessions')}
              className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
            >
              Back to Sessions
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 mb-4">Session not found</p>
          <button
            onClick={() => navigate('/sessions')}
            className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
          >
            Back to Sessions
          </button>
        </div>
      </div>
    );
  }

  const segments = session.transcription?.segments
    || session.transcription_segments
    || session.transcript_diarized?.segments
    || [];

  const filteredSegments = segments.filter(seg => {
    const matchesSpeaker = selectedSpeaker === 'all' || seg.speaker === selectedSpeaker;
    const matchesSearch = !searchTerm || seg.text.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSpeaker && matchesSearch;
  });

  const speakers = session.transcription?.speakers
    || [...new Set(segments.map(s => s.speaker || 'Speaker'))];

  const transcriptText = session.transcript
    || session.transcript_simple
    || session.transcription?.text
    || '';

  const hasTranscript = Boolean(transcriptText || segments.length > 0);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/sessions')}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  {session.title || session.name || 'Meeting Session'}
                </h1>
                {session.title && session.name !== session.title && (
                  <p className="text-sm text-gray-500 mt-1">Original: {session.name}</p>
                )}
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
              {/* Upload Audio Button */}
              {!session.audio_file && (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                >
                  {uploading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Upload Audio
                    </>
                  )}
                </button>
              )}
              
              {/* Generate Emails Button */}
              <button
                onClick={generateEmails}
                disabled={generatingEmail || !(session.transcript || session.transcript_simple || session.transcription?.text || session.transcription?.segments?.length)}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center gap-2"
              >
                {generatingEmail ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Mail className="w-4 h-4" />
                    Generate Emails
                  </>
                )}
              </button>
              
              {/* Download Dropdown Menu */}
              <div className="relative group">
                <button className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2">
                  <Download className="w-4 h-4" />
                  Downloads
                  <ChevronRight className="w-4 h-4 transform group-hover:rotate-90 transition-transform" />
                </button>
                
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                  <div className="py-2">
                    <button
                      onClick={downloadAudio}
                      disabled={!session.audio_file}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
                    >
                      <FileAudio className="w-4 h-4 text-purple-600" />
                      Audio (WAV)
                    </button>
                    
                    <button
                      onClick={downloadTranscript}
                      disabled={!hasTranscript}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
                    >
                      <FileText className="w-4 h-4 text-blue-600" />
                      Transcript (Simple)
                    </button>
                    
                    <button
                      onClick={async () => {
                        const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}/download/transcript`);
                        if (response.ok) {
                          const blob = await response.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `transcript_with_speakers_${session.id || sessionId}.txt`;
                          a.click();
                          URL.revokeObjectURL(url);
                        } else {
                          downloadTranscript();
                        }
                      }}
                      disabled={segments.length === 0}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
                    >
                      <Users className="w-4 h-4 text-green-600" />
                      Transcript (Speakers)
                    </button>
                    
                    <button
                      onClick={() => downloadSummary()}
                      disabled={!session.final_summary && !session.summary}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
                    >
                      <Brain className="w-4 h-4 text-purple-600" />
                      Summary (TXT)
                    </button>
                    
                    <button
                      onClick={async () => {
                        const response = await fetch(`${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}/download/minutes`);
                        if (response.ok) {
                          const blob = await response.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `minutes_${session.id || sessionId}.txt`;
                          a.click();
                          URL.revokeObjectURL(url);
                        }
                      }}
                      disabled={!session.final_summary?.minutes}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
                    >
                      <BookOpen className="w-4 h-4 text-indigo-600" />
                      Meeting Minutes
                    </button>
                    
                    <div className="border-t my-2"></div>
                    
                    <button
                      onClick={async () => {
                        try {
                          const token = localStorage.getItem('access_token');
                          const response = await fetch(
                            `${config.apiUrl}/api/simple/recording-sessions/${session.id}/download/summary/pdf`,
                            { headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) } }
                          );
                          if (!response.ok) throw new Error(`Export failed: ${response.status}`);
                          const blob = await response.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${(session.title || session.name || 'meeting').replace(/\s+/g, '_')}.pdf`;
                          document.body.appendChild(a);
                          a.click();
                          document.body.removeChild(a);
                          URL.revokeObjectURL(url);
                        } catch (err) {
                          console.error('PDF export error:', err);
                          alert('PDF export failed. Please try again.');
                        }
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                    >
                      <FileSpreadsheet className="w-4 h-4 text-red-600" />
                      Summary (PDF)
                    </button>

                    <button
                      onClick={async () => {
                        try {
                          const token = localStorage.getItem('access_token');
                          const response = await fetch(
                            `${config.apiUrl}/api/simple/recording-sessions/${session.id}/download/summary/docx`,
                            { headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) } }
                          );
                          if (!response.ok) throw new Error(`Export failed: ${response.status}`);
                          const blob = await response.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${(session.title || session.name || 'meeting').replace(/\s+/g, '_')}.docx`;
                          document.body.appendChild(a);
                          a.click();
                          document.body.removeChild(a);
                          URL.revokeObjectURL(url);
                        } catch (err) {
                          console.error('DOCX export error:', err);
                          alert('DOCX export failed. Please try again.');
                        }
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                    >
                      <FileText className="w-4 h-4 text-blue-600" />
                      Summary (DOCX)
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        onChange={handleAudioUpload}
        className="hidden"
      />

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* AI Summary Section */}
            {(session.final_summary || session.summary || session.progressive_summaries?.length || session.transcript) && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Brain className="w-5 h-5 text-purple-600" />
                  AI Summary
                  {session.metadata?.total_progressive_summaries && (
                    <span className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded-full">
                      {session.metadata.total_progressive_summaries} progressive updates
                    </span>
                  )}
                </h2>
                
                {/* Use final_summary first, then fall back to legacy summary field */}
                {(session.final_summary || session.summary) ? (
                  <div className="space-y-4">
                    {/* Executive Summary */}
                    {(session.final_summary?.executive || session.summary?.executive || session.summary?.analysis?.executive) && (
                      <div>
                        <h3 className="text-md font-medium text-gray-800 mb-2">Executive Summary</h3>
                        <p className="text-gray-700 bg-gray-50 p-4 rounded-lg">
                          {session.final_summary?.executive || session.summary?.executive || session.summary?.analysis?.executive}
                        </p>
                      </div>
                    )}
                    
                    {/* Key Discussion Points */}
                    {((session.final_summary?.bullets && session.final_summary.bullets.length > 0) || 
                      (session.summary?.bullets && session.summary.bullets.length > 0) ||
                      (session.summary?.analysis?.bullets && session.summary.analysis.bullets.length > 0)) && (
                      <div>
                        <h3 className="text-md font-medium text-gray-800 mb-2">Key Discussion Points</h3>
                        <ul className="space-y-2">
                          {(session.final_summary?.bullets || session.summary?.bullets || session.summary?.analysis?.bullets || []).map((bullet: string, idx: number) => (
                            <li key={idx} className="flex items-start gap-2">
                              <span className="text-purple-600 mt-1.5">•</span>
                              <span className="text-gray-700">{bullet}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {/* Action Items */}
                    {((session.final_summary?.actions && session.final_summary.actions.length > 0) ||
                      (session.summary?.actions && session.summary.actions.length > 0) ||
                      (session.summary?.analysis?.actions && session.summary.analysis.actions.length > 0)) && (
                      <div>
                        <h3 className="text-md font-medium text-gray-800 mb-2">Action Items</h3>
                        <div className="space-y-2">
                          {(session.final_summary?.actions || session.summary?.actions || session.summary?.analysis?.actions || []).map((action: any, idx: number) => (
                            <div key={idx} className="bg-yellow-50 border-l-4 border-yellow-400 p-3 rounded">
                              <p className="text-gray-800 font-medium">{action.action || action}</p>
                              {action.owner && (
                                <p className="text-sm text-gray-600 mt-1">Owner: {action.owner}</p>
                              )}
                              {action.priority && (
                                <span className={`inline-block px-2 py-1 text-xs rounded mt-1 ${
                                  action.priority.toLowerCase() === 'high' ? 'bg-red-100 text-red-800' :
                                  action.priority.toLowerCase() === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                                  'bg-green-100 text-green-800'
                                }`}>
                                  {action.priority} Priority
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {/* Important Decisions */}
                    {((session.final_summary?.decisions && session.final_summary.decisions.length > 0) ||
                      (session.summary?.decisions && session.summary.decisions.length > 0) ||
                      (session.summary?.analysis?.decisions && session.summary.analysis.decisions.length > 0)) && (
                      <div>
                        <h3 className="text-md font-medium text-gray-800 mb-2">Important Decisions</h3>
                        <ul className="space-y-2">
                          {(session.final_summary?.decisions || session.summary?.decisions || session.summary?.analysis?.decisions || []).map((decision: string, idx: number) => (
                            <li key={idx} className="flex items-start gap-2">
                              <span className="text-green-600 mt-1.5">✓</span>
                              <span className="text-gray-700">{decision}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {/* Meeting Minutes (new) */}
                    {session.final_summary?.minutes && (
                      <div>
                        <h3 className="text-md font-medium text-gray-800 mb-2">Meeting Minutes</h3>
                        <div className="text-gray-700 bg-gray-50 p-4 rounded-lg whitespace-pre-wrap">
                          {session.final_summary.minutes}
                        </div>
                      </div>
                    )}
                    
                    {/* Tasks (new) */}
                    {session.final_summary?.tasks && session.final_summary.tasks.length > 0 && (
                      <div>
                        <h3 className="text-md font-medium text-gray-800 mb-2">Tasks</h3>
                        <div className="space-y-2">
                          {session.final_summary.tasks.map((task: any, idx: number) => (
                            <div key={idx} className="bg-blue-50 border-l-4 border-blue-400 p-3 rounded">
                              <p className="text-gray-800">{task.task || task}</p>
                              {task.assignee && (
                                <p className="text-sm text-gray-600 mt-1">Assignee: {task.assignee}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <p className="text-gray-500 mb-4">
                      {session.status === 'processing' ? 
                        'AI summary is being generated...' : 
                        'AI summary not yet available'}
                    </p>
                    {session.status === 'processing' && (
                      <div className="flex items-center justify-center">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-600"></div>
                        <span className="ml-2 text-sm text-gray-500">Processing...</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Progressive Summaries Timeline */}
            {session.progressive_summaries && session.progressive_summaries.length > 0 && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Zap className="w-5 h-5 text-yellow-500" />
                  Progressive Summary Timeline
                  <span className="text-xs px-2 py-1 bg-yellow-100 text-yellow-700 rounded-full">
                    {session.progressive_summaries.length} updates
                  </span>
                </h2>
                
                <div className="space-y-4 max-h-96 overflow-y-auto">
                  {session.progressive_summaries.map((summary, idx) => (
                    <div key={idx} className="border-l-2 border-gray-200 pl-4 pb-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-3 h-3 bg-yellow-500 rounded-full -ml-6"></div>
                        <span className="text-sm font-medium text-gray-700">
                          Update #{idx + 1} - {summary.word_count_at_summary} words
                        </span>
                        <span className="text-xs text-gray-500">
                          {new Date(summary.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      
                      {/* Handle both new plain text format and legacy structured format */}
                      {summary.text ? (
                        // New plain text format
                        <div className="bg-gray-50 p-3 rounded text-sm text-gray-700 mb-2">
                          {summary.text}
                        </div>
                      ) : summary.sections ? (
                        // Legacy structured format
                        <>
                          {summary.sections.executive && (
                            <div className="bg-gray-50 p-3 rounded text-sm text-gray-700 mb-2">
                              {summary.sections.executive}
                            </div>
                          )}
                          
                          {summary.sections.bullets && summary.sections.bullets.length > 0 && (
                            <ul className="text-sm text-gray-600 space-y-1">
                              {summary.sections.bullets.slice(0, 3).map((bullet, bidx) => (
                                <li key={bidx}>• {bullet}</li>
                              ))}
                            </ul>
                          )}
                        </>
                      ) : (
                        // Fallback for empty summaries
                        <div className="text-sm text-gray-500 italic">
                          No summary content available
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Generated Emails Section */}
            {(generatedEmails.length > 0 || (session?.generated_emails?.length ?? 0) > 0) && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Mail className="w-5 h-5 text-green-600" />
                  Generated Emails
                  <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded-full">
                    {generatedEmails.length || session?.generated_emails?.length} emails
                  </span>
                </h2>
                
                <div className="space-y-4">
                  {(generatedEmails.length > 0 ? generatedEmails : session?.generated_emails || []).map((email: any, idx: number) => (
                    <div key={idx} className="border rounded-lg p-4 hover:bg-gray-50">
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <h4 className="font-medium text-gray-900">{email.subject}</h4>
                          <p className="text-sm text-gray-500 mt-1">
                            To: {email.to || 'stakeholders@company.com'}
                          </p>
                          {email.cc && (
                            <p className="text-sm text-gray-500">
                              CC: {email.cc}
                            </p>
                          )}
                        </div>
                        <button
                          onClick={() => {
                            // Copy email to clipboard
                            const emailText = `To: ${email.to || 'stakeholders@company.com'}\n${email.cc ? `CC: ${email.cc}\n` : ''}Subject: ${email.subject}\n\n${email.body}`;
                            navigator.clipboard.writeText(emailText);
                            alert('Email copied to clipboard!');
                          }}
                          className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                        >
                          Copy
                        </button>
                      </div>
                      
                      <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 p-3 rounded">
                        {email.body}
                      </div>
                      
                      {email.attachments && email.attachments.length > 0 && (
                        <div className="mt-2 text-sm text-gray-500">
                          <span className="font-medium">Attachments:</span> {email.attachments.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Audio Player */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Volume2 className="w-5 h-5 text-purple-600" />
                Audio Playback
              </h2>

              {session.audio_file ? (
                <>
                  <audio
                    ref={audioRef}
                    src={`${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}/download/audio`}
                    onTimeUpdate={handleTimeUpdate}
                    onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                    onError={(e) => {
                      console.error('Audio load error:', e);
                      console.log('Attempted URL:', `${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}/download/audio`);
                    }}
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
                </>
              ) : (
                <p className="text-gray-500 text-center py-4">No audio recording available</p>
              )}
            </div>

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
                {/* Show full transcript text if available */}
                {filteredSegments.length === 0 && transcriptText ? (
                  <div className="p-4 rounded-lg bg-gray-50">
                    <p className="text-gray-700 whitespace-pre-wrap">
                      {transcriptText}
                    </p>
                  </div>
                ) : filteredSegments.length === 0 && session.status === 'processing' ? (
                  <div className="text-center py-8">
                    <div className="flex items-center justify-center mb-4">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
                    </div>
                    <p className="text-gray-500">Transcription in progress...</p>
                  </div>
                ) : filteredSegments.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">
                    {searchTerm ? 'No matching segments found' : 
                     session.status === 'completed' ? 'No transcript available' : 'Transcription pending'}
                  </p>
                ) : (
                  filteredSegments.map((segment, index) => (
                    <div
                      key={index}
                      ref={(el: HTMLDivElement | null) => { segmentRefs.current[index] = el; }}
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
            {/* Processing Metadata */}
            {session.metadata && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Zap className="w-5 h-5 text-yellow-500" />
                  Processing Stats
                </h3>
                
                <div className="space-y-3">
                  {session.metadata.word_count && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Total Words</span>
                      <span className="text-sm font-medium">{session.metadata.word_count.toLocaleString()}</span>
                    </div>
                  )}
                  
                  {session.metadata.speaker_count && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Speakers</span>
                      <span className="text-sm font-medium">{session.metadata.speaker_count}</span>
                    </div>
                  )}
                  
                  {session.metadata.npu_accelerated !== undefined && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">NPU Accelerated</span>
                      <span className={`text-sm font-medium ${session.metadata.npu_accelerated ? 'text-green-600' : 'text-gray-500'}`}>
                        {session.metadata.npu_accelerated ? 'Yes' : 'No'}
                      </span>
                    </div>
                  )}
                  
                  {session.metadata.processing_time_ms && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Processing Time</span>
                      <span className="text-sm font-medium">
                        {(session.metadata.processing_time_ms / 1000).toFixed(1)}s
                      </span>
                    </div>
                  )}
                  
                  {session.metadata.model_used && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">AI Model</span>
                      <span className="text-sm font-medium">{session.metadata.model_used}</span>
                    </div>
                  )}
                  
                  {session.metadata.total_progressive_summaries && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Progressive Updates</span>
                      <span className="text-sm font-medium">{session.metadata.total_progressive_summaries}</span>
                    </div>
                  )}
                  
                  {session.duration && session.metadata.word_count && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Words/Minute</span>
                      <span className="text-sm font-medium">
                        {Math.round(session.metadata.word_count / (session.duration / 60))}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {/* AI Insights */}
            {insightsLoading && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Brain className="w-5 h-5 text-purple-600" />
                  AI Insights
                </h3>
                <div className="flex items-center justify-center py-6">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-600"></div>
                  <span className="ml-2 text-sm text-gray-500">Loading insights...</span>
                </div>
              </div>
            )}
            {!insightsLoading && insights && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Brain className="w-5 h-5 text-purple-600" />
                  AI Insights
                </h3>

                <div className="space-y-4">
                  {insights.keywords && insights.keywords.length > 0 && (
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Key Topics</p>
                      <div className="flex flex-wrap gap-2">
                        {insights.keywords.map((topic: string) => (
                          <span
                            key={topic}
                            className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm"
                          >
                            {topic}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {insights.sentiment && (
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Sentiment</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                          <div
                            className={`h-full rounded-full ${
                              insights.sentiment.overall === 'positive' ? 'bg-green-500' :
                              insights.sentiment.overall === 'negative' ? 'bg-red-500' :
                              'bg-yellow-500'
                            }`}
                            style={{ width: `${Math.round((insights.sentiment.score ?? 0.5) * 100)}%` }}
                          />
                        </div>
                        <span className="text-sm text-gray-600 capitalize">
                          {insights.sentiment.overall || 'Neutral'}
                        </span>
                      </div>
                    </div>
                  )}

                  {insights.speaker_insights && insights.speaker_insights.length > 0 && (
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Speaking Time</p>
                      <div className="space-y-2">
                        {insights.speaker_insights.map((si: any, idx: number) => (
                          <div key={idx} className="flex items-center justify-between">
                            <span className="text-sm text-gray-600">{si.speaker}</span>
                            <span className="text-sm font-medium">
                              {Math.round(si.talk_percentage ?? 0)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {insights.action_items && insights.action_items.length > 0 && (
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Action Items</p>
                      <ul className="space-y-1">
                        {insights.action_items.map((item: any, idx: number) => (
                          <li key={idx} className="text-sm text-gray-700 flex items-start gap-1">
                            <span className="text-yellow-500 mt-0.5">&#9632;</span>
                            <span>{typeof item === 'string' ? item : item.action || item.text || JSON.stringify(item)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {insights.key_decisions && insights.key_decisions.length > 0 && (
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Key Decisions</p>
                      <ul className="space-y-1">
                        {insights.key_decisions.map((decision: any, idx: number) => (
                          <li key={idx} className="text-sm text-gray-700 flex items-start gap-1">
                            <span className="text-green-600 mt-0.5">&#10003;</span>
                            <span>{typeof decision === 'string' ? decision : decision.text || JSON.stringify(decision)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

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

            {/* AI Chat Panel */}
            <div className="bg-white rounded-lg shadow-sm">
              <button
                onClick={() => setChatOpen(!chatOpen)}
                className="w-full p-4 flex items-center justify-between hover:bg-gray-50 rounded-lg transition-colors"
              >
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <MessageCircle className="w-5 h-5 text-purple-600" />
                  AI Chat
                </h3>
                <ChevronRight className={`w-5 h-5 text-gray-400 transition-transform ${chatOpen ? 'rotate-90' : ''}`} />
              </button>

              {chatOpen && (
                <div className="px-4 pb-4">
                  {/* Chat messages */}
                  <div className="border rounded-lg mb-3 max-h-64 overflow-y-auto bg-gray-50">
                    {chatMessages.length === 0 ? (
                      <div className="p-4 text-center text-sm text-gray-500">
                        Ask questions about this meeting.
                      </div>
                    ) : (
                      <div className="p-3 space-y-3">
                        {chatMessages.map((msg, idx) => (
                          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                              msg.role === 'user'
                                ? 'bg-purple-600 text-white'
                                : 'bg-white border text-gray-700'
                            }`}>
                              {msg.content}
                            </div>
                          </div>
                        ))}
                        {chatLoading && (
                          <div className="flex justify-start">
                            <div className="bg-white border rounded-lg px-3 py-2 text-sm text-gray-500">
                              <div className="flex items-center gap-2">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-purple-600"></div>
                                Thinking...
                              </div>
                            </div>
                          </div>
                        )}
                        <div ref={chatEndRef} />
                      </div>
                    )}
                  </div>

                  {/* Chat input */}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); } }}
                      placeholder="Ask about this meeting..."
                      disabled={chatLoading}
                      className="flex-1 px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
                    />
                    <button
                      onClick={sendChatMessage}
                      disabled={chatLoading || !chatMessage.trim()}
                      className="px-3 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
