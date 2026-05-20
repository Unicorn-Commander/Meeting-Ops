import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { config } from '../../config';

interface RoomLiveSummaryProps {
  /** Active session UUID. */
  sessionId: string | null;
  /** Active org slug for the X-MeetingOps-Org header. */
  orgSlug: string | null;
  /** Whether the room is currently recording. */
  recording: boolean;
  /**
   * Current transcript text — provided by the parent so we don't poll
   * twice. The component triggers a new summary once the transcript
   * grows by at least `wordTriggerDelta` words past the previous
   * summary.
   */
  transcript: string;
  /** Word-count delta that triggers an auto-summary. Default 200. */
  wordTriggerDelta?: number;
  /** Minimum seconds between auto-summaries. Default 90. */
  minIntervalSec?: number;
}

interface Slice {
  id: string;
  text: string;
  createdAt: string;
  wordCount: number;
}

function countWords(text: string): number {
  if (!text) return 0;
  const matches = text.trim().match(/\S+/g);
  return matches ? matches.length : 0;
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `slice-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * Renders the rolling auto-summary stack for a conference-room recording.
 *
 * Strategy:
 *  - Watch the transcript word count provided by the parent.
 *  - When word count grows by >= `wordTriggerDelta` past the last slice
 *    AND >= `minIntervalSec` seconds have passed, POST the current
 *    transcript to `/api/recordings/summarize` and push the result onto
 *    the slice stack.
 *  - Latest slice is expanded; older slices collapse to a header row.
 *
 * Slices live in component state, not persisted — they're regenerated
 * if the user navigates away and back, which is fine for v1.
 */
export default function RoomLiveSummary({
  sessionId,
  orgSlug,
  recording,
  transcript,
  wordTriggerDelta = 200,
  minIntervalSec = 90,
}: RoomLiveSummaryProps) {
  const [slices, setSlices] = useState<Slice[]>([]);
  const [summarizing, setSummarizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const lastWordsAtSummaryRef = useRef(0);
  const lastSummaryTimeRef = useRef(0);
  const slicesRef = useRef<Slice[]>([]);
  slicesRef.current = slices;

  // Reset state when session changes.
  useEffect(() => {
    setSlices([]);
    setExpandedIds(new Set());
    setError(null);
    lastWordsAtSummaryRef.current = 0;
    lastSummaryTimeRef.current = 0;
  }, [sessionId]);

  const runSummary = useCallback(async () => {
    if (!sessionId) return;
    if (!transcript || !transcript.trim()) return;
    setSummarizing(true);
    setError(null);
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      try {
        const token = localStorage.getItem('access_token');
        if (token) headers['Authorization'] = `Bearer ${token}`;
      } catch {
        /* ignore */
      }
      if (orgSlug) headers['X-MeetingOps-Org'] = orgSlug;
      const resp = await fetch(`${config.apiBaseUrl}/api/recordings/summarize`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify({
          transcript,
          session_id: sessionId,
        }),
      });
      if (!resp.ok) {
        let detail = `Status ${resp.status}`;
        try {
          const body = await resp.json();
          if (typeof body?.detail === 'string') detail = body.detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const data = (await resp.json()) as { summary?: string };
      const text = (data?.summary || '').trim();
      if (!text) {
        throw new Error('Empty summary response');
      }
      const wc = countWords(transcript);
      const slice: Slice = {
        id: uuid(),
        text,
        createdAt: new Date().toISOString(),
        wordCount: wc,
      };
      setSlices((prev) => [...prev, slice]);
      lastWordsAtSummaryRef.current = wc;
      lastSummaryTimeRef.current = Date.now();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Summary failed');
    } finally {
      setSummarizing(false);
    }
  }, [sessionId, transcript, orgSlug]);

  // Auto-trigger on word count + time.
  useEffect(() => {
    if (!recording || !sessionId) return;
    const wc = countWords(transcript);
    const elapsed = (Date.now() - lastSummaryTimeRef.current) / 1000;
    const wordDelta = wc - lastWordsAtSummaryRef.current;
    if (
      wc >= 30 && // never summarize a near-empty transcript
      wordDelta >= wordTriggerDelta &&
      elapsed >= minIntervalSec &&
      !summarizing
    ) {
      // Defer one tick so React commits state before the network call.
      const handle = window.setTimeout(() => runSummary(), 50);
      return () => window.clearTimeout(handle);
    }
    return undefined;
  }, [
    transcript,
    recording,
    sessionId,
    wordTriggerDelta,
    minIntervalSec,
    runSummary,
    summarizing,
  ]);

  const latestSliceId = slices.length > 0 ? slices[slices.length - 1].id : null;

  // Latest slice expanded by default unless toggled; older slices
  // collapsed unless toggled. The expanded set tracks user toggles.
  const isExpanded = (id: string) => {
    if (id === latestSliceId) return !expandedIds.has(id);
    return expandedIds.has(id);
  };
  const toggle = (id: string) =>
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const ordered = useMemo(() => [...slices].reverse(), [slices]);

  if (!recording) {
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles className="h-4 w-4" /> Live summary
        </h2>
        <p className="mt-2 text-sm leading-6 text-zinc-500">
          Auto-summary will start when the room is recording.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col rounded-2xl border border-zinc-800 bg-zinc-950/60 p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles className="h-4 w-4" /> Live summary
          {summarizing && (
            <Loader2 className="h-3 w-3 animate-spin text-zinc-500" />
          )}
        </h2>
        <button
          type="button"
          onClick={runSummary}
          disabled={summarizing || !transcript.trim()}
          className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3 w-3 ${summarizing ? 'animate-spin' : ''}`}
          />
          Summarize now
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {slices.length === 0 && !summarizing && (
        <p className="text-sm leading-6 text-zinc-500">
          Auto-summary will publish a slice once the transcript reaches{' '}
          {wordTriggerDelta} new words. You can also trigger one now.
        </p>
      )}

      {ordered.length > 0 && (
        <div className="flex flex-col gap-2">
          {ordered.map((slice) => {
            const expanded = isExpanded(slice.id);
            return (
              <div
                key={slice.id}
                className={`rounded-lg border transition-colors ${
                  slice.id === latestSliceId
                    ? 'border-fuchsia-500/40 bg-fuchsia-500/5'
                    : 'border-zinc-800 bg-black/30'
                }`}
              >
                <button
                  type="button"
                  onClick={() => toggle(slice.id)}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-zinc-100 hover:bg-zinc-800/40"
                >
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                    <span className="text-zinc-300">
                      {clockTime(slice.createdAt)}
                    </span>
                    <span className="text-zinc-600">·</span>
                    <span>{slice.wordCount} words</span>
                    {slice.id === latestSliceId && (
                      <span className="rounded-full border border-fuchsia-500/40 bg-fuchsia-500/10 px-1.5 py-0 text-[10px] uppercase text-fuchsia-200">
                        Latest
                      </span>
                    )}
                  </div>
                  {expanded ? (
                    <ChevronUp className="h-4 w-4 text-zinc-500" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-zinc-500" />
                  )}
                </button>
                {expanded && (
                  <div className="border-t border-zinc-800/80 px-3 py-2 text-sm leading-6 text-zinc-100 whitespace-pre-wrap">
                    {slice.text}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
