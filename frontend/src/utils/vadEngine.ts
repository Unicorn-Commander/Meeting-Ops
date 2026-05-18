import { MicVAD } from '@ricky0123/vad-web';

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
  onSpeechStart?: () => void;
  onSpeechEnd?: (chunk: VadAudioChunk) => Promise<void> | void;
  onMisfire?: () => void;
  onSilenceThreshold?: () => Promise<void> | void;
  onError?: (message: string) => void;
}

const SAMPLE_RATE = 16000;
const DEFAULT_SILENCE_THRESHOLD_MS = 30000;
const VAD_ASSET_BASE = 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.30/dist/';
const ONNX_WASM_BASE = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.0/dist/';

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

  constructor(private readonly options: AlwaysOnVadEngineOptions) {
    this.thresholdMs = options.silenceThresholdMs ?? DEFAULT_SILENCE_THRESHOLD_MS;
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    wakeLockRecording = true;
    await acquireWakeLock();

    if (!this.vad) {
      this.vad = await MicVAD.new({
        model: 'v5',
        startOnLoad: false,
        baseAssetPath: VAD_ASSET_BASE,
        onnxWASMBasePath: ONNX_WASM_BASE,
        getStream: async () => navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
          video: false,
        }),
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
    }

    await this.vad.start();
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

export function createVadEngine(options: AlwaysOnVadEngineOptions): AlwaysOnVadEngine {
  return new AlwaysOnVadEngine(options);
}
