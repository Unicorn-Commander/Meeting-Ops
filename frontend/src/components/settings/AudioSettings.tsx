import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { config } from '../../config';
import { SectionProps, useSettingsContext } from './SettingsContext';

interface AudioDevice {
  id: string;
  name: string;
  sampleRates: number[];
  channels: number;
  isDefault: boolean;
  isUSB: boolean;
}

export default function AudioSettings(_props: SectionProps) {
  const { settings, setSettings, micVolume, setMicVolume, hostCaps } =
    useSettingsContext();
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([]);
  const [audioDeviceError, setAudioDeviceError] = useState<string | null>(null);

  const fetchAudioDevices = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/audio-devices`);
      if (response.ok) {
        const data = await response.json();
        const devices = data.devices || data;

        const mappedDevices: AudioDevice[] = devices.map((device: any) => ({
          id: device.deviceId || device.id || `hw:${device.index},0`,
          name: device.name || device.label || 'Unknown Device',
          sampleRates:
            device.sampleRates ||
            device.sample_rates ||
            [device.sample_rate] || [44100, 48000],
          channels: device.channels || 1,
          isDefault:
            device.is_default ||
            device.isDefault ||
            device.name?.includes('USB') ||
            false,
          isUSB:
            device.name?.includes('USB') ||
            device.label?.includes('USB') ||
            false,
        }));

        setAudioDevices(mappedDevices);
        setAudioDeviceError(null);

        const defaultDevice =
          mappedDevices.find((d) => d.isDefault) ||
          mappedDevices.find((d) => d.isUSB) ||
          mappedDevices[0];
        if (defaultDevice && !settings.defaultDevice) {
          setSettings((prev: any) => ({
            ...prev,
            defaultDevice: defaultDevice.id,
            sampleRate: '44100',
          }));
        }
      }
    } catch (error) {
      console.error('Failed to fetch audio devices:', error);
      setAudioDevices([]);
      setAudioDeviceError(
        'Could not detect audio devices. Check that PipeWire is running and the backend is reachable.'
      );
    }
  };

  const adjustMicVolume = async (volume: number) => {
    try {
      const response = await fetch(`${config.apiUrl}/api/simple/audio/volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device: settings.defaultDevice,
          volume: volume,
        }),
      });
      if (response.ok) {
        setMicVolume(volume);
      }
    } catch (error) {
      console.log('Backend not available for volume control');
      setMicVolume(volume);
    }
  };

  useEffect(() => {
    fetchAudioDevices();
  }, []);

  if (!hostCaps.local_audio) return null;

  return (
    <div className="space-y-6">
      {audioDeviceError && audioDevices.length === 0 && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-red-200 font-medium">
                Audio Device Detection Failed
              </p>
              <p className="text-xs text-red-300 mt-1">{audioDeviceError}</p>
              <button
                onClick={() => {
                  setAudioDeviceError(null);
                  fetchAudioDevices();
                }}
                className="mt-2 px-3 py-1 bg-red-800 hover:bg-red-700 text-red-100 rounded text-xs transition-colors"
              >
                Retry Detection
              </button>
            </div>
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Recording Device
        </label>
        <select
          value={settings.defaultDevice}
          onChange={(e) => {
            const device = audioDevices.find((d) => d.id === e.target.value);
            setSettings({
              ...settings,
              defaultDevice: e.target.value,
              sampleRate: device?.sampleRates.includes(44100) ? '44100' : '48000',
            });
          }}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
        >
          {audioDevices.map((device) => (
            <option key={device.id} value={device.id}>
              {device.name} {device.isUSB && '(USB)'} {device.isDefault && '⭐'}
            </option>
          ))}
        </select>
        <p className="text-xs text-zinc-500 mt-1">
          {audioDevices.find((d) => d.id === settings.defaultDevice)?.isUSB
            ? '✅ USB microphone detected - optimal for recording'
            : 'Built-in microphone selected'}
        </p>
      </div>

      {settings.defaultDevice === 'hw:0,0' && (
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-2">
            USB Microphone Volume
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="0"
              max="100"
              value={micVolume}
              onChange={(e) => adjustMicVolume(parseInt(e.target.value))}
              className="flex-1 h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
            />
            <span className="text-sm text-zinc-200 w-12 text-right">
              {micVolume}%
            </span>
          </div>
          <p className="text-xs text-zinc-500 mt-1">
            Adjust microphone input sensitivity
          </p>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Sample Rate
        </label>
        <select
          value={settings.sampleRate}
          onChange={(e) => setSettings({ ...settings, sampleRate: e.target.value })}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
        >
          {audioDevices
            .find((d) => d.id === settings.defaultDevice)
            ?.sampleRates.map((rate) => (
              <option key={rate} value={rate}>
                {rate / 1000} kHz {rate === 44100 && '(USB Mic Native)'}
              </option>
            )) || [
            <option key="44100" value="44100">
              44.1 kHz
            </option>,
            <option key="48000" value="48000">
              48 kHz
            </option>,
          ]}
        </select>
        <p className="text-xs text-zinc-500 mt-1">
          Recording at native rate avoids resampling and preserves quality
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Transcription Model
        </label>
        <select
          value={settings.transcriptionModel}
          onChange={(e) =>
            setSettings({ ...settings, transcriptionModel: e.target.value })
          }
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
        >
          <option value="base">Whisper Base (Fastest, ~39MB)</option>
          <option value="small">Whisper Small (~244MB)</option>
          <option value="medium">Whisper Medium (~1.5GB)</option>
          <option value="large">Whisper Large (~3GB)</option>
          <option value="large-v2">Whisper Large-v2 (~3GB)</option>
          <option value="large-v3">Whisper Large-v3 (Best, ~3GB) ⭐</option>
        </select>
        <p className="text-xs text-zinc-500 mt-1">
          Large-v3 with NPU acceleration: 220x faster than CPU
        </p>
      </div>

      <div className="space-y-3">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={settings.liveTranscription}
            onChange={(e) =>
              setSettings({ ...settings, liveTranscription: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">
            Enable live transcription during recording
          </span>
        </label>

        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={settings.vadEnabled}
            onChange={(e) =>
              setSettings({ ...settings, vadEnabled: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">
            Voice Activity Detection (removes silence)
          </span>
        </label>

        {settings.vadEnabled && (
          <div className="ml-7">
            <label className="block text-xs text-zinc-400 mb-1">
              VAD Threshold (ms)
            </label>
            <input
              type="number"
              value={settings.vadThreshold}
              onChange={(e) =>
                setSettings({ ...settings, vadThreshold: parseInt(e.target.value) })
              }
              className="w-32 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-zinc-200"
              min="100"
              max="2000"
              step="100"
            />
          </div>
        )}
      </div>
    </div>
  );
}
