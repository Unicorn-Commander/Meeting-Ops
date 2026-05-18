import { useMemo, useState } from 'react';
import {
  Activity,
  Clock,
  PanelTopOpen,
  Pause,
  Play,
  RefreshCw,
  Sparkles,
  Square,
  UploadCloud,
} from 'lucide-react';
import { useAlwaysOn } from '../contexts/AlwaysOnContext';
import AlwaysOnPopout, { isDocumentPictureInPictureSupported } from './AlwaysOnPopout';

function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export default function AlwaysOnControl() {
  const alwaysOn = useAlwaysOn();
  const [popoutRequestKey, setPopoutRequestKey] = useState(0);
  const pipSupported = isDocumentPictureInPictureSupported();
  const isActive = alwaysOn.state === 'recording' || alwaysOn.state === 'paused' || alwaysOn.state === 'stopping';
  const transcriptText = useMemo(
    () => alwaysOn.liveTranscript.map((segment) => {
      const speaker = segment.speaker ? `${segment.speaker}: ` : '';
      return `${speaker}${segment.text}`;
    }).join('\n'),
    [alwaysOn.liveTranscript],
  );

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-5 shadow-xl shadow-black/20">
      <AlwaysOnPopout requestKey={popoutRequestKey} />

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
          <label className="mb-2 block text-sm font-medium text-zinc-300" htmlFor="always-on-summary">
            Live summary
          </label>
          <textarea
            id="always-on-summary"
            readOnly
            value={alwaysOn.summary.text}
            placeholder="No summary yet."
            className="h-52 w-full resize-none rounded-lg border border-zinc-800 bg-black/30 p-3 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
          />
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
            className="h-52 w-full resize-none rounded-lg border border-zinc-800 bg-black/30 p-3 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600"
          />
        </div>
      </div>
    </section>
  );
}
