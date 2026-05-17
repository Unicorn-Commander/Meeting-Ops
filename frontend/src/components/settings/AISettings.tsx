import { useEffect, useState } from 'react';
import { config } from '../../config';
import { SectionProps, useSettingsContext } from './SettingsContext';

interface AvailableModel {
  model_id: string;
  display_name: string;
  speed_estimate: string;
  vram_estimate: string;
  best_for: string;
  is_active: boolean;
}

export default function AISettings(_props: SectionProps) {
  const { settings, setSettings } = useSettingsContext();
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [modelSwitching, setModelSwitching] = useState(false);

  const fetchAvailableModels = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${config.apiUrl}/api/settings/models/available`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setAvailableModels(data.models || []);
        const activeModel = data.models?.find((m: any) => m.is_active);
        if (activeModel) {
          setSettings((prev: any) => ({ ...prev, llmModel: activeModel.model_id }));
        }
      }
    } catch (e) {
      console.log('Could not fetch available models:', e);
    }
  };

  const switchModel = async (modelId: string) => {
    setModelSwitching(true);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${config.apiUrl}/api/settings/models/active`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ model_id: modelId }),
      });
      if (res.ok) {
        setSettings((prev: any) => ({ ...prev, llmModel: modelId }));
        await fetchAvailableModels();
      }
    } catch (e) {
      console.error('Failed to switch model:', e);
    } finally {
      setModelSwitching(false);
    }
  };

  useEffect(() => {
    fetchAvailableModels();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          LLM Provider
        </label>
        <select
          value={settings.llmProvider}
          onChange={(e) => setSettings({ ...settings, llmProvider: e.target.value })}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
        >
          <option value="llamacpp">llama.cpp Vulkan (Local)</option>
          <option value="ollama">Ollama (Local)</option>
          <option value="openai">OpenAI API</option>
          <option value="anthropic">Anthropic Claude</option>
          <option value="custom">Custom Endpoint</option>
        </select>
      </div>

      {(settings.llmProvider === 'llamacpp' ||
        settings.llmProvider === 'ollama' ||
        settings.llmProvider === 'custom') && (
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-2">
            LLM Model
          </label>
          <select
            value={settings.llmModel}
            onChange={(e) => switchModel(e.target.value)}
            disabled={modelSwitching}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 disabled:opacity-50"
          >
            {availableModels.length > 0 ? (
              availableModels.map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {model.display_name} {model.is_active ? '(Active)' : ''}
                </option>
              ))
            ) : (
              <option value={settings.llmModel}>{settings.llmModel}</option>
            )}
          </select>
          {(() => {
            const activeModel = availableModels.find(
              (m) => m.model_id === settings.llmModel
            );
            if (activeModel) {
              return (
                <div className="mt-2 space-y-1">
                  <p className="text-xs text-zinc-500">
                    Speed: {activeModel.speed_estimate} &middot; VRAM:{' '}
                    {activeModel.vram_estimate}
                  </p>
                  <p className="text-xs text-zinc-400">{activeModel.best_for}</p>
                </div>
              );
            }
            return null;
          })()}
          {modelSwitching && (
            <p className="text-xs text-yellow-400 mt-1">Switching model...</p>
          )}
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Default Summary Format
        </label>
        <select
          value={settings.summaryFormat}
          onChange={(e) =>
            setSettings({ ...settings, summaryFormat: e.target.value })
          }
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
        >
          <option value="executive">Executive Summary</option>
          <option value="minutes">Meeting Minutes</option>
          <option value="bullets">Bullet Points</option>
          <option value="detailed">Detailed Report</option>
          <option value="standup">Standup Format</option>
          <option value="interview">Interview Notes</option>
        </select>
      </div>

      <div className="space-y-3">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={settings.enableAI}
            onChange={(e) =>
              setSettings({ ...settings, enableAI: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">Enable AI processing</span>
        </label>

        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={settings.autoGenerateActions}
            onChange={(e) =>
              setSettings({ ...settings, autoGenerateActions: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">Auto-generate action items</span>
        </label>

        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={settings.speakerDiarization}
            onChange={(e) =>
              setSettings({ ...settings, speakerDiarization: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">Speaker diarization</span>
        </label>

        {settings.speakerDiarization && (
          <div className="ml-7">
            <label className="block text-xs text-zinc-400 mb-1">Max Speakers</label>
            <input
              type="number"
              value={settings.maxSpeakers}
              onChange={(e) =>
                setSettings({ ...settings, maxSpeakers: parseInt(e.target.value) })
              }
              className="w-20 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-200"
              min="2"
              max="10"
            />
          </div>
        )}
      </div>
    </div>
  );
}
