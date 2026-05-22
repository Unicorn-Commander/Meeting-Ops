/**
 * Parallel full-session audio capture for always-on recording.
 *
 * The VAD-driven chunk path (vadEngine.ts) gives the live transcript its
 * low-latency text feed. THIS module runs a SEPARATE `MediaRecorder` on
 * the same MediaStream that produces a continuous WebM/Opus stream — one
 * small chunk every ~30 seconds — and POSTs each chunk to
 * `/api/recordings/sessions/{id}/audio-chunks` as it lands.
 *
 * Phase A.5 (desktop local-first): when the caller opts in, each chunk
 * is also persisted to IndexedDB via `localAudioStore` BEFORE the
 * upload queue picks it up. On stop, the caller can compute a SHA-256
 * + byte total against the local copy and POST a verification payload
 * to /finalize-audio; the server compares and either confirms (caller
 * wipes local) or returns the delta (caller backfills specific chunks
 * or POSTs the assembled blob to /full-audio).
 *
 * Why we need both:
 *   * VAD chunks are speech-bounded slices. They're not contiguous
 *     (silence is discarded), so concatenating them loses real timing.
 *   * The MediaRecorder stream is continuous, retains true wall-clock
 *     timing, and is what the server-side Parakeet 1.1B fp16 + pyannote
 *     diarization pipeline needs to do proper speaker matching.
 *
 * Privacy mode: callers MUST not call the server-upload codepath when
 * the session is in local-only mode. The recorder still streams chunks
 * into IndexedDB (so the user gets the same crash-recovery property
 * desktop users expect), but `localOnly: true` disables the network
 * fetch. The blob stays on the device for the local STT/LLM pipeline.
 *
 * Browser support:
 *   * Chrome / Edge / Firefox: WebM/Opus is universally supported.
 *   * Safari: supports `audio/mp4` (AAC) instead of WebM. We probe
 *     MIME types in order and pick the first the browser advertises.
 *     The server's reassembly step decodes any of these via ffmpeg, so
 *     codec drift across users in the same org is a non-issue.
 */
import { localAudioStore } from '../services/localAudioStore';

// Non-Safari MIME order: prefer WebM/Opus (Chrome/Edge/Firefox native).
const MIME_CANDIDATES_NON_SAFARI = [
  // Chrome / Firefox / Edge default. Opus is open + small.
  'audio/webm;codecs=opus',
  'audio/webm',
  // Safari (and the occasional Chromium that ships AAC) fallback.
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  // Older Firefox sometimes only advertises ogg.
  'audio/ogg;codecs=opus',
];

// Safari MIME order: ALWAYS prefer audio/mp4 (AAC) even on Safari 18.4+
// which now advertises WebM/Opus support. The MP4 path has been the
// stable production codec on iOS for years; the new WebM emitter still
// has edge cases around backgrounding + AirPods reconnects we don't
// want to inherit on a phone demo. Server-side ffmpeg reassembly takes
// either, so the user-visible behavior is identical.
const MIME_CANDIDATES_SAFARI = [
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/aac',
  // Fallbacks for Safari 18.4+ that exposes opus. We probe these last
  // on iOS/macOS Safari so we keep MP4 as the default unless mp4 is
  // genuinely unavailable.
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
];

/** Detect WebKit-family browsers (Safari macOS + iOS, plus all iOS
 * Chrome/Firefox/Edge which are required by App Store policy to wrap
 * WKWebView). We treat them all as Safari for MIME selection because
 * they all use the same MediaRecorder backend.
 *
 * We avoid relying on `navigator.userAgent` Safari sniffing alone
 * because Chrome on iOS also matches; instead we check for the
 * combination that distinguishes WebKit from Blink: no `chrome` global
 * and either iOS UA or macOS-Safari UA. */
function isWebKitFamily(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  // All iOS browsers are WebKit under the hood (App Store rule until
  // EU/UK browser-engine choice rolls out broadly; the WebKit code
  // path is still the default everywhere as of 2026-Q2).
  const isIOS = /iPhone|iPad|iPod/.test(ua)
    || (/Macintosh/.test(ua) && typeof navigator.maxTouchPoints === 'number' && navigator.maxTouchPoints > 1);
  if (isIOS) return true;
  // Desktop Safari: UA contains "Safari" but NOT "Chrome"/"Chromium"/"Edg".
  const isDesktopSafari = /Safari\//.test(ua) && !/Chrome\/|Chromium\/|Edg\//.test(ua);
  return isDesktopSafari;
}

