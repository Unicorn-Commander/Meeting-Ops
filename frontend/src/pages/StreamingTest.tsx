/**
 * Phase B.2 streaming WS smoke-test page.
 *
 * Opens a WebSocket against `/ws/sessions/{uuid}/live`, can either:
 *   - send a dummy 1 KB PCM16-formatted binary chunk wrapped in the
 *     19-byte header (seam test — no transcription expected),
 *   - capture mic audio via getUserMedia + AudioWorklet (or
 *     ScriptProcessorNode fallback) and stream real PCM16 frames so
 *     the meet-backend forwards them to the new
 *     meet-parakeet-stream-svc on midboy2.
 *
 * Prints every frame in both directions plus a separate "live
 * transcript" pane that aggregates `partial` / `final` JSON frames so
 * you can read what the model heard.
 *
 * Real Parakeet integration ships in Phase B.2 (this file). True NeMo
 * native streaming with draft+finalize tokens is Phase B.3.
 *
 * Wire format (canonical as of B.2 reconciliation 2026-05-22):
 *   bytes 0-3   uint32 BE  sequence_number
 *   bytes 4-11  uint64 BE  client_timestamp_us
 *   bytes 12-15 ASCII      payload_format  ("PC16" = 16 kHz mono PCM16)
 *   bytes 16-17 uint16 BE  sample_rate / 100  (160 = 16000)
 *   byte 18     uint8      flags (bit 0: is_final)
 *   bytes 19..N payload
 * See backend/api/streaming.py HEADER_STRUCT for the canonical Python
 * side and docs/phase-b-server-live-streaming.md section 4 for the
 * design rationale.
 */
import { useEffect, useRef, useState } from 'react';

type WSState = 'idle' | 'connecting' | 'open' | 'closing' | 'closed';
type MicState = 'idle' | 'requesting' | 'recording' | 'error';

const HEADER_BYTES = 19;
const DUMMY_PAYLOAD_BYTES = 1024; // ~32 ms of 16 kHz mono PCM16
const MIC_TARGET_SR = 16000;
// 200 ms of audio per WS frame at 16 kHz mono PCM16 (per design doc).
// 200ms * 16000Hz * 2 bytes = 6400 bytes per frame.
const MIC_FRAME_MS = 200;
const MIC_FRAME_SAMPLES = (MIC_TARGET_SR * MIC_FRAME_MS) / 1000;

function nowIso(): string {
  return new Date().toISOString();
}

function bytesPreview(buf: ArrayBuffer, max = 64): string {
  const view = new Uint8Array(buf, 0, Math.min(buf.byteLength, max));
  const hex = Array.from(view).map(b => b.toString(16).padStart(2, '0')).join(' ');
  return buf.byteLength > max ? `${hex} ... (+${buf.byteLength - max}B)` : hex;
}

interface TranscriptEntry {
  type: 'partial' | 'final';
  sequence: number;
  text: string;
  ts: string;
}

/** Build a binary frame with the canonical 19-byte BE header followed
 *  by the supplied PCM16 LE payload. Caller is responsible for the
 *  payload being valid 16 kHz mono PCM16 (or zero-filled for smoke). */
function buildFrame(seq: number, isFinal: boolean, payload: Int16Array | Uint8Array): ArrayBuffer {
  const payloadBytes = payload instanceof Int16Array
    ? new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength)
    : payload;
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

