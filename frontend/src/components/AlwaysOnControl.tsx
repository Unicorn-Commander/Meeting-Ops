import { useMemo, useState } from 'react';
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Clock,
  Mic,
  MonitorSpeaker,
  PanelTopOpen,
  Pause,
  Play,
  RefreshCw,
  Sparkles,
  Square,
  UploadCloud,
} from 'lucide-react';
import { useAlwaysOn, type AlwaysOnSummarySlice } from '../contexts/AlwaysOnContext';
import AlwaysOnPopout, { isDocumentPictureInPictureSupported } from './AlwaysOnPopout';
import { LIVE_SUMMARY_THRESHOLDS } from '../services/inBrowserLLM';
import AudioMeter from './AudioMeter';
import SessionMicChip from './SessionMicChip';
import ConfirmModal from './ConfirmModal';
import {
  audioSourceLabel,
  isTabCaptureSupported,
  type AudioSourceMode,
} from '../utils/audioSourceStream';

function relativeTime(iso: string): string {
  const created = new Date(iso).getTime();
  const diffMs = Date.now() - created;
  const sec = Math.max(0, Math.floor(diffMs / 1000));
  if (sec < 5) return 'just now';
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const rem = Math.round(sec % 60);
  return `${min}m ${rem}s`;
}

interface SliceCardProps {
  slice: AlwaysOnSummarySlice;
  expanded: boolean;
  onToggle: () => void;
  highlight?: boolean;
}

