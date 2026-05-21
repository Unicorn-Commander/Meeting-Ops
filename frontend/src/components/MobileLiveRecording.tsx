import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Mic, Square, ChevronUp, X, AlertCircle, Loader2, CheckCircle2, Smartphone } from 'lucide-react';
import { useUploads } from '../contexts/UploadsContext';
import {
  buildRecordingFilename,
  isLikelyTouchDevice,
  pickRecorderTarget,
  tapAudioLevel,
  unlockAudioContext,
  type MediaRecorderTarget,
} from '../utils/mobileRecording';
import {
  getPreferredDeviceId,
  openMicrophoneStream,
} from '../utils/audioDevicePreference';
import {
  isAlwaysOnActive,
  setRecordActive,
} from '../utils/recordingPresence';
import ConfirmModal from './ConfirmModal';

type RecorderState = 'idle' | 'preparing' | 'recording' | 'finalizing' | 'uploading';

const TITLE_STORAGE_KEY = 'meetingops.mobile.title.v1';
const ACTIVE_RECORDING_KEY = 'meetingops.mobile.activeRecording.v1';
const AUDIO_SOURCE_KEY = 'meetingops.mobile.audioSource.v1';

type AudioSource = 'mic' | 'tab' | 'mic+tab';

function supportsTabCapture(): boolean {
  return typeof navigator !== 'undefined'
    && !!navigator.mediaDevices
    && typeof (navigator.mediaDevices as any).getDisplayMedia === 'function';
}

