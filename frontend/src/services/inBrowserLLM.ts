import type {
  AppConfig,
  InitProgressReport,
  MLCEngine,
  ModelRecord,
} from '@mlc-ai/web-llm';
import { config } from '../config';

export const IN_BROWSER_LLM_MODEL_KEY = 'meetingops.inBrowserLLM.model.v1';
export const DEFAULT_MODEL_ID = 'qwen2.5-1.5b-instruct';

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
  // Order by quality/size, biggest-newest first. Entries whose actualModelId
  // isn't published by web-llm are silently filtered out at runtime (see
  // records.find check below), so we stage future variants here optimistically —
  // they appear in the picker the moment web-llm ships them.
  //
  // Verified against mlc-ai/web-llm prebuiltAppConfig 2026-05-19:
  // — Qwen3.6 + Gemma4 are NOT yet compiled for web-llm (open feature requests).
  //   Left in the list so they auto-appear when MLC publishes.
  // — Qwen 3.5 family IS available (0.8B/2B/4B/9B), newest series in browser today.
  // — Phi-4-mini IS available, very strong reasoning for its size.
  {
    id: 'gemma-4-e2b-it',
    actualModelId: 'gemma4-E2B-it-q4f16_1-MLC',
    label: 'Gemma 4 E2B (when published)',
  },
  {
    id: 'qwen3.6-1.7b',
    actualModelId: 'Qwen3.6-1.7B-q4f16_1-MLC',
    label: 'Qwen 3.6 1.7B (when published)',
  },
  {
    id: 'qwen3.5-9b',
    actualModelId: 'Qwen3.5-9B-q4f16_1-MLC',
    label: 'Qwen 3.5 9B (best quality, ~6GB)',
  },
  {
    id: 'phi-4-mini-instruct',
    actualModelId: 'Phi-4-mini-instruct-q4f16_1-MLC',
    label: 'Phi 4 Mini Instruct (strong reasoning)',
  },
  {
    id: 'qwen3.5-4b',
    actualModelId: 'Qwen3.5-4B-q4f16_1-MLC',
    label: 'Qwen 3.5 4B (recommended)',
  },
  {
    id: 'gemma-3-4b-it',
    actualModelId: 'gemma-3-4b-it-q4f16_1-MLC',
    label: 'Gemma 3 4B IT',
  },
  {
    id: 'qwen3.5-2b',
    actualModelId: 'Qwen3.5-2B-q4f16_1-MLC',
    label: 'Qwen 3.5 2B',
  },
  {
    id: 'qwen3-1.7b',
    actualModelId: 'Qwen3-1.7B-q4f16_1-MLC',
    label: 'Qwen 3 1.7B',
  },
  {
    id: 'qwen3.5-0.8b',
    actualModelId: 'Qwen3.5-0.8B-q4f16_1-MLC',
    label: 'Qwen 3.5 0.8B (fast)',
  },
  {
    id: 'qwen3-0.6b',
    actualModelId: 'Qwen3-0.6B-q4f16_1-MLC',
    label: 'Qwen 3 0.6B (smallest)',
  },
  {
    id: 'gemma-3-1b-it',
    actualModelId: 'gemma3-1b-it-q4f16_1-MLC',
    label: 'Gemma 3 1B IT',
  },
  {
    id: 'qwen2.5-1.5b-instruct',
    actualModelId: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
    label: 'Qwen 2.5 1.5B Instruct (default)',
  },
  {
    id: 'phi-3.5-mini-instruct',
    actualModelId: 'Phi-3.5-mini-instruct-q4f16_1-MLC',
    label: 'Phi 3.5 Mini Instruct',
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
  const response = await fetch(`${config.apiUrl}/api/recordings/summarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript, model_id: 'server' }),
    signal: opts?.signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Server-side summary failed.');
  }
  const data = await response.json();
  const text = String(data.summary || '').trim();
  if (text) {
    opts?.onToken?.(text);
    yield text;
  }
}

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
        max_tokens: 900,
        messages: [
          {
            role: 'system',
            content:
              'You summarize live meeting transcripts. Use only the transcript. Keep the answer concise and update-friendly.',
          },
          {
            role: 'user',
            content:
              'Write a rolling summary with current gist, decisions, action items, and open questions.\n\nTranscript:\n' +
              transcript.slice(-50000),
          },
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
