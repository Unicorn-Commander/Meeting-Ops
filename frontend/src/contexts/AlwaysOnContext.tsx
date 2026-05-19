import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { config } from '../config';
import { useOrg } from './OrgContext';
import { createVadEngine, type AlwaysOnVadEngine, type VadAudioChunk } from '../utils/vadEngine';
import {
  getLiveSummaryAutoConfig,
  getModelLabel,
  getStoredModelId,
  inBrowserLLM,
  LIVE_SUMMARY_THRESHOLDS,
  type LiveSummaryAutoConfig,
  type SummaryParagraph,
} from '../services/inBrowserLLM';

export type AlwaysOnState = 'idle' | 'starting' | 'recording' | 'paused' | 'stopping';

export interface LiveTranscriptSegment {
  id: string;
  sessionId: string;
  text: string;
  speaker?: string | null;
  start?: number;
  end?: number;
  timestamp: string;
}

export interface AlwaysOnSummarySlice {
  id: string;
  text: string;
  createdAt: string;
  transcriptStart: number;
  transcriptEnd: number;
  model: string;
  modelLabel: string;
  durationMs: number;
}

export interface AlwaysOnSummary {
  slices: AlwaysOnSummarySlice[];
  currentDraft: string;
  lastWordCountAtSummary: number;
  /** Latest slice text, kept for backward compatibility with older callers. */
  text: string;
  paragraphs: SummaryParagraph[];
  updatedAt?: string;
}

const EMPTY_SUMMARY: AlwaysOnSummary = {
  slices: [],
  currentDraft: '',
  lastWordCountAtSummary: 0,
  text: '',
  paragraphs: [],
};

