import { MicVAD } from '@ricky0123/vad-web';
import {
  buildAudioConstraints,
  getPreferredDeviceId,
  openMicrophoneStream,
} from './audioDevicePreference';

type WakeLockSentinelLike = {
  release: () => Promise<void>;
  addEventListener?: (
    type: 'release',
    listener: () => void,
    options?: AddEventListenerOptions,
  ) => void;
};

export interface VadAudioChunk {
  blob: Blob;
  durationSeconds: number;
  elapsedSeconds: number;
}

export interface AlwaysOnVadEngineOptions {
  silenceThresholdMs?: number;
  getElapsedSeconds: () => number;
  /**
   * Returns the deviceId to use for the next `getUserMedia` call. The
   * engine reads this at start time and every time a device hot-swap is
   * requested. Returning `null` means "system default".
   *
   * If omitted, falls back to the persisted preference in localStorage.
   */
  getPreferredDeviceId?: () => string | null;
  /**
   * Called after a successful hot-swap so the parent UI can sync its
   * "active device" indicator. Argument is the deviceId actually opened
   * (may be `null` if the requested device was unavailable and the
   * engine fell back to the system default).
   */
  onDeviceChanged?: (deviceId: string | null) => void;
  /**
   * Called whenever the engine opens (or re-opens) a mic stream. Useful
   * for live VU meters etc. — gets the raw `MediaStream` so the parent
   * can attach its own AnalyserNode without re-prompting permission.
   * Parent must NOT stop the tracks; the engine owns the lifecycle.
   */
  onStreamChanged?: (stream: MediaStream | null) => void;
  onSpeechStart?: () => void;
  onSpeechEnd?: (chunk: VadAudioChunk) => Promise<void> | void;
  onMisfire?: () => void;
  onSilenceThreshold?: () => Promise<void> | void;
  onError?: (message: string) => void;
}

const SAMPLE_RATE = 16000;
const DEFAULT_SILENCE_THRESHOLD_MS = 30000;
const VAD_ASSET_BASE = 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.30/dist/';
// onnxruntime-web pinned to 1.17.3 (package.json) — vad-web 0.0.30 declares
// onnxruntime-web "^1.17.0" and was actually built against the legacy WASM
// glue API that exposes K.getValue / K.stackAlloc on the Emscripten module.
// 1.19+ ships .mjs and a new module layout where getValue isn't on the
// exported object, so vad init throws "K.getValue is not a function" at
// the first inference. 1.17.3 is the last version where both work + every
// required .wasm file is published on jsdelivr.
const ONNX_WASM_BASE = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.3/dist/';

let wakeLock: WakeLockSentinelLike | null = null;
let wakeLockRecording = false;

async function acquireWakeLock(): Promise<void> {
  const nav = navigator as Navigator & {
    wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> };
  };
  if (!nav.wakeLock) return;
  try {
    wakeLock = await nav.wakeLock.request('screen');
    wakeLock.addEventListener?.('release', () => {
      wakeLock = null;
    });
  } catch {
    wakeLock = null;
  }
}

function releaseWakeLock(): void {
  const lock = wakeLock;
  wakeLock = null;
  lock?.release().catch(() => undefined);
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && wakeLockRecording) {
    acquireWakeLock();
  }
});

