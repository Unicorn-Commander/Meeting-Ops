import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Play, Pause, Download, Share2, Flag,
  Users, Clock, Calendar, FileText, Volume2,
  ChevronLeft, ChevronRight, Zap, Brain, Search,
  FileDown, FileAudio, FileSpreadsheet, BookOpen,
  Upload, Mail, Sparkles, RefreshCw, MessageCircle, Send,
  Briefcase, Edit2, Check
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { ErrorMessage } from '../components/ErrorMessage';
import { ProjectLinkPicker, type ProjectLink } from '../components/ProjectLinkPicker';
import {
  TranscriptionOptionsPanel,
  serializeTranscriptionOptions,
  DEFAULT_TRANSCRIPTION_OPTIONS,
  type TranscriptionOptions,
} from '../components/TranscriptionOptionsPanel';
import { SpeakerTagger } from '../components/SpeakerTagger';
import AudioPlayer from '../components/AudioPlayer';
import { SessionPermissionsModal } from '../components/SessionPermissionsModal';
import { SpeakerLabelEditor } from '../components/SpeakerLabelEditor';
import { SpeakerTimeline } from '../components/SpeakerTimeline';
import { EmailAttendeesModal } from '../components/EmailAttendeesModal';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';
import { useUploads } from '../contexts/UploadsContext';

/**
 * Normalize a backend error body into a user-readable string.
 *
 * FastAPI returns several shapes on errors:
 *  - 422 validation: { detail: [{loc:[...], msg:"...", type:"..."}] }
 *  - 4xx HTTPException(detail=string): { detail: "human message" }
 *  - 4xx HTTPException(detail=dict): { detail: { code, message, ... } } — used by quota errors
 *  - 5xx without a detail field: { } or HTML
 *
 * Passing any of these straight into new Error(x) where x is an object
 * produces the famous "[object Object]" UI bug. This helper prefers a
 * string message in priority order, then falls back to a stringified
 * representation that is still readable.
 */
function formatBackendError(body: any, status: number, fallback: string): string {
  const tag = `${fallback} (${status})`;
  if (!body) return tag;
  const d = body.detail ?? body;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    // FastAPI 422 validation errors
    const msgs = d
      .map((e) => (e && (e.msg || e.message)) || '')
      .filter(Boolean);
    return msgs.length ? `${tag}: ${msgs.join('; ')}` : tag;
  }
  if (typeof d === 'object') {
    if (typeof d.message === 'string') return d.message;
    if (typeof d.error === 'string') return d.error;
    try {
      return `${tag}: ${JSON.stringify(d)}`;
    } catch {
      return tag;
    }
  }
  return tag;
}

interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  confidence?: number;
}

interface Session {
  id: string;
  session_id?: string;          // UUID, distinct from numeric id
  name: string;
  title?: string;              // AI-generated title
  title_user_set?: boolean;    // True once the user has manually renamed
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
  // Project linking (Phase 2)
  project_app?: string | null;     // 'project-ops' | 'crisis-ops' | null
  project_id?: string | null;
  project_slug?: string | null;
}

const PROJECT_APP_LABELS: Record<string, string> = {
  'project-ops': 'Project-Ops',
  'crisis-ops': 'Crisis-Ops',
};

