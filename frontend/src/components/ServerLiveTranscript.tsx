/**
 * ServerLiveTranscript — Phase B.2/B.3 server-live transcript pane with
 * Sortformer speaker labels. Drop-in for any page that has an active
 * recording session and wants live transcript + speaker badges.
 *
 * Opens its own WebSocket to /ws/sessions/{sessionId}/live and runs its
 * own mic capture via the AudioWorklet helper. Coexists with whatever
 * other audio pipelines are running on the page — browsers happily share
 * one OS-level mic across multiple getUserMedia() calls.
 *
 * Designed for the Record page (LiveRecording.tsx) but reusable
 * anywhere. The admin-only /streaming-test page keeps its own UI for
 * the seam-test buttons; this component is the production view.
 *
 * Tier-gating happens at the call site — only render this for users
 * with `hasFeature('server_live')` true. Free-tier users see a
 * different UI path entirely.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { startPcm16Capture, type Pcm16Capture } from '../utils/audioWorkletCapture';

// Mirror the 19-byte BE header layout from StreamingTest.tsx + the
// streaming.py module docstring. Kept inline here so this component has
// no dependency on the admin page.
const HEADER_BYTES = 19;
const MIC_TARGET_SR = 16000;
const MIC_FRAME_SAMPLES = 3200; // 200 ms at 16 kHz

function buildFrame(seq: number, isFinal: boolean, payload: Int16Array): ArrayBuffer {
  const payloadBytes = new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength);
  const buf = new ArrayBuffer(HEADER_BYTES + payloadBytes.byteLength);
  const view = new DataView(buf);
  view.setUint32(0, seq, /* littleEndian */ false);
  view.setBigUint64(4, BigInt(Date.now()) * 1000n, false);
  // fmt "PC16"
  const fmt = new Uint8Array(buf, 12, 4);
  fmt[0] = 0x50; fmt[1] = 0x43; fmt[2] = 0x31; fmt[3] = 0x36;
  view.setUint16(16, 160, false); // 16000 / 100
  view.setUint8(18, isFinal ? 0x01 : 0x00);
  new Uint8Array(buf, HEADER_BYTES).set(payloadBytes);
  return buf;
}

// ---- Speaker badge rendering (kept in sync with StreamingTest.tsx) ----

interface SpeakerTurn {
  spk_id: number;
  spk_label?: string;
  start_ms: number;
  end_ms: number;
}

const SPEAKER_COLORS = ['#ef4444', '#10b981', '#3b82f6', '#f59e0b'];

function speakerColor(spkId: number): string {
  return SPEAKER_COLORS[
    ((spkId % SPEAKER_COLORS.length) + SPEAKER_COLORS.length) % SPEAKER_COLORS.length
  ];
}

function SpeakerBadges({ speakers }: { speakers?: SpeakerTurn[] }) {
  if (!speakers || speakers.length === 0) return null;
  const seen = new Map<number, SpeakerTurn>();
  for (const turn of speakers) {
    if (!seen.has(turn.spk_id)) seen.set(turn.spk_id, turn);
  }
  return (
    <span style={{ display: 'inline-flex', gap: 4, marginRight: 6, verticalAlign: 'middle' }}>
      {Array.from(seen.values()).map(turn => (
        <span
          key={turn.spk_id}
          style={{
            background: speakerColor(turn.spk_id),
            color: '#fff',
            padding: '1px 6px',
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: 0.2,
          }}
          title={`${turn.spk_label || `spk_${turn.spk_id}`} (first turn ${turn.start_ms}-${turn.end_ms}ms)`}
        >
          {turn.spk_label || `spk_${turn.spk_id}`}
        </span>
      ))}
    </span>
  );
}

// ---- Component ----

interface FinalizedToken {
  word: string;
  start: number;
  end: number;
  confidence?: number;
}

interface TranscriptEntry {
  type: 'partial' | 'final';
  sequence: number;
  text: string;
  speakers?: SpeakerTurn[];
  // v2.0.0: per-word finalized tokens (delta — only the words newly
  // promoted from draft → finalized in THIS frame). Empty arrays when
  // STREAMING_USE_V2_PARAKEET is off server-side.
  tokensFinalized?: FinalizedToken[];
  textDraft?: string;
  eouDetected?: boolean;
}

interface ServerLiveTranscriptProps {
  /** Session id from the parent page. Used as the WS path segment. */
  sessionId: string;
  /** When false, the WS + mic are kept torn down. Parent typically passes
   *  `isRecording && tier-allows-this`. */
  enabled: boolean;
}