export default function StreamingTest() {
  const [log, setLog] = useState<string[]>([]);
  const [state, setState] = useState<WSState>('idle');
  const [micState, setMicState] = useState<MicState>('idle');
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const seqRef = useRef(0);
  const sessionIdRef = useRef<string>('');

  // Mic capture refs
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const micBufRef = useRef<Int16Array[]>([]);

  const append = (line: string) => {
    setLog(prev => {
      const next = [...prev, `[${nowIso()}] ${line}`];
      return next.length > 500 ? next.slice(next.length - 500) : next;
    });
  };

  const connect = () => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      append('already connected/connecting; close first');
      return;
    }

    const sessionId = (globalThis.crypto?.randomUUID?.() ?? `b2-${Date.now().toString(36)}`);
    sessionIdRef.current = sessionId;
    seqRef.current = 0;
    setTranscript([]);

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws/sessions/${sessionId}/live`;
    append(`connecting -> ${url}`);
    setState('connecting');

    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      append(`WS open (session_id=${sessionId})`);
      setState('open');
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        append(`<- ${ev.data}`);
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'partial' || msg.type === 'final') {
            setTranscript(prev => [
              ...prev,
              {
                type: msg.type,
                sequence: msg.sequence ?? 0,
                text: msg.text ?? '',
                ts: nowIso(),
              },
            ].slice(-200));
          }
        } catch {
          // not JSON; ignore for transcript aggregation
        }
      } else if (ev.data instanceof ArrayBuffer) {
        append(`<- binary ${ev.data.byteLength}B  ${bytesPreview(ev.data)}`);
      } else {
        append(`<- (unknown frame type: ${typeof ev.data})`);
      }
    };

    ws.onerror = (ev) => {
      append(`error ${ev.type}`);
    };

    ws.onclose = (ev) => {
      append(`closed code=${ev.code} reason=${ev.reason || '(none)'} wasClean=${ev.wasClean}`);
      setState('closed');
      stopMic(); // make sure no orphan AudioContext after the socket dies
    };

    wsRef.current = ws;
  };

  const sendDummyChunk = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      append('cannot send: ws not open');
      return;
    }
    seqRef.current += 1;
    // Payload is left as zeros — this is a seam test, not an audio test.
    const buf = buildFrame(seqRef.current, false, new Uint8Array(DUMMY_PAYLOAD_BYTES));
    ws.send(buf);
    append(`-> binary seq=${seqRef.current} ${buf.byteLength}B (header ${HEADER_BYTES} + payload ${DUMMY_PAYLOAD_BYTES})`);
  };

  const startMic = async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      append('cannot start mic: ws not open');
      return;
    }
    if (micState === 'recording' || micState === 'requesting') {
      append('mic already starting/recording');
      return;
    }
    try {
      setMicState('requesting');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: MIC_TARGET_SR,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // ScriptProcessorNode is deprecated but it's the path that works on
      // every browser without shipping a separate worklet file. B.2's job
      // is to prove the path end-to-end; B.3 will move to AudioWorklet +
      // SharedArrayBuffer with COOP/COEP headers.
      const ctxCtor = (window as any).AudioContext || (window as any).webkitAudioContext;
      const audioCtx: AudioContext = new ctxCtor({ sampleRate: MIC_TARGET_SR });
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      sourceRef.current = source;
      // 4096-sample chunks at the AudioContext's nominal rate. We rebuffer
      // to MIC_FRAME_SAMPLES on the JS side before sending so frames stay
      // a constant ~200 ms regardless of how the device delivers them.
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        // Float32 -> PCM16 LE
        const i16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        micBufRef.current.push(i16);

        // Aggregate to MIC_FRAME_SAMPLES then ship.
        let totalSamples = micBufRef.current.reduce((n, b) => n + b.length, 0);
        while (totalSamples >= MIC_FRAME_SAMPLES) {
          const frame = new Int16Array(MIC_FRAME_SAMPLES);
          let written = 0;
          while (written < MIC_FRAME_SAMPLES && micBufRef.current.length > 0) {
            const head = micBufRef.current[0];
            const remaining = MIC_FRAME_SAMPLES - written;
            if (head.length <= remaining) {
              frame.set(head, written);
              written += head.length;
              micBufRef.current.shift();
            } else {
              frame.set(head.subarray(0, remaining), written);
              micBufRef.current[0] = head.subarray(remaining);
              written += remaining;
            }
          }
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            seqRef.current += 1;
            const buf = buildFrame(seqRef.current, false, frame);
            wsRef.current.send(buf);
          }
          totalSamples -= MIC_FRAME_SAMPLES;
        }
      };

      source.connect(processor);
      // Connect to destination is required for ScriptProcessor to fire in
      // most browsers, but we don't want audible feedback — pipe through
      // a gain node at 0 so the user doesn't hear themselves.
      const sink = audioCtx.createGain();
      sink.gain.value = 0;
      processor.connect(sink);
      sink.connect(audioCtx.destination);

      setMicState('recording');
      append(`mic started (${MIC_TARGET_SR} Hz mono, ~${MIC_FRAME_MS} ms frames)`);
    } catch (err) {
      console.error(err);
      append(`mic error: ${(err as Error).message}`);
      setMicState('error');
      stopMic();
    }
  };

  const stopMic = () => {
    if (processorRef.current) {
      try { processorRef.current.disconnect(); } catch {}
      processorRef.current = null;
    }
    if (sourceRef.current) {
      try { sourceRef.current.disconnect(); } catch {}
      sourceRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch {}
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    micBufRef.current = [];
    if (micState !== 'error') setMicState('idle');
  };

  const sendFlush = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      append('cannot send: ws not open');
      return;
    }
    const msg = JSON.stringify({ type: 'flush' });
    ws.send(msg);
    append(`-> ${msg}`);
  };

  const sendPing = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      append('cannot send: ws not open');
      return;
    }
    const msg = JSON.stringify({ type: 'ping' });
    ws.send(msg);
    append(`-> ${msg}`);
  };

  const sendEnd = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      append('cannot send: ws not open');
      return;
    }
    stopMic();
    const msg = JSON.stringify({ type: 'end' });
    ws.send(msg);
    append(`-> ${msg}`);
    setState('closing');
  };

  const disconnect = () => {
    const ws = wsRef.current;
    stopMic();
    if (!ws) return;
    if (ws.readyState <= WebSocket.OPEN) {
      ws.close(1000, 'client disconnect');
      append('-> client-initiated close 1000');
      setState('closing');
    }
  };

  const clearLog = () => setLog([]);
  const clearTranscript = () => setTranscript([]);

  // Best-effort cleanup if the user navigates away.
  useEffect(() => {
    return () => {
      stopMic();
      const ws = wsRef.current;
      if (ws && ws.readyState <= WebSocket.OPEN) {
        try { ws.close(1001, 'page unload'); } catch {}
      }
    };
  }, []);

  const connected = state === 'open';
  const micRecording = micState === 'recording';

  return (
    <div style={{ padding: 24, color: '#e7e7e7', maxWidth: 1080 }}>
      <h1 style={{ marginTop: 0 }}>Streaming Test (Phase B.2)</h1>
      <p style={{ opacity: 0.7, marginTop: 4 }}>
        Opens a WebSocket against{' '}
        <code>/ws/sessions/&lt;uuid&gt;/live</code> and either streams a
        dummy zero-filled chunk (seam test) or real microphone audio
        (real STT). Backend forwards windowed audio to{' '}
        <code>meet-parakeet-stream-svc</code> on midboy2 every ~2.5 s
        and emits <code>partial</code> / <code>final</code> JSON frames
        back. True NeMo native streaming lands in B.3; see{' '}
        <code>docs/phase-b-server-live-streaming.md</code>.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <button onClick={connect} disabled={connected || state === 'connecting'}>
          Connect
        </button>
        <button onClick={sendDummyChunk} disabled={!connected}>
          Send dummy chunk
        </button>
        <button onClick={startMic} disabled={!connected || micRecording}>
          Start mic
        </button>
        <button onClick={stopMic} disabled={!micRecording}>
          Stop mic
        </button>
        <button onClick={sendFlush} disabled={!connected}>
          Send {'{"type":"flush"}'}
        </button>
        <button onClick={sendPing} disabled={!connected}>
          Send {'{"type":"ping"}'}
        </button>
        <button onClick={sendEnd} disabled={!connected}>
          Send {'{"type":"end"}'}
        </button>
        <button onClick={disconnect} disabled={!connected}>
          Disconnect
        </button>
      </div>

      <div style={{ marginBottom: 8, fontSize: 13, opacity: 0.8 }}>
        ws: <strong>{state}</strong>
        {' · '}
        mic: <strong>{micState}</strong>
        {sessionIdRef.current && (
          <>
            {' · '}
            session_id: <code>{sessionIdRef.current}</code>
          </>
        )}
        {' · '}
        seq: <code>{seqRef.current}</code>
      </div>

      {/* Live transcript pane — populated from partial/final JSON frames. */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <strong style={{ fontSize: 14 }}>Live transcript</strong>
          <button onClick={clearTranscript} style={{ fontSize: 12 }}>
            Clear
          </button>
          <span style={{ fontSize: 12, opacity: 0.6 }}>
            {transcript.length} entries
          </span>
        </div>
        <div
          style={{
            background: '#080808',
            padding: 12,
            borderRadius: 6,
            fontSize: 14,
            maxHeight: 280,
            overflow: 'auto',
            border: '1px solid #1f1f1f',
            lineHeight: 1.5,
          }}
        >
          {transcript.length === 0 ? (
            <span style={{ opacity: 0.4 }}>
              (no partials yet — connect, start mic, and speak)
            </span>
          ) : (
            transcript.map((e, i) => (
              <div
                key={`${e.sequence}-${i}`}
                style={{
                  opacity: e.type === 'final' ? 1 : 0.72,
                  fontWeight: e.type === 'final' ? 500 : 400,
                  borderLeft: e.type === 'final' ? '2px solid #4caf50' : '2px solid #1976d2',
                  paddingLeft: 8,
                  marginBottom: 4,
                }}
                title={`${e.type} seq=${e.sequence} ${e.ts}`}
              >
                {e.text || <em style={{ opacity: 0.5 }}>(empty)</em>}
              </div>
            ))
          )}
        </div>
      </div>

      <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.6 }}>
        Raw WS traffic ({log.length} lines, capped at 500):
        <button onClick={clearLog} style={{ marginLeft: 8, fontSize: 12 }}>
          Clear log
        </button>
      </div>

      <pre
        style={{
          background: '#0a0a0a',
          padding: 12,
          borderRadius: 6,
          fontSize: 12,
          maxHeight: 400,
          overflow: 'auto',
          border: '1px solid #1f1f1f',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        {log.length === 0 ? '(no traffic yet — click Connect)' : log.join('\n')}
      </pre>
    </div>
  );
}