function encodeWav(samples: Float32Array, sampleRate = SAMPLE_RATE): Blob {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * bytesPerSample, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, samples.length * bytesPerSample, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

export class AlwaysOnVadEngine {
  private vad: MicVAD | null = null;
  private silenceTimer: number | null = null;
  private running = false;
  private thresholdMs: number;
  // Track the current stream so hot-swap can stop the old tracks and the
  // VU meter consumer can attach to the live one.
  private currentStream: MediaStream | null = null;
  private currentDeviceId: string | null = null;

  constructor(private readonly options: AlwaysOnVadEngineOptions) {
    this.thresholdMs = options.silenceThresholdMs ?? DEFAULT_SILENCE_THRESHOLD_MS;
  }

  /** The deviceId we're capturing from RIGHT NOW (may be null = default). */
  getActiveDeviceId(): string | null {
    return this.currentDeviceId;
  }

  /** The live MediaStream — for VU meters, etc. Null when not recording. */
  getActiveStream(): MediaStream | null {
    return this.currentStream;
  }

  /**
   * Try to switch the active capture device mid-session. Returns the
   * deviceId actually opened (may differ from the request if a fallback
   * fired). If the engine isn't running, this is a no-op — the next
   * start() will pick up the new preference via getPreferredDeviceId.
   *
   * The flow is "pause → stop old stream → reinit VAD with new stream →
   * resume". MicVAD doesn't expose a public stream-swap API, so we
   * destroy and rebuild. Expected gap: a few hundred ms during which
   * speech is dropped. We surface the gap via the running flag.
   */
  async switchDevice(deviceId: string | null): Promise<string | null> {
    if (!this.running || !this.vad) {
      // Engine not active — just persist nothing here, the caller has
      // already updated their preference. Next start() will read it.
      return deviceId;
    }

    // Pause and tear down the existing VAD instance entirely. MicVAD
    // captures the stream via its `getStream` callback at .new() time;
    // there's no public switch-stream method, so we recreate.
    try {
      await this.vad.pause();
    } catch {
      // ignore
    }
    try {
      await this.vad.destroy();
    } catch {
      // ignore
    }
    this.vad = null;
    this.stopCurrentStream();

    // Open the new stream. Build options snapshot the new deviceId.
    let opened: { stream: MediaStream; deviceId: string | null };
    try {
      opened = await openMicrophoneStream(deviceId);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.options.onError?.(`Failed to switch microphone: ${message}`);
      // We've blown away the old engine. Try to recover by falling back
      // to system default.
      try {
        opened = await openMicrophoneStream(null);
      } catch (fallbackErr) {
        const fmsg =
          fallbackErr instanceof Error
            ? fallbackErr.message
            : String(fallbackErr);
        this.options.onError?.(
          `No microphone available after fallback: ${fmsg}`,
        );
        this.running = false;
        return null;
      }
    }

    this.currentStream = opened.stream;
    this.currentDeviceId = opened.deviceId;
    this.options.onStreamChanged?.(opened.stream);
    this.options.onDeviceChanged?.(opened.deviceId);

    const newVad = await this.initVadFromStream(opened.stream);
    if (newVad) {
      await newVad.start();
    }
    return opened.deviceId;
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    wakeLockRecording = true;
    await acquireWakeLock();

    if (!this.vad) {
      // Open the stream ourselves so we control its lifecycle. The
      // MicVAD `getStream` callback returns the stream we already
      // opened — preventing it from invoking getUserMedia twice (once
      // for our analyser, once for the model).
      const preferredId =
        this.options.getPreferredDeviceId?.() ?? getPreferredDeviceId();
      try {
        const opened = await openMicrophoneStream(preferredId);
        this.currentStream = opened.stream;
        this.currentDeviceId = opened.deviceId;
        if (opened.fellBack) {
          this.options.onError?.(
            'Preferred microphone unavailable. Recording with system default.',
          );
        }
        this.options.onStreamChanged?.(opened.stream);
        this.options.onDeviceChanged?.(opened.deviceId);
      } catch (err) {
        this.running = false;
        wakeLockRecording = false;
        releaseWakeLock();
        throw err;
      }
      await this.initVadFromStream(this.currentStream);
    }

    await this.vad?.start();
  }

  private async initVadFromStream(
    stream: MediaStream | null,
  ): Promise<MicVAD | null> {
    if (!stream) return null;
    this.vad = await MicVAD.new({
      model: 'v5',
      startOnLoad: false,
      baseAssetPath: VAD_ASSET_BASE,
      onnxWASMBasePath: ONNX_WASM_BASE,
      // Hand back the stream we already opened. MicVAD will attach its
      // own analyser/worklet onto it; we keep the reference so the parent
      // UI can attach a VU meter to the same stream without prompting
      // for permission a second time.
      getStream: async () => stream,
      onSpeechStart: () => {
        this.clearSilenceTimer();
        this.options.onSpeechStart?.();
      },
      onSpeechEnd: async (audio: Float32Array) => {
        const durationSeconds = audio.length / SAMPLE_RATE;
        const elapsedSeconds = Math.max(
          0,
          this.options.getElapsedSeconds() - durationSeconds,
        );
        try {
          await this.options.onSpeechEnd?.({
            blob: encodeWav(audio),
            durationSeconds,
            elapsedSeconds,
          });
        } catch (err) {
          this.options.onError?.(err instanceof Error ? err.message : String(err));
        }
        this.scheduleSilenceTimer();
      },
      onVADMisfire: () => {
        this.options.onMisfire?.();
        this.scheduleSilenceTimer();
      },
      onSpeechRealStart: () => undefined,
      onFrameProcessed: () => undefined,
    });
    return this.vad;
  }

  private stopCurrentStream(): void {
    const s = this.currentStream;
    this.currentStream = null;
    this.currentDeviceId = null;
    if (s) {
      try {
        s.getTracks().forEach((t) => t.stop());
      } catch {
        // ignore
      }
    }
    this.options.onStreamChanged?.(null);
  }

  async pause(): Promise<void> {
    this.clearSilenceTimer();
    this.running = false;
    await this.vad?.pause();
  }

  async resume(): Promise<void> {
    if (this.running) return;
    this.running = true;
    wakeLockRecording = true;
    await acquireWakeLock();
    await this.vad?.start();
  }

  async stop(): Promise<void> {
    this.clearSilenceTimer();
    this.running = false;
    wakeLockRecording = false;
    await this.vad?.destroy();
    this.vad = null;
    this.stopCurrentStream();
    releaseWakeLock();
  }

  private scheduleSilenceTimer(): void {
    this.clearSilenceTimer();
    if (!this.running) return;
    this.silenceTimer = window.setTimeout(() => {
      this.silenceTimer = null;
      this.options.onSilenceThreshold?.();
    }, this.thresholdMs);
  }

  private clearSilenceTimer(): void {
    if (this.silenceTimer !== null) {
      window.clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
  }
}

// Re-export for callers that want to build constraints without importing
// the helper module directly.
export { buildAudioConstraints };

export function createVadEngine(options: AlwaysOnVadEngineOptions): AlwaysOnVadEngine {
  return new AlwaysOnVadEngine(options);
}