/** Pick the first MIME type the current browser will actually record in.
 * Returns an empty string when the browser exposes no MediaRecorder at
 * all (jsdom in tests, very old Safari) — callers should refuse to start
 * in that case rather than guess. Safari/iOS get an MP4-first probe
 * order; everyone else gets WebM-first. */
export function pickRecordableMime(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  const candidates = isWebKitFamily() ? MIME_CANDIDATES_SAFARI : MIME_CANDIDATES_NON_SAFARI;
  for (const mime of candidates) {
    try {
      if (MediaRecorder.isTypeSupported(mime)) return mime;
    } catch {
      // Some Safari builds throw on probing; treat as "not supported".
    }
  }
  return '';
}

/** Configuration knobs for the full-audio recorder. */
export interface FullAudioRecorderOptions {
  /** The MediaStream we're capturing from. Same stream as the VAD engine. */
  stream: MediaStream;
  /** Active session id — used in the upload URL. */
  sessionId: string;
  /** Base API URL (e.g. config.apiUrl). */
  apiUrl: string;
  /** Org slug for the X-MeetingOps-Org header (org-scoping). */
  orgSlug: string | null;
  /** How often the recorder emits a chunk via dataavailable. Default 30s. */
  timesliceMs?: number;
  /** Max retries per chunk before we surface a non-fatal warning. */
  maxRetries?: number;
  /** Initial backoff between retries (ms). Doubles each retry. Default 1s. */
  initialBackoffMs?: number;
  /**
   * Persist each chunk to IndexedDB before queuing the server upload.
   * Recommended on desktop browsers — gives crash recovery + the
   * verification payload at stop. Default false; AlwaysOnContext flips
   * this on when `capabilityClass === 'desktop-capable'`.
   */
  localPersistence?: boolean;
  /**
   * Local-only / privacy mode. When true the recorder STILL writes
   * each chunk to IndexedDB (so the local STT/LLM pipeline has source
   * audio + we keep crash recovery) but skips the server upload path
   * entirely. No /audio-chunks POSTs, no retries, nothing leaves the
   * device. Mutually compatible with localPersistence (privacy mode
   * implies local persistence by definition).
   */
  localOnly?: boolean;
  /** Called once per uploaded chunk with the chunk_index that succeeded. */
  onChunkUploaded?: (chunkIndex: number) => void;
  /** Called when a chunk hits maxRetries and is dropped. Non-fatal — the
   *  session keeps recording, the dropped chunk just leaves a gap in the
   *  server-side reassembled audio. */
  onChunkFailed?: (chunkIndex: number, error: Error) => void;
  /** Called once per chunk persisted to IndexedDB. Lets callers update
   *  a "buffered locally" counter even when server upload is off. */
  onChunkPersisted?: (chunkIndex: number, bytes: number) => void;
}

/** Public surface — what AlwaysOnContext holds onto. */
export interface FullAudioRecorderHandle {
  /** Start recording. Idempotent — calling twice is a no-op. */
  start(): void;
  /** Force an in-progress chunk to flush (drains the encoder). Called on stop. */
  flush(): Promise<void>;
  /** Stop recording. Waits for the final dataavailable + upload before
   *  resolving so the caller knows the queue is empty. */
  stop(): Promise<void>;
  /** True when actively recording. */
  isRecording(): boolean;
  /** Number of chunks the recorder has produced (regardless of upload state). */
  chunksProduced(): number;
  /** Bytes persisted locally so far. Cheap, in-memory counter — does
   *  not query IndexedDB. Zero when localPersistence is off. */
  localBytes(): number;
  /** MIME the recorder picked. Useful for the /full-audio fallback so
   *  the caller can label the blob correctly. */
  mimeType(): string;
}

