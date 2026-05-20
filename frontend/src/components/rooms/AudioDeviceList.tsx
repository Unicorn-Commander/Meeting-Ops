import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Mic, AlertCircle, Check } from 'lucide-react';
import roomsApi, { type AudioDevice } from '../../services/roomsApi';

interface AudioDeviceListProps {
  orgSlug: string | null;
  selectedDevicePath?: string | null;
  onSelect: (device: AudioDevice) => void;
  /**
   * Optional className for the container. Defaults to a stack of cards.
   */
  className?: string;
}

/**
 * Fetches `/api/system/audio-devices` and renders each row as a
 * selectable card. Mic-test buttons are intentionally omitted — these
 * are server-side devices that the browser can't probe directly. Phase
 * 2 will add a backend `/api/system/audio-devices/{path}/test` probe.
 */
export default function AudioDeviceList({
  orgSlug,
  selectedDevicePath,
  onSelect,
  className = '',
}: AudioDeviceListProps) {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDevices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await roomsApi.listAudioDevices({ orgSlug });
      setDevices(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audio devices');
      setDevices([]);
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-zinc-500">
          Server audio devices
        </div>
        <button
          type="button"
          onClick={fetchDevices}
          disabled={loading}
          className="flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {loading && (
        <div className="text-sm text-zinc-500">Loading…</div>
      )}

      {error && !loading && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {!loading && !error && devices.length === 0 && (
        <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-950/50 px-3 py-4 text-center text-sm text-zinc-500">
          No audio devices detected on the server.
          <div className="mt-1 text-xs">
            Plug in a USB microphone and tap Refresh.
          </div>
        </div>
      )}

      {!loading && !error && devices.length > 0 && (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {devices.map((d) => {
            const selected = selectedDevicePath === d.device_path;
            return (
              <button
                key={d.device_path}
                type="button"
                onClick={() => onSelect(d)}
                className={`flex items-start gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
                  selected
                    ? 'border-fuchsia-500/60 bg-fuchsia-500/10'
                    : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700 hover:bg-zinc-900'
                }`}
              >
                <div className="mt-0.5">
                  {selected ? (
                    <Check className="h-4 w-4 text-fuchsia-300" />
                  ) : (
                    <Mic className="h-4 w-4 text-zinc-400" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-zinc-100">
                    {d.device_name || d.card_name}
                  </div>
                  <div className="truncate text-xs text-zinc-500">
                    {d.card_name && d.card_name !== d.device_name ? `${d.card_name}  ·  ` : ''}
                    <span className="font-mono">{d.device_path}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
