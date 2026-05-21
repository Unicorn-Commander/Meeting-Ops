import { useMemo, useRef, useState, useEffect } from 'react';
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Headphones,
  Lightbulb,
  Mic,
  PanelTopOpen,
  Pause,
  Play,
  RefreshCw,
  RotateCw,
  Smartphone,
  Sparkles,
  Square,
  Trash2,
  UploadCloud,
  Users,
  X,
} from 'lucide-react';
import { useAlwaysOn, type AlwaysOnSummarySlice } from '../contexts/AlwaysOnContext';
import AlwaysOnPopout, { isDocumentPictureInPictureSupported } from './AlwaysOnPopout';
import { LIVE_SUMMARY_THRESHOLDS } from '../services/inBrowserLLM';
import AudioMeter from './AudioMeter';
import SessionMicChip from './SessionMicChip';
import ConfirmModal from './ConfirmModal';
import {
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

/**
 * Persisted flag — once the user clicks "Got it" on the audio-source
 * onboarding hint, we never show it again. Keyed under the existing
 * `meetingops.*` namespace alongside other UI prefs.
 */
const AUDIO_SOURCE_HINT_DISMISSED_KEY = 'meetingops.alwayson.audioSourceHintDismissed';

function readAudioSourceHintDismissed(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(AUDIO_SOURCE_HINT_DISMISSED_KEY) === '1';
  } catch {
    // Storage disabled (private window, quota, etc.) — treat as dismissed
    // so we don't loop on a banner the user can't dismiss.
    return true;
  }
}

function writeAudioSourceHintDismissed(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(AUDIO_SOURCE_HINT_DISMISSED_KEY, '1');
  } catch {
    // best-effort; banner will re-show next session but that's harmless
  }
}

interface AudioSourceHintBannerProps {
  onDismiss: () => void;
}

/**
 * First-time onboarding hint. Sits above the AudioSourcePicker and
 * nudges the user toward the use-case framing — pick "Online meeting"
 * to capture other voices from Zoom/Meet/Teams, "In-person, just me"
 * for solo notes, "Mixed" for hybrid. Dismissible; once dismissed,
 * never shown again.
 */
function AudioSourceHintBanner({ onDismiss }: AudioSourceHintBannerProps) {
  return (
    <div
      role="region"
      aria-label="Audio source tip"
      className="mt-5 flex items-start gap-3 rounded-lg border border-sky-500/40 bg-gradient-to-br from-sky-500/10 to-fuchsia-500/10 px-4 py-3 text-sm text-zinc-100"
    >
      <Lightbulb className="mt-0.5 h-5 w-5 flex-shrink-0 text-sky-300" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-white">Pick the kind of meeting you're in</div>
        <p className="mt-1 text-[13px] leading-5 text-zinc-300">
          <span className="font-medium text-sky-200">Online meeting</span> captures the
          meeting tab plus your mic so remote voices land in the transcript.{' '}
          <span className="font-medium text-zinc-200">In-person, just me</span> is your
          mic only.{' '}
          <span className="font-medium text-sky-200">Mixed</span> is both, for hybrid
          calls.
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-100 transition hover:bg-sky-500/20"
        >
          Got it
        </button>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss tip"
        className="rounded-md p-1 text-zinc-400 transition hover:bg-zinc-800/60 hover:text-zinc-100"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

interface AudioSourcePickerProps {
  value: AudioSourceMode;
  onChange: (mode: AudioSourceMode) => void;
  /** Disable picking once a session is live. Picker re-enables when idle. */
  disabled: boolean;
}

/**
 * Three use-case cards Aaron asked for — users don't think in
 * Mic/Tab/Mic+Tab, they think "I'm in a Zoom call" or "sitting at my
 * desk." Each card maps 1:1 to an AudioSourceMode under the hood:
 *
 *   In-person, just me   →  'mic'      (your microphone only)
 *   Online meeting       →  'mic+tab'  (default — captures meeting tab
 *                                       AND your voice, per Aaron's
 *                                       "regardless, capturing audio
 *                                       from people in the meeting")
 *   Mixed                →  'mic+tab'  (explicitly hybrid, same engine
 *                                       wiring but labeled differently
 *                                       so the picker reads cleanly for
 *                                       Aaron's "in-person + online"
 *                                       case)
 *
 * Within "Online meeting" we expose a sub-toggle to drop the mic if
 * the user is observing silently — flips the mode to 'tab'. Within
 * "In-person, just me" we expose the reciprocal — add tab if you're
 * also on a call — flips to 'mic+tab'. Both sub-toggles persist as
 * part of the same audioSourceMode setting, so behavior is durable
 * across page reloads without a second storage key.
 *
 * Advanced expander shows the raw Mic / Tab / Mic+Tab buttons for
 * power users who want to skip the framing.
 */

type UseCase = 'inperson' | 'online' | 'mixed';

function modeToUseCase(mode: AudioSourceMode): UseCase {
  // We treat 'tab' as a sub-state of 'online' (online + silent observer).
  // 'mic' is in-person, 'mic+tab' could be either online-active or mixed.
  // The last-explicit-pick is remembered via localStorage so we don't
  // bounce the user between two cards every time they reload.
  if (mode === 'mic') return 'inperson';
  if (mode === 'tab') return 'online';
  // mic+tab — fall back to the user's last-explicit choice if we have
  // one; otherwise default to 'online' (the more common case per Aaron).
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem(USE_CASE_HINT_KEY);
      if (stored === 'mixed' || stored === 'online') return stored;
    } catch {
      /* ignore */
    }
  }
  return 'online';
}

