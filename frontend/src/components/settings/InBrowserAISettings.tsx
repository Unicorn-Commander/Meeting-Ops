import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import {
  getAvailableModels,
  getStoredModelId,
  getWebGPUStatus,
  inBrowserLLM,
  refreshAvailableModels,
  setStoredModelId,
  type InBrowserModelOption,
} from '../../services/inBrowserLLM';
import type { SectionProps } from './SettingsContext';

function statusClasses(state: 'ready' | 'limited' | 'unavailable'): string {
  if (state === 'ready') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
  if (state === 'limited') return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
  return 'border-red-500/30 bg-red-500/10 text-red-300';
}

function optionDetail(option?: InBrowserModelOption): string {
  if (!option) return '';
  if (option.id === 'server') return 'Highest quality, uses the backend Qwen 3.6 endpoint.';
  const parts = [];
  if (option.vramRequiredMB) {
    parts.push(`${(option.vramRequiredMB / 1024).toFixed(1)} GB VRAM`);
  }
  if (option.lowResourceRequired) {
    parts.push('low-resource profile');
  }
  parts.push(option.source === 'curated' ? 'curated default' : 'web-llm prebuilt');
  return parts.join(' · ');
}

export default function InBrowserAISettings(_props: SectionProps) {
  const [models, setModels] = useState<InBrowserModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState(getStoredModelId);
  const [serverMode, setServerMode] = useState(() => getStoredModelId() === 'server');
  const [downloadProgress, setDownloadProgress] = useState<number | null>(null);
  const [downloadState, setDownloadState] = useState<'idle' | 'downloading' | 'ready' | 'error'>('idle');

  const webGPUStatus = useMemo(() => getWebGPUStatus(), []);
  const selectedOption = models.find((model) => model.id === selectedModel);

  useEffect(() => {
    const available = getAvailableModels();
    setModels(available);
    const current = getStoredModelId();
    if (!available.some((model) => model.id === current)) {
      const fallback = available.find((model) => model.id !== 'server')?.id || 'server';
      setSelectedModel(fallback);
      setStoredModelId(fallback);
    }
    refreshAvailableModels().then((loaded) => {
      setModels(loaded);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (webGPUStatus.forcedServer && selectedModel !== 'server') {
      setSelectedModel('server');
      setServerMode(true);
      setStoredModelId('server');
    }
  }, [selectedModel, webGPUStatus.forcedServer]);

  const updateModel = (modelId: string) => {
    setSelectedModel(modelId);
    setServerMode(modelId === 'server');
    setStoredModelId(modelId);
  };

  const updateServerMode = (enabled: boolean) => {
    setServerMode(enabled);
    if (enabled) {
      updateModel('server');
      return;
    }
    const fallback = models.find((model) => model.id !== 'server')?.id || 'server';
    updateModel(fallback);
  };

  const downloadModel = async () => {
    if (selectedModel === 'server') return;
    setDownloadState('downloading');
    setDownloadProgress(0);
    try {
      await inBrowserLLM.preloadModel(selectedModel, {
        onProgress: (report) => {
          setDownloadProgress(Math.max(0, Math.min(1, report.progress || 0)));
        },
      });
      setDownloadProgress(1);
      setDownloadState('ready');
    } catch {
      setDownloadState('error');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-white">In-browser AI</h3>
          <p className="mt-1 text-sm text-zinc-400">
            Browser summaries are private and fast after download. Server mode is stronger and uses backend GPU time.
          </p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-medium ${statusClasses(webGPUStatus.state)}`}>
          WebGPU {webGPUStatus.label}
        </span>
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-zinc-300" htmlFor="in-browser-model">
          Summary model
        </label>
        <select
          id="in-browser-model"
          value={selectedModel}
          onChange={(event) => updateModel(event.target.value)}
          disabled={webGPUStatus.forcedServer}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-zinc-200 outline-none focus:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.label}
            </option>
          ))}
        </select>
        <p className="mt-2 text-xs text-zinc-500">
          {webGPUStatus.forcedServer ? webGPUStatus.detail : optionDetail(selectedOption)}
        </p>
      </div>

      <label className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 bg-black/20 px-4 py-3">
        <span>
          <span className="block text-sm font-medium text-zinc-200">Use server-side LLM instead</span>
          <span className="mt-1 block text-xs text-zinc-500">Routes summaries to backend Qwen 3.6.</span>
        </span>
        <input
          type="checkbox"
          checked={serverMode}
          onChange={(event) => updateServerMode(event.target.checked)}
          className="h-4 w-4 rounded border-zinc-600 bg-zinc-800"
        />
      </label>

      <div>
        <button
          onClick={downloadModel}
          disabled={serverMode || webGPUStatus.forcedServer || downloadState === 'downloading'}
          className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-200 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {downloadState === 'downloading' ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Download model now
        </button>

        {downloadProgress !== null && (
          <div className="mt-3 max-w-md">
            <div className="mb-1 flex items-center justify-between text-xs text-zinc-500">
              <span>{downloadState === 'ready' ? 'Cached' : downloadState === 'error' ? 'Download failed' : 'Downloading'}</span>
              <span>{Math.round(downloadProgress * 100)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-zinc-800">
              <div
                className={`h-full transition-all ${downloadState === 'error' ? 'bg-red-400' : 'bg-sky-400'}`}
                style={{ width: `${Math.round(downloadProgress * 100)}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