/**
 * Build a parallel full-audio recorder bound to the given stream.
 *
 * Lifecycle: the caller (AlwaysOnContext) constructs one of these per
 * session and tears it down on stop(). The recorder owns its own upload
 * queue (sequential FIFO with retries) so out-of-order ACKs at the
 * server don't matter — each chunk_index is idempotent on the server side.
 */
export function createFullAudioRecorder(
  options: FullAudioRecorderOptions,
): FullAudioRecorderHandle | null {
  const mime = pickRecordableMime();
  if (!mime) {
    // No supported MediaRecorder MIME type — caller should noop and the
    // session still works via the chunks-text path. Reprocess just won't
    // run for this session.
    return null;
  }

  const timeslice = options.timesliceMs ?? 30_000;
  const maxRetries = options.maxRetries ?? 5;
  const initialBackoff = options.initialBackoffMs ?? 1000;
  const localPersistence = options.localPersistence === true || options.localOnly === true;
  const localOnly = options.localOnly === true;

  let recorder: MediaRecorder | null = null;
  let started = false;
  let stopped = false;
  let chunkIndex = 0;
  let localBytesAccumulated = 0;
  // Sequential upload queue. We chain promises so chunks land on the server
  // in arrival order even when the network is flaky. The server is
  // idempotent on chunk_index either way, so out-of-order isn't unsafe —
  // sequential is just easier to reason about.
  let uploadChain: Promise<void> = Promise.resolve();
  let stopResolve: (() => void) | null = null;
  let pendingFlush: Promise<void> | null = null;
  let pendingFlushResolve: (() => void) | null = null;

  const buildHeaders = (): HeadersInit => {
    const headers: Record<string, string> = {};
    // Bearer auth + org header — match the existing chunks endpoints'
    // expectations. The chunks-text endpoint uses these via cookie/JWT
    // auth so /audio-chunks does the same.
    try {
      const token = window.localStorage?.getItem('access_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;
    } catch {
      /* localStorage blocked — fall back to cookie auth */
    }
    if (options.orgSlug) headers['X-MeetingOps-Org'] = options.orgSlug;
    return headers;
  };

  const persistLocally = async (indexAtCreation: number, blob: Blob): Promise<void> => {
    if (!localPersistence) return;
    if (!localAudioStore.isAvailable()) return;
    try {
      await localAudioStore.appendChunk(options.sessionId, indexAtCreation, blob, mime);
      localBytesAccumulated += blob.size;
      options.onChunkPersisted?.(indexAtCreation, blob.size);
    } catch (err) {
      // Best-effort. We don't surface an error here because the server
      // upload (in non-privacy mode) is still the authoritative copy.
      // In privacy mode a failure means the chunk is genuinely lost,
      // but there's not much we can do at this layer beyond logging.
      // eslint-disable-next-line no-console
      console.warn(
        `[full-audio] Local persist failed for chunk ${indexAtCreation}:`,
        err,
      );
    }
  };

  const uploadChunk = async (
    indexAtCreation: number,
    blob: Blob,
  ): Promise<void> => {
    if (localOnly) return;
    const form = new FormData();
    // Browser-side extension hint for the server's _safe_ext switch. We
    // base it on the recorder MIME; server stores under chunk_index.<ext>.
    const ext = mime.includes('mp4')
      ? 'mp4'
      : mime.includes('aac')
        ? 'aac'
        : mime.includes('ogg')
          ? 'ogg'
          : 'webm';
    form.append('chunk', blob, `audio-${indexAtCreation}.${ext}`);
    form.append('chunk_index', String(indexAtCreation));

    let attempt = 0;
    let backoff = initialBackoff;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      try {
        const resp = await fetch(
          `${options.apiUrl}/api/recordings/sessions/${options.sessionId}/audio-chunks`,
          {
            method: 'POST',
            headers: buildHeaders(),
            body: form,
            credentials: 'include',
          },
        );
        if (!resp.ok) {
          // 4xx is permanent — no point retrying a client-side error
          // (e.g. session ended, invalid session_id). Surface as failure
          // immediately so we don't loop forever.
          if (resp.status >= 400 && resp.status < 500) {
            const detail = await resp.text().catch(() => '');
            throw new Error(
              `audio-chunks ${resp.status}: ${detail.slice(0, 200) || 'client error'}`,
            );
          }
          throw new Error(`audio-chunks ${resp.status}`);
        }
        options.onChunkUploaded?.(indexAtCreation);
        return;
      } catch (err) {
        attempt += 1;
        if (attempt > maxRetries) {
          options.onChunkFailed?.(
            indexAtCreation,
            err instanceof Error ? err : new Error(String(err)),
          );
          // Swallow — we never want to halt the recording loop on a
          // failed upload. The dropped chunk just leaves a gap; the
          // server's ffmpeg reassembly tolerates missing indices.
          return;
        }
        // Re-throw client errors immediately (no retry — see above).
        if (err instanceof Error && err.message.startsWith('audio-chunks 4')) {
          options.onChunkFailed?.(indexAtCreation, err);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, backoff));
        backoff *= 2;
      }
    }
  };

  const queueUpload = (blob: Blob) => {
    const indexAtCreation = chunkIndex;
    chunkIndex += 1;
    // Persist FIRST, then queue server upload. This ordering is what
    // makes "browser tab crashes mid-upload" a recoverable case: the
    // chunk is on disk before the network request even starts.
    uploadChain = uploadChain
      .then(() => persistLocally(indexAtCreation, blob))
      .then(() => uploadChunk(indexAtCreation, blob))
      .catch((err) => {
        // Final safety net — uploadChunk swallows internally, but if
        // something unexpected leaks we don't want to break the chain.
        // eslint-disable-next-line no-console
        console.warn('[full-audio] queue saw unexpected error', err);
      });
  };

  return {
    start(): void {
      if (started || stopped) return;
      started = true;
      try {
        recorder = new MediaRecorder(options.stream, { mimeType: mime });
      } catch (err) {
        // Some Safari builds throw at construction with a more permissive
        // MIME hint; try the bare type one more time.
        try {
          recorder = new MediaRecorder(options.stream);
        } catch (innerErr) {
          // eslint-disable-next-line no-console
          console.warn(
            '[full-audio] MediaRecorder construction failed; full audio path disabled for this session.',
            innerErr,
          );
          started = false;
          return;
        }
      }
      recorder.ondataavailable = (event: BlobEvent) => {
        if (!event.data || event.data.size === 0) return;
        queueUpload(event.data);
        // If we were waiting for a flush, resolve once this dataavailable
        // is queued. The actual upload is already chained.
        if (pendingFlushResolve) {
          const resolve = pendingFlushResolve;
          pendingFlushResolve = null;
          pendingFlush = null;
          resolve();
        }
      };
      recorder.onstop = () => {
        // Final flush already queued via the last dataavailable that
        // fires before onstop. Resolve the outer stop()'s promise after
        // the upload chain drains.
        uploadChain
          .catch(() => undefined)
          .then(() => {
            if (stopResolve) {
              const resolve = stopResolve;
              stopResolve = null;
              resolve();
            }
          });
      };
      recorder.start(timeslice);
    },

    async flush(): Promise<void> {
      // Ask the recorder to dump whatever's in its current encoder
      // buffer as a chunk. Resolves once that chunk is queued (not yet
      // uploaded — but enqueued behind any pending uploads so stop()
      // can wait on uploadChain for full drain).
      if (!recorder || recorder.state !== 'recording') return;
      if (pendingFlush) return pendingFlush;
      pendingFlush = new Promise<void>((resolve) => {
        pendingFlushResolve = resolve;
      });
      try {
        recorder.requestData();
      } catch (err) {
        // requestData throws on Firefox <= 65 if no slice is pending;
        // treat as already-flushed.
        // eslint-disable-next-line no-console
        console.debug('[full-audio] requestData skipped', err);
        if (pendingFlushResolve) {
          const resolve = pendingFlushResolve;
          pendingFlushResolve = null;
          pendingFlush = null;
          resolve();
        }
      }
      return pendingFlush ?? Promise.resolve();
    },

    async stop(): Promise<void> {
      if (stopped) return;
      stopped = true;
      if (!recorder || recorder.state === 'inactive') {
        // Drain whatever's already queued before resolving.
        await uploadChain.catch(() => undefined);
        return;
      }
      const drain = new Promise<void>((resolve) => {
        stopResolve = resolve;
      });
      try {
        recorder.stop();
      } catch (err) {
        // If stop() throws (recorder already inactive), just drain the chain.
        // eslint-disable-next-line no-console
        console.debug('[full-audio] stop() threw, draining queue', err);
        if (stopResolve) {
          const resolve = stopResolve;
          stopResolve = null;
          resolve();
        }
      }
      await drain;
      await uploadChain.catch(() => undefined);
    },

    isRecording(): boolean {
      return Boolean(recorder && recorder.state === 'recording');
    },

    chunksProduced(): number {
      return chunkIndex;
    },

    localBytes(): number {
      return localBytesAccumulated;
    },

    mimeType(): string {
      return mime;
    },
  };
}