function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `slice-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function countWords(text: string): number {
  if (!text) return 0;
  const matches = text.trim().match(/\S+/g);
  return matches ? matches.length : 0;
}

function thresholdSpec(threshold: LiveSummaryAutoConfig['threshold']) {
  return LIVE_SUMMARY_THRESHOLDS.find((t) => t.id === threshold) ?? LIVE_SUMMARY_THRESHOLDS[1];
}

export interface AlwaysOnContextValue {
  state: AlwaysOnState;
  vadActive: boolean;
  currentSessionId: string | null;
  chunksUploaded: number;
  elapsedSeconds: number;
  summary: AlwaysOnSummary;
  liveTranscript: LiveTranscriptSegment[];
  error: string | null;
  statusText: string;
  sessionsCompleted: number;
  summarizing: boolean;
  modelLoadProgress: number | null;
  autoConfig: LiveSummaryAutoConfig;
  transcriptWordCount: number;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  triggerSummarize: () => Promise<void>;
}

const AlwaysOnContext = createContext<AlwaysOnContextValue | null>(null);

function paragraphsFromText(text: string): SummaryParagraph[] {
  const timestamp = new Date().toISOString();
  return text
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => ({ text: part, timestamp }));
}

function formatSourceLabel(): string {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  return nav.userAgentData?.platform || navigator.platform || 'Browser PWA';
}

function transcriptSegmentId(sessionId: string, segment: any): string {
  const text = String(segment.text || '').trim();
  const start = Number(segment.start ?? segment.start_time ?? 0);
  const end = Number(segment.end ?? segment.end_time ?? 0);
  const safeStart = Number.isFinite(start) ? start : 0;
  const safeEnd = Number.isFinite(end) ? end : 0;
  return [
    sessionId,
    safeStart.toFixed(2),
    safeEnd.toFixed(2),
    text.slice(0, 80),
  ].join(':');
}

export function AlwaysOnProvider({ children }: { children: ReactNode }) {
  const { activeOrganization } = useOrg();
  const [state, setState] = useState<AlwaysOnState>('idle');
  const [vadActive, setVadActive] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [chunksUploaded, setChunksUploaded] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [summary, setSummary] = useState<AlwaysOnSummary>(EMPTY_SUMMARY);
  const [liveTranscript, setLiveTranscript] = useState<LiveTranscriptSegment[]>([]);
  const [autoConfig, setAutoConfig] = useState<LiveSummaryAutoConfig>(() => getLiveSummaryAutoConfig());
  const [error, setError] = useState<string | null>(null);
  const [statusText, setStatusText] = useState('Idle');
  const [sessionsCompleted, setSessionsCompleted] = useState(0);
  const [summarizing, setSummarizing] = useState(false);
  const [modelLoadProgress, setModelLoadProgress] = useState<number | null>(null);

  const engineRef = useRef<AlwaysOnVadEngine | null>(null);
  const stateRef = useRef<AlwaysOnState>('idle');
  const sessionRef = useRef<string | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const uploadQueueRef = useRef<Promise<void>>(Promise.resolve());
  const splitInFlightRef = useRef(false);
  const summarizeAbortRef = useRef<AbortController | null>(null);
  const transcriptSocketRef = useRef<WebSocket | null>(null);
  const autoDebounceRef = useRef<number | null>(null);
  const lastAutoFireRef = useRef<number>(Date.now());
  const summarizingRef = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<LiveSummaryAutoConfig>).detail;
      if (detail) setAutoConfig(detail);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'meetingops.liveSummary.autoConfig.v1') {
        setAutoConfig(getLiveSummaryAutoConfig());
      }
    };
    window.addEventListener('meetingops:live-summary-auto-config', handler as EventListener);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('meetingops:live-summary-auto-config', handler as EventListener);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    sessionRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    if (state !== 'recording' && state !== 'paused') return;
    const tick = window.setInterval(() => {
      if (!startedAtRef.current) return;
      setElapsedSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(tick);
  }, [state]);

  const appendTranscriptSegments = useCallback((segments: any[], sessionId: string) => {
    if (!segments.length) return;
    const timestamp = new Date().toISOString();
    const normalized = segments
      .map((segment) => {
        const text = String(segment.text || '').trim();
        if (!text) return null;
        const start = Number(segment.start ?? segment.start_time ?? 0);
        const end = Number(segment.end ?? segment.end_time ?? 0);
        return {
          id: transcriptSegmentId(sessionId, segment),
          sessionId,
          text,
          speaker: segment.speaker || segment.speaker_id || null,
          start: Number.isFinite(start) ? start : 0,
          end: Number.isFinite(end) ? end : 0,
          timestamp,
        } satisfies LiveTranscriptSegment;
      })
      .filter((segment): segment is LiveTranscriptSegment => Boolean(segment));

    if (!normalized.length) return;
    setLiveTranscript((prev) => {
      const seen = new Set(prev.map((segment) => segment.id));
      const next = [...prev];
      for (const segment of normalized) {
        if (seen.has(segment.id)) continue;
        seen.add(segment.id);
        next.push(segment);
      }
      return next.slice(-80);
    });
  }, []);

  useEffect(() => {
    if (!currentSessionId) return;
    const socket = new WebSocket(config.wsEndpoints.transcription(currentSessionId));
    transcriptSocketRef.current = socket;
    let closedByEffect = false;

    const ping = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'ping' }));
      }
    }, 25000);

    socket.onopen = () => {
      if (stateRef.current === 'recording') {
        setStatusText('Listening');
      }
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(String(event.data));
        if (data.type !== 'transcription') return;
        const segments = Array.isArray(data.segments)
          ? data.segments
          : data.segment
            ? [data.segment]
            : [];
        appendTranscriptSegments(segments, currentSessionId);
      } catch {
        // Ignore keepalive/status payloads that are not transcript updates.
      }
    };
    socket.onerror = () => {
      if (!closedByEffect && stateRef.current === 'recording') {
        setStatusText('Transcript stream reconnecting');
      }
    };
    socket.onclose = () => {
      if (transcriptSocketRef.current === socket) {
        transcriptSocketRef.current = null;
      }
    };

    return () => {
      closedByEffect = true;
      window.clearInterval(ping);
      if (transcriptSocketRef.current === socket) {
        transcriptSocketRef.current = null;
      }
      socket.close();
    };
  }, [appendTranscriptSegments, currentSessionId]);

  const createSession = useCallback(async (): Promise<string> => {
    if (!activeOrganization) {
      throw new Error('No active organization is selected.');
    }

    const response = await fetch(`${config.apiUrl}/api/recordings/start-always-on`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        org_id: activeOrganization.id,
        source_label: formatSourceLabel(),
      }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || 'Failed to start always-on session.');
    }
    const session = await response.json();
    const sessionId = String(session.id);
    setCurrentSessionId(sessionId);
    sessionRef.current = sessionId;
    return sessionId;
  }, [activeOrganization]);

  const finalizeSession = useCallback(async (sessionId: string): Promise<void> => {
    const response = await fetch(`${config.apiUrl}/api/recordings/sessions/${sessionId}/finalize`, {
      method: 'POST',
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || 'Failed to finalize always-on session.');
    }
  }, []);

  const uploadChunk = useCallback(async (chunk: VadAudioChunk): Promise<void> => {
    let sessionId = sessionRef.current;
    if (!sessionId) {
      sessionId = await createSession();
    }

    const form = new FormData();
    form.append('chunk', chunk.blob, `always-on-${Date.now()}.wav`);
    form.append('elapsed_seconds', String(Math.max(0, chunk.elapsedSeconds)));

    const response = await fetch(`${config.apiUrl}/api/recordings/sessions/${sessionId}/chunks`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || 'Always-on chunk upload failed.');
    }
    const data = await response.json();
    const segments = Array.isArray(data.segments) ? data.segments : [];
    appendTranscriptSegments(segments, sessionId);
    setChunksUploaded((count) => count + 1);
  }, [appendTranscriptSegments, createSession]);

  const queueChunkUpload = useCallback((chunk: VadAudioChunk) => {
    uploadQueueRef.current = uploadQueueRef.current
      .then(() => uploadChunk(chunk))
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setStatusText('Upload failed');
      });
  }, [uploadChunk]);

  const splitSession = useCallback(async () => {
    if (splitInFlightRef.current || stateRef.current !== 'recording') return;
    const sessionId = sessionRef.current;
    if (!sessionId) return;

    splitInFlightRef.current = true;
    setVadActive(false);
    setStatusText('Listening for next meeting...');
    try {
      await uploadQueueRef.current;
      setSessionsCompleted((count) => count + 1);
      void finalizeSession(sessionId).catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
      });
      if (stateRef.current === 'recording') {
        await createSession();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    } finally {
      splitInFlightRef.current = false;
    }
  }, [createSession, finalizeSession]);

  const getElapsed = useCallback(() => {
    if (!startedAtRef.current) return 0;
    return (Date.now() - startedAtRef.current) / 1000;
  }, []);

  const ensureEngine = useCallback(() => {
    if (!engineRef.current) {
      engineRef.current = createVadEngine({
        getElapsedSeconds: getElapsed,
        silenceThresholdMs: 30000,
        onSpeechStart: () => {
          setVadActive(true);
          setStatusText('Speech detected');
        },
        onSpeechEnd: (chunk) => {
          setVadActive(false);
          setStatusText('Processing speech chunk');
          queueChunkUpload(chunk);
        },
        onMisfire: () => {
          setVadActive(false);
        },
        onSilenceThreshold: splitSession,
        onError: (message) => setError(message),
      });
    }
    return engineRef.current;
  }, [getElapsed, queueChunkUpload, splitSession]);

  const start = useCallback(async () => {
    if (stateRef.current !== 'idle') return;
    setState('starting');
    setError(null);
    setStatusText('Starting microphone and VAD');
    setSummary(EMPTY_SUMMARY);
    lastAutoFireRef.current = Date.now();
    setLiveTranscript([]);
    setChunksUploaded(0);
    setSessionsCompleted(0);
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);

    try {
      await createSession();
      await ensureEngine().start();
      setState('recording');
      setStatusText('Listening');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await engineRef.current?.stop().catch(() => undefined);
      engineRef.current = null;
      sessionRef.current = null;
      setCurrentSessionId(null);
      startedAtRef.current = null;
      setState('idle');
      setStatusText('Idle');
      setError(message);
    }
  }, [createSession, ensureEngine]);

  const pause = useCallback(async () => {
    if (stateRef.current !== 'recording') return;
    setState('paused');
    setVadActive(false);
    setStatusText('Paused');
    await engineRef.current?.pause();
  }, []);

  const resume = useCallback(async () => {
    if (stateRef.current !== 'paused') return;
    setState('recording');
    setStatusText('Listening');
    await engineRef.current?.resume();
  }, []);

  const stop = useCallback(async () => {
    if (stateRef.current === 'idle' || stateRef.current === 'stopping') return;
    setState('stopping');
    setVadActive(false);
    setStatusText('Stopping');
    summarizeAbortRef.current?.abort();

    const sessionId = sessionRef.current;
    try {
      await engineRef.current?.stop();
      engineRef.current = null;
      await uploadQueueRef.current;
      if (sessionId) {
        setStatusText('Generating final summary');
        await finalizeSession(sessionId);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    } finally {
      sessionRef.current = null;
      setCurrentSessionId(null);
      startedAtRef.current = null;
      setState('idle');
      setStatusText('Idle');
    }
  }, [finalizeSession]);

  const transcriptText = useMemo(
    () => liveTranscript
      .map((segment) => `${segment.speaker ? `${segment.speaker}: ` : ''}${segment.text}`)
      .join('\n')
      .trim(),
    [liveTranscript],
  );

  const transcriptWordCount = useMemo(() => countWords(transcriptText), [transcriptText]);

  const triggerSummarize = useCallback(async () => {
    if (!transcriptText || summarizingRef.current) return;
    const wordCountAtStart = transcriptWordCount;

    summarizeAbortRef.current?.abort();
    const controller = new AbortController();
    summarizeAbortRef.current = controller;
    summarizingRef.current = true;
    setSummarizing(true);
    setModelLoadProgress(0);

    const startedAt = Date.now();
    const modelId = getStoredModelId();
    const previousSlice = summary.slices[summary.slices.length - 1];
    const sliceText = ''; // accumulates tokens
    let text = sliceText;

    setSummary((prev) => ({ ...prev, currentDraft: '' }));

    try {
      for await (const token of inBrowserLLM.summarize(transcriptText, modelId, {
        signal: controller.signal,
        previousSummary: previousSlice?.text,
        sessionId: sessionRef.current ?? undefined,
        onProgress: (report) => {
          setModelLoadProgress(Math.max(0, Math.min(1, report.progress || 0)));
        },
      })) {
        if (controller.signal.aborted) break;
        text += token;
        setSummary((prev) => ({ ...prev, currentDraft: text }));
      }

      if (controller.signal.aborted) {
        setSummary((prev) => ({ ...prev, currentDraft: '' }));
        return;
      }

      const finalText = text.trim();
      if (!finalText) {
        setSummary((prev) => ({ ...prev, currentDraft: '' }));
        return;
      }

      const slice: AlwaysOnSummarySlice = {
        id: uuid(),
        text: finalText,
        createdAt: new Date().toISOString(),
        transcriptStart: previousSlice ? previousSlice.transcriptEnd : 0,
        transcriptEnd: wordCountAtStart,
        model: modelId,
        modelLabel: getModelLabel(modelId),
        durationMs: Date.now() - startedAt,
      };

      setSummary((prev) => {
        const slices = [...prev.slices, slice];
        return {
          slices,
          currentDraft: '',
          lastWordCountAtSummary: wordCountAtStart,
          text: slice.text,
          paragraphs: paragraphsFromText(slice.text),
          updatedAt: slice.createdAt,
        };
      });
      lastAutoFireRef.current = Date.now();
    } catch (err) {
      if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
      }
      setSummary((prev) => ({ ...prev, currentDraft: '' }));
    } finally {
      summarizingRef.current = false;
      setSummarizing(false);
      setModelLoadProgress(null);
    }
  }, [summary.slices, transcriptText, transcriptWordCount]);

  useEffect(() => {
    if (state !== 'recording') return;
    if (!autoConfig.enabled) return;

    const spec = thresholdSpec(autoConfig.threshold);
    if (spec.kind === 'words') {
      const sinceLast = transcriptWordCount - summary.lastWordCountAtSummary;
      if (sinceLast < spec.value) return;
    } else {
      const sinceLast = Date.now() - lastAutoFireRef.current;
      if (sinceLast < spec.value) return;
      if (transcriptWordCount === 0) return;
    }
    if (summarizingRef.current) return;
    if (autoDebounceRef.current) return;

    autoDebounceRef.current = window.setTimeout(() => {
      autoDebounceRef.current = null;
      if (stateRef.current !== 'recording') return;
      if (summarizingRef.current) return;
      void triggerSummarize();
    }, 500);

    return () => {
      if (autoDebounceRef.current) {
        window.clearTimeout(autoDebounceRef.current);
        autoDebounceRef.current = null;
      }
    };
  }, [
    autoConfig.enabled,
    autoConfig.threshold,
    state,
    summary.lastWordCountAtSummary,
    transcriptWordCount,
    triggerSummarize,
  ]);

  useEffect(() => {
    if (state !== 'recording') return;
    const spec = thresholdSpec(autoConfig.threshold);
    if (spec.kind !== 'time') return;
    if (!autoConfig.enabled) return;
    const tick = window.setInterval(() => {
      const sinceLast = Date.now() - lastAutoFireRef.current;
      if (sinceLast < spec.value) return;
      if (summarizingRef.current) return;
      if (autoDebounceRef.current) return;
      autoDebounceRef.current = window.setTimeout(() => {
        autoDebounceRef.current = null;
        if (stateRef.current !== 'recording') return;
        if (summarizingRef.current) return;
        if (transcriptWordCount === 0) return;
        void triggerSummarize();
      }, 500);
    }, 5_000);
    return () => window.clearInterval(tick);
  }, [autoConfig.enabled, autoConfig.threshold, state, transcriptWordCount, triggerSummarize]);

  useEffect(() => () => {
    summarizeAbortRef.current?.abort();
    transcriptSocketRef.current?.close();
    engineRef.current?.stop().catch(() => undefined);
    if (autoDebounceRef.current) {
      window.clearTimeout(autoDebounceRef.current);
      autoDebounceRef.current = null;
    }
  }, []);

  const value = useMemo<AlwaysOnContextValue>(() => ({
    state,
    vadActive,
    currentSessionId,
    chunksUploaded,
    elapsedSeconds,
    summary,
    liveTranscript,
    error,
    statusText,
    sessionsCompleted,
    summarizing,
    modelLoadProgress,
    autoConfig,
    transcriptWordCount,
    start,
    stop,
    pause,
    resume,
    triggerSummarize,
  }), [
    state,
    vadActive,
    currentSessionId,
    chunksUploaded,
    elapsedSeconds,
    summary,
    liveTranscript,
    error,
    statusText,
    sessionsCompleted,
    summarizing,
    modelLoadProgress,
    autoConfig,
    transcriptWordCount,
    start,
    stop,
    pause,
    resume,
    triggerSummarize,
  ]);

  return (
    <AlwaysOnContext.Provider value={value}>
      {children}
    </AlwaysOnContext.Provider>
  );
}

export function useAlwaysOn(): AlwaysOnContextValue {
  const context = useContext(AlwaysOnContext);
  if (!context) {
    throw new Error('useAlwaysOn must be used inside AlwaysOnProvider');
  }
  return context;
}