type ConnState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export default function ServerLiveTranscript({ sessionId, enabled }: ServerLiveTranscriptProps) {
  const [conn, setConn] = useState<ConnState>('idle');
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const seqRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const captureRef = useRef<Pcm16Capture | null>(null);
  const userTerminatedRef = useRef(false);

  // Compose the WS URL. Same pattern StreamingTest.tsx uses.
  const wsUrl = (() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/ws/sessions/${encodeURIComponent(sessionId)}/live`;
  })();

  const teardown = useCallback(() => {
    if (captureRef.current) {
      try { captureRef.current.stop(); } catch { /* best effort */ }
      captureRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (wsRef.current) {
      try { wsRef.current.close(1000, 'component teardown'); } catch { /* best effort */ }
      wsRef.current = null;
    }
    seqRef.current = 0;
  }, []);

  useEffect(() => {
    if (!enabled || !sessionId) {
      userTerminatedRef.current = true;
      teardown();
      setConn('idle');
      setTranscript([]);
      setErrorMsg(null);
      return;
    }
    userTerminatedRef.current = false;
    setConn('connecting');
    setErrorMsg(null);

    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setConn('open');
      // Once WS is open, attach mic and start streaming binary frames.
      (async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, sampleRate: MIC_TARGET_SR },
          });
          if (userTerminatedRef.current) {
            stream.getTracks().forEach(t => t.stop());
            return;
          }
          streamRef.current = stream;
          const capture = await startPcm16Capture(
            stream,
            (frame) => {
              if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                seqRef.current += 1;
                const buf = buildFrame(seqRef.current, false, frame);
                wsRef.current.send(buf);
              }
            },
            { sampleRate: MIC_TARGET_SR, frameSamples: MIC_FRAME_SAMPLES },
          );
          if (userTerminatedRef.current) {
            try { capture.stop(); } catch { /* best effort */ }
            return;
          }
          captureRef.current = capture;
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          setErrorMsg(`Mic access denied: ${msg}`);
          setConn('error');
        }
      })();
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'partial' || msg.type === 'final') {
          const entry: TranscriptEntry = {
            type: msg.type,
            sequence: msg.sequence ?? 0,
            text: (msg.text ?? '').trim(),
            speakers: Array.isArray(msg.speakers) ? msg.speakers : undefined,
            tokensFinalized: Array.isArray(msg.tokens_finalized)
              ? (msg.tokens_finalized as FinalizedToken[])
              : undefined,
            textDraft: typeof msg.text_draft === 'string' ? msg.text_draft : undefined,
            eouDetected: Boolean(msg.eou_detected),
          };
          // Allow empty text when an EOU marker fires alone — the chip
          // alone is informative even without new words.
          if (!entry.text && !entry.eouDetected) return;
          setTranscript(prev => {
            // Cap at 200 entries to keep DOM manageable on long sessions.
            const next = [...prev, entry];
            return next.length > 200 ? next.slice(-200) : next;
          });
        } else if (msg.type === 'error') {
          setErrorMsg(`${msg.reason ?? 'error'}: ${msg.detail ?? ''}`);
        }
      } catch {
        // Ignore non-JSON text frames.
      }
    };

    ws.onerror = () => {
      setErrorMsg('WebSocket error');
      setConn('error');
    };

    ws.onclose = () => {
      setConn('closed');
      if (!userTerminatedRef.current) {
        // Mic capture continues to be live in case the parent re-enables.
        // The teardown effect cleanup will handle real shutdown.
      }
    };

    return () => {
      userTerminatedRef.current = true;
      teardown();
    };
  }, [enabled, sessionId, wsUrl, teardown]);

  if (!enabled) return null;

  return (
    <div
      style={{
        marginTop: 16,
        marginBottom: 16,
        background: '#080808',
        padding: 12,
        borderRadius: 6,
        border: '1px solid #1f1f1f',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <strong style={{ fontSize: 14 }}>Server live transcript</strong>
        <span style={{ fontSize: 11, opacity: 0.5 }}>
          (Phase B.2 — Parakeet streaming + Sortformer speakers)
        </span>
        <span
          style={{
            fontSize: 11,
            padding: '1px 6px',
            borderRadius: 4,
            background:
              conn === 'open' ? '#10b981' :
              conn === 'connecting' ? '#f59e0b' :
              conn === 'error' ? '#ef4444' :
              '#3f3f46',
            color: '#fff',
          }}
        >
          {conn}
        </span>
        <span style={{ fontSize: 11, opacity: 0.5 }}>
          {transcript.length} entries
        </span>
      </div>
      {errorMsg && (
        <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 6 }}>
          {errorMsg}
        </div>
      )}
      <div
        style={{
          fontSize: 13,
          maxHeight: 200,
          overflow: 'auto',
          lineHeight: 1.5,
        }}
      >
        {transcript.length === 0 ? (
          <span style={{ opacity: 0.4 }}>
            (no partials yet, speak to populate)
          </span>
        ) : (
          transcript.map((e, i) => (
            <div
              key={`${e.sequence}-${i}`}
              style={{
                opacity: e.type === 'final' ? 1 : 0.78,
                fontWeight: e.type === 'final' ? 500 : 400,
                borderLeft: e.type === 'final' ? '2px solid #4caf50' : '2px solid #1976d2',
                paddingLeft: 8,
                marginBottom: 3,
              }}
              title={`${e.type} seq=${e.sequence}${e.tokensFinalized ? ` tokens=${e.tokensFinalized.length}` : ''}`}
            >
              <SpeakerBadges speakers={e.speakers} />
              {e.text}
              {/* v2.0.0: in-flight draft tokens — model has not committed
                  these yet, may revise. Rendered in faint italic so users
                  see the leading edge of the stream without confusing it
                  with finalized text. Hidden when text_draft is empty. */}
              {e.textDraft && (
                <span style={{ opacity: 0.45, fontStyle: 'italic', marginLeft: 4 }}>
                  {e.textDraft}
                </span>
              )}
              {/* v2.0.0: EOU detection chip. Fires when the model emits
                  the <EOU> end-of-utterance token, telling the user the
                  system recognized they stopped talking. Subtle indicator
                  rather than a big banner. */}
              {e.eouDetected && (
                <span
                  style={{
                    marginLeft: 6,
                    padding: '1px 5px',
                    borderRadius: 3,
                    background: '#52525b',
                    color: '#d4d4d8',
                    fontSize: 10,
                    fontWeight: 600,
                    letterSpacing: 0.3,
                  }}
                  title="End of utterance detected by streaming model"
                >
                  EOU
                </span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
