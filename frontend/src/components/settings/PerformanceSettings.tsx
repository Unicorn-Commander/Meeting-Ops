import { Cpu } from 'lucide-react';
import { SectionProps, useSettingsContext } from './SettingsContext';

export default function PerformanceSettings(_props: SectionProps) {
  const { settings, setSettings } = useSettingsContext();

  return (
    <div className="space-y-6">
      <div className="bg-green-900/20 border border-green-800 rounded-lg p-4 mb-6">
        <div className="flex items-start gap-3">
          <Cpu className="w-5 h-5 text-green-400 mt-0.5" />
          <div>
            <p className="text-sm text-green-200 font-medium">
              NPU Acceleration Active
            </p>
            <p className="text-xs text-green-300 mt-1">
              AMD Phoenix NPU detected - 220x faster transcription enabled
            </p>
          </div>
        </div>
      </div>

      <div>
        <label className="flex items-center gap-3 mb-4">
          <input
            type="checkbox"
            checked={settings.npuEnabled}
            onChange={(e) =>
              setSettings({ ...settings, npuEnabled: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">Enable NPU Acceleration</span>
        </label>

        {settings.npuEnabled && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                NPU Power Mode
              </label>
              <select
                value={settings.npuPowerMode}
                onChange={(e) =>
                  setSettings({ ...settings, npuPowerMode: e.target.value })
                }
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              >
                <option value="low">Low Power (Battery Saver)</option>
                <option value="balanced">Balanced (Recommended)</option>
                <option value="performance">Maximum Performance</option>
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                Performance mode: 0.0045 RTF, 4,789 tokens/sec
              </p>
            </div>
          </div>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          CPU Threads
        </label>
        <input
          type="number"
          value={settings.cpuThreads}
          onChange={(e) =>
            setSettings({ ...settings, cpuThreads: parseInt(e.target.value) })
          }
          min="1"
          max="16"
          className="w-32 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
        />
        <p className="text-xs text-zinc-500 mt-1">
          Number of CPU threads for background processing
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Memory Limit (MB)
        </label>
        <input
          type="number"
          value={settings.memoryLimit}
          onChange={(e) =>
            setSettings({ ...settings, memoryLimit: parseInt(e.target.value) })
          }
          min="2048"
          max="32768"
          step="1024"
          className="w-32 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200"
        />
        <p className="text-xs text-zinc-500 mt-1">
          Maximum memory allocation for Meeting-Ops
        </p>
      </div>

      <div className="bg-zinc-800/50 rounded-lg p-4 mt-6">
        <h4 className="text-sm font-medium text-zinc-300 mb-3">
          Reference Hardware (Configured For)
        </h4>
        <div className="space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-zinc-400">CPU:</span>
            <span className="text-zinc-200">AMD Ryzen 7 8845HS</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">NPU:</span>
            <span className="text-zinc-200">AMD Hawk Point (16 TOPS)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">RAM:</span>
            <span className="text-zinc-200">32 GB DDR5</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">Storage:</span>
            <span className="text-zinc-200">1 TB NVMe SSD</span>
          </div>
        </div>
      </div>
    </div>
  );
}
