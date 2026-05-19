import type {
  AppConfig,
  InitProgressReport,
  MLCEngine,
  ModelRecord,
} from '@mlc-ai/web-llm';
import { config } from '../config';

export const IN_BROWSER_LLM_MODEL_KEY = 'meetingops.inBrowserLLM.model.v1';
export const DEFAULT_MODEL_ID = 'qwen2.5-1.5b-instruct';

export const LIVE_SUMMARY_AUTO_KEY = 'meetingops.liveSummary.autoConfig.v1';

export type LiveSummaryThreshold =
  | 'words_200'
  | 'words_500'
  | 'minute_1'
  | 'minutes_5';

export interface LiveSummaryAutoConfig {
  enabled: boolean;
  threshold: LiveSummaryThreshold;
}

export const DEFAULT_AUTO_CONFIG: LiveSummaryAutoConfig = {
  enabled: true,
  threshold: 'words_500',
};

export const LIVE_SUMMARY_THRESHOLDS: Array<{
  id: LiveSummaryThreshold;
  label: string;
  kind: 'words' | 'time';
  value: number;
}> = [
  { id: 'words_200', label: 'Every 200 words', kind: 'words', value: 200 },
  { id: 'words_500', label: 'Every 500 words', kind: 'words', value: 500 },
  { id: 'minute_1', label: 'Every 1 minute', kind: 'time', value: 60_000 },
  { id: 'minutes_5', label: 'Every 5 minutes', kind: 'time', value: 300_000 },
];

export function getLiveSummaryAutoConfig(): LiveSummaryAutoConfig {
  if (typeof window === 'undefined') return DEFAULT_AUTO_CONFIG;
  const raw = window.localStorage.getItem(LIVE_SUMMARY_AUTO_KEY);
  if (!raw) return DEFAULT_AUTO_CONFIG;
  try {
    const parsed = JSON.parse(raw) as Partial<LiveSummaryAutoConfig>;
    const valid = LIVE_SUMMARY_THRESHOLDS.some((t) => t.id === parsed.threshold);
    return {
      enabled: parsed.enabled ?? DEFAULT_AUTO_CONFIG.enabled,
      threshold: valid ? (parsed.threshold as LiveSummaryThreshold) : DEFAULT_AUTO_CONFIG.threshold,
    };
  } catch {
    return DEFAULT_AUTO_CONFIG;
  }
}

export function setLiveSummaryAutoConfig(config: LiveSummaryAutoConfig): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(LIVE_SUMMARY_AUTO_KEY, JSON.stringify(config));
  try {
    window.dispatchEvent(
      new CustomEvent<LiveSummaryAutoConfig>('meetingops:live-summary-auto-config', {
        detail: config,
      }),
    );
  } catch { /* noop */ }
}

export interface SummaryParagraph {
  text: string;
  timestamp: string;
}

export interface SummaryResult {
  text: string;
  paragraphs: SummaryParagraph[];
}

export interface InBrowserModelOption {
  id: string;
  actualModelId: string | null;
  label: string;
  vramRequiredMB?: number;
  lowResourceRequired?: boolean;
  source: 'curated' | 'web-llm' | 'server';
}

export interface WebGPUStatus {
  state: 'ready' | 'limited' | 'unavailable';
  label: string;
  detail: string;
  forcedServer: boolean;
}

export interface SummarizeOptions {
  signal?: AbortSignal;
  onToken?: (token: string) => void;
  onProgress?: (report: InitProgressReport) => void;
  previousSummary?: string;
  sessionId?: string;
}

export interface PreloadOptions {
  signal?: AbortSignal;
  onProgress?: (report: InitProgressReport) => void;
}

export interface Summarizer {
  summarize(
    transcript: string,
    modelId: string,
    opts?: SummarizeOptions,
  ): AsyncIterable<string>;
  preloadModel(modelId: string, opts?: PreloadOptions): Promise<void>;
}

const CURATED_MODELS: Array<{
  id: string;
  actualModelId: string;
  label: string;
}> = [
  // Newest first. Entries whose actualModelId isn't published by web-llm
  // are silently filtered out at runtime (see records.find check below),
  // so we can stage future variants here optimistically — they appear in
  // the picker the moment web-llm ships them.
  {
    id: 'gemma-4-e2b-it',
    actualModelId: 'gemma4-E2B-it-q4f16_1-MLC',
    label: 'Gemma 4 E2B (text mode)',
  },
  {
    id: 'qwen3.6-1.7b',
    actualModelId: 'Qwen3.6-1.7B-q4f16_1-MLC',
    label: 'Qwen 3.6 1.7B',
  },
  {
    id: 'qwen3-1.7b',
    actualModelId: 'Qwen3-1.7B-q4f16_1-MLC',
    label: 'Qwen 3 1.7B',
  },
  {
    id: 'qwen3-0.6b',
    actualModelId: 'Qwen3-0.6B-q4f16_1-MLC',
    label: 'Qwen 3 0.6B (smallest, fastest)',
  },
  {
    id: 'gemma-3-1b-it',
    actualModelId: 'gemma3-1b-it-q4f16_1-MLC',
    label: 'Gemma 3 1B IT',
  },
  {
    id: 'qwen2.5-1.5b-instruct',
    actualModelId: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
    label: 'Qwen 2.5 1.5B Instruct',
  },
  {
    id: 'phi-3.5-mini-instruct',
    actualModelId: 'Phi-3.5-mini-instruct-q4f16_1-MLC',
    label: 'Phi 3.5 Mini Instruct (best quality)',
  },
];