// ---------------------------------------------------------------------------
// Verification helpers — called by AlwaysOnContext at stop() time.
// ---------------------------------------------------------------------------

export interface FinalizeAudioVerificationResponse {
  status?: 'complete' | 'incomplete' | string;
  reprocessing_started?: boolean;
  reason?: string;
  session_id?: string;
  server_bytes?: number;
  server_chunks?: number[];
  missing_chunks?: number[];
  expected_chunks?: number;
  job_id?: string;
}

export interface VerifyAudioInput {
  apiUrl: string;
  orgSlug: string | null;
  sessionId: string;
  clientChunkCount: number;
  clientBytesTotal: number;
  clientSha256: string;
}

/**
 * POST a verification payload to /finalize-audio. The server reassembles
 * the chunks it has on disk and compares to (count, bytes, sha). On
 * match it returns `{status: 'complete'}` and queues the reprocess
 * pipeline as usual. On mismatch it returns `{status: 'incomplete'}`
 * with the missing chunk indices so the caller can backfill or fall
 * back to /full-audio.
 */
export async function postFinalizeAudioWithVerification(
  input: VerifyAudioInput,
): Promise<FinalizeAudioVerificationResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  try {
    const token = window.localStorage?.getItem('access_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } catch {
    /* localStorage blocked — fall back to cookie auth */
  }
  if (input.orgSlug) headers['X-MeetingOps-Org'] = input.orgSlug;

  const resp = await fetch(
    `${input.apiUrl}/api/recordings/sessions/${input.sessionId}/finalize-audio`,
    {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify({
        client_chunk_count: input.clientChunkCount,
        client_bytes_total: input.clientBytesTotal,
        client_sha256: input.clientSha256,
      }),
    },
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => '');
    throw new Error(
      `finalize-audio ${resp.status}: ${detail.slice(0, 200) || 'request failed'}`,
    );
  }
  return (await resp.json()) as FinalizeAudioVerificationResponse;
}