const USE_CASE_HINT_KEY = 'meetingops.alwayson.useCaseHint';

function rememberUseCase(uc: UseCase): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(USE_CASE_HINT_KEY, uc);
  } catch {
    /* ignore */
  }
}

function AudioSourcePicker({ value, onChange, disabled }: AudioSourcePickerProps) {
  const tabSupported = isTabCaptureSupported();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const useCase = modeToUseCase(value);

  // Sub-toggle for "Online meeting" — when true (default), include mic
  // on top of tab audio. When false, capture tab only (silent observer).
  const onlineIncludesMic = value === 'mic+tab';
  // Sub-toggle for "In-person, just me" — when true, ALSO include tab
  // (e.g. you're in-person AND on a call). When false (default), mic only.
  const inpersonIncludesTab = value === 'mic+tab' && useCase === 'mixed';

  const pickInperson = () => {
    rememberUseCase('inperson');
    onChange('mic');
  };
  const pickOnline = () => {
    rememberUseCase('online');
    // Default Online = mic+tab (per Aaron: "capturing audio from people
    // in the meeting" is non-negotiable, but mic-on-top is the right
    // default for an active participant). Sub-toggle below can flip
    // to tab-only.
    onChange('mic+tab');
  };
  const pickMixed = () => {
    rememberUseCase('mixed');
    onChange('mic+tab');
  };

  const cards: Array<{
    id: UseCase;
    icon: React.ElementType;
    title: string;
    sub: string;
    blurb: string;
    onClick: () => void;
    disabled: boolean;
  }> = [
    {
      id: 'inperson',
      icon: Mic,
      title: 'In-person, just me',
      sub: 'Solo notes / room mic',
      blurb: "Just my microphone. Best when no one else is on a call.",
      onClick: pickInperson,
      disabled,
    },
    {
      id: 'online',
      icon: Headphones,
      title: 'Online meeting',
      sub: 'Zoom / Meet / Teams',
      blurb: 'Captures the meeting tab audio. Includes my mic by default.',
      onClick: pickOnline,
      disabled: disabled || !tabSupported,
    },
    {
      id: 'mixed',
      icon: Users,
      title: 'Mixed',
      sub: 'Me + meeting audio',
      blurb: 'Both my mic AND a shared tab. For in-person + remote calls.',
      onClick: pickMixed,
      disabled: disabled || !tabSupported,
    },
  ];

  return (
    <div className="mt-5 rounded-lg border border-zinc-800 bg-black/20 px-4 py-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-zinc-200">
          What kind of meeting?
        </span>
        {(value === 'tab' || value === 'mic+tab') && !disabled && (
          <span className="text-[11px] text-zinc-500">
            You'll pick a tab after clicking Start.
          </span>
        )}
      </div>

      <div
        className="grid grid-cols-1 gap-2 sm:grid-cols-3"
        role="radiogroup"
        aria-label="Audio source use case"
      >
        {cards.map((card) => {
          const Icon = card.icon;
          const active = useCase === card.id;
          return (
            <button
              key={card.id}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={card.disabled}
              onClick={card.onClick}
              className={`flex flex-col items-start gap-2 rounded-lg border px-3 py-3 text-left text-xs transition-colors ${
                active
                  ? 'border-fuchsia-500 bg-fuchsia-600/20 text-white'
                  : 'border-zinc-800 bg-zinc-900 text-zinc-200 hover:bg-zinc-800'
              } ${card.disabled ? 'cursor-not-allowed opacity-40' : ''}`}
              title={
                card.id !== 'inperson' && !tabSupported
                  ? 'Tab audio requires a Chromium-based desktop browser'
                  : undefined
              }
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                <span className="font-semibold">{card.title}</span>
              </div>
              <div className="text-[11px] text-zinc-400">{card.sub}</div>
              <div className="text-[11px] leading-4 text-zinc-500">{card.blurb}</div>
            </button>
          );
        })}
      </div>

      {/* Sub-toggles. Online-meeting card lets the user drop their mic
          for silent observation. In-person card lets the user add tab
          audio when they're also dialed into a call. Both flip the
          underlying mode without leaving the chosen use case. */}
      {useCase === 'online' && !disabled && (
        <label className="mt-3 flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-xs text-zinc-300">
          <input
            type="checkbox"
            checked={onlineIncludesMic}
            onChange={(e) => onChange(e.target.checked ? 'mic+tab' : 'tab')}
            className="h-3.5 w-3.5 accent-fuchsia-500"
          />
          <span>
            Also include my mic{' '}
            <span className="text-zinc-500">(recommended for active participants)</span>
          </span>
        </label>
      )}
      {useCase === 'inperson' && !disabled && tabSupported && (
        <label className="mt-3 flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-xs text-zinc-300">
          <input
            type="checkbox"
            checked={inpersonIncludesTab}
            onChange={(e) => {
              if (e.target.checked) {
                rememberUseCase('mixed');
                onChange('mic+tab');
              } else {
                onChange('mic');
              }
            }}
            className="h-3.5 w-3.5 accent-fuchsia-500"
          />
          <span>
            Include meeting tab audio{' '}
            <span className="text-zinc-500">(if I'm also on a call)</span>
          </span>
        </label>
      )}

      {!tabSupported && (
        <p className="mt-2 text-[11px] text-zinc-500">
          Tab audio requires a Chromium-based desktop browser (Chrome / Edge / Brave).
          Mic-only still works everywhere.
        </p>
      )}

      {/* Advanced expander — raw mode picker for power users who want
          the unframed semantics. Same three modes, no copy. */}
      <button
        type="button"
        onClick={() => setShowAdvanced((s) => !s)}
        className="mt-3 inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200"
        aria-expanded={showAdvanced}
      >
        {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        Advanced: pick audio source manually
      </button>
      {showAdvanced && (
        <div className="mt-2 grid grid-cols-3 gap-2" role="radiogroup" aria-label="Raw audio source">
          {(
            [
              { id: 'mic', label: 'Mic', sub: 'getUserMedia' },
              { id: 'tab', label: 'Tab', sub: 'getDisplayMedia' },
              { id: 'mic+tab', label: 'Mic + Tab', sub: 'Web Audio mix' },
            ] as Array<{ id: AudioSourceMode; label: string; sub: string }>
          ).map((opt) => {
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
                className={`rounded-lg border px-2 py-1.5 text-left text-[11px] transition-colors ${
                  active
                    ? 'border-fuchsia-500 bg-fuchsia-600/20 text-white'
                    : 'border-zinc-800 bg-zinc-900 text-zinc-200 hover:bg-zinc-800'
                } ${optDisabled ? 'cursor-not-allowed opacity-40' : ''}`}
              >
                <div className="font-semibold">{opt.label}</div>
                <div className="text-[10px] text-zinc-500">{opt.sub}</div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface InSessionSourceMenuProps {
  /** Current mode from the engine. */
  value: AudioSourceMode;
  /** Triggered after the user confirms the swap. */
  onSwap: (mode: AudioSourceMode) => Promise<void>;
  /** True while a swap is in flight; disables the menu. */
  swapping: boolean;
}

/**
 * In-session source dropdown — Aaron's "would be nice if that could
 * be changed on the fly" feature. Renders as a chip-shaped button that
 * opens a menu of the three use cases. Picking a different one triggers
 * a confirm modal (cheap, but Aaron explicitly wanted users to know
 * the current chunk would finalize). On confirm we call
 * `alwaysOn.switchAudioSource` which goes through the same opener
 * the device-swap uses — ~200ms gap.
 */
function InSessionSourceMenu({ value, onSwap, swapping }: InSessionSourceMenuProps) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<AudioSourceMode | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const tabSupported = isTabCaptureSupported();
  const useCase = modeToUseCase(value);

  // Close on outside click — simple captured-handler pattern, no
  // popper or focus trap (the menu is tiny and self-contained).
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener('mousedown', onDoc);
    return () => window.removeEventListener('mousedown', onDoc);
  }, [open]);

  const friendlyLabel: Record<UseCase, string> = {
    inperson: 'In-person',
    online: 'Online meeting',
    mixed: 'Mixed',
  };
  const friendlyIcon: Record<UseCase, React.ElementType> = {
    inperson: Mic,
    online: Headphones,
    mixed: Users,
  };
  const Icon = friendlyIcon[useCase];

  const items: Array<{ uc: UseCase; mode: AudioSourceMode; label: string; disabled: boolean }> = [
    { uc: 'inperson', mode: 'mic', label: 'In-person, just me', disabled: false },
    { uc: 'online', mode: 'mic+tab', label: 'Online meeting', disabled: !tabSupported },
    { uc: 'mixed', mode: 'mic+tab', label: 'Mixed (me + meeting)', disabled: !tabSupported },
  ];

  return (
    <div ref={containerRef} className="relative inline-flex">
      <button
        type="button"
        disabled={swapping}
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
          value === 'mic'
            ? 'border-zinc-700 bg-zinc-800/70 text-zinc-200 hover:bg-zinc-800'
            : 'border-sky-500/40 bg-sky-500/10 text-sky-200 hover:bg-sky-500/20'
        } disabled:cursor-not-allowed disabled:opacity-50`}
        title="Click to switch the audio source mid-session"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Icon className="h-3.5 w-3.5" />
        Source: {friendlyLabel[useCase]}
        <ChevronDown className="h-3 w-3 opacity-60" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1 w-56 rounded-lg border border-zinc-700 bg-zinc-900 p-1 shadow-xl shadow-black/40"
        >
          {items.map((item) => {
            const ItemIcon = friendlyIcon[item.uc];
            const active = useCase === item.uc;
            return (
              <button
                key={item.uc}
                role="menuitemradio"
                aria-checked={active}
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  if (active) return; // no-op pick of current source
                  setPending(item.mode);
                  // Sync the use-case hint so the next session reload
                  // remembers "Mixed" vs "Online" within mic+tab.
                  rememberUseCase(item.uc);
                }}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                  active
                    ? 'bg-fuchsia-600/20 text-white'
                    : 'text-zinc-200 hover:bg-zinc-800'
                } ${item.disabled ? 'cursor-not-allowed opacity-40' : ''}`}
              >
                <ItemIcon className="h-3.5 w-3.5" />
                {item.label}
                {active && <span className="ml-auto text-[10px] text-zinc-400">current</span>}
              </button>
            );
          })}
          {!tabSupported && (
            <div className="px-2 pt-1 pb-0.5 text-[10px] text-zinc-500">
              Tab capture needs a Chromium-based desktop browser.
            </div>
          )}
        </div>
      )}
      <ConfirmModal
        isOpen={pending !== null}
        title="Switch audio source mid-recording?"
        description={(
          <>
            The current chunk will finalize and the new source will take
            over. There's a brief audio gap (under a second) during the
            swap. Continue?
          </>
        )}
        confirmLabel="Switch"
        cancelLabel="Cancel"
        tone="primary"
        onConfirm={async () => {
          const target = pending;
          setPending(null);
          if (target) await onSwap(target);
        }}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}

