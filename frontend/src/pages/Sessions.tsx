import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Plus, Search, Filter, Calendar, Mic, Clock, Users,
  FileText, Download, Trash2, Play, Eye, Tag,
  ChevronDown, ChevronUp, Grid, List, SortAsc, SortDesc,
  Upload, FolderOpen, Star, Archive, MessageSquare, X, Loader2,
  ArrowUp, ArrowDown, ArrowUpDown
} from 'lucide-react';
import { SessionCreator } from '../components/SessionCreator';
import { MeetingIntelligenceDashboard } from '../components/MeetingIntelligenceDashboard';
import { config } from '../config';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  TranscriptionOptionsPanel,
  DEFAULT_TRANSCRIPTION_OPTIONS,
  serializeTranscriptionOptions,
  type TranscriptionOptions,
} from '../components/TranscriptionOptionsPanel';
import { useUploads } from '../contexts/UploadsContext';
import { useOrg } from '../contexts/OrgContext';
import { TagChip } from '../components/TagChip';
import MobileSessionsList from '../components/MobileSessionsList';

interface Participant {
  id: string;
  name: string;
  email?: string | null;
  role?: string | null;
}

interface Session {
  id: string;
  name: string;
  title?: string;              // AI-generated title
  description?: string;
  created_at: string;
  updated_at: string;
  duration?: number;
  status: 'idle' | 'active' | 'recording' | 'completed' | 'processing' | 'failed';
  participants?: Participant[];
  tags?: string[];
  audio_file?: string;
  transcript?: string;
  summary?: any;               // AI-generated summary
  summary_preview?: string;    // Plain-text snippet for list views
  speaker_count?: number;      // Distinct speakers, server-computed
  has_transcript: boolean;
  has_audio: boolean;
  session_type?: 'live' | 'upload';
}

interface RagMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: {session_id: string; title: string; score: number}[];
  rewrittenQuery?: string | null;
}

type SortKey = 'date' | 'name' | 'duration' | 'speakers' | 'status';

const VIEW_MODE_KEY = 'meetingops.sessionsViewMode.v1';
const VALID_SORT_KEYS: ReadonlyArray<SortKey> = ['date', 'name', 'duration', 'speakers', 'status'];

function deriveSpeakerCount(session: Session): number {
  if (typeof session.speaker_count === 'number' && session.speaker_count > 0) {
    return session.speaker_count;
  }
  const segs = (session as any)?.transcription?.segments;
  if (!Array.isArray(segs) || segs.length === 0) return 0;
  const set = new Set<string>();
  for (const s of segs) {
    if (s && s.speaker) set.add(s.speaker);
  }
  return set.size;
}

function truncate(text: string, max: number): string {
  if (!text) return '';
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + '…';
}

interface SessionsTableProps {
  sessions: Session[];
  sortBy: SortKey;
  sortOrder: 'asc' | 'desc';
  onHeaderSort: (key: SortKey) => void;
  statusFilter: string[];
  speakerFilter: string[];
  onStatusFilterChange: (values: string[]) => void;
  onSpeakerFilterChange: (values: string[]) => void;
  openColumnFilter: null | 'status' | 'speakers';
  onOpenColumnFilter: (col: null | 'status' | 'speakers') => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  formatDuration: (seconds?: number) => string;
  getStatusColor: (status: string) => string;
  getStatusLabel: (status: string) => string;
}

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'completed', label: 'Completed' },
  { value: 'processing', label: 'Processing' },
  { value: 'active', label: 'Recording' },
  { value: 'idle', label: 'Idle' },
  { value: 'failed', label: 'Failed' },
];

const SPEAKER_BUCKETS: Array<{ value: string; label: string; test: (n: number) => boolean }> = [
  { value: '0', label: 'No speakers', test: (n) => n === 0 },
  { value: '1', label: '1 speaker', test: (n) => n === 1 },
  { value: '2-3', label: '2–3 speakers', test: (n) => n >= 2 && n <= 3 },
  { value: '4+', label: '4 or more', test: (n) => n >= 4 },
];