function SliceCard({ slice, expanded, onToggle, highlight }: SliceCardProps) {
  const range = `words ${slice.transcriptStart}-${slice.transcriptEnd}`;
  return (
    <div
      className={`rounded-lg border ${highlight ? 'border-sky-500/40 bg-sky-500/5' : 'border-zinc-800 bg-black/30'} transition-colors`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-zinc-100 hover:bg-zinc-800/40 rounded-t-lg"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            <span title={slice.createdAt} className="text-zinc-300">{relativeTime(slice.createdAt)}</span>
            <span className="text-zinc-600">·</span>
            <span>{clockTime(slice.createdAt)}</span>
            <span className="text-zinc-600">·</span>
            <span>{range}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 font-medium text-sky-200">
              {slice.modelLabel}
            </span>
            <span className="rounded-full border border-zinc-700 bg-zinc-800/70 px-2 py-0.5 text-zinc-300">
              {formatDurationMs(slice.durationMs)}
            </span>
          </div>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
      </button>
      {expanded && (
        <div className="border-t border-zinc-800/80 px-4 py-3 text-sm leading-6 text-zinc-100 whitespace-pre-wrap">
          {slice.text}
        </div>
      )}
    </div>
  );
}

function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

interface AudioSourcePickerProps {
  value: AudioSourceMode;
  onChange: (mode: AudioSourceMode) => void;
  /** Disable picking once a session is live. Picker re-enables when idle. */
  disabled: boolean;
}

/**
 * Picker for the always-on session's audio source. Three radio options:
 *   - Mic: existing behavior, the user's chosen microphone
 *   - Tab audio: capture a Chrome tab's audio via getDisplayMedia
 *   - Mic + Tab: mix both (useful for in-person + remote hybrid)
 *
 * Tab + Mic+Tab are hidden in browsers without getDisplayMedia (Safari
 * on iOS, older browsers). The user-friendly explanation lives in the
 * helper text below the radio group — "you'll be prompted to pick a tab
 * after clicking Start".
 */
function AudioSourcePicker({ value, onChange, disabled }: AudioSourcePickerProps) {
  const tabSupported = isTabCaptureSupported();
  const options: { id: AudioSourceMode; label: string; sub: string }[] = [
    { id: 'mic', label: 'Mic', sub: 'Your microphone' },
    { id: 'tab', label: 'Tab audio', sub: 'Capture a Chrome tab' },
    { id: 'mic+tab', label: 'Mic + Tab', sub: 'Both, mixed' },
  ];

  return (
    <div className="mt-5 rounded-lg border border-zinc-800 bg-black/20 px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs uppercase tracking-wide text-zinc-500">
          Audio source
        </span>
        {value !== 'mic' && (value === 'tab' || value === 'mic+tab') && !disabled && (
          <span className="text-[11px] text-zinc-500">
            You'll pick a tab after clicking Start.
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Audio source for always-on">
        {options.map((opt) => {
          const isTabOption = opt.id !== 'mic';
          const optDisabled = disabled || (isTabOption && !tabSupported);
          const active = value === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={optDisabled}
              onClick={() => onChange(opt.id)}
              className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                active
                  ? 'border-fuchsia-500 bg-fuchsia-600/20 text-white'
                  : 'border-zinc-800 bg-zinc-900 text-zinc-200 hover:bg-zinc-800'
              } ${optDisabled ? 'cursor-not-allowed opacity-40' : ''}`}
              title={
                isTabOption && !tabSupported
                  ? 'Tab audio requires a Chromium-based desktop browser'
                  : undefined
              }
            >
              <div className="font-semibold">{opt.label}</div>
              <div className="text-[11px] text-zinc-400">{opt.sub}</div>
            </button>
          );
        })}
      </div>
      {!tabSupported && (
        <p className="mt-2 text-[11px] text-zinc-500">
          Tab audio requires a Chromium-based desktop browser (Chrome / Edge / Brave).
        </p>
      )}
    </div>
  );
}

export default function AlwaysOnControl() {
  const alwaysOn = useAlwaysOn();
  const [popoutRequestKey, setPopoutRequestKey] = useState(0);
  const [expandedSliceIds, setExpandedSliceIds] = useState<Set<string>>(new Set());
  const pipSupported = isDocumentPictureInPictureSupported();
  const isActive = alwaysOn.state === 'recording' || alwaysOn.state === 'paused' || alwaysOn.state === 'stopping';
  const transcriptText = useMemo(
    () => alwaysOn.liveTranscript.map((segment) => {
      const speaker = segment.speaker ? `${segment.speaker}: ` : '';
      return `${speaker}${segment.text}`;
    }).join('\n'),
    [alwaysOn.liveTranscript],
  );

  const orderedSlices = useMemo(
    () => [...alwaysOn.summary.slices].reverse(),
    [alwaysOn.summary.slices],
  );
  const latestSliceId = orderedSlices[0]?.id;
  const thresholdLabel = useMemo(() => {
    const match = LIVE_SUMMARY_THRESHOLDS.find((t) => t.id === alwaysOn.autoConfig.threshold);
    return match?.label ?? '';
  }, [alwaysOn.autoConfig.threshold]);

  const toggleSlice = (id: string) => {
    setExpandedSliceIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-5 shadow-xl shadow-black/20">
      <AlwaysOnPopout requestKey={popoutRequestKey} />

      {/* Simultaneous-recording guard. start() refuses to begin when the
          explicit Record button is active and sets startBlockedByRecord;
          this modal asks the user to stop the other one first. Dismissing
          it clears the flag — the user can then stop Record from its own
          surface and retry. */}
      <ConfirmModal
        isOpen={alwaysOn.startBlockedByRecord}
        title="Recording already in progress"
        description={(
          <>
            The Record button is already capturing audio. Stop that recording
            first, then try starting always-on again.
          </>
        )}
        confirmLabel="Got it"
        cancelLabel="Cancel"
        tone="danger"
        onConfirm={alwaysOn.clearStartBlocked}
        onCancel={alwaysOn.clearStartBlocked}
      />


      {/* Privacy-mode banners: live notice when local-only is active for
          the current session, and a degraded-mode warning when the user
          asked for local-only but WebGPU is missing. */}
      {alwaysOn.localOnly && (
        <div className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          Local-only mode — nothing leaves this device.
        </div>
      )}
      {alwaysOn.localOnlyForcedOff && !alwaysOn.localOnly && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          WebGPU required for local-only mode. Falling back to standard mode for this session.
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10 text-red-300">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Always-on recording</h2>
              <p className="text-sm text-zinc-400">{alwaysOn.statusText}</p>
            </div>
          </div>
          {alwaysOn.error && (
            <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              {alwaysOn.error}
            </div>
          )}
          {/* Active mic indicator + per-session override. Only shown while
              a session is live — the chip is meaningless when idle. The
              mic chip is hidden when the audio source isn't mic-based,
              since deviceId selection doesn't apply to tab capture. */}
          {isActive && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {(alwaysOn.audioSourceMode === 'mic' || alwaysOn.audioSourceMode === 'mic+tab') && (
                <>
                  <SessionMicChip
                    activeDeviceId={alwaysOn.activeMicDeviceId}
                    onSelect={(id) => void alwaysOn.switchMicDevice(id)}
                    disabled={alwaysOn.switchingDevice}
                  />
                  {alwaysOn.switchingDevice && (
                    <span className="text-xs text-zinc-400">Switching…</span>
                  )}
                </>
              )}
              {/* Audio source chip — shows what the session is currently
                  capturing. Read-only mid-session; the picker (below the
                  controls) is disabled while recording. */}
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
                  alwaysOn.audioSourceMode === 'mic'
                    ? 'border-zinc-700 bg-zinc-800/70 text-zinc-200'
                    : 'border-sky-500/40 bg-sky-500/10 text-sky-200'
                }`}
                title="Audio source for this session. Change before starting to use a different source."
              >
                {alwaysOn.audioSourceMode === 'mic' ? (
                  <Mic className="h-3.5 w-3.5" />
                ) : (
                  <MonitorSpeaker className="h-3.5 w-3.5" />
                )}
                {audioSourceLabel(alwaysOn.audioSourceMode)}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {alwaysOn.state === 'idle' ? (
            <button
              onClick={alwaysOn.start}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-red-500"
            >
              <Play className="h-4 w-4" />
              Start always-on
            </button>
          ) : (
            <>
              {alwaysOn.state === 'paused' ? (
                <button
                  onClick={alwaysOn.resume}
                  className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 transition hover:bg-emerald-500/20"
                >
                  <Play className="h-4 w-4" />
                  Resume
                </button>
              ) : (
                <button
                  onClick={alwaysOn.pause}
                  disabled={alwaysOn.state !== 'recording'}
                  className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Pause className="h-4 w-4" />
                  Pause
                </button>
              )}
              <button
                onClick={alwaysOn.stop}
                disabled={alwaysOn.state === 'stopping'}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            </>
          )}

          <button
            onClick={alwaysOn.triggerSummarize}
            disabled={!isActive || alwaysOn.liveTranscript.length === 0 || alwaysOn.summarizing}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-200 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {alwaysOn.summarizing ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Summarize now
          </button>

          <button
            onClick={() => setPopoutRequestKey(Date.now())}
            disabled={!pipSupported}
            title={pipSupported ? 'Open picture-in-picture view' : 'Picture-in-picture is only available in supported Chromium browsers.'}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <PanelTopOpen className="h-4 w-4" />
            Pop out
          </button>
        </div>
      </div>

      {/* Audio source picker. Lets the user passively listen to a tab
          (e.g. the meeting window in a separate Chrome tab) instead of
          just the local mic. Locked during recording — the picker only
          takes effect on the next start(). */}
      <AudioSourcePicker
        value={alwaysOn.audioSourceMode}
        onChange={alwaysOn.setAudioSourceMode}
        disabled={isActive || alwaysOn.state === 'starting'}
      />

      {/* Live VU meter — gives the user confidence the mic is hearing them
          even between speech chunks (the VAD indicator only flips during
          actual speech). Connected to the engine's live stream so we
          don't double-open getUserMedia. */}
      {isActive && alwaysOn.activeMicStream && (
        <div className="mt-5 rounded-lg border border-zinc-800 bg-black/30 px-3 py-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-xs uppercase tracking-wide text-zinc-500">
              Mic level
            </span>
          </div>
          <AudioMeter
            stream={alwaysOn.activeMicStream}
            compact
            showNumeric
            ariaLabel="Live microphone level"
          />
        </div>
      )}

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div className="rounded-lg border border-zinc-800 bg-black/20 px-3 py-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">VAD</div>
          <div className="mt-2 flex items-center gap-2 text-sm text-zinc-100">
            <span className={`h-2.5 w-2.5 rounded-full ${alwaysOn.vadActive ? 'bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.7)]' : 'bg-zinc-700'}`} />
            {alwaysOn.vadActive ? 'Speech' : 'Quiet'}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-black/20 px-3 py-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">Elapsed</div>
          <div className="mt-2 flex items-center gap-2 text-sm font-mono text-zinc-100">
            <Clock className="h-4 w-4 text-zinc-500" />
            {formatDuration(alwaysOn.elapsedSeconds)}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-black/20 px-3 py-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">Chunks</div>
          <div className="mt-2 flex items-center gap-2 text-sm text-zinc-100">
            <UploadCloud className="h-4 w-4 text-zinc-500" />
            {alwaysOn.chunksUploaded}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-black/20 px-3 py-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">Sessions</div>
          <div className="mt-2 text-sm text-zinc-100">{alwaysOn.sessionsCompleted}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-black/20 px-3 py-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">Current</div>
          <div className="mt-2 truncate text-sm text-zinc-100">{alwaysOn.currentSessionId || 'None'}</div>
        </div>
      </div>

      {alwaysOn.modelLoadProgress !== null && (
        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between text-xs text-zinc-500">
            <span>Model download</span>
            <span>{Math.round(alwaysOn.modelLoadProgress * 100)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-zinc-800">
            <div
              className="h-full bg-sky-400 transition-all"
              style={{ width: `${Math.round(alwaysOn.modelLoadProgress * 100)}%` }}
            />
          </div>
        </div>
      )}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="block text-sm font-medium text-zinc-300">Live summary</label>
            <span className="text-xs text-zinc-500">
              {alwaysOn.autoConfig.enabled
                ? `Auto-updates ${thresholdLabel.toLowerCase()}`
                : 'Manual mode'}
              {' · '}
              {alwaysOn.transcriptWordCount} words
            </span>
          </div>

          <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1">
            {alwaysOn.summary.currentDraft && (
              <div className="rounded-lg border border-sky-500/40 bg-sky-500/5 p-4">
                <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-sky-300">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  Generating next slice
                </div>
                <div className="text-sm leading-6 text-zinc-100 whitespace-pre-wrap">
                  {alwaysOn.summary.currentDraft}
                </div>
              </div>
            )}

            {orderedSlices.length === 0 && !alwaysOn.summary.currentDraft && (
              <div className="rounded-lg border border-dashed border-zinc-800 bg-black/20 p-4 text-sm text-zinc-500">
                {alwaysOn.autoConfig.enabled
                  ? 'Live summary will appear once enough conversation has been captured.'
                  : 'Auto-summarize is off. Use “Summarize now” to capture a slice.'}
              </div>
            )}

            {orderedSlices.map((slice) => (
              <SliceCard
                key={slice.id}
                slice={slice}
                expanded={slice.id === latestSliceId ? !expandedSliceIds.has(slice.id) : expandedSliceIds.has(slice.id)}
                onToggle={() => toggleSlice(slice.id)}
                highlight={slice.id === latestSliceId}
              />
            ))}
          </div>
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium text-zinc-300" htmlFor="always-on-transcript">
            Live transcript
          </label>
          <textarea
            id="always-on-transcript"
            readOnly
            value={transcriptText}
            placeholder="No transcript yet."
            className="h-[28rem] w-full resize-none rounded-lg border border-zinc-800 bg-black/30 p-3 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
          />
        </div>
      </div>
    </section>
  );
}