function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export default function MobileLiveRecording() {
  const { uploads, startUploads } = useUploads();
  const [state, setState] = useState<RecorderState>('idle');
  const [title, setTitle] = useState<string>(() => {
    const stored = localStorage.getItem(TITLE_STORAGE_KEY);
    if (stored) return stored;
    const now = new Date();
    return `Meeting ${now.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`;
  });
  const [duration, setDuration] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [moreOpen, setMoreOpen] = useState(false);
  const [transcript, setTranscript] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [recorderTarget, setRecorderTarget] = useState<MediaRecorderTarget | null>(null);
  const [lastUploadLocalId, setLastUploadLocalId] = useState<string | null>(null);
  const [audioSource, setAudioSource] = useState<AudioSource>(() => {
    const v = localStorage.getItem(AUDIO_SOURCE_KEY);
    return (v === 'tab' || v === 'mic+tab') ? v : 'mic';
  });
  // Collision-guard prompt — surfaces when the user taps Record while
  // always-on is capturing. We refuse to start until they confirm + stop
  // always-on from its own surface.
  const [collisionOpen, setCollisionOpen] = useState(false);
  const tabCaptureAvailable = supportsTabCapture();

  useEffect(() => {
    localStorage.setItem(AUDIO_SOURCE_KEY, audioSource);
  }, [audioSource]);

  const streamRef = useRef<MediaStream | null>(null);
  const auxStreamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);
  const levelTapRef = useRef<{ stop: () => void } | null>(null);
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setRecorderTarget(pickRecorderTarget());
  }, []);

  useEffect(() => {
    localStorage.setItem(TITLE_STORAGE_KEY, title);
  }, [title]);

  useEffect(() => {
    if (!transcriptScrollRef.current) return;
    const node = transcriptScrollRef.current;
    node.scrollTop = node.scrollHeight;
  }, [transcript]);

  useEffect(() => {
    if (state !== 'recording') return;
    const id = window.setInterval(() => {
      if (startTimeRef.current) {
        setDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    }, 500);
    tickRef.current = id;
    return () => { window.clearInterval(id); tickRef.current = null; };
  }, [state]);

  const cleanupCapture = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try { recorderRef.current.stop(); } catch { /* noop */ }
    }
    recorderRef.current = null;
    [streamRef.current, auxStreamRef.current].forEach((s) => {
      if (s) s.getTracks().forEach((track) => track.stop());
    });
    streamRef.current = null;
    auxStreamRef.current = null;
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
    if (levelTapRef.current) {
      levelTapRef.current.stop();
      levelTapRef.current = null;
    }
    setAudioLevel(0);
    // Cross-surface presence flag — clear here so error/unmount paths
    // free always-on. Idempotent.
    setRecordActive(false);
  }, []);

  useEffect(() => () => cleanupCapture(), [cleanupCapture]);

  const trackedUpload = useMemo(() => {
    if (!lastUploadLocalId) return null;
    return uploads.find((u) => u.localId === lastUploadLocalId) ?? null;
  }, [uploads, lastUploadLocalId]);

  const beginRecording = useCallback(async () => {
    setError(null);
    setPermissionDenied(false);

    // Cross-surface guard. If always-on is already capturing audio,
    // prompt the user instead of silently starting a second capture.
    if (isAlwaysOnActive()) {
      setCollisionOpen(true);
      return;
    }

    setState('preparing');
    unlockAudioContext();

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot capture audio. Update to the latest Safari or Chrome.');
      setState('idle');
      return;
    }

    let micStream: MediaStream | null = null;
    let tabStream: MediaStream | null = null;
    const wantsMic = audioSource === 'mic' || audioSource === 'mic+tab';
    const wantsTab = audioSource === 'tab' || audioSource === 'mic+tab';

    try {
      if (wantsMic) {
        // Honor the user's preferred mic from Settings. If the saved
        // device is unplugged we fall back to system default silently —
        // the user has no other place to keep the session alive.
        const opened = await openMicrophoneStream(getPreferredDeviceId(), {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        });
        micStream = opened.stream;
      }
      if (wantsTab) {
        if (!tabCaptureAvailable) {
          throw new Error('Tab audio capture requires a Chromium-based desktop browser');
        }
        const display = await (navigator.mediaDevices as any).getDisplayMedia({
          video: true,
          audio: true,
        });
        const audioTracks = display.getAudioTracks();
        if (audioTracks.length === 0) {
          display.getTracks().forEach((t: MediaStreamTrack) => t.stop());
          throw new Error('No tab audio captured. Check "Share tab audio" in the picker dialog.');
        }
        display.getVideoTracks().forEach((t: MediaStreamTrack) => t.stop());
        tabStream = new MediaStream(audioTracks);
      }
    } catch (err: any) {
      const denied = err?.name === 'NotAllowedError' || err?.name === 'SecurityError';
      setPermissionDenied(denied);
      micStream?.getTracks().forEach((t) => t.stop());
      tabStream?.getTracks().forEach((t) => t.stop());
      setError(denied
        ? 'Audio access was blocked. Allow microphone/tab capture and retry.'
        : `Could not start audio capture: ${err?.message ?? err}`);
      setState('idle');
      return;
    }

    let stream: MediaStream;
    if (micStream && tabStream) {
      const ctx = new AudioContext();
      const dest = ctx.createMediaStreamDestination();
      ctx.createMediaStreamSource(micStream).connect(dest);
      ctx.createMediaStreamSource(tabStream).connect(dest);
      stream = dest.stream;
      audioCtxRef.current = ctx;
      auxStreamRef.current = tabStream;
      streamRef.current = micStream;
    } else if (tabStream) {
      stream = tabStream;
      streamRef.current = tabStream;
    } else if (micStream) {
      stream = micStream;
      streamRef.current = micStream;
    } else {
      setError('No audio source selected.');
      setState('idle');
      return;
    }

    const target = recorderTarget ?? pickRecorderTarget();
    if (!target) {
      setError('MediaRecorder is unavailable in this browser.');
      stream.getTracks().forEach((track) => track.stop());
      setState('idle');
      return;
    }

    let recorder: MediaRecorder;
    try {
      recorder = target.mimeType ? new MediaRecorder(stream, { mimeType: target.mimeType }) : new MediaRecorder(stream);
    } catch (err: any) {
      setError(`Recorder failed to initialize: ${err?.message ?? err}`);
      stream.getTracks().forEach((track) => track.stop());
      setState('idle');
      return;
    }

    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onerror = (event: any) => {
      setError(`Recording error: ${event?.error?.message ?? 'unknown'}`);
      cleanupCapture();
      setState('idle');
    };

    // streamRef/auxStreamRef were set above per source; don't clobber here.
    recorderRef.current = recorder;
    levelTapRef.current = tapAudioLevel(stream, setAudioLevel);

    recorder.start(2000);
    startTimeRef.current = Date.now();
    setDuration(0);
    setTranscript([]);
    setLastUploadLocalId(null);
    setState('recording');
    // Flip the cross-surface presence flag — always-on refuses to start
    // while this is true. cleanupCapture + finishRecording clear it.
    setRecordActive(true);

    localStorage.setItem(ACTIVE_RECORDING_KEY, JSON.stringify({
      startedAt: startTimeRef.current,
      title,
      mimeType: target.mimeType,
      extension: target.extension,
    }));
  }, [cleanupCapture, recorderTarget, title]);

  const finishRecording = useCallback(async () => {
    if (state !== 'recording') return;
    setState('finalizing');
    const recorder = recorderRef.current;
    if (!recorder) {
      cleanupCapture();
      setState('idle');
      return;
    }

    const completion = new Promise<Blob>((resolve) => {
      const handler = () => {
        const target = recorderTarget ?? pickRecorderTarget();
        const mime = target?.mimeType || 'audio/webm';
        resolve(new Blob(chunksRef.current, { type: mime }));
      };
      recorder.addEventListener('stop', handler, { once: true });
    });

    try {
      recorder.stop();
    } catch (err) {
      // Treat as completed; fall through to assembly.
    }

    const blob = await completion;
    cleanupCapture();
    localStorage.removeItem(ACTIVE_RECORDING_KEY);

    if (blob.size === 0) {
      setError('No audio was captured. Check your microphone permissions and try again.');
      setState('idle');
      return;
    }

    const target = recorderTarget ?? pickRecorderTarget();
    const extension = target?.extension ?? 'webm';
    const mime = target?.mimeType || blob.type || 'audio/webm';
    const filename = buildRecordingFilename(extension, title);
    const file = new File([blob], filename, { type: mime, lastModified: Date.now() });

    setState('uploading');
    const localId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setLastUploadLocalId(localId);
    try {
      await startUploads([file], { action: 'transcribe' });
    } catch (err: any) {
      setError(err?.message ?? 'Upload failed.');
    } finally {
      setState('idle');
      setDuration(0);
    }
  }, [cleanupCapture, recorderTarget, startUploads, state, title]);

  const handlePrimaryTap = useCallback(() => {
    if (state === 'idle') {
      void beginRecording();
    } else if (state === 'recording') {
      void finishRecording();
    }
  }, [beginRecording, finishRecording, state]);

  const isBusy = state === 'preparing' || state === 'finalizing' || state === 'uploading';
  const buttonLabel = state === 'idle'
    ? 'Tap to record'
    : state === 'preparing'
      ? 'Starting mic...'
      : state === 'recording'
        ? 'Tap to stop'
        : state === 'finalizing'
          ? 'Finalizing...'
          : 'Uploading...';

  const supportsRecording = isLikelyTouchDevice() && typeof MediaRecorder !== 'undefined';

  const helperText = !supportsRecording
    ? 'This phone does not support in-browser recording. Use the desktop layout, or upload an existing audio file from Sessions.'
    : error
      ? error
      : 'Recordings upload to Meeting-Ops automatically when you stop. The page can stay open while you talk.';

  return (
    <div className="flex flex-col bg-zinc-950 text-zinc-100 min-h-screen md:hidden"
         style={{
           paddingTop: 'env(safe-area-inset-top)',
           paddingLeft: 'env(safe-area-inset-left)',
           paddingRight: 'env(safe-area-inset-right)',
         }}>
      <div className="px-4 pt-4 pb-2 border-b border-zinc-800 flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-fuchsia-500 to-indigo-500 flex items-center justify-center shrink-0">
          <Mic className="w-4 h-4 text-white" />
        </div>
        <input
          aria-label="Meeting title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={state === 'recording' || state === 'uploading'}
          className="flex-1 bg-transparent text-base font-semibold text-white outline-none border-b border-transparent focus:border-fuchsia-500 transition-colors py-1 disabled:text-zinc-400 disabled:cursor-not-allowed"
          placeholder="Meeting title"
        />
      </div>

      <div className="px-4 pt-4 pb-3 flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <div className="text-3xl font-mono tabular-nums text-white">{formatDuration(duration)}</div>
          <div className="text-xs uppercase tracking-wider text-zinc-400">
            {state === 'recording' ? (
              <span className="text-red-300 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" /> Live
              </span>
            ) : state === 'preparing' ? 'Starting'
              : state === 'finalizing' ? 'Finalizing'
                : state === 'uploading' ? 'Uploading'
                  : 'Ready'}
          </div>
        </div>

        <div className="h-3 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-fuchsia-500 to-indigo-500 transition-[width] duration-100"
            style={{ width: `${Math.round(Math.min(1, audioLevel) * 100)}%` }}
          />
        </div>

        {trackedUpload && (
          <div className="rounded-xl bg-zinc-900/80 border border-zinc-800 px-3 py-2 flex items-center gap-3 text-xs">
            {trackedUpload.stage === 'done' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : trackedUpload.stage === 'failed' ? (
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            ) : (
              <Loader2 className="w-4 h-4 text-fuchsia-400 shrink-0 animate-spin" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-zinc-200 truncate">{trackedUpload.filename}</div>
              <div className="text-zinc-500">{trackedUpload.stage} {trackedUpload.progress ? `· ${trackedUpload.progress}%` : ''}</div>
            </div>
          </div>
        )}
      </div>

      <div
        ref={transcriptScrollRef}
        className="flex-1 overflow-y-auto px-4 pb-40 pt-2 space-y-2 text-sm leading-relaxed"
      >
        {/* Phase A mobile gate explainer. The live-transcript and
            live-summary panes are intentionally absent on mobile —
            phones can't run Parakeet 0.6B or the in-browser LLM well
            enough to be honest about it. We frame this as a deliberate
            mode, not a missing feature. */}
        <div className="rounded-xl bg-sky-500/5 border border-sky-500/30 p-4 text-sm">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sky-500/20 text-sky-300">
              <Smartphone className="h-4 w-4" />
            </div>
            <div>
              <div className="font-medium text-sky-100 mb-1">Capture-only mode</div>
              <div className="text-zinc-300">
                Your device captures audio and uploads it as you record.
                The full transcript and AI summary will be ready about a
                minute after the meeting ends, on the session page.
              </div>
            </div>
          </div>
        </div>
        {transcript.length === 0 ? (
          <div className="rounded-xl bg-zinc-900/60 border border-zinc-800 p-4 text-zinc-400 text-sm">
            <div className="font-medium text-zinc-200 mb-1">{state === 'recording' ? 'Listening…' : 'No transcript yet'}</div>
            <div>{helperText}</div>
          </div>
        ) : (
          transcript.map((line, idx) => (
            <div key={idx} className="rounded-lg bg-zinc-900/40 border border-zinc-900 px-3 py-2">{line}</div>
          ))
        )}
      </div>

      <div
        className="fixed bottom-0 left-0 right-0 z-30 px-4 pt-3 bg-zinc-950/90 backdrop-blur border-t border-zinc-800"
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}
      >
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setMoreOpen(true)}
            className="h-16 min-w-16 px-4 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-200 active:bg-zinc-800 transition-colors flex items-center justify-center gap-2"
            aria-label="More controls"
          >
            <ChevronUp className="w-5 h-5" />
            <span className="text-xs">More</span>
          </button>
          <button
            type="button"
            onClick={handlePrimaryTap}
            disabled={isBusy || !supportsRecording}
            className={`flex-1 min-h-[64px] h-16 rounded-2xl text-white font-semibold text-base flex items-center justify-center gap-2 active:scale-[0.98] transition-all shadow-lg shadow-fuchsia-900/30 ${
              state === 'recording'
                ? 'bg-red-600 active:bg-red-500'
                : 'bg-gradient-to-r from-fuchsia-600 to-indigo-600 active:from-fuchsia-500 active:to-indigo-500'
            } ${(isBusy || !supportsRecording) ? 'opacity-60' : ''}`}
            aria-pressed={state === 'recording'}
          >
            {state === 'recording' ? <Square className="w-6 h-6" fill="currentColor" /> : <Mic className="w-6 h-6" />}
            <span>{buttonLabel}</span>
          </button>
        </div>
        {permissionDenied && (
          <div className="mt-3 rounded-lg bg-red-900/30 border border-red-800/60 px-3 py-2 text-xs text-red-200 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {moreOpen && (
        <div className="fixed inset-0 z-40 flex flex-col">
          <button
            type="button"
            className="flex-1 bg-black/60"
            onClick={() => setMoreOpen(false)}
            aria-label="Close panel"
          />
          <div
            className="bg-zinc-950 border-t border-zinc-800 rounded-t-3xl px-5 pt-4"
            style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 16px)' }}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold text-base">Recording options</h2>
              <button
                type="button"
                onClick={() => setMoreOpen(false)}
                className="w-9 h-9 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-300"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-4 text-sm text-zinc-300">
              <div>
                <div className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Audio source</div>
                <div className="grid grid-cols-3 gap-2">
                  {(['mic', 'tab', 'mic+tab'] as AudioSource[]).map((opt) => {
                    const disabled = (opt !== 'mic' && !tabCaptureAvailable) || state === 'recording';
                    const active = audioSource === opt;
                    const label = opt === 'mic' ? 'Mic' : opt === 'tab' ? 'Tab' : 'Mic + Tab';
                    return (
                      <button
                        key={opt}
                        type="button"
                        disabled={disabled}
                        onClick={() => setAudioSource(opt)}
                        className={`rounded-lg border px-2 py-2 text-xs transition-colors ${
                          active
                            ? 'bg-fuchsia-600 border-fuchsia-500 text-white'
                            : 'bg-zinc-900 border-zinc-800 text-zinc-200 active:bg-zinc-800'
                        } ${disabled ? 'opacity-40' : ''}`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  {tabCaptureAvailable
                    ? 'Tab capture (Zoom Web / Meet / etc.) needs you to pick a browser tab and tick "Share tab audio" in the picker.'
                    : 'Tab capture is desktop-Chromium only. iOS Safari only supports mic.'}
                </div>
              </div>
              <div>
                <div className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Audio format</div>
                <div className="text-zinc-200">
                  {recorderTarget?.mimeType
                    ? `${recorderTarget.mimeType} (.${recorderTarget.extension})`
                    : 'Default browser format'}
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  Safari emits audio/mp4 (m4a) only. The upload pipeline transcodes either way.
                </div>
              </div>
              <div>
                <div className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Install</div>
                <div className="text-zinc-200">
                  Tap the Share icon, then "Add to Home Screen" to launch Meet-Ops without the Safari chrome.
                </div>
              </div>
              <div>
                <div className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Sessions</div>
                <a
                  href="#/sessions"
                  className="inline-flex items-center px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-200 active:bg-zinc-800"
                  onClick={() => setMoreOpen(false)}
                >
                  View completed sessions
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Cross-surface collision guard for mobile. Mirrors the desktop
          flow: refuses to start a tap-Record while always-on is live. */}
      <ConfirmModal
        isOpen={collisionOpen}
        title="Always-on is already recording"
        description={(
          <>
            Always-on capture is currently running. Stop it from the
            Always-on panel, then tap Record again.
          </>
        )}
        confirmLabel="Got it"
        cancelLabel="Cancel"
        tone="danger"
        onConfirm={() => setCollisionOpen(false)}
        onCancel={() => setCollisionOpen(false)}
      />
    </div>
  );
}
