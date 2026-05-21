/**
 * Parallel full-session audio capture for always-on recording.
 *
 * The VAD-driven chunk path (vadEngine.ts) gives the live transcript its
 * low-latency text feed. THIS module runs a SEPARATE `MediaRecorder` on
 * the same MediaStream that produces a continuous WebM/Opus stream — one
 * small chunk every ~30 seconds — and POSTs each chunk to
 * `/api/recordings/sessions/{id}/audio-chunks` as it lands.
 *
 * Why we need both:
 *   * VAD chunks are speech-bounded slices. They're not contiguous
 *     (silence is discarded), so concatenating them loses real timing.
 *   * The MediaRecorder stream is continuous, retains true wall-clock
 *     timing, and is what the server-side Parakeet 1.1B fp16 + pyannote
 *     diarization pipeline needs to do proper speaker matching.
 *
 * Privacy mode: callers MUST not instantiate this recorder when the
 * session is in local-only mode. The audio bytes never leave the device
 * if you never start the parallel recorder.
 *
 * Browser support:
 *   * Chrome / Edge / Firefox: WebM/Opus is universally supported.
 *   * Safari: supports `audio/mp4` (AAC) instead of WebM. We probe
 *     MIME types in order and pick the first the browser advertises.
 *     The server's reassembly step decodes any of these via ffmpeg, so
 *     codec drift across users in the same org is a non-issue.
 */

const MIME_CANDIDATES = [
  // Chrome / Firefox / Edge default. Opus is open + small.
  'audio/webm;codecs=opus',
  'audio/webm',
  // Safari path. AAC in MP4 container is the only thing Safari's
  // MediaRecorder produces.
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  // Older Firefox sometimes only advertises ogg.
  'audio/ogg;codecs=opus',
];

/** Pick the first MIME type the current browser will actually record in.
 * Returns an empty string when the browser exposes no MediaRecorder at
 * all (jsdom in tests, very old Safari) — callers should refuse to start
 * in that case rather than guess. */
export function pickRecordableMime(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const mime of MIME_CANDIDATES) {
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
  /** Called once per uploaded chunk with the chunk_index that succeeded. */
  onChunkUploaded?: (chunkIndex: number) => void;
  /** Called when a chunk hits maxRetries and is dropped. Non-fatal — the
   *  session keeps recording, the dropped chunk just leaves a gap in the
   *  server-side reassembled audio. */
  onChunkFailed?: (chunkIndex: number, error: Error) => void;
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

  let recorder: MediaRecorder | null = null;
  let started = false;
  let stopped = false;
  let chunkIndex = 0;
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

  const uploadChunk = async (
    indexAtCreation: number,
    blob: Blob,
  ): Promise<void> => {
    const form = new FormData();
    // Browser-side extension hint for the server's _safe_ext switch. We
    // base it on the recorder MIME; server stores under chunk_index.<ext>.
    const ext = mime.includes('mp4') ? 'mp4' : mime.includes('ogg') ? 'ogg' : 'webm';
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
    uploadChain = uploadChain
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
  };
}