/**
 * Upload an entire assembled audio blob to /full-audio. The server
 * replaces any existing reassembled audio for the session and triggers
 * the reprocess pipeline. Use as the bulletproof fallback when chunk
 * verification says we can't repair via per-chunk backfill.
 */
export async function postFullAudio(input: {
  apiUrl: string;
  orgSlug: string | null;
  sessionId: string;
  blob: Blob;
  mimeType: string;
}): Promise<FinalizeAudioVerificationResponse> {
  const headers: Record<string, string> = {};
  try {
    const token = window.localStorage?.getItem('access_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } catch {
    /* localStorage blocked — fall back to cookie auth */
  }
  if (input.orgSlug) headers['X-MeetingOps-Org'] = input.orgSlug;

  const ext = input.mimeType.includes('mp4')
    ? 'mp4'
    : input.mimeType.includes('aac')
      ? 'aac'
      : input.mimeType.includes('ogg')
        ? 'ogg'
        : 'webm';
  const form = new FormData();
  form.append('audio', input.blob, `full-audio.${ext}`);
  const resp = await fetch(
    `${input.apiUrl}/api/recordings/sessions/${input.sessionId}/full-audio`,
    {
      method: 'POST',
      headers,
      credentials: 'include',
      body: form,
    },
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => '');
    throw new Error(
      `full-audio ${resp.status}: ${detail.slice(0, 200) || 'request failed'}`,
    );
  }
  return (await resp.json()) as FinalizeAudioVerificationResponse;
}