export default function AlwaysOnControl() {
  const alwaysOn = useAlwaysOn();
  const [popoutRequestKey, setPopoutRequestKey] = useState(0);
  const [expandedSliceIds, setExpandedSliceIds] = useState<Set<string>>(new Set());
  // Lifecycle confirm modals. Both are dismissable; the destructive
  // Discard surfaces the consequences before firing.
  const [discardOpen, setDiscardOpen] = useState(false);
  const [newSessionOpen, setNewSessionOpen] = useState(false);
  // Brief inline "copied" indicator next to the session id chip.
  const [copiedSessionId, setCopiedSessionId] = useState(false);
  // First-time onboarding hint for the audio-source picker. Lazy-init
  // from localStorage so SSR-style guards still work and we only touch
  // storage once on mount.
  const [audioSourceHintDismissed, setAudioSourceHintDismissed] = useState<boolean>(
    () => readAudioSourceHintDismissed(),
  );
  const dismissAudioSourceHint = () => {
    writeAudioSourceHintDismissed();
    setAudioSourceHintDismissed(true);
  };
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
              {/* On-the-fly source dropdown. Aaron asked for the source
                  to be swappable mid-session, so this used to be a
                  read-only chip but is now a clickable menu. Picking a
                  different option opens a confirm modal and triggers
                  alwaysOn.switchAudioSource → engine.switchDevice with
                  the new mode (~200ms gap). */}
              <InSessionSourceMenu
                value={alwaysOn.audioSourceMode}
                swapping={alwaysOn.switchingDevice}
                onSwap={(mode) => alwaysOn.switchAudioSource(mode)}
              />
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
                Stop & save
              </button>
              {/* Discard — opens a confirm modal then hard-deletes the
                  current session. Disabled mid-stop because the engine is
                  in an inconsistent state until stop() resolves. */}
              <button
                onClick={() => setDiscardOpen(true)}
                disabled={alwaysOn.state === 'stopping'}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm font-medium text-red-200 transition hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                title="Permanently delete this recording"
              >
                <Trash2 className="h-4 w-4" />
                Discard
              </button>
              {/* New session — finalize current + start fresh. Confirmed
                  because the user may have intended Pause instead. */}
              <button
                onClick={() => setNewSessionOpen(true)}
                disabled={alwaysOn.state === 'stopping'}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                title="Save current and start a new session"
              >
                <RotateCw className="h-4 w-4" />
                New session
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

      {/* Session header — visible while a session is live. Shows the
          session ID (with click-to-copy), the start time, and elapsed.
          The elapsed metric is still rendered in the stats grid below
          for parity; the header just keeps the info above-the-fold. */}
      {isActive && alwaysOn.currentSessionId && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 bg-black/20 px-3 py-2 text-xs text-zinc-300">
          <span className="text-zinc-500">Session</span>
          <button
            type="button"
            onClick={async () => {
              if (!alwaysOn.currentSessionId) return;
              try {
                await navigator.clipboard.writeText(alwaysOn.currentSessionId);
                setCopiedSessionId(true);
                setTimeout(() => setCopiedSessionId(false), 1500);
              } catch {
                /* clipboard may be blocked; user can still see the truncated id */
              }
            }}
            className="inline-flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-900/70 px-2 py-1 font-mono text-[11px] text-zinc-200 hover:bg-zinc-800"
            title={`Click to copy ${alwaysOn.currentSessionId}`}
          >
            <span>
              {alwaysOn.currentSessionId.length > 12
                ? `${alwaysOn.currentSessionId.slice(0, 8)}...${alwaysOn.currentSessionId.slice(-4)}`
                : alwaysOn.currentSessionId}
            </span>
            <Copy className="h-3 w-3 text-zinc-500" aria-hidden="true" />
          </button>
          {copiedSessionId && (
            <span className="text-[11px] text-emerald-300">copied</span>
          )}
          {alwaysOn.sessionStartedAt && (
            <>
              <span className="text-zinc-700">|</span>
              <span className="text-zinc-500">Started</span>
              <span>{clockTime(alwaysOn.sessionStartedAt)}</span>
            </>
          )}
          <span className="text-zinc-700">|</span>
          <span className="text-zinc-500">Elapsed</span>
          <span className="font-mono">{formatDuration(alwaysOn.elapsedSeconds)}</span>
        </div>
      )}

      {/* Confirm modals for the destructive / disruptive controls.
          discardSession() hard-deletes the current session (audio +
          chunks + qdrant embeddings + DB row); restartSession() stops
          current and immediately starts a new one. */}
      <ConfirmModal
        isOpen={discardOpen}
        title="Discard this recording?"
        description={(
          <>
            Audio, transcript, and summaries for this session will be{' '}
            <span className="font-semibold text-red-200">deleted permanently</span>.
            This cannot be undone.
          </>
        )}
        confirmLabel="Discard"
        cancelLabel="Cancel"
        tone="danger"
        onConfirm={async () => {
          setDiscardOpen(false);
          await alwaysOn.discardSession();
        }}
        onCancel={() => setDiscardOpen(false)}
      />
      <ConfirmModal
        isOpen={newSessionOpen}
        title="Start a fresh session?"
        description={(
          <>
            The current session will be saved (chunks finalized) and a new
            session begins immediately. You can review the saved session
            from the Sessions list.
          </>
        )}
        confirmLabel="Start new session"
        cancelLabel="Cancel"
        tone="primary"
        onConfirm={async () => {
          setNewSessionOpen(false);
          await alwaysOn.restartSession();
        }}
        onCancel={() => setNewSessionOpen(false)}
      />

      {/* First-time onboarding hint for the audio-source picker. Hidden
          once dismissed (localStorage). Also suppressed in privacy mode
          since local-only users may have different routing concerns and
          we want to keep that surface focused. */}
      {!audioSourceHintDismissed && !alwaysOn.localOnly && (
        <AudioSourceHintBanner onDismiss={dismissAudioSourceHint} />
      )}

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

      {alwaysOn.isCaptureOnlyMode ? (
        // Phase A mobile gate. Browser STT + LLM are skipped on phones
        // and tablets — both panes would be empty anyway, so we render
        // a friendly explainer in their place. Recording duration,
        // audio meter, and the stop button stay above; the full
        // transcript and summary land in the session ~60s after stop
        // via the server reprocess pass.
        <div className="mt-5 rounded-lg border border-sky-500/30 bg-sky-500/5 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-500/20 text-sky-300">
              <Smartphone className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-medium text-sky-100">Capture-only mode</div>
              <p className="mt-1 text-sm text-zinc-300">
                Your device captures audio and uploads it as you record. The
                full transcript and AI summary will be ready about a minute
                after the meeting ends, on the session page.
              </p>
            </div>
          </div>
        </div>
      ) : (
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
      )}
    </section>
  );
}