export const SessionDetails: React.FC = () => {
  const { id: sessionId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { getOrgQueryUrl, activeOrganization } = useOrg();
  const { startUploads } = useUploads();
  
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
  // Re-process modal: re-runs the transcribe -> diarize -> summarize -> embed
  // pipeline against the existing audio with new options.
  const [showReprocessModal, setShowReprocessModal] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  // Speaker link + org speaker library — fetched once per session so the
  // inline SpeakerLabelEditor popover can render assign/merge targets
  // without making the user open the side-panel SpeakerTagger.
  const [speakerLinks, setSpeakerLinks] = useState<Array<{ id: number; raw_label: string; speaker_id: number | null; speaker_display?: string | null }>>([]);
  const [orgSpeakers, setOrgSpeakers] = useState<Array<{ id: number; display_name: string; has_centroid: boolean }>>([]);
  const [speakerVersion, setSpeakerVersion] = useState(0);  // bump to refresh after edits
  const [reprocessOpts, setReprocessOpts] = useState<TranscriptionOptions>(
    DEFAULT_TRANSCRIPTION_OPTIONS,
  );
  const [reprocessError, setReprocessError] = useState<string | null>(null);
  // Per-upload options for the audio-attach flow on this page.
  const [attachOpts, setAttachOpts] = useState<TranscriptionOptions>(
    DEFAULT_TRANSCRIPTION_OPTIONS,
  );
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

  // Project link editor state
  const [editingProjectLink, setEditingProjectLink] = useState(false);
  // Title editing: title_user_set flips True in the backend when the user
  // saves a custom title, which then prevents auto-summary from
  // overwriting the rename on the next reprocess.
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [projectLinkDraft, setProjectLinkDraft] = useState<ProjectLink>({
    project_app: null,
    project_id: null,
    project_slug: null,
  });
  const [savingProjectLink, setSavingProjectLink] = useState(false);

  // TTS state — single-voice "listen to summary" + multi-voice podcast
  const [ttsProvider, setTtsProvider] = useState<{ name: string; supports_podcast: boolean } | null>(null);
  const [ttsVoices, setTtsVoices] = useState<Array<{ voice_id: string; label: string }>>([]);
  const [summaryVoice, setSummaryVoice] = useState<string>('');
  const [hostVoice, setHostVoice] = useState<string>('');
  const [analystVoice, setAnalystVoice] = useState<string>('');
  const [summaryAudioUrl, setSummaryAudioUrl] = useState<string | null>(null);
  const [summaryAudioLoading, setSummaryAudioLoading] = useState(false);
  const [summaryAudioError, setSummaryAudioError] = useState<string | null>(null);
  const [podcastAudioUrl, setPodcastAudioUrl] = useState<string | null>(null);
  const [podcastAudioLoading, setPodcastAudioLoading] = useState(false);
  const [podcastAudioError, setPodcastAudioError] = useState<string | null>(null);
  const [podcastScript, setPodcastScript] = useState<Array<{ speaker_id: string; text: string }>>([]);

  const ttsHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = localStorage.getItem('access_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;
    return headers;
  };

  // Probe the active org's TTS provider so we know whether to show the
  // podcast button.
  useEffect(() => {
    if (!sessionId) return;
    (async () => {
      try {
        const res = await fetch(`${config.apiUrl}/api/tts/voices`, { headers: ttsHeaders() });
        if (res.ok) {
          const data = await res.json();
          setTtsProvider({ name: data.provider, supports_podcast: !!data.supports_podcast });
          const voices: Array<{ voice_id: string; label: string }> = Array.isArray(data.voices) ? data.voices : [];
          setTtsVoices(voices);
          // Pick sensible defaults: alice/frank are VibeVoice's stock host/analyst pair.
          // For other providers fall back to the first / second voice in the list.
          const ids = voices.map((v) => v.voice_id);
          const pickHost = ids.includes('alice') ? 'alice' : ids[0] || '';
          const pickAnalyst = ids.includes('frank') ? 'frank' : ids[1] || ids[0] || '';
          setSummaryVoice((prev) => prev || pickHost);
          setHostVoice((prev) => prev || pickHost);
          setAnalystVoice((prev) => prev || pickAnalyst);
        }
      } catch {
        /* non-fatal */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, activeOrganization?.slug]);

  // Lazily restore an existing podcast script on page load so the artifact is
  // visible without forcing a re-render. The audio URL is restored opportunistically;
  // 404 just means no podcast yet for this session.
  useEffect(() => {
    if (!sessionId) return;
    (async () => {
      try {
        const res = await fetch(
          `${config.apiUrl}/api/sessions/${sessionId}/tts/podcast/script`,
          { headers: ttsHeaders() },
        );
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.script) && data.script.length) {
            setPodcastScript(data.script);
            setPodcastAudioUrl(`${config.apiUrl}/api/sessions/${sessionId}/tts/podcast.mp3`);
          }
        }
      } catch {
        /* non-fatal */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, activeOrganization?.slug]);

  // Bridge a TTS job lifecycle: kicks off /tts/{kind}/start, opens
  // /ws/tts/{job_id}, returns when stage is 'done' (resolves with audio_url)
  // or 'failed' (rejects with the error).
  const trackTtsJob = (jobId: string, onProgress?: (pct: number) => void) =>
    new Promise<{ audio_url: string }>((resolve, reject) => {
      const wsScheme = config.apiUrl.startsWith('https') ? 'wss' : 'ws';
      const wsUrl = config.apiUrl.replace(/^https?/, wsScheme) + `/ws/tts/${jobId}`;
      const socket = new WebSocket(wsUrl);
      socket.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (typeof payload.progress_pct === 'number') onProgress?.(payload.progress_pct);
          if (payload.stage === 'done' && payload.audio_url) {
            socket.close();
            resolve({ audio_url: payload.audio_url });
          } else if (payload.stage === 'failed') {
            socket.close();
            reject(new Error(payload.error_message || 'TTS render failed'));
          }
        } catch {
          /* keep listening */
        }
      };
      socket.onerror = () => reject(new Error('TTS progress socket error'));
      socket.onclose = (ev) => {
        if (ev.code !== 1000 && ev.code !== 1005) {
          // close codes other than normal/no-status mean we lost the socket
          // before stage=done; surface that as a failure.
          reject(new Error(`TTS progress socket closed (${ev.code})`));
        }
      };
    });

  const synthesizeSummary = async (regenerate = false) => {
    if (!session) return;
    setSummaryAudioLoading(true);
    setSummaryAudioError(null);
    try {
      const id = session.id || sessionId;
      const voiceParam = summaryVoice ? `&voice=${encodeURIComponent(summaryVoice)}` : '';
      const startRes = await fetch(
        `${config.apiUrl}/api/sessions/${id}/tts/summary/start?format=mp3${voiceParam}`,
        { method: 'POST', headers: ttsHeaders() },
      );
      if (!startRes.ok) {
        const detail = await startRes.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${startRes.status}`);
      }
      const job = await startRes.json();
      const result = await trackTtsJob(job.job_id);
      const stamp = regenerate ? `?ts=${Date.now()}` : '';
      setSummaryAudioUrl(`${config.apiUrl}${result.audio_url}${stamp}`);
    } catch (err: any) {
      setSummaryAudioError(err?.message || 'Failed to synthesize audio.');
    } finally {
      setSummaryAudioLoading(false);
    }
  };

  const synthesizePodcast = async (regenerate = false) => {
    if (!session) return;
    setPodcastAudioLoading(true);
    setPodcastAudioError(null);
    try {
      const id = session.id || sessionId;
      const voiceParams =
        (hostVoice ? `&host_voice=${encodeURIComponent(hostVoice)}` : '') +
        (analystVoice ? `&analyst_voice=${encodeURIComponent(analystVoice)}` : '');
      const startRes = await fetch(
        `${config.apiUrl}/api/sessions/${id}/tts/podcast/start?format=mp3${voiceParams}`,
        { method: 'POST', headers: ttsHeaders() },
      );
      if (startRes.status === 501) {
        const detail = await startRes.json().catch(() => ({}));
        throw new Error(detail.detail || 'Active TTS provider does not support podcast mode.');
      }
      if (!startRes.ok) {
        const detail = await startRes.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${startRes.status}`);
      }
      const job = await startRes.json();
      const result = await trackTtsJob(job.job_id);
      const stamp = regenerate ? `?ts=${Date.now()}` : '';
      setPodcastAudioUrl(`${config.apiUrl}${result.audio_url}${stamp}`);
      // Fetch the script artifact now that synthesis succeeded.
      try {
        const scriptRes = await fetch(
          `${config.apiUrl}/api/sessions/${id}/tts/podcast/script`,
          { headers: ttsHeaders() },
        );
        if (scriptRes.ok) {
          const data = await scriptRes.json();
          setPodcastScript(data.script || []);
        }
      } catch {
        /* script fetch is non-fatal */
      }
    } catch (err: any) {
      setPodcastAudioError(err?.message || 'Failed to generate podcast.');
    } finally {
      setPodcastAudioLoading(false);
    }
  };

  useEffect(() => {
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

  // Fetch speaker_session_link rows + the org's enrolled speakers once
  // per session (and re-fetch whenever speakerVersion bumps after an
  // inline rename/assign/merge). Powers the SpeakerLabelEditor popover
  // inside each transcript turn.
  useEffect(() => {
    if (!sessionId || !session) return;
    const orgSlug = activeOrganization?.slug;
    const headers: Record<string, string> = {};
    if (orgSlug) headers['X-MeetingOps-Org'] = orgSlug;
    const sid = String(session.id || sessionId);
    (async () => {
      try {
        const [linksRes, speakersRes] = await Promise.all([
          fetch(`${config.apiBaseUrl}/api/sessions/${sid}/speaker-links`, { headers }),
          fetch(`${config.apiBaseUrl}/api/speakers`, { headers }),
        ]);
        if (linksRes.ok) {
          const linksData = await linksRes.json();
          setSpeakerLinks(
            Array.isArray(linksData)
              ? linksData.map((l: any) => ({
                  id: l.id,
                  raw_label: l.raw_label,
                  speaker_id: l.speaker_id ?? null,
                  speaker_display: l.speaker?.display_name ?? l.speaker_display ?? null,
                }))
              : [],
          );
        }
        if (speakersRes.ok) {
          const speakersData = await speakersRes.json();
          setOrgSpeakers(
            Array.isArray(speakersData)
              ? speakersData.map((s: any) => ({
                  id: s.id,
                  display_name: s.display_name,
                  has_centroid: !!s.has_centroid,
                }))
              : [],
          );
        }
      } catch {
        /* non-fatal — the editor will just show empty lists */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, session?.id, activeOrganization?.slug, speakerVersion]);

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
      const url = `${config.apiUrl}/api/simple/recording-sessions/${sessionId}`;
      
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        
        // Normalize transcription data - prefer transcription_segments, then diarized segments
        if (!data.transcription) {
          data.transcription = {};
        }

        if (data.transcription_segments && data.transcription_segments.length > 0) {
          data.transcription.segments = data.transcription_segments;
        } else if (data.transcript_diarized?.segments?.length) {
          data.transcription.segments = data.transcript_diarized.segments;
        }

        if (!data.transcription.text && data.transcript_simple) {
          data.transcription.text = data.transcript_simple;
        }
        
        setSession(data);
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

  const runReprocess = async () => {
    if (!session) return;
    setReprocessing(true);
    setReprocessError(null);
    try {
      const id = session.id || sessionId;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const token = localStorage.getItem('access_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;
      const res = await fetch(`/api/uploads/sessions/${id}/reprocess`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          transcription_options: serializeTranscriptionOptions(reprocessOpts),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(formatBackendError(detail, res.status, 'Reprocess failed'));
      }
      setShowReprocessModal(false);
      // Pipeline reruns asynchronously; the upload tray will surface progress.
      // Refresh session view so the user sees status flip back to "processing".
      await fetchSession();
    } catch (err: any) {
      setReprocessError(err?.message || 'Reprocess failed.');
    } finally {
      setReprocessing(false);
    }
  };

  const handleAudioUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !session) return;

    if (!file.type.startsWith('audio/') && !file.type.startsWith('video/')) {
      alert('Please select an audio or video file');
      return;
    }

    setUploading(true);
    try {
      // Hand off to the chunked uploads pipeline with action=attach so the
      // file binds to this session, gets transcribed/diarized/summarized via
      // ProviderRegistry, and shows progress + retry in the global upload
      // tray. Tier quotas are enforced server-side at /uploads/start.
      const targetSessionId = String(session.session_id || session.id || sessionId);
      await startUploads([file], {
        action: 'attach',
        targetSessionId,
        transcriptionOptions: serializeTranscriptionOptions(attachOpts),
      });
      setShowUploadModal(false);
      // Pipeline updates session.status / transcript asynchronously; refresh
      // here so the page reflects the queued state immediately.
      await fetchSession();
    } catch (error: any) {
      console.error('Upload failed:', error);
      alert(error?.message || 'Failed to upload audio file');
    } finally {
      setUploading(false);
      event.target.value = '';
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

  const openProjectLinkEditor = () => {
    if (!session) return;
    setProjectLinkDraft({
      project_app: session.project_app ?? null,
      project_id: session.project_id ?? null,
      project_slug: session.project_slug ?? null,
    });
    setEditingProjectLink(true);
  };

  const startEditTitle = () => {
    if (!session) return;
    setTitleDraft(session.title || session.name || "");
    setEditingTitle(true);
  };

  const saveTitle = async () => {
    if (!session) return;
    setSavingTitle(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ title: titleDraft }),
        },
      );
      if (response.ok) {
        const data = await response.json();
        setSession({
          ...session,
          title: data.title ?? titleDraft,
          name: data.title ?? titleDraft,
          title_user_set: data.title_user_set ?? true,
        });
        setEditingTitle(false);
      } else {
        const errText = await response.text();
        alert(`Failed to rename session: ${errText}`);
      }
    } catch (err) {
      console.error('Title save failed:', err);
      alert('Failed to rename session');
    } finally {
      setSavingTitle(false);
    }
  };

  const saveProjectLink = async () => {
    if (!session) return;
    setSavingProjectLink(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}/project-link`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            project_app: projectLinkDraft.project_app,
            project_id: projectLinkDraft.project_id,
            project_slug: projectLinkDraft.project_slug,
          }),
        },
      );
      if (response.ok) {
        const data = await response.json();
        setSession({
          ...session,
          project_app: data.project_app ?? null,
          project_id: data.project_id ?? null,
          project_slug: data.project_slug ?? null,
        });
        setEditingProjectLink(false);
      } else {
        const errText = await response.text();
        alert(`Failed to update project link: ${errText}`);
      }
    } catch (err) {
      console.error('Project link save failed:', err);
      alert('Failed to update project link');
    } finally {
      setSavingProjectLink(false);
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
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <button
                onClick={() => navigate('/sessions')}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors flex-shrink-0"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              
              <div className="min-w-0 flex-1">
                {editingTitle ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={titleDraft}
                      onChange={(e) => setTitleDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveTitle();
                        if (e.key === 'Escape') setEditingTitle(false);
                      }}
                      autoFocus
                      maxLength={200}
                      className="text-2xl font-bold text-gray-900 border-b-2 border-purple-500 focus:outline-none bg-transparent flex-1 min-w-[200px]"
                      placeholder="Meeting title..."
                    />
                    <button
                      onClick={saveTitle}
                      disabled={savingTitle}
                      className="p-1.5 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
                      title="Save (Enter)"
                    >
                      {savingTitle ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Check className="w-4 h-4" />
                      )}
                    </button>
                    <button
                      onClick={() => setEditingTitle(false)}
                      disabled={savingTitle}
                      className="px-2 py-1 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300"
                      title="Cancel (Esc)"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={startEditTitle}
                    className="flex items-center gap-2 text-left group"
                    title="Click to rename"
                  >
                    <h1 className="text-2xl font-bold text-gray-900 break-words leading-tight">
                      {session.title || session.name || 'Meeting Session'}
                    </h1>
                    <Edit2 className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                )}
                {!editingTitle && session.title && session.name && session.name !== session.title && (
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
                {/* Project link badge / editor */}
                <div className="mt-2">
                  {editingProjectLink ? (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 max-w-xl">
                      <div className="flex items-center gap-2 mb-2 text-sm font-medium text-gray-700">
                        <Briefcase className="w-4 h-4 text-purple-600" />
                        Edit project link
                      </div>
                      {/* Reuse the picker (dark-themed; wrap to lighten contrast on the white card) */}
                      <div className="bg-gray-900 rounded p-3">
                        <ProjectLinkPicker
                          value={projectLinkDraft}
                          onChange={setProjectLinkDraft}
                          hideLabel
                        />
                      </div>
                      <div className="flex items-center gap-2 mt-3">
                        <button
                          onClick={saveProjectLink}
                          disabled={savingProjectLink}
                          className="flex items-center gap-1 px-3 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 disabled:opacity-50"
                        >
                          {savingProjectLink ? (
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5" />
                          )}
                          Save
                        </button>
                        <button
                          onClick={() => setEditingProjectLink(false)}
                          disabled={savingProjectLink}
                          className="px-3 py-1.5 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300 disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : session.project_app && session.project_slug ? (
                    <div className="flex items-center gap-2">
                      <a
                        href={`/projects/${session.project_slug}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1 bg-purple-100 text-purple-700 hover:bg-purple-200 rounded-full text-sm font-medium transition-colors"
                        title={`Open in ${PROJECT_APP_LABELS[session.project_app] || session.project_app}`}
                      >
                        <Briefcase className="w-3.5 h-3.5" />
                        <span>{PROJECT_APP_LABELS[session.project_app] || session.project_app}</span>
                        <span className="text-purple-500">/</span>
                        <span>{session.project_slug}</span>
                      </a>
                      <button
                        onClick={openProjectLinkEditor}
                        className="p-1 text-gray-400 hover:text-gray-700 rounded"
                        title="Edit project link"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={openProjectLinkEditor}
                      className="inline-flex items-center gap-1.5 px-3 py-1 bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700 rounded-full text-xs font-medium transition-colors"
                      title="Link this meeting to a project"
                    >
                      <Briefcase className="w-3.5 h-3.5" />
                      Link to project
                    </button>
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
              {/* Share button — opens the per-meeting permissions modal where
                  you can invite individual users (internal or external) and
                  manage access levels. Default access (org-wide, project) is
                  surfaced inside the modal. */}
              <button
                onClick={() => setShowShareModal(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2 text-sm"
                title="Share this meeting with others"
              >
                <Share2 className="w-4 h-4" />
                Share
              </button>
              {/* Email button — opens the email-attendees modal where the
                  user picks named speakers + content (link / summary PDF /
                  transcript PDF) and sends via Postmark Meeting-Ops server. */}
              <button
                onClick={() => setShowEmailModal(true)}
                className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 flex items-center gap-2 text-sm"
                title="Email this meeting to attendees"
              >
                <Mail className="w-4 h-4" />
                Email
              </button>
              {/* Re-process button — re-runs transcribe/diarize/summarize against
                  the existing audio. Lets users change STT engine, speaker
                  count, summary template etc. without re-uploading. */}
              {session.audio_file && (
                <button
                  onClick={() => {
                    setReprocessOpts(DEFAULT_TRANSCRIPTION_OPTIONS);
                    setReprocessError(null);
                    setShowReprocessModal(true);
                  }}
                  disabled={reprocessing}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2 text-sm"
                  title="Re-run transcription with different options"
                >
                  <RefreshCw className="w-4 h-4" />
                  Re-process
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

                    <button
                      onClick={async () => {
                        try {
                          const token = localStorage.getItem('access_token');
                          const response = await fetch(
                            `${config.apiUrl}/api/simple/recording-sessions/${session.id}/download/summary/md`,
                            { headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) } }
                          );
                          if (!response.ok) throw new Error(`Export failed: ${response.status}`);
                          const blob = await response.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${(session.title || session.name || 'meeting').replace(/\s+/g, '_')}.md`;
                          document.body.appendChild(a);
                          a.click();
                          document.body.removeChild(a);
                          URL.revokeObjectURL(url);
                        } catch (err) {
                          console.error('Markdown export error:', err);
                          alert('Markdown export failed. Please try again.');
                        }
                      }}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                    >
                      <FileDown className="w-4 h-4 text-gray-700" />
                      Summary (Markdown)
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

            {/* Phase 3: speaker tagger — confirm/change diarized labels */}
            <SpeakerTagger sessionId={String(session.id || sessionId)} />

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
                        <div className="text-gray-700 bg-gray-50 p-4 rounded-lg session-md">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {String(session.final_summary?.executive || session.summary?.executive || session.summary?.analysis?.executive || '')}
                          </ReactMarkdown>
                        </div>
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
                        <div className="text-gray-700 bg-gray-50 p-4 rounded-lg session-md">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {String(session.final_summary.minutes)}
                          </ReactMarkdown>
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

            {/* Listen-to-summary + podcast recap (Phase 4c-2 — VibeVoice TTS) */}
            {(session.final_summary || session.summary || session.transcript_simple || session.transcript) && (
              <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Volume2 className="w-5 h-5 text-purple-600" />
                  Listen
                  {ttsProvider && (
                    <span className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded-full font-normal">
                      {ttsProvider.name}
                    </span>
                  )}
                </h2>

                <div className="space-y-3">
                  <div>
                    {ttsVoices.length > 1 && (
                      <label className="block text-xs text-gray-600 mb-1">
                        Narrator voice
                        <select
                          value={summaryVoice}
                          onChange={(e) => setSummaryVoice(e.target.value)}
                          className="ml-2 text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                          disabled={summaryAudioLoading}
                        >
                          {ttsVoices.map((v) => (
                            <option key={v.voice_id} value={v.voice_id}>{v.label}</option>
                          ))}
                        </select>
                      </label>
                    )}
                    {!summaryAudioUrl ? (
                      <button
                        type="button"
                        onClick={() => synthesizeSummary(false)}
                        disabled={summaryAudioLoading}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-500 disabled:opacity-50"
                      >
                        {summaryAudioLoading ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <Play className="w-4 h-4" />
                        )}
                        {summaryAudioLoading ? 'Synthesizing...' : 'Listen to summary'}
                      </button>
                    ) : (
                      <AudioPlayer
                        src={summaryAudioUrl}
                        downloadAs={`summary-${session.id || sessionId}.mp3`}
                        caption="AI-narrated meeting summary."
                        onRegenerate={() => synthesizeSummary(true)}
                        regenerating={summaryAudioLoading}
                      />
                    )}
                    {summaryAudioError && (
                      <div className="mt-2 text-sm text-red-600">{summaryAudioError}</div>
                    )}
                  </div>

                  {ttsProvider?.supports_podcast && (
                    <div className="pt-3 border-t border-gray-100">
                      {ttsVoices.length > 1 && (
                        <div className="mb-2 grid grid-cols-2 gap-2">
                          <label className="block text-xs text-gray-600">
                            Host voice
                            <select
                              value={hostVoice}
                              onChange={(e) => setHostVoice(e.target.value)}
                              className="mt-1 w-full text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                              disabled={podcastAudioLoading}
                            >
                              {ttsVoices.map((v) => (
                                <option key={v.voice_id} value={v.voice_id}>{v.label}</option>
                              ))}
                            </select>
                          </label>
                          <label className="block text-xs text-gray-600">
                            Analyst voice
                            <select
                              value={analystVoice}
                              onChange={(e) => setAnalystVoice(e.target.value)}
                              className="mt-1 w-full text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                              disabled={podcastAudioLoading}
                            >
                              {ttsVoices.map((v) => (
                                <option key={v.voice_id} value={v.voice_id}>{v.label}</option>
                              ))}
                            </select>
                          </label>
                        </div>
                      )}
                      {!podcastAudioUrl ? (
                        <button
                          type="button"
                          onClick={() => synthesizePodcast(false)}
                          disabled={podcastAudioLoading}
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-fuchsia-600 text-white text-sm font-medium hover:bg-fuchsia-500 disabled:opacity-50"
                        >
                          {podcastAudioLoading ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                          ) : (
                            <Sparkles className="w-4 h-4" />
                          )}
                          {podcastAudioLoading ? 'Generating podcast...' : 'Generate podcast version'}
                        </button>
                      ) : (
                        <div className="space-y-3">
                          <AudioPlayer
                            src={podcastAudioUrl}
                            downloadAs={`podcast-${session.id || sessionId}.mp3`}
                            caption="Two-host podcast recap (host + analyst)."
                            onRegenerate={() => synthesizePodcast(true)}
                            regenerating={podcastAudioLoading}
                          />
                          {podcastScript.length > 0 && (
                            <details className="text-xs text-gray-600">
                              <summary className="cursor-pointer hover:text-gray-800">
                                Podcast script ({podcastScript.length} turns)
                              </summary>
                              <div className="mt-2 space-y-2 bg-gray-50 p-3 rounded max-h-64 overflow-y-auto">
                                {podcastScript.map((turn, i) => (
                                  <div key={i}>
                                    <span className="font-semibold text-purple-700">
                                      {turn.speaker_id === 'host' ? 'Host' : 'Analyst'}:
                                    </span>{' '}
                                    {turn.text}
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}
                        </div>
                      )}
                      {podcastAudioError && (
                        <div className="mt-2 text-sm text-red-600">{podcastAudioError}</div>
                      )}
                    </div>
                  )}
                  {ttsProvider && !ttsProvider.supports_podcast && (
                    <div className="text-xs text-gray-500">
                      Switch your TTS provider to VibeVoice in{' '}
                      <a href="/settings" className="text-purple-600 hover:underline">Settings</a>{' '}
                      to enable podcast recaps.
                    </div>
                  )}
                </div>
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

            {/* Transcript — kept at the bottom of the left column so the AI
                Summary stays above the fold. Still has the full set of
                navigation tools inside: speaker timeline, filter chips,
                inline rename, click-to-seek. */}
            <div className="bg-white rounded-lg shadow-sm p-6 flex flex-col" style={{ height: 'calc(100vh - 200px)', minHeight: '480px' }}>
              <div className="flex items-center justify-between mb-4 flex-shrink-0">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <FileText className="w-5 h-5 text-purple-600" />
                  Transcript
                  {speakers.length > 0 && (
                    <span className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded-full">
                      {speakers.length} speaker{speakers.length !== 1 ? 's' : ''}
                    </span>
                  )}
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

              {/* Speaker timeline swimlane — one lane per speaker, colored
                  bars at the time-ranges where they spoke, click any bar
                  to seek the audio player. Renders only when we have a
                  duration and multiple speakers. */}
              {speakers.length > 1 && (
                <SpeakerTimeline
                  duration={session.duration || segments.reduce((m, s) => Math.max(m, s.end || 0), 0)}
                  segments={segments.map((s) => ({ start: s.start, end: s.end, speaker: s.speaker }))}
                  speakers={speakers}
                  currentTime={currentTime}
                  onSeek={(t) => {
                    if (audioRef.current) {
                      audioRef.current.currentTime = t;
                      audioRef.current.play().catch(() => undefined);
                    }
                  }}
                />
              )}

              {/* Speaker filter chips — click to filter to one speaker */}
              {speakers.length > 1 && (
                <div className="flex flex-wrap gap-2 mb-3 flex-shrink-0">
                  <button
                    onClick={() => setSelectedSpeaker('all')}
                    className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                      selectedSpeaker === 'all'
                        ? 'bg-purple-600 text-white border-purple-600'
                        : 'bg-gray-50 text-gray-600 border-gray-200 hover:border-gray-400'
                    }`}
                  >
                    All ({segments.length})
                  </button>
                  {speakers.map((sp) => {
                    const count = segments.filter((s) => s.speaker === sp).length;
                    return (
                      <button
                        key={sp}
                        onClick={() => setSelectedSpeaker(sp)}
                        className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                          selectedSpeaker === sp
                            ? 'bg-purple-600 text-white border-purple-600'
                            : 'bg-gray-50 text-gray-600 border-gray-200 hover:border-gray-400'
                        }`}
                      >
                        {sp} ({count})
                      </button>
                    );
                  })}
                </div>
              )}

              <div ref={transcriptRef} className="space-y-3 flex-1 min-h-0 overflow-y-auto pr-1">
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
                      className={`p-3 rounded-lg cursor-pointer transition-all ${
                        activeSegment === index
                          ? 'bg-purple-50 border-l-4 border-purple-600'
                          : 'hover:bg-gray-50 border-l-4 border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-3 mb-1">
                        <SpeakerLabelEditor
                          speaker={segment.speaker || 'Speaker'}
                          sessionId={String(session.id || sessionId)}
                          links={speakerLinks}
                          speakers={orgSpeakers}
                          onChanged={() => {
                            setSpeakerVersion((v) => v + 1);
                            fetchSession();
                          }}
                        />
                        <span className="text-xs text-gray-500">
                          {formatTime(segment.start)} - {formatTime(segment.end)}
                        </span>
                        {segment.confidence && (
                          <span className="text-xs text-gray-400">
                            {Math.round(segment.confidence * 100)}%
                          </span>
                        )}
                      </div>
                      <p className="text-gray-700 text-sm leading-relaxed">{segment.text}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Audio Player — sits right below the transcript so playback
                is paired with the transcript view; AudioPlayer component
                has its own volume + scrub + download controls. */}
            <div className="bg-white rounded-lg shadow-sm p-4">
              {session.audio_file ? (
                <AudioPlayer
                  src={getOrgQueryUrl(`${config.apiUrl}/api/simple/recording-sessions/${session.id || sessionId}/download/audio`)}
                  downloadAs={`${(session.title || session.name || 'meeting').replace(/\s+/g, '_')}.wav`}
                  externalAudioRef={audioRef}
                  onTimeUpdate={(t) => setCurrentTime(t)}
                />
              ) : (
                <p className="text-gray-500 text-center py-2 text-sm">No audio recording available</p>
              )}
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
                        {insights.keywords.map((topic: any, idx: number) => {
                          // Backend returns KeywordTrend objects {word, frequency, trend, category};
                          // older payloads / non-extracted runs send plain strings. Coerce either way
                          // so React never tries to render an object as a child (error #31).
                          const word = typeof topic === "string" ? topic : topic?.word ?? "";
                          if (!word) return null;
                          return (
                            <span
                              key={`${idx}-${word}`}
                              className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm"
                            >
                              {word}
                            </span>
                          );
                        })}
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

      {/* Per-meeting permissions modal */}
      <SessionPermissionsModal
        sessionId={session.id || sessionId || ''}
        isOpen={showShareModal}
        onClose={() => setShowShareModal(false)}
      />

      {/* Email-to-attendees modal */}
      <EmailAttendeesModal
        sessionId={session.id || sessionId || ''}
        isOpen={showEmailModal}
        onClose={() => setShowEmailModal(false)}
      />

      {/* Re-process modal */}
      {showReprocessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-lg rounded-lg border border-gray-700 bg-gray-950 shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <RefreshCw className="h-4 w-4 text-purple-400" />
                <h3 className="text-base font-semibold text-white">Re-process this recording</h3>
              </div>
              <button
                onClick={() => setShowReprocessModal(false)}
                className="rounded p-1 text-gray-400 hover:bg-gray-800 hover:text-white"
              >
                <Check className="hidden" />
                ✕
              </button>
            </div>
            <div className="space-y-4 px-5 py-4 text-sm text-gray-300">
              <p className="text-xs text-gray-400">
                Re-runs transcription, diarization, summarization, and embedding
                against the existing audio file. Override any options below; the
                rest fall back to your org's default Provider Settings.
              </p>
              <TranscriptionOptionsPanel
                value={reprocessOpts}
                onChange={setReprocessOpts}
                defaultOpen={true}
              />
              {reprocessError && (
                <p className="rounded border border-red-700 bg-red-900/30 px-3 py-2 text-xs text-red-300">
                  {reprocessError}
                </p>
              )}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-gray-800 px-5 py-3">
              <button
                onClick={() => setShowReprocessModal(false)}
                disabled={reprocessing}
                className="rounded px-3 py-2 text-sm text-gray-400 hover:bg-gray-800 hover:text-white disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={runReprocess}
                disabled={reprocessing}
                className="inline-flex items-center gap-2 rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
              >
                {reprocessing ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Queuing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4" />
                    Queue re-process
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