let enginePromise: Promise<MLCEngine> | null = null;
let loadedActualModelId: string | null = null;
let webLLMModulePromise: Promise<typeof import('@mlc-ai/web-llm')> | null = null;
let cachedModelRecords: ModelRecord[] | null = null;

async function loadWebLLM(): Promise<typeof import('@mlc-ai/web-llm')> {
  if (!webLLMModulePromise) {
    webLLMModulePromise = import('@mlc-ai/web-llm').then((mod) => {
      cachedModelRecords = mod.prebuiltAppConfig.model_list.filter(
        (record) => (record.model_type ?? 0) === 0,
      );
      return mod;
    });
  }
  return webLLMModulePromise;
}

function llmRecords(): ModelRecord[] {
  return cachedModelRecords ?? [];
}

function findRecord(modelId: string): ModelRecord | undefined {
  return llmRecords().find((record) => record.model_id === modelId);
}

function displayName(modelId: string): string {
  return modelId
    .replace(/-MLC.*$/, '')
    .replace(/q[0-9]f[0-9]+(?:_[0-9])?/gi, '')
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function getWebGPUStatus(): WebGPUStatus {
  if (typeof navigator === 'undefined') {
    return {
      state: 'unavailable',
      label: 'Unavailable',
      detail: 'Browser APIs are not available.',
      forcedServer: true,
    };
  }

  const nav = navigator as Navigator & { gpu?: unknown; deviceMemory?: number };
  if (!nav.gpu) {
    return {
      state: 'unavailable',
      label: 'Unavailable',
      detail: 'This browser does not expose WebGPU.',
      forcedServer: true,
    };
  }

  const memoryGB = nav.deviceMemory;
  if (typeof memoryGB === 'number' && memoryGB < 4) {
    return {
      state: 'limited',
      label: 'Limited',
      detail: `${memoryGB} GB device memory detected; server mode is required.`,
      forcedServer: true,
    };
  }

  return {
    state: 'ready',
    label: 'Ready',
    detail: 'WebGPU is available for in-browser summaries.',
    forcedServer: false,
  };
}

export function getStoredModelId(): string {
  if (typeof window === 'undefined') return DEFAULT_MODEL_ID;
  const status = getWebGPUStatus();
  if (status.forcedServer) return 'server';
  return localStorage.getItem(IN_BROWSER_LLM_MODEL_KEY) || DEFAULT_MODEL_ID;
}

export function setStoredModelId(modelId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(IN_BROWSER_LLM_MODEL_KEY, modelId);
}

export function getAvailableModels(): InBrowserModelOption[] {
  const records = llmRecords();
  const seen = new Set<string>();
  const options: InBrowserModelOption[] = [
    {
      id: 'server',
      actualModelId: null,
      label: 'Server-side Qwen 3.6',
      source: 'server',
    },
  ];

  for (const curated of CURATED_MODELS) {
    const record = records.find((item) => item.model_id === curated.actualModelId);
    if (records.length > 0 && !record) continue;
    seen.add(curated.actualModelId);
    options.push({
      id: curated.id,
      actualModelId: curated.actualModelId,
      label: curated.label,
      vramRequiredMB: record?.vram_required_MB,
      lowResourceRequired: record?.low_resource_required,
      source: 'curated',
    });
  }

  for (const record of records) {
    if (seen.has(record.model_id)) continue;
    if (!/(qwen|gemma|phi|llama|smollm|olmo|mistral)/i.test(record.model_id)) {
      continue;
    }
    options.push({
      id: record.model_id,
      actualModelId: record.model_id,
      label: displayName(record.model_id),
      vramRequiredMB: record.vram_required_MB,
      lowResourceRequired: record.low_resource_required,
      source: 'web-llm',
    });
  }

  return options;
}

export async function refreshAvailableModels(): Promise<InBrowserModelOption[]> {
  await loadWebLLM();
  return getAvailableModels();
}

export function getModelLabel(modelId: string): string {
  if (!modelId) return 'Unknown';
  if (modelId === 'server') return 'Server Qwen 3.6';
  const option = getAvailableModels().find((item) => item.id === modelId);
  if (option) return option.label;
  return displayName(modelId);
}

export function resolveActualModelId(modelId: string): string {
  if (modelId === 'server') return 'server';
  const option = getAvailableModels().find((item) => item.id === modelId);
  if (option?.actualModelId && findRecord(option.actualModelId)) {
    return option.actualModelId;
  }
  if (findRecord(modelId)) return modelId;

  const defaultOption = getAvailableModels().find(
    (item) => item.id === DEFAULT_MODEL_ID,
  );
  if (defaultOption?.actualModelId) return defaultOption.actualModelId;

  const fallback = llmRecords().find((record) => /qwen|gemma/i.test(record.model_id));
  return fallback?.model_id || llmRecords()[0]?.model_id || modelId;
}

function forceServer(modelId: string): boolean {
  return modelId === 'server' || getWebGPUStatus().forcedServer;
}

async function loadEngine(
  modelId: string,
  onProgress?: (report: InitProgressReport) => void,
): Promise<MLCEngine> {
  const webllm = await loadWebLLM();
  const actualModelId = resolveActualModelId(modelId);
  if (actualModelId === 'server') {
    throw new Error('Server mode does not load a browser model.');
  }

  const appConfig: AppConfig = {
    ...webllm.prebuiltAppConfig,
    cacheBackend: 'indexeddb',
  };

  if (!enginePromise) {
    enginePromise = webllm.CreateMLCEngine(actualModelId, {
      appConfig,
      initProgressCallback: onProgress,
      logLevel: 'WARN',
    });
    loadedActualModelId = actualModelId;
    return enginePromise;
  }

  const engine = await enginePromise;
  engine.setInitProgressCallback(onProgress);
  if (loadedActualModelId !== actualModelId) {
    await engine.reload(actualModelId);
    loadedActualModelId = actualModelId;
  }
  return engine;
}

async function* summarizeWithServer(
  transcript: string,
  opts?: SummarizeOptions,
): AsyncIterable<string> {
  // The slice endpoint streams SSE tokens; reuse it for both fresh and
  // continuing slices so the user sees tokens land in real time.
  const response = await fetch(`${config.apiUrl}/api/recordings/summarize-slice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      transcript,
      previous_summary: opts?.previousSummary || undefined,
      session_id: opts?.sessionId || undefined,
    }),
    signal: opts?.signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Server-side summary failed.');
  }
  if (!response.body) {
    throw new Error('Server stream returned an empty body.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      if (opts?.signal?.aborted) break;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() ?? '';
      for (const event of events) {
        const line = event.split('\n').find((l) => l.startsWith('data: '));
        if (!line) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;
        try {
          const parsed = JSON.parse(payload);
          if (parsed.token) {
            opts?.onToken?.(parsed.token);
            yield parsed.token as string;
          }
          if (parsed.error) {
            throw new Error(String(parsed.error));
          }
          if (parsed.done) {
            return;
          }
        } catch (err) {
          if (err instanceof Error && err.message) throw err;
        }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* noop */ }
  }
}

function buildUserPrompt(transcript: string, previousSummary?: string): string {
  const tail = transcript.slice(-50000);
  if (previousSummary && previousSummary.trim()) {
    return [
      'Previous running summary:',
      previousSummary.trim(),
      '',
      'New transcript since that summary (most recent at the bottom):',
      tail,
    ].join('\n');
  }
  return [
    'Transcript so far (most recent at the bottom):',
    tail,
  ].join('\n');
}

const SLICE_SYSTEM_PROMPT =
  'You are a live meeting summarizer. The user is currently in a meeting and wants a running summary that updates as new conversation happens. Given the transcript so far and the previous summary, produce an updated summary that:\n' +
  '- Leads with what is NEW since the previous summary\n' +
  '- Preserves key context, decisions, and action items from before\n' +
  '- Stays under 200 words\n' +
  '- Reads naturally, like notes a thoughtful attendee would take\n\n' +
  'Do not list speakers verbatim. Do not repeat the previous summary word-for-word.';

export class WebLLMSummarizer implements Summarizer {
  async *summarize(
    transcript: string,
    modelId: string,
    opts?: SummarizeOptions,
  ): AsyncIterable<string> {
    if (forceServer(modelId)) {
      yield* summarizeWithServer(transcript, opts);
      return;
    }

    const actualModelId = resolveActualModelId(modelId);
    const engine = await loadEngine(actualModelId, opts?.onProgress);
    if (opts?.signal?.aborted) {
      await engine.interruptGenerate();
      return;
    }

    const abortHandler = () => {
      engine.interruptGenerate();
    };
    opts?.signal?.addEventListener('abort', abortHandler, { once: true });

    try {
      const stream = await engine.chat.completions.create({
        model: actualModelId,
        stream: true,
        temperature: 0.25,
        max_tokens: 600,
        messages: [
          { role: 'system', content: SLICE_SYSTEM_PROMPT },
          { role: 'user', content: buildUserPrompt(transcript, opts?.previousSummary) },
        ],
      } as any);

      for await (const chunk of stream as unknown as AsyncIterable<any>) {
        if (opts?.signal?.aborted) break;
        const token = chunk?.choices?.[0]?.delta?.content || '';
        if (!token) continue;
        opts?.onToken?.(token);
        yield token;
      }
    } finally {
      opts?.signal?.removeEventListener('abort', abortHandler);
    }
  }

  async preloadModel(modelId: string, opts?: PreloadOptions): Promise<void> {
    if (forceServer(modelId)) return;
    const engine = await loadEngine(modelId, opts?.onProgress);
    if (opts?.signal?.aborted) {
      await engine.interruptGenerate();
    }
  }
}

export const inBrowserLLM = new WebLLMSummarizer();