const SessionsTable: React.FC<SessionsTableProps> = ({
  sessions,
  sortBy,
  sortOrder,
  onHeaderSort,
  statusFilter,
  speakerFilter,
  onStatusFilterChange,
  onSpeakerFilterChange,
  openColumnFilter,
  onOpenColumnFilter,
  onOpen,
  onDelete,
  formatDuration,
  getStatusColor,
  getStatusLabel,
}) => {
  const filtered = useMemo(() => {
    return sessions.filter((s) => {
      if (statusFilter.length > 0 && !statusFilter.includes(s.status)) return false;
      if (speakerFilter.length > 0) {
        const n = deriveSpeakerCount(s);
        const ok = speakerFilter.some((v) => {
          const b = SPEAKER_BUCKETS.find((x) => x.value === v);
          return b ? b.test(n) : false;
        });
        if (!ok) return false;
      }
      return true;
    });
  }, [sessions, statusFilter, speakerFilter]);

  const renderSortIcon = (key: SortKey) => {
    if (sortBy !== key) {
      return <ArrowUpDown className="w-3.5 h-3.5 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />;
    }
    return sortOrder === 'asc'
      ? <ArrowUp className="w-3.5 h-3.5 text-purple-300" />
      : <ArrowDown className="w-3.5 h-3.5 text-purple-300" />;
  };

  const headerBtn = (key: SortKey, label: string, extra?: string) => (
    <button
      type="button"
      onClick={() => onHeaderSort(key)}
      className={`group inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-300 hover:text-white transition-colors ${extra || ''}`}
      aria-sort={sortBy === key ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <span>{label}</span>
      {renderSortIcon(key)}
    </button>
  );

  const toggleMulti = (current: string[], v: string, setter: (vals: string[]) => void) => {
    if (current.includes(v)) setter(current.filter((x) => x !== v));
    else setter([...current, v]);
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="max-h-[calc(100vh-260px)] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-gray-900/95 backdrop-blur">
            <tr className="border-b border-gray-800">
              <th className="px-4 py-3 text-left">{headerBtn('name', 'Title')}</th>
              <th className="px-4 py-3 text-left whitespace-nowrap">{headerBtn('date', 'Date')}</th>
              <th className="px-4 py-3 text-left whitespace-nowrap">{headerBtn('duration', 'Duration')}</th>
              <th className="px-4 py-3 text-left whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {headerBtn('speakers', 'Speakers')}
                  <div className="relative" data-column-filter>
                    <button
                      type="button"
                      onClick={() => onOpenColumnFilter(openColumnFilter === 'speakers' ? null : 'speakers')}
                      className={`p-1 rounded hover:bg-gray-800 transition-colors ${speakerFilter.length > 0 ? 'text-purple-300' : 'text-gray-500 hover:text-gray-300'}`}
                      aria-label="Filter by speakers"
                      aria-expanded={openColumnFilter === 'speakers'}
                    >
                      <Filter className="w-3.5 h-3.5" />
                      {speakerFilter.length > 0 && (
                        <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-purple-500" />
                      )}
                    </button>
                    {openColumnFilter === 'speakers' && (
                      <div className="absolute left-0 top-7 w-44 rounded-lg border border-gray-700 bg-gray-900 shadow-xl p-2 z-20" data-column-filter>
                        {SPEAKER_BUCKETS.map((b) => {
                          const checked = speakerFilter.includes(b.value);
                          return (
                            <label key={b.value} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-800 cursor-pointer text-xs text-gray-200">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleMulti(speakerFilter, b.value, onSpeakerFilterChange)}
                                className="accent-purple-500"
                              />
                              {b.label}
                            </label>
                          );
                        })}
                        {speakerFilter.length > 0 && (
                          <button
                            type="button"
                            onClick={() => onSpeakerFilterChange([])}
                            className="mt-1 w-full text-xs text-gray-400 hover:text-white px-2 py-1 border-t border-gray-800"
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </th>
              <th className="px-4 py-3 text-left whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-gray-300">Participants</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-300">Tags</th>
              <th className="px-4 py-3 text-left whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {headerBtn('status', 'Status')}
                  <div className="relative" data-column-filter>
                    <button
                      type="button"
                      onClick={() => onOpenColumnFilter(openColumnFilter === 'status' ? null : 'status')}
                      className={`p-1 rounded hover:bg-gray-800 transition-colors ${statusFilter.length > 0 ? 'text-purple-300' : 'text-gray-500 hover:text-gray-300'}`}
                      aria-label="Filter by status"
                      aria-expanded={openColumnFilter === 'status'}
                    >
                      <Filter className="w-3.5 h-3.5" />
                      {statusFilter.length > 0 && (
                        <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-purple-500" />
                      )}
                    </button>
                    {openColumnFilter === 'status' && (
                      <div className="absolute right-0 top-7 w-44 rounded-lg border border-gray-700 bg-gray-900 shadow-xl p-2 z-20" data-column-filter>
                        {STATUS_OPTIONS.map((opt) => {
                          const checked = statusFilter.includes(opt.value);
                          return (
                            <label key={opt.value} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-800 cursor-pointer text-xs text-gray-200">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleMulti(statusFilter, opt.value, onStatusFilterChange)}
                                className="accent-purple-500"
                              />
                              {opt.label}
                            </label>
                          );
                        })}
                        {statusFilter.length > 0 && (
                          <button
                            type="button"
                            onClick={() => onStatusFilterChange([])}
                            className="mt-1 w-full text-xs text-gray-400 hover:text-white px-2 py-1 border-t border-gray-800"
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </th>
              <th className="px-4 py-3 text-right whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-gray-300">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-gray-500 text-sm">
                  No sessions match the current filters.
                </td>
              </tr>
            ) : (
              filtered.map((session) => {
                const fullTitle = session.title || session.name || 'Untitled';
                const truncated = truncate(fullTitle, 60);
                const speakerCount = deriveSpeakerCount(session);
                const participants = session.participants || [];
                const tags = session.tags || [];
                const visibleTags = [...tags].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())).slice(0, 3);
                const hiddenTagCount = tags.length - visibleTags.length;
                return (
                  <tr
                    key={session.id}
                    className="border-b border-gray-800/60 hover:bg-gray-800/40 transition-colors"
                  >
                    <td className="px-4 py-3 align-middle">
                      <button
                        type="button"
                        onClick={() => onOpen(session.id)}
                        title={fullTitle}
                        className="block text-left font-medium text-white hover:text-purple-300 transition-colors max-w-[44ch] truncate"
                      >
                        {truncated}
                      </button>
                      {session.summary_preview && (
                        <div
                          className="mt-1 text-xs text-gray-400 max-w-[44ch] line-clamp-2"
                          title={session.summary_preview}
                        >
                          {session.summary_preview}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 align-middle whitespace-nowrap text-gray-300">
                      {session.created_at ? new Date(session.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3 align-middle whitespace-nowrap text-gray-300 tabular-nums">
                      {formatDuration(session.duration)}
                    </td>
                    <td className="px-4 py-3 align-middle whitespace-nowrap text-gray-300 tabular-nums">
                      {speakerCount > 0 ? speakerCount : <span className="text-gray-600">—</span>}
                    </td>
                    <td className="px-4 py-3 align-middle text-gray-300">
                      {participants.length > 0 ? (
                        <span
                          className="inline-block max-w-[28ch] truncate align-middle"
                          title={participants.map((p) => p.name).join(', ')}
                        >
                          {participants.slice(0, 2).map((p) => p.name).join(', ')}
                          {participants.length > 2 && ` +${participants.length - 2}`}
                        </span>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 align-middle">
                      {visibleTags.length > 0 ? (
                        <div className="flex flex-wrap gap-1 max-w-[32ch]">
                          {visibleTags.map((tag) => (
                            <TagChip key={tag} tag={tag} />
                          ))}
                          {hiddenTagCount > 0 && (
                            <span
                              className="px-2 py-0.5 text-xs rounded-full border border-gray-700 bg-gray-800 text-gray-400"
                              title={tags.slice(visibleTags.length).join(', ')}
                            >
                              +{hiddenTagCount}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 align-middle whitespace-nowrap">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${getStatusColor(session.status)}`}>
                        {getStatusLabel(session.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-middle text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => onOpen(session.id)}
                          className="p-2 rounded-md text-gray-300 hover:text-white hover:bg-purple-600/30 transition-colors"
                          title="Open session"
                          aria-label="Open session"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onDelete(session.id)}
                          className="p-2 rounded-md text-red-400 hover:text-red-300 hover:bg-red-600/20 transition-colors"
                          title="Delete session"
                          aria-label="Delete session"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 border-t border-gray-800 text-xs text-gray-500 flex items-center justify-between">
        <span>
          {filtered.length} {filtered.length === 1 ? 'session' : 'sessions'}
          {(statusFilter.length > 0 || speakerFilter.length > 0) && (
            <span className="text-gray-600"> (filtered from {sessions.length})</span>
          )}
        </span>
        {(statusFilter.length > 0 || speakerFilter.length > 0) && (
          <button
            type="button"
            onClick={() => {
              onStatusFilterChange([]);
              onSpeakerFilterChange([]);
            }}
            className="text-gray-400 hover:text-white"
          >
            Clear column filters
          </button>
        )}
      </div>
    </div>
  );
};

export const Sessions: React.FC = () => {
  const navigate = useNavigate();
  const { startUploads } = useUploads();
  const { activeOrganization } = useOrg();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [filteredSessions, setFilteredSessions] = useState<Session[]>([]);
  // Active tag filter chips (AND). Server applies the filter via ?tags=
  // so the UI never has to reason about which sessions to hide locally.
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  // All tags used across the org's sessions; powers the filter chip bar.
  const [orgTags, setOrgTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showCreator, setShowCreator] = useState(false);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  // viewMode persists to localStorage; mobile shell ignores it (always card list).
  const [viewMode, setViewMode] = useState<'grid' | 'list'>(() => {
    try {
      const stored = localStorage.getItem(VIEW_MODE_KEY);
      return stored === 'list' ? 'list' : 'grid';
    } catch {
      return 'grid';
    }
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  // Sort state hydrates from URL ?sort=&order= so refresh keeps the
  // user's column choice. Falls back to date-desc if missing/invalid.
  const initialSort: SortKey = (() => {
    const s = searchParams.get('sort');
    return s && (VALID_SORT_KEYS as ReadonlyArray<string>).includes(s) ? (s as SortKey) : 'date';
  })();
  const initialOrder: 'asc' | 'desc' = searchParams.get('order') === 'asc' ? 'asc' : 'desc';
  const [sortBy, setSortByState] = useState<SortKey>(initialSort);
  const [sortOrder, setSortOrderState] = useState<'asc' | 'desc'>(initialOrder);
  // Table-only column filters (multi-select).
  const [tableStatusFilter, setTableStatusFilter] = useState<string[]>([]);
  const [tableSpeakerFilter, setTableSpeakerFilter] = useState<string[]>([]);
  const [openColumnFilter, setOpenColumnFilter] = useState<null | 'status' | 'speakers'>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [searchResults, setSearchResults] = useState<Session[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_MODE_KEY, viewMode);
    } catch { /* non-fatal */ }
  }, [viewMode]);

  // Keep URL params in sync when sort changes. Replace=true so back-button
  // doesn't fill up with every header click.
  const setSort = useCallback((key: SortKey, order: 'asc' | 'desc') => {
    setSortByState(key);
    setSortOrderState(order);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('sort', key);
      next.set('order', order);
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const handleHeaderSort = useCallback((key: SortKey) => {
    if (sortBy === key) {
      setSort(key, sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      // First click on a new column → sensible default: text asc, numbers desc.
      const defaultOrder: 'asc' | 'desc' = (key === 'name' || key === 'status') ? 'asc' : 'desc';
      setSort(key, defaultOrder);
    }
  }, [sortBy, sortOrder, setSort]);

  // Close column-filter popovers on outside click.
  useEffect(() => {
    if (!openColumnFilter) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t && t.closest('[data-column-filter]')) return;
      setOpenColumnFilter(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [openColumnFilter]);

  // Cross-meeting RAG chat state (multi-turn)
  const [ragMessages, setRagMessages] = useState<RagMessage[]>([]);
  const [ragLoading, setRagLoading] = useState(false);
  const [showRagPanel, setShowRagPanel] = useState(false);
  const [ragFollowUp, setRagFollowUp] = useState('');
  const ragEndRef = useRef<HTMLDivElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  // Debounced server-side search (keyword + semantic)
  const performSearch = useCallback(async (query: string) => {
    if (!query || query.length < 2) {
      setSearchResults(null);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    try {
      const headers: Record<string, string> = {};
      const token = localStorage.getItem('access_token');
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // Run keyword search and semantic search in parallel
      const [keywordRes, semanticRes] = await Promise.allSettled([
        fetch(
          `${config.apiBaseUrl}/api/simple/recording-sessions/search?q=${encodeURIComponent(query)}`,
          { headers }
        ),
        fetch(
          `${config.apiBaseUrl}/api/simple/recording-sessions/semantic-search?q=${encodeURIComponent(query)}&limit=10`,
          { headers }
        ),
      ]);

      const seenIds = new Set<string>();
      const merged: Session[] = [];

      // Process keyword results first (exact matches)
      if (keywordRes.status === 'fulfilled' && keywordRes.value.ok) {
        const data = await keywordRes.value.json();
        for (const r of data) {
          if (!seenIds.has(r.id)) {
            seenIds.add(r.id);
            merged.push({
              id: r.id,
              name: r.name,
              description: r.description || '',
              created_at: r.created_at,
              updated_at: r.created_at,
              status: r.status || 'completed',
              duration: r.duration || 0,
              has_transcript: r.match_field === 'transcript',
              has_audio: !!(r.duration && r.duration > 0),
              _snippet: r.snippet,
              _matchField: r.match_field,
            } as Session);
          }
        }
      }

      // Append semantic results that weren't in keyword results
      if (semanticRes.status === 'fulfilled' && semanticRes.value.ok) {
        const data = await semanticRes.value.json();
        for (const r of (data.results || [])) {
          if (!seenIds.has(r.session_id) && r.score > 0.3) {
            seenIds.add(r.session_id);
            merged.push({
              id: r.session_id,
              name: r.title || 'Untitled',
              description: r.snippet || '',
              created_at: r.created_at || '',
              updated_at: r.created_at || '',
              status: 'completed',
              duration: 0,
              has_transcript: true,
              has_audio: false,
              _snippet: r.snippet,
              _matchField: `semantic (${Math.round(r.score * 100)}% match)`,
            } as Session);
          }
        }
      }

      setSearchResults(merged);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setIsSearching(false);
    }
  }, []);

  // Handle search input with debounce
  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchQuery(value);
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    searchTimerRef.current = setTimeout(() => {
      performSearch(value);
    }, 300);
  }, [performSearch]);

  // Cross-meeting RAG query (multi-turn)
  const sendRagMessage = useCallback(async (message: string) => {
    if (!message || message.length < 2) return;
    setRagLoading(true);
    setShowRagPanel(true);
    // Add user message to conversation
    setRagMessages(prev => [...prev, { role: 'user', content: message }]);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${config.apiBaseUrl}/api/ai-chat/rag/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message, limit: 5 }),
      });
      if (res.ok) {
        const data = await res.json();
        setRagMessages(prev => [...prev, {
          role: 'assistant',
          content: data.answer || 'No answer generated.',
          sources: data.sources || [],
          rewrittenQuery: data.metadata?.rewritten_query || null,
        }]);
      } else {
        const errText = await res.text();
        setRagMessages(prev => [...prev, {
          role: 'assistant',
          content: `Error: ${res.status} - ${errText}`,
        }]);
      }
    } catch (err) {
      console.error('RAG query failed:', err);
      setRagMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Failed to reach the AI service. Is the backend running?',
      }]);
    } finally {
      setRagLoading(false);
      setRagFollowUp('');
      setTimeout(() => ragEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, []);

  // Initial RAG query from search bar
  const askAiAboutMeetings = useCallback(async () => {
    if (!searchQuery || searchQuery.length < 2) return;
    // Clear previous conversation when starting a new topic from search
    setRagMessages([]);
    // Also clear server-side history for a fresh start
    try {
      const token = localStorage.getItem('access_token');
      await fetch(`${config.apiBaseUrl}/api/ai-chat/rag/history`, {
        method: 'DELETE',
        headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
      });
    } catch { /* ignore */ }
    sendRagMessage(searchQuery);
  }, [searchQuery, sendRagMessage]);

  // Handle follow-up submit
  const handleRagFollowUp = useCallback(() => {
    if (!ragFollowUp.trim() || ragLoading) return;
    sendRagMessage(ragFollowUp.trim());
  }, [ragFollowUp, ragLoading, sendRagMessage]);

  // Load persisted RAG chat history from server on mount
  useEffect(() => {
    const loadRagHistory = async () => {
      try {
        const token = localStorage.getItem('access_token');
        const res = await fetch(`${config.apiBaseUrl}/api/ai-chat/rag/history`, {
          headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        });
        if (res.ok) {
          const data = await res.json();
          // Validate that we got actual chat messages (not other data)
          if (Array.isArray(data) && data.length > 0 && data[0].role && data[0].content) {
            const restored: RagMessage[] = data.map((msg: any) => ({
              role: msg.role as 'user' | 'assistant',
              content: msg.content,
            }));
            setRagMessages(restored);
            setShowRagPanel(true);
          }
        }
      } catch {
        // Ignore - history loading is best-effort
      }
    };
    loadRagHistory();
  }, []);

  useEffect(() => {
    const loadOrgTags = async () => {
      try {
        const headers: any = {};
        const token = localStorage.getItem('access_token');
        if (token) headers['Authorization'] = `Bearer ${token}`;
        if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;
        const res = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/tags`, { headers });
        if (!res.ok) return;
        const data = await res.json();
        if (Array.isArray(data?.tags)) setOrgTags(data.tags);
      } catch { /* non-fatal */ }
    };
    loadOrgTags();
  }, [activeOrganization?.slug, sessions]);

  useEffect(() => {
    fetchSessions({ showSpinner: true });
    const interval = setInterval(() => fetchSessions({ showSpinner: false }), 10000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTags.join(','), activeOrganization?.slug]);

  useEffect(() => {
    filterSessions();
  }, [sessions, searchQuery, searchResults, statusFilter, typeFilter, sortBy, sortOrder]);

  // showSpinner=false on polling refresh so the list doesn't flash
  // through the empty-loading state every 10 seconds. Initial mount + filter
  // changes still show the spinner. Background ticks set `refreshing` so the
  // mobile shell can show a subtle "refreshing" indicator without ripping
  // the list out from under the user.
  const fetchSessions = async ({ showSpinner = true }: { showSpinner?: boolean } = {}) => {
    if (showSpinner) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    try {
      const headers: any = {};
      const token = localStorage.getItem('access_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;

      const tagsParam = selectedTags.length > 0 ? `?tags=${selectedTags.map(encodeURIComponent).join(',')}` : '';
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions${tagsParam}`, {
        headers
      });

      if (response.ok) {
        const data = await response.json();
        setSessions(data);
      } else {
        console.error('Failed to fetch sessions:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      if (showSpinner) {
        setLoading(false);
      } else {
        setRefreshing(false);
      }
    }
  };

  const filterSessions = () => {
    console.log('Filtering sessions. Total sessions:', sessions.length);
    
    // Use server-side search results when a search query is active
    let filtered = (searchQuery && searchQuery.length >= 2 && searchResults !== null)
      ? [...searchResults]
      : [...sessions];

    // Client-side name/title filter for short queries (< 2 chars)
    if (searchQuery && searchQuery.length < 2) {
      filtered = filtered.filter(session =>
        session.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.description?.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(session => session.status === statusFilter);
    }

    // Type filter
    if (typeFilter !== 'all') {
      filtered = filtered.filter(session => session.session_type === typeFilter);
    }

    // Sort
    console.log('📊 After filtering:', filtered.length, 'sessions remain');
    filtered.sort((a, b) => {
      let aValue: any, bValue: any;

      switch (sortBy) {
        case 'name':
          aValue = (a.title || a.name || '').toLowerCase();
          bValue = (b.title || b.name || '').toLowerCase();
          break;
        case 'duration':
          aValue = a.duration || 0;
          bValue = b.duration || 0;
          break;
        case 'speakers':
          aValue = deriveSpeakerCount(a);
          bValue = deriveSpeakerCount(b);
          break;
        case 'status':
          aValue = (a.status || '').toLowerCase();
          bValue = (b.status || '').toLowerCase();
          break;
        case 'date':
        default:
          aValue = new Date(a.created_at).getTime();
          bValue = new Date(b.created_at).getTime();
          break;
      }

      if (sortOrder === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });

    setFilteredSessions(filtered);
  };

  const handleSessionCreated = (sessionId: string) => {
    setShowCreator(false);
    fetchSessions();
    // Navigate to the new session
    navigate(`/sessions/${sessionId}`);
  };

  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadOptions, setUploadOptions] = useState<TranscriptionOptions>(
    DEFAULT_TRANSCRIPTION_OPTIONS,
  );
  // When true, the *next* file picked via the file input opens the
  // options modal instead of auto-starting. The big upload tile leaves
  // this false (fastest path); the smaller "with options" link flips
  // it true just before invoking the picker.
  const [pickerWithOptions, setPickerWithOptions] = useState(false);

  const handleUploadPicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (files.length === 0) return;
    if (pickerWithOptions) {
      // Explicit "with options" path: route through the modal so the
      // user can pick STT engine, diarization sensitivity, summary
      // template, etc. before the run begins.
      setPickerWithOptions(false);
      setPendingFiles(files);
      setUploadOptions(DEFAULT_TRANSCRIPTION_OPTIONS);
      return;
    }
    // Default fast path: kick off processing with the org defaults.
    // Matches drag-and-drop behaviour for consistency. The Re-process
    // button on SessionDetails covers tweaking options after the fact.
    void startUploads(files, { action: 'transcribe' });
  };

  const confirmUpload = () => {
    if (pendingFiles.length === 0) return;
    const opts = serializeTranscriptionOptions(uploadOptions);
    void startUploads(pendingFiles, {
      action: 'transcribe',
      ...(opts ? { transcriptionOptions: opts } : {}),
    });
    setPendingFiles([]);
  };

  const cancelUpload = () => {
    setPendingFiles([]);
  };



  const deleteSession = async (sessionId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) return;

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        fetchSessions();
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
      alert('Failed to delete session');
    }
  };

  const downloadTranscript = async (session: Session) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}/transcript`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const blob = new Blob([data.transcript || 'No transcript available'], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${session.name}_transcript.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download transcript:', error);
    }
  };

  const downloadAudio = async (session: Session) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/simple/recording-sessions/${session.id}/audio`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${session.name}_audio.wav`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download audio:', error);
    }
  };

  const downloadSummary = (session: Session) => {
    if (!session.summary) {
      alert('No summary available for download');
      return;
    }
    
    let content = `MEETING SUMMARY\n`;
    content += `===============\n\n`;
    content += `Meeting: ${session.title || session.name}\n`;
    content += `Date: ${new Date(session.created_at).toLocaleDateString()}\n`;
    content += `Duration: ${session.duration ? formatDuration(session.duration) : 'N/A'}\n\n`;
    
    if (session.summary.analysis?.executive) {
      content += `EXECUTIVE SUMMARY\n`;
      content += `-----------------\n`;
      content += `${session.summary.analysis.executive}\n\n`;
    }
    
    if (session.summary.analysis?.bullets && session.summary.analysis.bullets.length > 0) {
      content += `KEY DISCUSSION POINTS\n`;
      content += `---------------------\n`;
      session.summary.analysis.bullets.forEach((bullet: string) => {
        content += `• ${bullet}\n`;
      });
      content += '\n';
    }
    
    if (session.summary.analysis?.decisions && session.summary.analysis.decisions.length > 0) {
      content += `IMPORTANT DECISIONS\n`;
      content += `-------------------\n`;
      session.summary.analysis.decisions.forEach((decision: string) => {
        content += `✓ ${decision}\n`;
      });
      content += '\n';
    }
    
    if (session.summary.analysis?.actions && session.summary.analysis.actions.length > 0) {
      content += `ACTION ITEMS\n`;
      content += `------------\n`;
      session.summary.analysis.actions.forEach((action: any) => {
        content += `□ ${action.action}\n`;
        if (action.owner) content += `  Owner: ${action.owner}\n`;
        if (action.priority) content += `  Priority: ${action.priority}\n`;
        content += '\n';
      });
    }
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${(session.title || session.name).replace(/\s+/g, '_')}_summary.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
      case 'recording': return 'text-red-400 bg-red-500/10 border-red-500';
      case 'completed': return 'text-green-400 bg-green-500/10 border-green-500';
      case 'processing': return 'text-yellow-400 bg-yellow-500/10 border-yellow-500';
      case 'failed': return 'text-red-400 bg-red-500/10 border-red-500/50';
      default: return 'text-gray-400 bg-gray-500/10 border-gray-500';
    }
  };

  const getStatusLabel = (status: string) => {
    if (status === 'active') return 'Recording';
    if (status === 'failed') return 'Failed';
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (selectedSession) {
    const meetingData = {
      transcript: selectedSession.transcript || '',
      notes: null,
      sessionId: selectedSession.id,
      duration: selectedSession.duration || 0,
      participants: (selectedSession.participants || []).map((p) => p.name),
      topics: []
    };

    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <div className="p-6">
          <button
            onClick={() => setSelectedSession(null)}
            className="mb-6 flex items-center gap-2 text-purple-400 hover:text-purple-300"
          >
            ← Back to Sessions
          </button>
          
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white">{selectedSession.name}</h1>
            <p className="text-gray-400">{selectedSession.description}</p>
          </div>

          <MeetingIntelligenceDashboard
            meetingData={meetingData}
            isRecording={selectedSession.status === 'recording' || selectedSession.status === 'active'}
            className="w-full"
          />
        </div>
      </div>
    );
  }

  return (
    <>
      <MobileSessionsList
        sessions={filteredSessions as any}
        loading={loading}
        refreshing={refreshing || isSearching}
        searchQuery={searchQuery}
        onSearchChange={(value) => {
          setSearchQuery(value);
          if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
          searchTimerRef.current = setTimeout(() => {
            performSearch(value);
          }, 300);
        }}
        orgTags={orgTags}
        selectedTags={selectedTags}
        onToggleTag={(tag) => {
          setSelectedTags((prev) =>
            prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
          );
        }}
        onClearTags={() => setSelectedTags([])}
      />
      <div className="hidden md:block min-h-screen bg-gray-950 text-white">
      {showCreator && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
          <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <SessionCreator
              onClose={() => setShowCreator(false)}
              onSessionCreated={handleSessionCreated}
            />
          </div>
        </div>
      )}

      <div className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white">Sessions</h1>
            <p className="text-gray-400 mt-1">Manage your meeting recordings and transcriptions</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => uploadInputRef.current?.click()}
              className="flex items-center gap-2 rounded-lg bg-cyan-600 px-5 py-3 text-white transition-colors hover:bg-cyan-500"
            >
              <Upload className="w-5 h-5" />
              Upload Audio/Video
            </button>
            <button
              onClick={() => setShowCreator(true)}
              className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
            >
              <Plus className="w-5 h-5" />
              New Session
            </button>
          </div>
          <input
            ref={uploadInputRef}
            type="file"
            multiple
            accept="audio/*,video/*,.mp3,.wav,.m4a,.ogg,.flac,.opus,.aac,.mp4,.mov,.mkv,.webm,.avi"
            onChange={handleUploadPicked}
            className="hidden"
          />
        </div>

        {/* Controls */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 mb-6">
          <div className="flex items-center gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search sessions (keyword + semantic)..."
                value={searchQuery}
                onChange={handleSearchChange}
                className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-purple-500"
              />
            </div>

            {/* Ask AI - Cross-meeting RAG */}
            {searchQuery && searchQuery.length >= 2 && (
              <button
                onClick={askAiAboutMeetings}
                disabled={ragLoading}
                className="flex items-center gap-2 px-4 py-2 bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50 text-white rounded-lg transition-colors whitespace-nowrap"
                title="Ask AI about all meetings"
              >
                {ragLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <MessageSquare className="w-4 h-4" />
                )}
                Ask AI
              </button>
            )}

            {/* View Mode Toggle */}
            <div className="flex items-center bg-gray-800 rounded-lg">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 rounded-l-lg ${viewMode === 'grid' ? 'bg-purple-600 text-white' : 'text-gray-400'}`}
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded-r-lg ${viewMode === 'list' ? 'bg-purple-600 text-white' : 'text-gray-400'}`}
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            {/* Filters */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
            >
              <Filter className="w-4 h-4" />
              Filters
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {/* Extended Filters */}
          {showFilters && (
            <div className="mt-4 pt-4 border-t border-gray-800">
              <div className="grid grid-cols-4 gap-4">
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="all">All Status</option>
                  <option value="idle">Idle</option>
                  <option value="active">Recording</option>
                  <option value="processing">Processing</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                </select>

                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="all">All Types</option>
                  <option value="live">Live Recording</option>
                  <option value="upload">Uploaded Audio</option>
                </select>

                <select
                  value={sortBy}
                  onChange={(e) => setSort(e.target.value as SortKey, sortOrder)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="date">Sort by Date</option>
                  <option value="name">Sort by Name</option>
                  <option value="duration">Sort by Duration</option>
                  <option value="speakers">Sort by Speakers</option>
                  <option value="status">Sort by Status</option>
                </select>

                <button
                  onClick={() => setSort(sortBy, sortOrder === 'asc' ? 'desc' : 'asc')}
                  className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-white transition-colors"
                >
                  {sortOrder === 'asc' ? <SortAsc className="w-4 h-4" /> : <SortDesc className="w-4 h-4" />}
                  {sortOrder === 'asc' ? 'Ascending' : 'Descending'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Tag filter chip palette — multi-select AND. */}
        {orgTags.length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 mb-6 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 uppercase tracking-wide mr-1">Tags:</span>
            {orgTags.map((tag) => {
              const selected = selectedTags.includes(tag);
              return (
                <TagChip
                  key={tag}
                  tag={tag}
                  variant="filter"
                  selected={selected}
                  onClick={() => {
                    setSelectedTags((prev) =>
                      selected ? prev.filter((t) => t !== tag) : [...prev, tag]
                    );
                  }}
                />
              );
            })}
            {selectedTags.length > 0 && (
              <button
                onClick={() => setSelectedTags([])}
                className="ml-2 text-xs text-gray-400 hover:text-white underline-offset-2 hover:underline"
              >
                Clear ({selectedTags.length})
              </button>
            )}
          </div>
        )}

        {/* RAG Chat Panel (multi-turn) */}
        {showRagPanel && (
          <div className="bg-gray-900 rounded-lg border border-fuchsia-800/50 p-4 mb-6">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-fuchsia-400" />
                <h3 className="text-lg font-semibold text-fuchsia-300">AI Chat</h3>
                <span className="text-xs text-gray-500">across all meetings</span>
              </div>
              <div className="flex items-center gap-2">
                {ragMessages.length > 0 && (
                  <button
                    onClick={async () => {
                      setRagMessages([]);
                      try {
                        const token = localStorage.getItem('access_token');
                        await fetch(`${config.apiBaseUrl}/api/ai-chat/rag/history`, {
                          method: 'DELETE',
                          headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
                        });
                      } catch { /* ignore */ }
                    }}
                    className="px-2 py-1 text-xs text-gray-400 hover:text-white border border-gray-700 rounded transition-colors"
                    title="Clear conversation"
                  >
                    Clear
                  </button>
                )}
                <button
                  onClick={() => setShowRagPanel(false)}
                  className="p-1 text-gray-400 hover:text-white rounded transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Conversation history */}
            <div className="max-h-96 overflow-y-auto space-y-3 mb-3">
              {ragMessages.map((msg, idx) => (
                <div key={idx}>
                  {msg.role === 'user' ? (
                    <div className="flex justify-end">
                      <div className="max-w-[85%] bg-fuchsia-700/30 border border-fuchsia-700/50 rounded-lg px-3 py-2 text-sm text-gray-200">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {msg.rewrittenQuery && (
                        <p className="text-xs text-gray-500 italic">
                          Searched for: "{msg.rewrittenQuery}"
                        </p>
                      )}
                      <div className="text-gray-200 text-sm whitespace-pre-wrap leading-relaxed">
                        {msg.content}
                      </div>
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="border-t border-gray-800 pt-2 mt-2">
                          <p className="text-xs text-gray-500 mb-1.5">Sources:</p>
                          <div className="flex flex-wrap gap-2">
                            {msg.sources.map((src, sidx) => (
                              <button
                                key={sidx}
                                onClick={() => navigate(`/sessions/${src.session_id}`)}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-lg border border-gray-700 transition-colors"
                              >
                                <FileText className="w-3 h-3 text-fuchsia-400" />
                                {src.title || 'Untitled'}
                                <span className="text-gray-500">({Math.round(src.score * 100)}%)</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {ragLoading && (
                <div className="flex items-center gap-3 py-2">
                  <Loader2 className="w-4 h-4 text-fuchsia-400 animate-spin" />
                  <span className="text-gray-400 text-sm">Searching meetings and generating answer...</span>
                </div>
              )}
              <div ref={ragEndRef} />
            </div>

            {/* Follow-up input */}
            {ragMessages.length > 0 && (
              <div className="flex gap-2 border-t border-gray-800 pt-3">
                <input
                  type="text"
                  value={ragFollowUp}
                  onChange={(e) => setRagFollowUp(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleRagFollowUp(); } }}
                  placeholder="Ask a follow-up question..."
                  disabled={ragLoading}
                  className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:border-fuchsia-500 disabled:opacity-50"
                />
                <button
                  onClick={handleRagFollowUp}
                  disabled={ragLoading || !ragFollowUp.trim()}
                  className="px-4 py-2 bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50 text-white rounded-lg text-sm transition-colors"
                >
                  Send
                </button>
              </div>
            )}
          </div>
        )}

        {/* Sessions */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="w-8 h-8 border-4 border-purple-400 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <p className="text-gray-400">Loading sessions...</p>
            </div>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="text-center py-12">
            <FolderOpen className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-300 mb-2">No Sessions Found</h3>
            <p className="text-gray-500 mb-6">
              {searchQuery || statusFilter !== 'all' || typeFilter !== 'all' 
                ? 'Try adjusting your filters or search query.'
                : 'Create your first session to get started.'
              }
            </p>
            {!searchQuery && statusFilter === 'all' && typeFilter === 'all' && (
              <button
                onClick={() => setShowCreator(true)}
                className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors mx-auto"
              >
                <Plus className="w-5 h-5" />
                Create First Session
              </button>
            )}
          </div>
        ) : (
          viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <button
              onClick={() => uploadInputRef.current?.click()}
              className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed border-cyan-500/70 bg-gray-900 p-6 text-center transition-colors hover:border-cyan-300 hover:bg-gray-900/80"
            >
              <Upload className="mb-3 h-10 w-10 text-cyan-300" />
              <span className="text-lg font-semibold text-white">Upload Audio/Video</span>
              <span className="mt-2 max-w-xs text-sm text-gray-400">Drop files anywhere or pick recordings to transcribe as meetings.</span>
              <span
                role="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setPickerWithOptions(true);
                  uploadInputRef.current?.click();
                }}
                className="mt-3 text-xs text-cyan-300/80 hover:text-cyan-200 underline-offset-2 hover:underline cursor-pointer"
              >
                Upload with options…
              </span>
            </button>
            {filteredSessions.map(session => (
              <div
                key={session.id}
                className="bg-gray-900 border border-gray-800 rounded-lg hover:border-gray-700 transition-all p-6"
              >
                <div className="space-y-4">
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-semibold text-white text-lg break-words line-clamp-2 leading-tight">
                        {session.title || session.name}
                      </h3>
                      {session.title && session.name !== session.title && (
                        <p className="text-gray-500 text-xs mt-0.5">Original: {session.name}</p>
                      )}
                      {session.description && (
                        <p className="text-gray-400 text-sm mt-1 line-clamp-2">{session.description}</p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`px-2 py-1 rounded-full text-xs border ${getStatusColor(session.status)}`}>
                        {getStatusLabel(session.status)}
                      </span>
                      {session.summary && (
                        <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded border border-purple-500/30">
                          AI Summary
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Meta */}
                  <div className="space-y-2 text-sm text-gray-400">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4" />
                      {new Date(session.created_at).toLocaleDateString()}
                    </div>
                    {session.duration && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        {formatDuration(session.duration)}
                      </div>
                    )}
                    {session.participants && session.participants.length > 0 && (
                      <div className="flex items-center gap-2">
                        <Users className="w-4 h-4" />
                        <span className="truncate">
                          {session.participants.slice(0, 3).map((p) => p.name).join(', ')}
                          {session.participants.length > 3 && ` +${session.participants.length - 3} more`}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* AI Summary Preview */}
                  {session.summary?.analysis?.executive && (
                    <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 bg-purple-400 rounded-full"></div>
                        <span className="text-xs text-purple-300 font-medium">AI Summary</span>
                      </div>
                      <p className="text-gray-300 text-sm line-clamp-2">
                        {session.summary.analysis.executive}
                      </p>
                      {session.summary.analysis.actions && session.summary.analysis.actions.length > 0 && (
                        <div className="mt-2 text-xs text-gray-400">
                          {session.summary.analysis.actions.length} action item{session.summary.analysis.actions.length !== 1 ? 's' : ''}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tags */}
                  {session.tags && session.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {[...session.tags].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())).slice(0, 4).map((tag) => (
                        <TagChip key={tag} tag={tag} />
                      ))}
                      {session.tags.length > 4 && (
                        <span className="px-2 py-0.5 text-xs rounded-full border border-gray-700 bg-gray-800 text-gray-400">
                          +{session.tags.length - 4}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => navigate(`/sessions/${session.id}`)}
                      className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded transition-colors"
                    >
                      <Eye className="w-4 h-4" />
                      View Details
                    </button>

                    {session.has_transcript && (
                      <button
                        onClick={() => downloadTranscript(session)}
                        className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                        title="Download Transcript"
                      >
                        <FileText className="w-4 h-4" />
                      </button>
                    )}

                    {session.summary && (
                      <button
                        onClick={() => downloadSummary(session)}
                        className="p-2 bg-green-700 hover:bg-green-600 text-green-300 rounded transition-colors"
                        title="Download Summary"
                      >
                        <FileText className="w-4 h-4" />
                      </button>
                    )}

                    {session.has_audio && (
                      <button
                        onClick={() => downloadAudio(session)}
                        className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                        title="Download Audio"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    )}

                    <button
                      onClick={() => deleteSession(session.id)}
                      className="p-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded transition-colors"
                      title="Delete Session"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          ) : (
            <SessionsTable
              sessions={filteredSessions}
              sortBy={sortBy}
              sortOrder={sortOrder}
              onHeaderSort={handleHeaderSort}
              statusFilter={tableStatusFilter}
              speakerFilter={tableSpeakerFilter}
              onStatusFilterChange={setTableStatusFilter}
              onSpeakerFilterChange={setTableSpeakerFilter}
              openColumnFilter={openColumnFilter}
              onOpenColumnFilter={setOpenColumnFilter}
              onOpen={(id) => navigate(`/sessions/${id}`)}
              onDelete={deleteSession}
              formatDuration={formatDuration}
              getStatusColor={getStatusColor}
              getStatusLabel={getStatusLabel}
            />
          )
        )}
      </div>

{pendingFiles.length > 0 && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
    <div className="w-full max-w-2xl rounded-lg bg-gray-900 border border-gray-700 shadow-2xl">
      <div className="border-b border-gray-800 px-6 py-4">
        <h3 className="text-lg font-semibold text-white">Confirm upload</h3>
        <p className="mt-1 text-sm text-gray-400">
          {pendingFiles.length} file{pendingFiles.length === 1 ? '' : 's'} ready. Pick options below, then Start.
        </p>
      </div>
      <div className="max-h-[60vh] overflow-y-auto px-6 py-4 space-y-4">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">Files</p>
          <ul className="space-y-1">
            {pendingFiles.map((f, idx) => (
              <li key={idx} className="flex items-center justify-between text-sm text-gray-200 bg-gray-800/60 rounded px-3 py-2">
                <span className="truncate pr-2">{f.name}</span>
                <span className="text-xs text-gray-500">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
              </li>
            ))}
          </ul>
        </div>
        <TranscriptionOptionsPanel value={uploadOptions} onChange={setUploadOptions} defaultOpen />
      </div>
      <div className="flex items-center justify-end gap-3 border-t border-gray-800 px-6 py-3">
        <button
          onClick={cancelUpload}
          className="px-4 py-2 text-sm text-gray-300 hover:text-white"
        >
          Cancel
        </button>
        <button
          onClick={confirmUpload}
          className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700"
        >
          Start processing
        </button>
      </div>
    </div>
  </div>
)}

    </div>
    </>
  );
};
