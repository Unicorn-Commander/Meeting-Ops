import React from 'react';
import { Cpu, Users, Sparkles, FileText, ChevronDown, ChevronRight, Brain } from 'lucide-react';

// LiteLLM model ids currently loaded on the local GPU tier. Keep in sync
// with services/transcription_options.py LOCAL_LLM_MODELS.
export const LOCAL_LLM_MODELS: { id: string; label: string }[] = [
  { id: '', label: 'Org default (Gemma 4 26B MoE)' },
  { id: 'gemma-4-26b-moe', label: 'Gemma 4 26B MoE (default, fast + accurate)' },
  { id: 'qwen3.6-35b-moe', label: 'Qwen 3.6 35B MoE (highest quality)' },
  { id: 'qwen3.6-35b-moe-ud', label: 'Qwen 3.6 35B MoE UD (long-context)' },
  { id: 'qwen3.5-27b', label: 'Qwen 3.5 27B' },
  { id: 'qwen3.5-27b-opus-distill', label: 'Qwen 3.5 27B (Opus-distilled)' },
  { id: 'qwen3.5-35b-a3b', label: 'Qwen 3.5 35B A3B' },
  { id: 'gpt-oss-20b-cuda', label: 'GPT-OSS 20B (CUDA)' },
  { id: 'gpt-oss-120b', label: 'GPT-OSS 120B' },
  { id: 'gemma-4-e4b', label: 'Gemma 4 E4B (tiny / fast tier)' },
];

export interface TranscriptionOptions {
  stt_provider?: 'whisper' | 'parakeet' | null;
  stt_model?: string | null;
  language?: string | null;
  diarization_mode?: 'auto' | 'manual' | 'off' | null;
  diarization_num_speakers?: number | null;
  voice_fingerprint?: boolean | null;
  summary_template?: 'standard' | 'executive' | 'technical' | null;
  // LLM override for summarization. Empty = org default
  // (LLM_MODEL_QUALITY env -> gemma-4-26b-moe today).
  llm_model?: string | null;
  // When false (default), suppresses <think> blocks for Qwen 3.5/3.6 and
  // Gemma 4 chat templates. Flip on for reasoning-heavy work.
  llm_thinking?: boolean | null;
}

export const DEFAULT_TRANSCRIPTION_OPTIONS: TranscriptionOptions = {
  stt_provider: null,
  diarization_mode: null,
  voice_fingerprint: null,
  summary_template: null,
};

interface Props {
  value: TranscriptionOptions;
  onChange: (next: TranscriptionOptions) => void;
  /** Default expanded? Useful in modals where space allows. */
  defaultOpen?: boolean;
  /** Hide org-level note (used when caller already explained the override semantics). */
  hideHelp?: boolean;
}

