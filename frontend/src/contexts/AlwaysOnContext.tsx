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
  getAutoPreferUsb,
  getPreferredDeviceId,
  isUsbAudioDevice,
  setPreferredDeviceId,
} from '../utils/audioDevicePreference';
import { showToast } from '../components/Toast';
import { toast as toastify } from 'react-toastify';
import {
  getLiveSummaryAutoConfig,
  getModelLabel,
  getStoredModelId,
  inBrowserLLM,
  LIVE_SUMMARY_THRESHOLDS,
  type LiveSummaryAutoConfig,
  type SummaryParagraph,
} from '../services/inBrowserLLM';
import {
  CLIENT_STT_PROVENANCE,
  inBrowserSTT,
} from '../services/inBrowserSTT';
import {
  getSTTMode,
  type SttMode,
} from '../services/inBrowserSTTSettings';
import {
  getLocalOnly,
  isPrivacyModeAvailable,
} from '../services/privacyMode';
import {
  appendChunk as appendLocalChunk,
  appendSlice as appendLocalSlice,
  createLocalSession,
  endSession as endLocalSession,
  type LocalTranscriptChunk,
} from '../services/localSessionStore';

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
  sttMode: SttMode;
  sttReady: boolean;
  sttLoadProgress: number | null;
  sttLoadLabel: string | null;
  sttBrowserFailed: boolean;
  /** True when the current session is local-only (nothing leaves the device). */
  localOnly: boolean;
  /** True when WebGPU is missing and local-only would degrade to standard mode. */
  localOnlyForcedOff: boolean;
  /**
   * The deviceId we're actually capturing from right now. May differ from
   * the persisted preference if a fallback fired (e.g. plug-out). `null`
   * means "system default".
   */
  activeMicDeviceId: string | null;
  /**
   * The live `MediaStream` for the current capture. UI consumers can
   * attach AnalyserNodes to it for VU meters without re-prompting the
   * user for mic permission.
   */
  activeMicStream: MediaStream | null;
  /** True while a device swap is in flight (engine is restarting). */
  switchingDevice: boolean;
  /**
   * Switch to a different microphone mid-session. The persistent default
   * in localStorage is NOT touched — this is a per-session override.
   * To change the default, call setPreferredDeviceId() from
   * `utils/audioDevicePreference` instead.
   */
  switchMicDevice: (deviceId: string | null) => Promise<void>;
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
  // Browser STT lifecycle. `sttBrowserFailed` is sticky for the *session*:
  // once a transcribe() throws we route subsequent chunks to the server
  // path until the user explicitly opts back in. This avoids the failure
  // mode of "every chunk hits the broken model again and the user sees
  // 30 toasts in a row."
  const [sttMode, setSttMode] = useState<SttMode>(() => getSTTMode());
  const [sttReady, setSttReady] = useState(false);
  const [sttLoadProgress, setSttLoadProgress] = useState<number | null>(null);
  const [sttLoadLabel, setSttLoadLabel] = useState<string | null>(null);
  const [sttBrowserFailed, setSttBrowserFailed] = useState(false);

  const sttModeRef = useRef<SttMode>(sttMode);
  const sttReadyRef = useRef(false);
  const sttBrowserFailedRef = useRef(false);
  const sttLoadAbortRef = useRef<AbortController | null>(null);

  // Privacy mode: toggle persisted in localStorage. Locked-in per-session
  // at start() time so a mid-meeting setting flip doesn't half-upload.
  // When WebGPU is unavailable, the setting flips to "available off"
  // and we silently treat the session as standard.
  const [localOnlyPref, setLocalOnlyPref] = useState<boolean>(() => getLocalOnly());
  const localOnlyAvailable = useMemo(() => isPrivacyModeAvailable(), []);
  const [activeLocalOnly, setActiveLocalOnly] = useState<boolean>(false);
  const activeLocalOnlyRef = useRef<boolean>(false);
  useEffect(() => {
    activeLocalOnlyRef.current = activeLocalOnly;
  }, [activeLocalOnly]);
  const localOnlyForcedOff = localOnlyPref && !localOnlyAvailable;

  // Device-aware capture state. activeMicDeviceId is the deviceId we're
  // RIGHT NOW capturing from (may differ from the saved preference if a
  // fallback fired). activeMicStream is the live MediaStream so the UI
  // can attach a VU meter without re-prompting permission.
  const [activeMicDeviceId, setActiveMicDeviceId] = useState<string | null>(
    () => getPreferredDeviceId(),
  );
  const [activeMicStream, setActiveMicStream] = useState<MediaStream | null>(
    null,
  );
  const [switchingDevice, setSwitchingDevice] = useState<boolean>(false);
  // Track the USB-swap toast so we don't pile up duplicates when the user
  // wiggles a cable. Keyed by deviceId.
  const usbToastShownRef = useRef<Set<string>>(new Set());

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

  // Keep refs in sync — VAD callbacks need to read the latest values
  // without re-binding (the callbacks are created via createVadEngine
  // once per provider mount).
  useEffect(() => {
    sttModeRef.current = sttMode;
  }, [sttMode]);
  useEffect(() => {
    sttReadyRef.current = sttReady;
  }, [sttReady]);
  useEffect(() => {
    sttBrowserFailedRef.current = sttBrowserFailed;
  }, [sttBrowserFailed]);

  // Settings UI writes via setSTTMode() + dispatches an event. Pick it up
  // in any open tab so the picker stays in sync.
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<SttMode>).detail;
      if (detail) setSttMode(detail);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'meetingops.stt.mode.v1') {
        setSttMode(getSTTMode());
      }
    };
    window.addEventListener('meetingops:stt-mode', handler as EventListener);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('meetingops:stt-mode', handler as EventListener);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail;
      if (typeof detail === 'boolean') setLocalOnlyPref(detail);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'meetingops.privacyMode.localOnly') {
        setLocalOnlyPref(getLocalOnly());
      }
    };
    window.addEventListener('meetingops:privacy-mode', handler as EventListener);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('meetingops:privacy-mode', handler as EventListener);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  // Kick off the browser STT load whenever the mode flips to
  // 'browser-parakeet' (including first mount). Don't block the UI on it
  // — the VAD `onSpeechEnd` handler routes through the server path until
  // the model is ready, then auto-switches to browser. This is the same
  // idea as inBrowserLLM's lazy load.
  useEffect(() => {
    if (sttMode !== 'browser-parakeet') {
      // We can't actually unload the model from another tab; this just
      // tells our local context to stop trying.
      setSttReady(false);
      setSttLoadProgress(null);
      setSttLoadLabel(null);
      sttLoadAbortRef.current?.abort();
      sttLoadAbortRef.current = null;
      return;
    }
    if (inBrowserSTT.isReady()) {
      setSttReady(true);
      setSttLoadProgress(1);
      setSttLoadLabel('Ready');
      return;
    }

    const controller = new AbortController();
    sttLoadAbortRef.current = controller;
    setSttLoadProgress(0);
    setSttLoadLabel('Loading');
    setSttBrowserFailed(false);

    inBrowserSTT
      .load({
        signal: controller.signal,
        onProgress: (pct, label) => {
          setSttLoadProgress(pct);
          if (label) setSttLoadLabel(label);
        },
      })
      .then(() => {
        if (controller.signal.aborted) return;
        setSttReady(true);
        setSttLoadProgress(1);
        setSttLoadLabel('Ready');
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        // We failed to even load. Mark failed and fall back to server.
        // The picker will show this state and the user can retry.
        setSttBrowserFailed(true);
        setSttReady(false);
        setSttLoadProgress(null);
        setSttLoadLabel(`Load failed: ${message.slice(0, 80)}`);
        // eslint-disable-next-line no-console
        console.warn('[always-on] Browser STT load failed:', err);
      });

    return () => {
      controller.abort();
      if (sttLoadAbortRef.current === controller) {
        sttLoadAbortRef.current = null;
      }
    };
  }, [sttMode]);

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
    // Local-only sessions never touch the server, so there's nothing on
    // the other side of the websocket. Skip the connection entirely.
    if (activeLocalOnlyRef.current || currentSessionId.startsWith('local-')) return;
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
    // Local-only mode skips the server entirely. Session id lives only
    // in IndexedDB; the rest of the always-on plumbing routes through
    // the same id (with the `local-` prefix) but no network traffic
    // ever fires for chunks / slices / finalize.
    if (activeLocalOnlyRef.current) {
      const session = await createLocalSession();
      setCurrentSessionId(session.id);
      sessionRef.current = session.id;
      return session.id;
    }

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
    // Local-only finalize is handled inline by stop() (final-summary
    // roll-up + endLocalSession). Don't touch the network here.
    if (activeLocalOnlyRef.current) return;
    const response = await fetch(`${config.apiUrl}/api/recordings/sessions/${sessionId}/finalize`, {
      method: 'POST',
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || 'Failed to finalize always-on session.');
    }
  }, []);

  // Audio-blob path: legacy + fallback when browser STT is not ready
  // (model still downloading) or has failed mid-meeting. Posts the WAV to
  // the same `/chunks` endpoint that pre-Parakeet-in-browser code uses.
  const uploadAudioChunk = useCallback(async (
    chunk: VadAudioChunk,
    sessionId: string,
  ): Promise<void> => {
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
  }, [appendTranscriptSegments]);

  // Text path: browser already transcribed. We POST the text + provenance
  // metadata, and *also* append the new segment to the local transcript
  // immediately for the live view. The backend will broadcast the same
  // segment via the websocket; the de-dup in appendTranscriptSegments
  // (matching id) means we won't double-render.
  const uploadTextChunk = useCallback(async (
    chunk: VadAudioChunk,
    text: string,
    sessionId: string,
  ): Promise<void> => {
    const response = await fetch(
      `${config.apiUrl}/api/recordings/sessions/${sessionId}/chunks-text`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          duration_seconds: chunk.durationSeconds,
          elapsed_seconds: Math.max(0, chunk.elapsedSeconds),
          provenance: CLIENT_STT_PROVENANCE,
        }),
      },
    );
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || 'Always-on text chunk upload failed.');
    }
    // Optimistic append for immediate feedback. If the websocket beats
    // us, the segment id is stable enough that we'll dedupe.
    const start = Math.max(0, chunk.elapsedSeconds);
    appendTranscriptSegments(
      [{
        text,
        start,
        end: start + (chunk.durationSeconds || 0),
        speaker: null,
      }],
      sessionId,
    );
  }, [appendTranscriptSegments]);

  const uploadChunk = useCallback(async (chunk: VadAudioChunk): Promise<void> => {
    let sessionId = sessionRef.current;
    if (!sessionId) {
      sessionId = await createSession();
    }

    const localOnly = activeLocalOnlyRef.current;

    // Local-only mode: STT MUST be browser-side. No server fallback.
    // If transcription fails we surface a toast via setError and drop
    // the chunk (the user keeps recording, no audio leaves the device).
    if (localOnly) {
      try {
        const text = await inBrowserSTT.transcribe(chunk.blob);
        const trimmed = (text || '').trim();
        if (!trimmed) {
          setChunksUploaded((count) => count + 1);
          return;
        }
        const elapsed = Math.max(0, chunk.elapsedSeconds);
        const localChunk: LocalTranscriptChunk = {
          text: trimmed,
          elapsedSeconds: elapsed,
          durationSeconds: chunk.durationSeconds || 0,
          provenance: CLIENT_STT_PROVENANCE,
          createdAt: new Date().toISOString(),
        };
        await appendLocalChunk(sessionId, localChunk);
        // Update the live transcript view for immediate feedback. The
        // websocket isn't connected in local mode, so this is the only
        // surface that shows the chunk.
        appendTranscriptSegments(
          [{
            text: trimmed,
            start: elapsed,
            end: elapsed + (chunk.durationSeconds || 0),
            speaker: null,
          }],
          sessionId,
        );
        setChunksUploaded((count) => count + 1);
        return;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        // eslint-disable-next-line no-console
        console.warn('[always-on] Local-only STT failed for chunk:', message);
        setError(`Local STT failed: ${message.slice(0, 120)}. Chunk dropped (nothing leaves the device).`);
        setChunksUploaded((count) => count + 1);
        return;
      }
    }

    const wantBrowser =
      sttModeRef.current === 'browser-parakeet'
      && sttReadyRef.current
      && !sttBrowserFailedRef.current;

    if (wantBrowser) {
      try {
        const text = await inBrowserSTT.transcribe(chunk.blob);
        const trimmed = (text || '').trim();
        if (!trimmed) {
          // Browser model returned empty (likely a misfire or noise) —
          // don't waste a server round-trip on it. The chunk is dropped.
          setChunksUploaded((count) => count + 1);
          return;
        }
        await uploadTextChunk(chunk, trimmed, sessionId);
        setChunksUploaded((count) => count + 1);
        return;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        // eslint-disable-next-line no-console
        console.warn('[always-on] Browser STT failed for chunk, falling back:', message);
        setSttBrowserFailed(true);
        setError(`Browser STT failed: ${message.slice(0, 120)}. Falling back to server.`);
        // Intentional fallthrough to audio path so the user doesn't lose
        // the chunk.
      }
    }

    await uploadAudioChunk(chunk, sessionId);
    setChunksUploaded((count) => count + 1);
  }, [appendTranscriptSegments, createSession, uploadAudioChunk, uploadTextChunk]);

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
      if (activeLocalOnlyRef.current) {
        // Local split: close the IndexedDB session without a final
        // summary roll-up — we never want to block the next session on
        // an LLM pass. The user can re-open the local session later if
        // they want a roll-up retroactively (out of scope for v1).
        endLocalSession(sessionId, null).catch((err) => {
          // eslint-disable-next-line no-console
          console.warn('[always-on] Local split end failed:', err);
        });
      } else {
        void finalizeSession(sessionId).catch((err) => {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
        });
      }
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
        // Read from localStorage at each start/swap so cross-tab Settings
        // edits propagate without a page reload.
        getPreferredDeviceId: () => getPreferredDeviceId(),
        onDeviceChanged: (deviceId) => {
          setActiveMicDeviceId(deviceId);
        },
        onStreamChanged: (stream) => {
          setActiveMicStream(stream);
        },
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

  /**
   * Hot-swap the active mic mid-session. Does NOT touch the persisted
   * preference — that's by design, so a per-session override doesn't
   * leak into the default. Pause-switch-resume is ~few-hundred-ms in
   * practice; we set `switchingDevice` while it's happening so the UI
   * can disable the picker.
   */
  const switchMicDevice = useCallback(
    async (deviceId: string | null) => {
      // If not in an active recording, this is a no-op. AlwaysOnControl
      // disables the picker in that state, but be defensive.
      if (stateRef.current !== 'recording' && stateRef.current !== 'paused') {
        return;
      }
      const engine = engineRef.current;
      if (!engine) return;
      setSwitchingDevice(true);
      const wasPaused = stateRef.current === 'paused';
      try {
        // Resume first if paused; switchDevice tears down + recreates the
        // VAD instance, and it's simpler to do that from a running state.
        if (wasPaused) {
          await engine.resume();
        }
        const opened = await engine.switchDevice(deviceId);
        // The engine fires onDeviceChanged already; this is just for the
        // optimistic update in case the callback hasn't landed yet.
        setActiveMicDeviceId(opened);
        if (wasPaused) {
          // Restore prior pause state — don't surprise the user.
          await engine.pause();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(`Mic swap failed: ${message}`);
      } finally {
        setSwitchingDevice(false);
      }
    },
    [],
  );

  // devicechange listener — fires on USB plug/unplug. Three behaviors:
  //   1. New USB device appears: if auto-prefer-USB is ON and we're
  //      recording, surface a "Switch?" toast. If idle, just notify so
  //      the user knows their picker has fresh options.
  //   2. Currently-active device disappears (recording): auto-fall-back
  //      to system default and toast a notification.
  //   3. Otherwise: silent re-enumeration (Settings page will see it
  //      through its own useAudioDevices hook).
  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) return;

    // Snapshot current input devices so we can diff. Initial fetch may be
    // label-less if no permission has been granted yet; that's fine — we
    // only care about presence/absence of deviceIds for diffing.
    let prevDevices: MediaDeviceInfo[] = [];
    const refreshDevices = async () => {
      try {
        const all = await navigator.mediaDevices.enumerateDevices();
        return all.filter((d) => d.kind === 'audioinput');
      } catch {
        return [];
      }
    };

    let cancelled = false;
    void (async () => {
      prevDevices = await refreshDevices();
      if (cancelled) return;
    })();

    const onDeviceChange = async () => {
      const fresh = await refreshDevices();
      const prev = prevDevices;
      prevDevices = fresh;

      const prevIds = new Set(prev.map((d) => d.deviceId));
      const freshIds = new Set(fresh.map((d) => d.deviceId));

      // (1) New USB device(s) appeared
      const newUsb = fresh.filter(
        (d) => !prevIds.has(d.deviceId) && isUsbAudioDevice(d),
      );
      // (2) Active device disappeared
      const activeId =
        engineRef.current?.getActiveDeviceId() ?? getPreferredDeviceId();
      const activeLost =
        activeId && prevIds.has(activeId) && !freshIds.has(activeId);

      if (
        activeLost &&
        (stateRef.current === 'recording' || stateRef.current === 'paused')
      ) {
        // Engine fall-back: switch to system default and toast.
        try {
          await engineRef.current?.switchDevice(null);
        } catch (err) {
          // engine will surface via onError; nothing else to do.
        }
        showToast.warning(
          'Selected microphone was disconnected. Switched to system default.',
        );
        // Clear the now-invalid saved preference so the next session
        // doesn't try to use it again. (The user can pick a new one in
        // Settings; we just stop pointing at a ghost.)
        if (getPreferredDeviceId() === activeId) {
          setPreferredDeviceId(null);
        }
      }

      if (
        newUsb.length > 0 &&
        getAutoPreferUsb() &&
        (stateRef.current === 'recording' || stateRef.current === 'paused')
      ) {
        // Only one toast per new device id per page-life. Wiggling a
        // cable shouldn't spam.
        for (const dev of newUsb) {
          if (usbToastShownRef.current.has(dev.deviceId)) continue;
          usbToastShownRef.current.add(dev.deviceId);
          const label = dev.label?.trim() || 'New USB microphone';
          const toastId = toastify.info(
            (
              <div className="flex items-center gap-3">
                <div className="flex-1 text-sm">
                  <div className="font-medium">USB mic detected</div>
                  <div className="text-xs opacity-80">{label}</div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    void switchMicDevice(dev.deviceId);
                    // Update the saved default too — the user explicitly
                    // chose this mic, persist for future sessions.
                    setPreferredDeviceId(dev.deviceId);
                    toastify.dismiss(toastId);
                  }}
                  className="rounded bg-emerald-500/30 px-2 py-1 text-xs font-semibold text-emerald-100 hover:bg-emerald-500/50"
                >
                  Switch
                </button>
                <button
                  type="button"
                  onClick={() => toastify.dismiss(toastId)}
                  className="rounded bg-zinc-700/50 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-600/60"
                >
                  Keep current
                </button>
              </div>
            ),
            {
              autoClose: 15000,
              closeOnClick: false,
              draggable: false,
            },
          );
        }
      }
    };

    navigator.mediaDevices.addEventListener('devicechange', onDeviceChange);
    return () => {
      cancelled = true;
      navigator.mediaDevices.removeEventListener(
        'devicechange',
        onDeviceChange,
      );
    };
    // switchMicDevice is stable (refs); listing it as a dep would cause
    // a churn on every render. We intentionally leave it out.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

    // Lock the privacy mode for this session at start. If the user
    // wants local-only but WebGPU is missing, fall back silently to
    // standard mode for this session — the banner in the UI tells them
    // we did so. Otherwise honor the toggle.
    const useLocalOnly = localOnlyPref && localOnlyAvailable;
    activeLocalOnlyRef.current = useLocalOnly;
    setActiveLocalOnly(useLocalOnly);

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
    const wasLocalOnly = activeLocalOnlyRef.current;
    // Snapshot the slices we accumulated before clearing state.
    const slicesSnapshot = [...summary.slices];

    try {
      await engineRef.current?.stop();
      engineRef.current = null;
      await uploadQueueRef.current;
      if (sessionId) {
        if (wasLocalOnly) {
          setStatusText('Generating final summary locally');
          let finalText: string | null = null;
          // Concatenate slice texts oldest-first for the roll-up. If
          // there are no slices, we still close the session — the user
          // may have just talked for under one summary threshold.
          if (slicesSnapshot.length > 0) {
            const joined = slicesSnapshot
              .map((s, i) => `Slice ${i + 1} (${s.createdAt}):\n${s.text.trim()}`)
              .join('\n\n');
            const modelId = getStoredModelId();
            try {
              const finalController = new AbortController();
              let buffer = '';
              for await (const token of inBrowserLLM.summarizeFinal(joined, modelId, {
                signal: finalController.signal,
                sessionId,
              })) {
                buffer += token;
              }
              finalText = buffer.trim() || null;
            } catch (err) {
              // eslint-disable-next-line no-console
              console.warn('[always-on] Local final summary failed:', err);
              setError('Local final summary failed; slices are still saved.');
            }
          }
          await endLocalSession(sessionId, finalText);
        } else {
          setStatusText('Generating final summary');
          await finalizeSession(sessionId);
        }
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
      activeLocalOnlyRef.current = false;
      setActiveLocalOnly(false);
    }
  }, [finalizeSession, summary.slices]);

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

      // Local-only mode: persist the slice to IndexedDB. Best-effort —
      // a write failure surfaces a toast but doesn't block the live UI.
      if (activeLocalOnlyRef.current && sessionRef.current) {
        appendLocalSlice(sessionRef.current, {
          text: finalText,
          wordRangeStart: slice.transcriptStart,
          wordRangeEnd: slice.transcriptEnd,
          model: modelId,
          createdAt: slice.createdAt,
        }).catch((err) => {
          // eslint-disable-next-line no-console
          console.warn('[always-on] Local slice persist failed:', err);
        });
      }

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
    sttMode,
    sttReady,
    sttLoadProgress,
    sttLoadLabel,
    sttBrowserFailed,
    localOnly: activeLocalOnly,
    localOnlyForcedOff,
    activeMicDeviceId,
    activeMicStream,
    switchingDevice,
    switchMicDevice,
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
    sttMode,
    sttReady,
    sttLoadProgress,
    sttLoadLabel,
    sttBrowserFailed,
    activeLocalOnly,
    localOnlyForcedOff,
    activeMicDeviceId,
    activeMicStream,
    switchingDevice,
    switchMicDevice,
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
