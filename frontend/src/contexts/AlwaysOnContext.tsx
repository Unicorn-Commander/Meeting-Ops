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
import { createVadEngine, type AlwaysOnVadEngine, type VadAudioChunk, type VadStreamOpenResult } from '../utils/vadEngine';
import {
  getAutoPreferUsb,
  getPreferredDeviceId,
  isUsbAudioDevice,
  setPreferredDeviceId,
} from '../utils/audioDevicePreference';
import {
  AUDIO_SOURCE_MODE_EVENT,
  AUDIO_SOURCE_MODE_KEY,
  getAudioSourceMode,
  openAudioSourceStream,
  setAudioSourceMode,
  type AudioSourceMode,
  type OpenedAudioSource,
} from '../utils/audioSourceStream';
import {
  isRecordActive,
  setAlwaysOnActive,
} from '../utils/recordingPresence';
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
  deleteLocalSession,
  endSession as endLocalSession,
  isLocalSessionId,
  markParakeetPassFailed,
  markParakeetPassRunning,
  saveParakeetPass,
  type LocalTranscriptChunk,
} from '../services/localSessionStore';
import {
  createFullAudioRecorder,
  postFinalizeAudioWithVerification,
  postFullAudio,
  type FullAudioRecorderHandle,
} from '../utils/fullAudioRecorder';
import {
  detectDevice,
  shouldRunBrowserInference,
  shouldShowCaptureOnlyBanner,
  type DeviceCapability,
} from '../utils/deviceDetection';
import {
  localAudioStore,
  type LocalAudioSessionMeta,
} from '../services/localAudioStore';


// Localstorage key matches PipelineStatusPicker. Read at upload time so the
// user can toggle Diarization on/off mid-session and the next chunk reflects
// the change without restarting the engine.
const DIARIZATION_OFF_KEY = 'meetingops.pipeline.diarization.off.v1';