export const TranscriptionOptionsPanel: React.FC<Props> = ({
  value,
  onChange,
  defaultOpen = false,
  hideHelp = false,
}) => {
  const [open, setOpen] = React.useState(defaultOpen);
  const set = <K extends keyof TranscriptionOptions>(k: K, v: TranscriptionOptions[K]) =>
    onChange({ ...value, [k]: v });

  const provider = value.stt_provider ?? '';
  const diarMode = value.diarization_mode ?? 'auto';
  const summaryTpl = value.summary_template ?? 'standard';
  const voiceFP = value.voice_fingerprint !== false; // default on

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900/50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <Sparkles className="h-4 w-4 text-purple-400" />
          Transcription options
          <span className="text-xs text-gray-500 font-normal">
            (optional, overrides org defaults)
          </span>
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500" />
        )}
      </button>
      {open && (
        <div className="space-y-4 border-t border-gray-800 px-4 py-4">
          {/* STT engine */}
          <div>
            <label className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-300">
              <Cpu className="h-3.5 w-3.5 text-cyan-400" />
              Speech-to-text engine
            </label>
            <select
              value={provider}
              onChange={(e) => set('stt_provider', (e.target.value || null) as any)}
              className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
            >
              <option value="">Use org default</option>
              <option value="whisper">whisper.cpp large-v3-turbo (accurate, ~9× realtime)</option>
              <option value="parakeet">NeMo Parakeet-TDT 1.1B (fast, ~30× realtime, word timestamps)</option>
            </select>
          </div>

          {/* Diarization */}
          <div>
            <label className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-300">
              <Users className="h-3.5 w-3.5 text-emerald-400" />
              Speaker diarization
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(['auto', 'manual', 'off'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => set('diarization_mode', mode)}
                  className={`rounded border px-3 py-2 text-xs ${
                    diarMode === mode
                      ? 'border-emerald-500 bg-emerald-500/10 text-emerald-200'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  {mode === 'auto'
                    ? 'Auto-detect'
                    : mode === 'manual'
                    ? 'Manual count'
                    : 'No diarization'}
                </button>
              ))}
            </div>
            {diarMode === 'manual' && (
              <div className="mt-2 flex items-center gap-3">
                <label className="text-xs text-gray-400">Speakers:</label>
                <input
                  type="number"
                  min={1}
                  max={24}
                  value={value.diarization_num_speakers ?? 2}
                  onChange={(e) =>
                    set('diarization_num_speakers', Math.max(1, Math.min(24, Number(e.target.value) || 1)))
                  }
                  className="w-20 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-white"
                />
              </div>
            )}
          </div>

          {/* Voice fingerprinting */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-300">
              <input
                type="checkbox"
                checked={voiceFP}
                onChange={(e) => set('voice_fingerprint', e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 text-purple-500"
                disabled={diarMode === 'off'}
              />
              <span className={diarMode === 'off' ? 'text-gray-500' : ''}>
                Match speakers against the org voice library
              </span>
            </label>
            {!hideHelp && (
              <p className="ml-5 mt-1 text-[11px] text-gray-500">
                When on, ECAPA voice embeddings are matched against enrolled SpeakerProfiles —
                each diarized cluster picks up a known person's name when confidence is high enough.
              </p>
            )}
          </div>

          {/* Summary template */}
          <div>
            <label className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-300">
              <FileText className="h-3.5 w-3.5 text-amber-400" />
              Summary style
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(['standard', 'executive', 'technical'] as const).map((tpl) => (
                <button
                  key={tpl}
                  type="button"
                  onClick={() => set('summary_template', tpl)}
                  className={`rounded border px-3 py-2 text-xs capitalize ${
                    summaryTpl === tpl
                      ? 'border-amber-500 bg-amber-500/10 text-amber-200'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  {tpl}
                </button>
              ))}
            </div>
          </div>

          {/* LLM model + thinking mode */}
          <div>
            <label className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-300">
              <Brain className="h-3.5 w-3.5 text-pink-400" />
              Summarization model
            </label>
            <select
              value={value.llm_model ?? ''}
              onChange={(e) => set('llm_model', e.target.value || null)}
              className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-pink-500 focus:outline-none"
            >
              {LOCAL_LLM_MODELS.map((m) => (
                <option key={m.id || '_default'} value={m.id}>{m.label}</option>
              ))}
            </select>
            <label className="mt-2 flex items-center gap-2 text-xs text-gray-300">
              <input
                type="checkbox"
                checked={value.llm_thinking === true}
                onChange={(e) => set('llm_thinking', e.target.checked ? true : null)}
                className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 text-pink-500"
              />
              <span>
                Enable model thinking traces (Qwen 3.5+ / Gemma 4)
                <span className="ml-1 text-[11px] text-gray-500">
                  (default off — thinking traces bloat output)
                </span>
              </span>
            </label>
          </div>
        </div>
      )}
    </div>
  );
};

/** Strip null / undefined values before sending to the backend. */
export function serializeTranscriptionOptions(
  opts: TranscriptionOptions,
): Record<string, any> | undefined {
  const out: Record<string, any> = {};
  for (const [k, v] of Object.entries(opts)) {
    if (v !== null && v !== undefined) out[k] = v;
  }
  return Object.keys(out).length ? out : undefined;
}

export default TranscriptionOptionsPanel;