function getDiarizationOff(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(DIARIZATION_OFF_KEY) === '1';
  } catch {
    return false;
  }
}

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
  /**
   * The audio source mode the user has picked: mic / tab / mic+tab.
   * Persisted in localStorage; mirrored here so the UI can react.
   * When mode != 'mic' the SessionMicChip + auto-prefer-USB are no-ops
   * for the duration of the session.
   */
  audioSourceMode: AudioSourceMode;
  /** Persist a new audio source mode. Only takes effect on next start. */
  setAudioSourceMode: (mode: AudioSourceMode) => void;
  /**
   * Swap the active audio source mid-session. Tears down the current
   * stream (mic, tab, or mixed AudioContext) and reopens via the new
   * mode through the engine's stream opener — same path switchMicDevice
   * uses, ~200ms gap. Also persists the new mode so the next start()
   * picks up where the user left off. No-op when idle.
   */
  switchAudioSource: (mode: AudioSourceMode) => Promise<void>;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  triggerSummarize: () => Promise<void>;
  /**
   * Hard-delete the current session. For server-backed sessions this
   * calls `DELETE /api/recordings/sessions/{id}` which cascades to
   * transcript rows + audio chunks on disk + qdrant points. For
   * local-only sessions we just drop the IndexedDB record. After the
   * delete the engine is reset to `idle` so the next Start begins a
   * brand new session (no leftover state).
   */
  discardSession: () => Promise<void>;
  /**
   * Stop and immediately start again. Finalizes the current session
   * normally (so it's saved and visible in the sessions list) and
   * begins a new session with a fresh UUID. Audio source + mic
   * selection + privacy mode are preserved across the swap.
   */
  restartSession: () => Promise<void>;
  /** ISO timestamp when the current session began (or null when idle). */
  sessionStartedAt: string | null;
  /**
   * Result of the cross-surface collision check, run as part of start().
   * When non-null, the start() call refused to begin because the
   * Record button surface is already active. Callers (AlwaysOnControl)
   * surface a confirm modal asking the user to stop the other one first.
   */
  startBlockedByRecord: boolean;
  /**
   * Reset the blocked state. Called by the UI after the user dismisses
   * the collision modal (whether they decide to abort or proceed).
   */
  clearStartBlocked: () => void;
  /**
   * Result of the one-shot device-capability probe (see
   * `utils/deviceDetection.ts`). Stable across the lifetime of the
   * provider — UI components read it to decide whether to render the
   * live-transcript/summary panes or the capture-only banner.
   */
  deviceCapability: DeviceCapability;
  /**
   * True when this device is a phone or tablet. In capture-only mode
   * we deliberately skip browser-side Parakeet 0.6B + Qwen 3 0.6B /
   * Gemma 4 E2B loads, MediaRecorder still captures audio and uploads
   * chunks, and the server reprocess pass produces the full transcript
   * + summary at meeting completion.
   */
  isCaptureOnlyMode: boolean;
  /**
   * Phase A.5 orphan sessions — recordings that started on this device
   * but never finalized (browser crash, hard refresh, tab close mid-
   * meeting). UI renders a banner offering Resume Upload / Discard.
   * Empty on mobile + desktop-fallback (local persistence is off).
   */
  orphanSessions: LocalAudioSessionMeta[];
  /** Session id currently being resumed via the orphan banner, or null. */
  resumingOrphan: string | null;
  /** Resume an orphan — verify against the server, backfill or full-
   *  audio upload as needed, kick the reprocess pipeline. */
  resumeOrphanSession: (sessionId: string) => Promise<void>;
  /** Drop the local chunks for an orphan without uploading. */
  discardOrphanSession: (sessionId: string) => Promise<void>;
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
  // ISO timestamp the user-visible session "Started" header reads.
  // Cleared in stop()/discard so the UI knows when to hide the header.
  const [sessionStartedAt, setSessionStartedAt] = useState<string | null>(null);
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

  // Phase A mobile gate. detectDevice() is a one-shot synchronous probe
  // — no async adapter requests, no permission prompts — so a useMemo
  // is safe. On phones / tablets we hard-skip Parakeet 0.6B + the
  // browser LLM loads downstream and the UI swaps to a capture-only
  // banner. Audio capture (fullAudioRecorder chunked upload) and the
  // server-side slice polling stay running, so the server reprocess
  // pass still produces a full transcript + summary at completion.
  const deviceCapability = useMemo(() => detectDevice(), []);
  const isCaptureOnlyMode = shouldShowCaptureOnlyBanner(deviceCapability);
  const allowBrowserInference = shouldRunBrowserInference(deviceCapability);

  // Phase A.5 orphan tracking. On desktop-capable browsers we open the
  // local IndexedDB store at mount and check for sessions that started
  // but never finalized (browser crash, tab close mid-meeting, hard
  // refresh). The UI surfaces a banner that lets the user Resume Upload
  // or Discard. List is refreshed after every stop() / discard() so
  // it stays accurate without polling.
  const [orphanSessions, setOrphanSessions] = useState<LocalAudioSessionMeta[]>([]);
  const [resumingOrphan, setResumingOrphan] = useState<string | null>(null);

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

  // Audio source mode (mic | tab | mic+tab). Persisted via the helper.
  // We mirror into state so the picker UI stays reactive, and listen for
  // cross-tab + custom events so a Settings flip in another tab updates
  // the picker. Locked at start() time so a mid-session change doesn't
  // half-swap the engine.
  const [audioSourceMode, setAudioSourceModeState] = useState<AudioSourceMode>(
    () => getAudioSourceMode(),
  );
  const activeAudioSourceModeRef = useRef<AudioSourceMode>('mic');
  // Tracks the opened source so we can register an "unexpected end"
  // listener on the underlying tab stream — when the user closes the
  // shared tab, the track ends and we want to gracefully stop the
  // session + toast.
  const openedSourceRef = useRef<OpenedAudioSource | null>(null);

  // Cross-surface guard. When the user clicks Start while the explicit
  // Record button is active, we set this flag so the UI can surface a
  // confirm modal instead of silently running two captures.
  const [startBlockedByRecord, setStartBlockedByRecord] = useState<boolean>(false);

  // Forward-ref to stop() — populated below after stop is defined.
  // Used inside the engine opener's track-ended handler, which is built
  // in ensureEngine() (defined before stop). Without this we'd have a
  // temporal-dead-zone reference.
  const stopRef = useRef<() => Promise<void>>(async () => undefined);
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
  // Parallel full-session MediaRecorder. Lives alongside the VAD engine so
  // the server can re-run STT + diarization + speaker id + a quality final
  // summary against the contiguous audio after the meeting ends. NULL in
  // privacy mode (we never instantiate the recorder so audio cannot leak).
  const fullAudioRecorderRef = useRef<FullAudioRecorderHandle | null>(null);
  // Slice polling — replaces the in-browser Qwen 3 0.6B slice rolling for
  // standard-mode (server) sessions. Privacy mode keeps the legacy local
  // slice path (see triggerSummarize below).
  const sliceFetchAbortRef = useRef<AbortController | null>(null);

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

  // Audio source mode listener — keeps the picker in sync if Settings or
  // another tab flips it. Does NOT swap the engine mid-session; the new
  // mode applies on the next start().
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<AudioSourceMode>).detail;
      if (detail === 'mic' || detail === 'tab' || detail === 'mic+tab') {
        setAudioSourceModeState(detail);
      }
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === AUDIO_SOURCE_MODE_KEY) {
        setAudioSourceModeState(getAudioSourceMode());
      }
    };
    window.addEventListener(AUDIO_SOURCE_MODE_EVENT, handler as EventListener);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(AUDIO_SOURCE_MODE_EVENT, handler as EventListener);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  const updateAudioSourceMode = useCallback((mode: AudioSourceMode) => {
    // Persist immediately. The local state will follow via the event
    // listener above, but we also call setState here so a same-tick
    // re-render sees the new value without round-tripping through the
    // event loop.
    setAudioSourceMode(mode);
    setAudioSourceModeState(mode);
  }, []);

  const clearStartBlocked = useCallback(() => {
    setStartBlockedByRecord(false);
  }, []);

  // Kick off the browser STT load whenever the mode flips to
  // 'browser-parakeet' (including first mount). Don't block the UI on it
  // — the VAD `onSpeechEnd` handler routes through the server path until
  // the model is ready, then auto-switches to browser. This is the same
  // idea as inBrowserLLM's lazy load.
  useEffect(() => {
    // Phase A mobile gate. On phones / tablets we never attempt to
    // load Parakeet 0.6B INT8 — the WASM fallback is sub-realtime on
    // iOS Safari and the model weights blow past the mobile origin
    // storage cap. Audio still captures + uploads via the chunked
    // MediaRecorder path, and the server reprocess pass at completion
    // produces the full transcript. The label tells anyone debugging
    // why STT isn't initializing.
    if (!allowBrowserInference) {
      setSttReady(false);
      setSttLoadProgress(null);
      setSttLoadLabel('Skipped on mobile');
      sttLoadAbortRef.current?.abort();
      sttLoadAbortRef.current = null;
      return;
    }
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
  }, [sttMode, allowBrowserInference]);

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
    // Kick off the server-side reprocess pipeline if we uploaded full
    // audio chunks during the session. The endpoint is idempotent +
    // skips itself when no chunks landed (privacy mode would never reach
    // this branch anyway because activeLocalOnlyRef.current short-circuits
    // above). We fire-and-forget — the user can navigate to the session
    // detail page to watch the reprocess banner; we don't want stop() to
    // block on a server-side STT pipeline that takes 30+ seconds.
    try {
      await fetch(
        `${config.apiUrl}/api/recordings/sessions/${sessionId}/finalize-audio`,
        { method: 'POST' },
      );
    } catch (err) {
      // Non-fatal — the live transcript stays as the canonical record.
      // eslint-disable-next-line no-console
      console.warn('[always-on] finalize-audio kick-off failed:', err);
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
    if (getDiarizationOff()) form.append('skip_diarization', 'true');

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
          skip_diarization: getDiarizationOff(),
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
        // Source-aware stream opener. Reads the locked-in mode from the
        // ref each call so a session that was started in 'tab' stays in
        // 'tab' even if the user flips the picker mid-session.
        openStream: async (deviceId): Promise<VadStreamOpenResult> => {
          const mode = activeAudioSourceModeRef.current;
          // Dispose any previously-opened source (e.g. on hot-swap). The
          // engine also calls releaseExtras via stopCurrentStream(), but
          // this is belt-and-suspenders.
          const previous = openedSourceRef.current;
          openedSourceRef.current = null;
          if (previous) {
            try {
              previous.cleanup();
            } catch {
              // ignore
            }
          }

          const opened = await openAudioSourceStream(mode, {
            preferredDeviceId: deviceId,
          });
          openedSourceRef.current = opened;

          // Register the tab-closed listener. When the underlying tab
          // stream ends (user closes the captured tab, navigates away,
          // or clicks "Stop sharing" in the Chrome bar) we gracefully
          // stop the session and surface a toast.
          opened.onUnexpectedEnd((reason) => {
            // Only fire if we're still the active source — defensive
            // against a stale closure after stop()/restart.
            if (openedSourceRef.current !== opened) return;
            const label = reason === 'tab' ? 'Captured tab closed' : 'Audio source ended';
            showToast.warning(`${label} — recording stopped.`);
            // Defer the actual stop to the next tick so the engine
            // doesn't race with track-ended teardown inside MicVAD.
            window.setTimeout(() => {
              if (stateRef.current === 'recording' || stateRef.current === 'paused') {
                void stopRef.current();
              }
            }, 0);
          });

          return {
            stream: opened.stream,
            // Mic-only sources can return their deviceId; tab and mic+tab
            // return null since "deviceId" doesn't apply.
            deviceId: mode === 'mic' ? deviceId : null,
            fellBack: false,
            // The VAD engine calls releaseExtras as part of stopCurrentStream().
            // That hooks into our opener's cleanup, which stops raw streams +
            // closes the AudioContext used for mic+tab mixing.
            releaseExtras: () => {
              if (openedSourceRef.current === opened) {
                openedSourceRef.current = null;
              }
              opened.cleanup();
            },
          };
        },
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
    // `stop` is intentionally omitted from deps — it's a stable callback
    // and including it would re-create the engine on every state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  /**
   * Hot-swap the audio source mode mid-session. Updates the locked ref
   * the engine opener reads from, persists to localStorage, then calls
   * engine.switchDevice() to trigger the full opener path — which now
   * sees the new mode and reopens mic / tab / mic+tab accordingly.
   *
   * No special pause handling beyond what switchMicDevice already does;
   * the engine teardown is the same regardless of which mode we land in.
   * Gap is roughly the same as switchMicDevice (~few hundred ms).
   */
  const switchAudioSource = useCallback(
    async (mode: AudioSourceMode) => {
      // If not active, just persist for next start — same semantics as
      // setAudioSourceMode would have given.
      if (stateRef.current !== 'recording' && stateRef.current !== 'paused') {
        setAudioSourceMode(mode);
        setAudioSourceModeState(mode);
        activeAudioSourceModeRef.current = mode;
        return;
      }
      // Same mode — nothing to do.
      if (activeAudioSourceModeRef.current === mode) {
        return;
      }
      const engine = engineRef.current;
      if (!engine) return;
      setSwitchingDevice(true);
      const wasPaused = stateRef.current === 'paused';
      // Capture the previous mode so we can revert if the swap fails.
      const previousMode = activeAudioSourceModeRef.current;
      // Lock the new mode in BEFORE calling switchDevice — the engine
      // opener reads activeAudioSourceModeRef inside its callback, so
      // it has to be flipped first or the reopen happens with the old
      // mode. Also persist + flip state so the UI chip reflects the
      // new target immediately.
      activeAudioSourceModeRef.current = mode;
      setAudioSourceMode(mode);
      setAudioSourceModeState(mode);
      try {
        if (wasPaused) {
          await engine.resume();
        }
        // For mic-based modes we want to preserve the user's current
        // mic deviceId; for tab-only the deviceId is irrelevant and the
        // opener ignores it. Reading getActiveDeviceId() so a per-session
        // mic override survives the source switch.
        const currentDeviceId = engine.getActiveDeviceId();
        const opened = await engine.switchDevice(currentDeviceId);
        setActiveMicDeviceId(opened);
        if (wasPaused) {
          await engine.pause();
        }
        // Friendly use-case label for the toast — matches the new
        // /record page framing so the user sees the same words they
        // clicked, not the underlying mechanism.
        const friendlyLabel =
          mode === 'mic'
            ? 'In-person (mic only)'
            : mode === 'tab'
              ? 'Online meeting (tab only)'
              : 'Mixed (mic + tab)';
        showToast.success(`Audio source switched to ${friendlyLabel}`);
      } catch (err) {
        // Roll back the locked mode + state so the UI and engine stay
        // in sync with reality (we never opened the new source).
        activeAudioSourceModeRef.current = previousMode;
        setAudioSourceMode(previousMode);
        setAudioSourceModeState(previousMode);
        const message = err instanceof Error ? err.message : String(err);
        setError(`Source swap failed: ${message}`);
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

    // Cross-surface guard. If the explicit Record button is in use,
    // refuse to start until the user resolves the collision. The UI
    // shows a confirm modal driven by `startBlockedByRecord`; the
    // caller dismisses + retries.
    if (isRecordActive()) {
      setStartBlockedByRecord(true);
      return;
    }

    setState('starting');
    setError(null);
    setStatusText('Starting microphone and VAD');
    setSummary(EMPTY_SUMMARY);
    lastAutoFireRef.current = Date.now();
    setLiveTranscript([]);
    setChunksUploaded(0);
    setSessionsCompleted(0);
    startedAtRef.current = Date.now();
    setSessionStartedAt(new Date().toISOString());
    setElapsedSeconds(0);

    // Lock the privacy mode for this session at start. If the user
    // wants local-only but WebGPU is missing, fall back silently to
    // standard mode for this session — the banner in the UI tells them
    // we did so. Otherwise honor the toggle.
    const useLocalOnly = localOnlyPref && localOnlyAvailable;
    activeLocalOnlyRef.current = useLocalOnly;
    setActiveLocalOnly(useLocalOnly);

    // Lock the audio source mode for this session. Same locking pattern
    // as privacy mode — a mid-session flip in another tab doesn't half-
    // swap the engine. The ref is read inside the engine opener.
    const lockedMode = getAudioSourceMode();
    activeAudioSourceModeRef.current = lockedMode;
    setAudioSourceModeState(lockedMode);

    // Flag the presence so the explicit Record surfaces can refuse a
    // collision. Cleared in stop() or in the catch branch below.
    setAlwaysOnActive(true);

    try {
      await createSession();
      await ensureEngine().start();
      // After the VAD engine boots we have an active MediaStream we can
      // share with the parallel full-audio recorder.
      //
      // Phase A.5 — local-first on desktop: we spin the recorder up in
      // BOTH standard and privacy modes when the device is desktop-
      // capable. Standard mode still streams chunks to the server AND
      // persists each one to IndexedDB (so a crash mid-meeting can
      // recover up to the last chunk). Privacy mode skips the server
      // upload entirely (`localOnly: true`) but keeps writing to IDB
      // so the local STT/LLM pipeline has source audio. Mobile +
      // desktop-fallback get the server-only path (no local persist)
      // — phones don't have the storage budget and fallback browsers
      // (no WebGPU) shouldn't need it either.
      const stream = engineRef.current?.getActiveStream?.() ?? activeMicStream;
      const sessionIdForRecord = sessionRef.current;
      const desktopLocalFirst =
        deviceCapability.capabilityClass === 'desktop-capable'
        && localAudioStore.isAvailable();
      if (stream && sessionIdForRecord && (activeOrganization || useLocalOnly)) {
        if (desktopLocalFirst) {
          try {
            await localAudioStore.createSessionMetadata(
              sessionIdForRecord,
              new Date().toISOString(),
              useLocalOnly,
            );
          } catch (err) {
            // Non-fatal — recorder still runs without metadata seeding.
            // eslint-disable-next-line no-console
            console.warn('[always-on] localAudioStore metadata seed failed:', err);
          }
        }
        const recorder = createFullAudioRecorder({
          stream,
          sessionId: sessionIdForRecord,
          apiUrl: config.apiUrl,
          orgSlug: activeOrganization?.slug ?? null,
          timesliceMs: 30_000,
          maxRetries: 5,
          initialBackoffMs: 1000,
          localPersistence: desktopLocalFirst,
          localOnly: useLocalOnly,
          onChunkFailed: (idx, err) => {
            // eslint-disable-next-line no-console
            console.warn(
              `[always-on] Full-audio chunk ${idx} dropped after retries:`,
              err.message,
            );
          },
        });
        if (recorder) {
          fullAudioRecorderRef.current = recorder;
          recorder.start();
        }
      }
      setState('recording');
      setStatusText('Listening');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await engineRef.current?.stop().catch(() => undefined);
      engineRef.current = null;
      sessionRef.current = null;
      setCurrentSessionId(null);
      setSessionStartedAt(null);
      startedAtRef.current = null;
      setAlwaysOnActive(false);
      setState('idle');
      setStatusText('Idle');
      setError(message);
    }
  }, [createSession, ensureEngine, localOnlyPref, localOnlyAvailable, deviceCapability, activeOrganization, activeMicStream]);

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
      // Tear down the full-audio recorder FIRST so it flushes the last
      // chunk into the upload queue before we drain. The recorder owns its
      // own internal sequential queue; stop() resolves once that's empty.
      const recorder = fullAudioRecorderRef.current;
      fullAudioRecorderRef.current = null;
      if (recorder) {
        try {
          await recorder.flush();
        } catch {
          /* flush is best-effort */
        }
        try {
          await recorder.stop();
        } catch {
          /* stop is best-effort — gap in audio is acceptable */
        }
      }
      await engineRef.current?.stop();
      engineRef.current = null;
      await uploadQueueRef.current;
      if (sessionId) {
        if (wasLocalOnly) {
          // Phase A.6: two-stage local pass at stop.
          //  Stage 1 — live-slice roll-up (pre-A.6 behaviour) so we
          //  always have *some* summary if the user closes the tab
          //  mid-Stage-2 or the full-audio pass blows up.
          //  Stage 2 — Parakeet 0.6B INT8 over the assembled IDB blob
          //  to produce a high-quality transcript, then a second LLM
          //  final-summary pass over that full transcript. Status is
          //  written into the local session row at each step so the
          //  Local Sessions UI can show "running" → "complete" / "failed".
          setStatusText('Generating live-quality summary locally');
          // Snapshot of the assembled audio blob — needed for Stage 2
          // AND for marking the audio MIME / byte total on the session
          // row. Computed once, reused.
          let assembledForPass: Awaited<ReturnType<typeof localAudioStore.getAssembledBlob>> | null = null;
          // Mark the local audio session ended (privacy mode keeps it
          // in IndexedDB — user manages via the Local Sessions surface).
          if (deviceCapability.capabilityClass === 'desktop-capable'
            && localAudioStore.isAvailable()) {
            try {
              assembledForPass = await localAudioStore.getAssembledBlob(sessionId);
              await localAudioStore.setSessionFinalized(sessionId, assembledForPass.sha256);
            } catch (err) {
              // No chunks (e.g. user stopped before first 30s) — just
              // log and continue. The slice rollup below handles the
              // text-only case.
              // eslint-disable-next-line no-console
              console.debug('[always-on] No local audio to finalize:', err);
            }
          }
          let liveFinalText: string | null = null;
          // Concatenate slice texts oldest-first for the live-slice
          // roll-up. If there are no slices, we still close the session —
          // the user may have just talked for under one summary threshold.
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
              liveFinalText = buffer.trim() || null;
            } catch (err) {
              // eslint-disable-next-line no-console
              console.warn('[always-on] Local live-slice final summary failed:', err);
              setError('Local live summary failed; slices are still saved.');
            }
          }
          await endLocalSession(sessionId, liveFinalText);

          // Stage 2 — full-quality Parakeet pass + LLM re-summary. Only
          // attempted when we actually have an assembled blob AND the
          // browser can run inference (desktop-capable, which is the
          // same gate that allowed privacy-mode in the first place).
          if (
            assembledForPass
            && assembledForPass.bytes > 0
            && shouldRunBrowserInference(deviceCapability)
          ) {
            const assembled = assembledForPass;
            await markParakeetPassRunning(sessionId).catch(() => undefined);
            try {
              // Parakeet load may not have happened yet if the user
              // hadn't enabled browser STT for live captions. Force-load
              // it now (idempotent — second await resolves immediately).
              setStatusText('Loading local STT for full-audio pass');
              await inBrowserSTT.load({
                onProgress: (pct, label) => {
                  // Surface progress as a percent + label so the user
                  // sees movement during a 30-60s first-load. We reuse
                  // statusText since this is a one-shot stop-time pass.
                  const pctTxt = Math.round(pct * 100);
                  setStatusText(
                    label
                      ? `Loading local STT: ${label} (${pctTxt}%)`
                      : `Loading local STT (${pctTxt}%)`,
                  );
                },
              });
              const sttStarted = performance.now();
              setStatusText('Running local STT on full audio');
              const fullTranscriptRaw = await inBrowserSTT.transcribe(assembled.blob);
              const fullTranscript = (fullTranscriptRaw || '').trim();
              const sttElapsedSec = Math.max(
                0,
                Math.round((performance.now() - sttStarted) / 1000),
              );
              // eslint-disable-next-line no-console
              console.info(
                `[always-on] Local Parakeet pass: ${fullTranscript.length} chars in ${sttElapsedSec}s (RTF=${inBrowserSTT.getDiagnostics().lastRTF?.toFixed(3) ?? 'n/a'})`,
              );

              if (!fullTranscript) {
                // Parakeet returned an empty transcript — likely a
                // codec mismatch or silent audio. Fall back to the
                // live-slice summary we already saved.
                await markParakeetPassFailed(
                  sessionId,
                  'Local STT returned an empty transcript. Live-slice summary kept as final.',
                );
              } else {
                setStatusText('Running local summary over full transcript');
                const modelId = getStoredModelId();
                const llmStarted = performance.now();
                const finalController = new AbortController();
                let llmBuffer = '';
                for await (const token of inBrowserLLM.summarizeFinal(
                  fullTranscript,
                  modelId,
                  { signal: finalController.signal, sessionId },
                )) {
                  llmBuffer += token;
                }
                const llmElapsedSec = Math.max(
                  0,
                  Math.round((performance.now() - llmStarted) / 1000),
                );
                const fullSummary = llmBuffer.trim();
                // eslint-disable-next-line no-console
                console.info(
                  `[always-on] Local LLM full-summary: ${fullSummary.length} chars in ${llmElapsedSec}s`,
                );
                if (!fullSummary) {
                  await markParakeetPassFailed(
                    sessionId,
                    'Local summary returned empty output. Live-slice summary kept as final.',
                  );
                } else {
                  await saveParakeetPass(
                    sessionId,
                    fullTranscript,
                    fullSummary,
                    {
                      mimeType: assembled.blob.type || null,
                      bytes: assembled.bytes,
                    },
                  );
                  setStatusText('Done. Session saved locally.');
                }
              }
            } catch (err) {
              const message = err instanceof Error ? err.message : String(err);
              // eslint-disable-next-line no-console
              console.warn('[always-on] Full-audio local pass failed:', message);
              await markParakeetPassFailed(sessionId, message).catch(() => undefined);
              // Friendly toast — the live-slice summary is still
              // saved, the user isn't left with nothing.
              setError(
                "Couldn't run full-quality local pass — saved live-quality summary instead.",
              );
            }
          }
        } else {
          setStatusText('Generating final summary');
          // Phase A.5 — verify-then-confirm. When local persistence is
          // on we compute SHA-256 + byte count from IDB and POST those
          // alongside the finalize call. Server compares to its on-disk
          // chunk state; on match it returns status=complete and we
          // wipe the local copy. On mismatch we POST the assembled
          // blob to /full-audio as the bulletproof recovery path.
          // Without local persistence (desktop-fallback, mobile), we
          // fall back to the pre-A.5 finalize call.
          const localFirstActive =
            deviceCapability.capabilityClass === 'desktop-capable'
            && localAudioStore.isAvailable();
          let verificationOk = false;
          if (localFirstActive) {
            try {
              const localMeta = await localAudioStore.getSessionMetadata(sessionId);
              if (localMeta && localMeta.chunk_count > 0) {
                const assembled = await localAudioStore.getAssembledBlob(sessionId);
                await localAudioStore.setSessionFinalized(sessionId, assembled.sha256);
                const verify = await postFinalizeAudioWithVerification({
                  apiUrl: config.apiUrl,
                  orgSlug: activeOrganization?.slug ?? null,
                  sessionId,
                  clientChunkCount: assembled.chunkCount,
                  clientBytesTotal: assembled.bytes,
                  clientSha256: assembled.sha256,
                });
                if (verify.status === 'complete' || verify.reprocessing_started) {
                  verificationOk = true;
                  // Server has it. Local copy is safe to drop; we
                  // wipe asynchronously so stop() returns fast.
                  void localAudioStore.wipeSession(sessionId).catch((err) => {
                    // eslint-disable-next-line no-console
                    console.warn('[always-on] local wipe failed (non-fatal):', err);
                  });
                } else if (verify.status === 'incomplete') {
                  // Server is missing chunks. Fall back to the
                  // assembled-blob path — simplest reliable recovery
                  // surface; partial backfill is a v2.
                  setStatusText('Recovering audio from local copy');
                  const recovery = await postFullAudio({
                    apiUrl: config.apiUrl,
                    orgSlug: activeOrganization?.slug ?? null,
                    sessionId,
                    blob: assembled.blob,
                    mimeType: fullAudioRecorderRef.current?.mimeType()
                      ?? localMeta.mime_type
                      ?? 'audio/webm',
                  });
                  if (recovery.reprocessing_started) {
                    verificationOk = true;
                    void localAudioStore.wipeSession(sessionId).catch(() => undefined);
                  }
                }
              }
            } catch (err) {
              // eslint-disable-next-line no-console
              console.warn('[always-on] Local-first verify path failed:', err);
              // Fall through to the legacy finalize path so the
              // session still completes via server-side state.
            }
          }
          if (!verificationOk) {
            await finalizeSession(sessionId);
          } else {
            // Verification path already kicked the reprocess via the
            // /finalize-audio response. We still need to mark the
            // session row "complete" on the server so the legacy
            // /finalize endpoint runs (transcript_simple finalization,
            // duration, etc.). The pre-A.5 finalizeSession() helper
            // hits both /finalize AND /finalize-audio; we just hit
            // /finalize here.
            try {
              await fetch(
                `${config.apiUrl}/api/recordings/sessions/${sessionId}/finalize`,
                { method: 'POST' },
              );
            } catch (err) {
              // eslint-disable-next-line no-console
              console.warn('[always-on] /finalize kick-off failed:', err);
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    } finally {
      sessionRef.current = null;
      setCurrentSessionId(null);
      setSessionStartedAt(null);
      startedAtRef.current = null;
      setState('idle');
      setStatusText('Idle');
      activeLocalOnlyRef.current = false;
      setActiveLocalOnly(false);
      // Clear the cross-surface presence flag — the Record button is
      // free to start now. Idempotent if it's already cleared.
      setAlwaysOnActive(false);
      // Drop the opened-source ref. The engine called releaseExtras
      // already which invoked our cleanup; this just nukes the dangling
      // reference so the GC can drop it.
      openedSourceRef.current = null;
    }
  }, [finalizeSession, summary.slices]);

  // Wire stopRef now that stop is defined. Used by ensureEngine's
  // track-ended handler (which is constructed before stop in the file
  // order). Don't include stop in the engine's dep array — re-creating
  // the engine on every stop change would be wrong.
  useEffect(() => {
    stopRef.current = stop;
  }, [stop]);

  const transcriptText = useMemo(
    () => liveTranscript
      .map((segment) => `${segment.speaker ? `${segment.speaker}: ` : ''}${segment.text}`)
      .join('\n')
      .trim(),
    [liveTranscript],
  );

  const transcriptWordCount = useMemo(() => countWords(transcriptText), [transcriptText]);

  // === Server-side slice polling (standard mode) =====================
  //
  // Standard-mode browser always-on sessions now read their slice stack
  // from the server (Qwen 3.6 35B-A3B-Vision quality) instead of running
  // Qwen 3 0.6B INT8 in the browser. Privacy mode keeps the legacy local
  // path below — server polling never fires when activeLocalOnlyRef is
  // true.
  //
  // We mirror the RoomLiveSummary polling pattern: GET every 5s while
  // recording, plus one refresh on session change so a reviewer landing
  // on a paused/stopped session sees the persisted slices.
  const refreshServerSlices = useCallback(async (sessionId: string): Promise<void> => {
    if (activeLocalOnlyRef.current) return;
    sliceFetchAbortRef.current?.abort();
    const controller = new AbortController();
    sliceFetchAbortRef.current = controller;

    try {
      const headers: Record<string, string> = {};
      try {
        const token = window.localStorage?.getItem('access_token');
        if (token) headers['Authorization'] = `Bearer ${token}`;
      } catch {
        /* ignore */
      }
      if (activeOrganization?.slug) {
        headers['X-MeetingOps-Org'] = activeOrganization.slug;
      }
      const resp = await fetch(
        `${config.apiUrl}/api/recordings/sessions/${sessionId}/summary-slices`,
        {
          method: 'GET',
          signal: controller.signal,
          headers,
          credentials: 'include',
        },
      );
      if (!resp.ok) {
        // Network blips self-heal on the next tick. We only surface
        // real failures (the user-visible error banner is reserved for
        // genuine issues).
        return;
      }
      const data = (await resp.json()) as {
        slices?: Array<{
          id: string;
          text: string;
          word_count?: number;
          word_range_start?: number;
          word_range_end?: number;
          model?: string;
          provider?: string;
          created_at?: string;
          triggered_by?: string;
        }>;
      };
      const rawSlices = Array.isArray(data.slices) ? data.slices : [];
      if (rawSlices.length === 0) return;
      const normalized: AlwaysOnSummarySlice[] = rawSlices.map((s) => ({
        id: String(s.id || ''),
        text: String(s.text || ''),
        createdAt: s.created_at || new Date().toISOString(),
        transcriptStart: Number(s.word_range_start || 0),
        transcriptEnd: Number(s.word_range_end || s.word_count || 0),
        model: String(s.model || 'server-llm'),
        modelLabel: String(s.model || 'Server LLM'),
        durationMs: 0,
      }));
      const latest = normalized[normalized.length - 1];
      setSummary({
        slices: normalized,
        currentDraft: '',
        lastWordCountAtSummary: latest?.transcriptEnd ?? 0,
        text: latest?.text ?? '',
        paragraphs: latest ? paragraphsFromText(latest.text) : [],
        updatedAt: latest?.createdAt,
      });
    } catch (err) {
      if (controller.signal.aborted) return;
      // eslint-disable-next-line no-console
      console.debug('[always-on] slice refresh failed', err);
    }
  }, [activeOrganization]);

  // Poll the server-rolled slice stack every 5s while recording. Skipped
  // in privacy mode (no server traffic) and when there's no active
  // session id. Also runs once on session change so a reviewer landing
  // on a paused session sees the latest persisted slices.
  useEffect(() => {
    if (!currentSessionId) return;
    if (activeLocalOnlyRef.current) return;
    if (currentSessionId.startsWith('local-')) return;
    // Initial fetch on mount / session swap.
    void refreshServerSlices(currentSessionId);
    if (state !== 'recording' && state !== 'paused') return;
    const tick = window.setInterval(() => {
      void refreshServerSlices(currentSessionId);
    }, 5_000);
    return () => window.clearInterval(tick);
  }, [currentSessionId, state, refreshServerSlices]);

  const triggerSummarize = useCallback(async () => {
    // Standard mode: ask the server to roll a slice now. POST returns
    // the new slice; the polling loop above will reconcile if the server
    // happened to auto-trigger one in the meantime.
    if (!activeLocalOnlyRef.current) {
      const sessionId = sessionRef.current;
      if (!sessionId) return;
      if (summarizingRef.current) return;
      summarizingRef.current = true;
      setSummarizing(true);
      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };
        try {
          const token = window.localStorage?.getItem('access_token');
          if (token) headers['Authorization'] = `Bearer ${token}`;
        } catch {
          /* ignore */
        }
        if (activeOrganization?.slug) {
          headers['X-MeetingOps-Org'] = activeOrganization.slug;
        }
        const resp = await fetch(
          `${config.apiUrl}/api/recordings/sessions/${sessionId}/summary-slices`,
          {
            method: 'POST',
            headers,
            credentials: 'include',
          },
        );
        if (resp.status === 422) {
          // No new transcript since the last slice — not really an error.
          // The polling loop will eventually pick up new slices when
          // there's enough new content.
          return;
        }
        if (!resp.ok) {
          const detail = await resp.text().catch(() => '');
          throw new Error(detail || `Summarize failed (${resp.status})`);
        }
        // Refresh once to surface the new slice immediately rather than
        // waiting for the 5s poll tick.
        await refreshServerSlices(sessionId);
        lastAutoFireRef.current = Date.now();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
      } finally {
        summarizingRef.current = false;
        setSummarizing(false);
      }
      return;
    }

    // Privacy mode (local-only) — keeps the legacy browser Qwen 3 0.6B
    // path. The server is forbidden in this mode, so we have no other
    // choice. The slice quality is lower but at least nothing leaves the
    // device.
    //
    // Phase A mobile gate: even if a user somehow enters local-only on
    // mobile (privacyMode.localOnly toggled on AND WebGPU advertised by
    // iOS 17+), we refuse to fire the browser LLM. The slice queue
    // stays empty until they're on a desktop — capture-only is the
    // contract on mobile.
    if (!allowBrowserInference) {
      return;
    }
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
  }, [
    activeOrganization,
    refreshServerSlices,
    summary.slices,
    transcriptText,
    transcriptWordCount,
    allowBrowserInference,
  ]);

  // Client-side auto-trigger — runs ONLY in privacy/local-only mode.
  // Standard mode delegates to the server's word-count threshold (set
  // via ROOM_SLICE_TRIGGER_WORDS env, default 500 words) and reads
  // slices via the 5s polling loop above. Without this gate, both
  // surfaces would race to fire slices and the user would see double
  // entries.
  useEffect(() => {
    if (state !== 'recording') return;
    if (!autoConfig.enabled) return;
    if (!activeLocalOnly) return; // server-side trigger handles standard mode

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
    activeLocalOnly,
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
    if (!activeLocalOnly) return; // server-side trigger handles standard mode
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
  }, [
    activeLocalOnly,
    autoConfig.enabled,
    autoConfig.threshold,
    state,
    transcriptWordCount,
    triggerSummarize,
  ]);

  useEffect(() => () => {
    summarizeAbortRef.current?.abort();
    transcriptSocketRef.current?.close();
    engineRef.current?.stop().catch(() => undefined);
    fullAudioRecorderRef.current?.stop().catch(() => undefined);
    fullAudioRecorderRef.current = null;
    sliceFetchAbortRef.current?.abort();
    sliceFetchAbortRef.current = null;
    if (autoDebounceRef.current) {
      window.clearTimeout(autoDebounceRef.current);
      autoDebounceRef.current = null;
    }
    // Clean up the opened source (closes AudioContext, stops tab stream).
    if (openedSourceRef.current) {
      try {
        openedSourceRef.current.cleanup();
      } catch {
        // ignore
      }
      openedSourceRef.current = null;
    }
    // Drop the presence flag — if the user navigates away mid-session
    // the next mount shouldn't think a stale always-on session is live.
    setAlwaysOnActive(false);
  }, []);

  /**
   * Hard-delete the current session and reset to idle. Server-backed
   * sessions call DELETE /api/recordings/sessions/{id} which cascades
   * to transcript rows + audio chunks on disk + qdrant points. Local-
   * only sessions just drop the IndexedDB record.
   *
   * Engine is stopped first (no chunks-in-flight after the delete) and
   * the DB row is wiped before we surface success — if the cascade
   * delete fails the session stays around and we surface the error.
   */
  const discardSession = useCallback(async () => {
    if (stateRef.current === 'idle') return;
    const sessionId = sessionRef.current;
    const wasLocalOnly = activeLocalOnlyRef.current;

    setState('stopping');
    setVadActive(false);
    setStatusText('Discarding session');
    summarizeAbortRef.current?.abort();

    try {
      // Stop the full-audio recorder BEFORE the VAD engine so we drain
      // its upload queue ahead of the delete request — otherwise a chunk
      // could land on the server immediately after we deleted the session
      // row and recreate the per-session directory.
      const recorder = fullAudioRecorderRef.current;
      fullAudioRecorderRef.current = null;
      if (recorder) {
        try {
          await recorder.stop();
        } catch {
          /* tear-down errors are non-fatal during discard */
        }
      }
      // Stop the engine BEFORE we touch the backend — otherwise an
      // in-flight chunk-upload can race the delete and recreate a row.
      await engineRef.current?.stop().catch(() => undefined);
      engineRef.current = null;
      await uploadQueueRef.current;

      if (sessionId) {
        if (wasLocalOnly || isLocalSessionId(sessionId)) {
          await deleteLocalSession(sessionId);
          // Privacy-mode session: also drop the local audio chunks
          // from IDB. The user explicitly asked to discard, so we don't
          // keep the audio around either.
          if (localAudioStore.isAvailable()) {
            await localAudioStore.wipeSession(sessionId).catch(() => undefined);
          }
        } else {
          const res = await fetch(
            `${config.apiUrl}/api/recordings/sessions/${sessionId}`,
            { method: 'DELETE' },
          );
          if (!res.ok) {
            const detail = await res.text().catch(() => '');
            throw new Error(detail || `DELETE failed (${res.status})`);
          }
          // Server delete cascaded the chunks dir — also wipe our
          // local mirror so we don't leak storage.
          if (localAudioStore.isAvailable()) {
            await localAudioStore.wipeSession(sessionId).catch(() => undefined);
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Discard failed: ${message}`);
    } finally {
      sessionRef.current = null;
      setCurrentSessionId(null);
      setSessionStartedAt(null);
      startedAtRef.current = null;
      setSummary(EMPTY_SUMMARY);
      setLiveTranscript([]);
      setChunksUploaded(0);
      setState('idle');
      setStatusText('Idle');
      activeLocalOnlyRef.current = false;
      setActiveLocalOnly(false);
      setAlwaysOnActive(false);
      openedSourceRef.current = null;
    }
  }, []);

  // Forward-ref for start() — populated in an effect below since start
  // depends on createSession + ensureEngine which are defined earlier
  // in the file. restartSession needs to wait for stop() before
  // start()ing again, so we go through this ref.
  const startRef = useRef<() => Promise<void>>(async () => undefined);
  useEffect(() => {
    startRef.current = start;
  }, [start]);

  // ---------------------------------------------------------------
  // Phase A.5 — Orphan session detection + resume.
  // ---------------------------------------------------------------

  /** Re-query IDB and refresh the orphan banner. Cheap; called on
   *  mount and after every stop/discard so the banner stays accurate. */
  const refreshOrphanSessions = useCallback(async () => {
    if (deviceCapability.capabilityClass !== 'desktop-capable') return;
    if (!localAudioStore.isAvailable()) return;
    try {
      await localAudioStore.init();
      const orphans = await localAudioStore.getOrphanedSessions();
      setOrphanSessions(orphans);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[always-on] orphan scan failed:', err);
      setOrphanSessions([]);
    }
  }, [deviceCapability]);

  // One-shot scan on mount. Captures the "browser crashed mid-meeting"
  // case where the user reopens the tab and we have chunks sitting in
  // IDB with no live session.
  useEffect(() => {
    void refreshOrphanSessions();
  }, [refreshOrphanSessions]);

  /** Resume Upload — re-runs the verification + recovery dance against
   *  the server using the locally-buffered chunks. Idempotent; safe to
   *  retry from a button click. */
  const resumeOrphanSession = useCallback(async (sessionId: string) => {
    if (!activeOrganization) {
      setError('Pick an organization before resuming the upload.');
      return;
    }
    if (!localAudioStore.isAvailable()) return;
    setResumingOrphan(sessionId);
    try {
      const meta = await localAudioStore.getSessionMetadata(sessionId);
      if (!meta || meta.chunk_count === 0) {
        // Nothing to upload — just clean up.
        await localAudioStore.wipeSession(sessionId);
        await refreshOrphanSessions();
        return;
      }
      const assembled = await localAudioStore.getAssembledBlob(sessionId);
      await localAudioStore.setSessionFinalized(sessionId, assembled.sha256);
      // Try verification first — server may already have most of
      // the chunks if the crash happened after upload but before
      // we wiped the local copy.
      const verify = await postFinalizeAudioWithVerification({
        apiUrl: config.apiUrl,
        orgSlug: activeOrganization.slug ?? null,
        sessionId,
        clientChunkCount: assembled.chunkCount,
        clientBytesTotal: assembled.bytes,
        clientSha256: assembled.sha256,
      });
      if (verify.status === 'complete' || verify.reprocessing_started) {
        await localAudioStore.wipeSession(sessionId);
      } else {
        // Server is missing chunks. POST the assembled blob via
        // /full-audio for guaranteed recovery.
        const recovery = await postFullAudio({
          apiUrl: config.apiUrl,
          orgSlug: activeOrganization.slug ?? null,
          sessionId,
          blob: assembled.blob,
          mimeType: meta.mime_type || 'audio/webm',
        });
        if (recovery.reprocessing_started) {
          await localAudioStore.wipeSession(sessionId);
        }
      }
      // Also kick the legacy /finalize so transcript_simple +
      // duration are finalized server-side. Best-effort.
      try {
        await fetch(
          `${config.apiUrl}/api/recordings/sessions/${sessionId}/finalize`,
          { method: 'POST' },
        );
      } catch {
        /* non-fatal */
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Resume upload failed: ${message.slice(0, 200)}`);
    } finally {
      setResumingOrphan(null);
      await refreshOrphanSessions();
    }
  }, [activeOrganization, refreshOrphanSessions]);

  /** Discard an orphan — drop the local chunks without uploading. We
   *  do NOT touch the server-side row (the user can clean that up
   *  through the Sessions list if they want). */
  const discardOrphanSession = useCallback(async (sessionId: string) => {
    if (!localAudioStore.isAvailable()) return;
    try {
      await localAudioStore.wipeSession(sessionId);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Discard orphan failed: ${message.slice(0, 200)}`);
    } finally {
      await refreshOrphanSessions();
    }
  }, [refreshOrphanSessions]);

  // Refresh after stop/discard so the banner clears once the chunks
  // are wiped from IDB. We piggyback on the state transition rather
  // than wiring it into the stop body so the helper stays self-contained.
  useEffect(() => {
    if (state === 'idle') void refreshOrphanSessions();
  }, [state, refreshOrphanSessions]);

  /**
   * Stop the current session normally (so it's saved + finalized) and
   * immediately start a new one. Audio source mode + privacy mode are
   * preserved across the swap; the only thing that changes is the
   * session UUID. If stop() fails, we don't auto-start — the user can
   * see the error and retry.
   */
  const restartSession = useCallback(async () => {
    if (stateRef.current === 'idle') {
      // Nothing live; just start.
      await startRef.current();
      return;
    }
    await stop();
    // Give the engine a tick to fully release the mic + AudioContext
    // before we reopen. Without this, Chromium sometimes 0-channels
    // the new MediaStream for ~50ms.
    await new Promise<void>((resolve) => setTimeout(resolve, 50));
    await startRef.current();
  }, [stop]);

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
    audioSourceMode,
    setAudioSourceMode: updateAudioSourceMode,
    switchAudioSource,
    start,
    stop,
    pause,
    resume,
    triggerSummarize,
    discardSession,
    restartSession,
    sessionStartedAt,
    startBlockedByRecord,
    clearStartBlocked,
    deviceCapability,
    isCaptureOnlyMode,
    orphanSessions,
    resumingOrphan,
    resumeOrphanSession,
    discardOrphanSession,
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
    audioSourceMode,
    updateAudioSourceMode,
    switchAudioSource,
    start,
    stop,
    pause,
    resume,
    triggerSummarize,
    discardSession,
    restartSession,
    sessionStartedAt,
    startBlockedByRecord,
    clearStartBlocked,
    deviceCapability,
    isCaptureOnlyMode,
    orphanSessions,
    resumingOrphan,
    resumeOrphanSession,
    discardOrphanSession,
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
