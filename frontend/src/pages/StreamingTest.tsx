/**
 * Phase B.1 streaming WS smoke-test page.
 *
 * Opens a WebSocket against `/ws/sessions/{uuid}/live`, lets the operator
 * send a dummy 1 KB PCM16-formatted binary chunk wrapped in the 19-byte
 * header the meet-backend speaks, and prints every frame in both directions.
 *
 * Real Parakeet integration + a microphone capture path ship in Phase B.2.
 * This page is intentionally minimal — just enough to prove the
 * Cloudflare -> oauth2-proxy -> Traefik -> FastAPI WS upgrade seam.
 */
import { useRef, useState } from 'react';

type WSState = 'idle' | 'connecting' | 'open' | 'closing' | 'closed';

const HEADER_BYTES = 19;
const DUMMY_PAYLOAD_BYTES = 1024; // ~32 ms of 16 kHz mono PCM16

function nowIso(): string {
  return new Date().toISOString();
}

function bytesPreview(buf: ArrayBuffer, max = 64): string {
  const view = new Uint8Array(buf, 0, Math.min(buf.byteLength, max));
  const hex = Array.from(view).map(b => b.toString(16).padStart(2, '0')).join(' ');
  return buf.byteLength > max ? `${hex} ... (+${buf.byteLength - max}B)` : hex;
}

export default function StreamingTest() {
  const [log, setLog] = useState<string[]>([]);
  const [state, setState] = useState<WSState>('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const seqRef = useRef(0);
  const sessionIdRef = useRef<string>('');

  const append = (line: string) => {
    // Cap log to last 500 entries so a long test session doesn't gum up
    // the React render. The full traffic is in the browser console too.
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

    const sessionId = (globalThis.crypto?.randomUUID?.() ?? `b1-${Date.now().toString(36)}`);
    sessionIdRef.current = sessionId;
    seqRef.current = 0;

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
    };

    wsRef.current = ws;
  };

  const sendDummyChunk = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      append('cannot send: ws not open');
      return;
    }

    const buf = new ArrayBuffer(HEADER_BYTES + DUMMY_PAYLOAD_BYTES);
    const view = new DataView(buf);

    seqRef.current += 1;

    // Header layout — must match HEADER_STRUCT (">IQ4sHB") on the
    // backend in backend/api/streaming.py.
    //   bytes 0-3   uint32 BE  sequence
    //   bytes 4-11  uint64 BE  client_timestamp_us
    //   bytes 12-15 ASCII      payload_format ("PC16")
    //   bytes 16-17 uint16 BE  sample_rate / 100  (160 = 16000 Hz)
    //   byte 18     uint8      flags  (bit 0: is_final)
    view.setUint32(0, seqRef.current, /* littleEndian */ false);
    view.setBigUint64(4, BigInt(Date.now()) * 1000n, false);
    const fmt = new Uint8Array(buf, 12, 4);
    fmt[0] = 0x50; // 'P'
    fmt[1] = 0x43; // 'C'
    fmt[2] = 0x31; // '1'
    fmt[3] = 0x36; // '6'
    view.setUint16(16, 160, false); // 16000 Hz / 100
    view.setUint8(18, 0); // not-final

    // Payload is left as zeros — this is a seam test, not an audio test.
    ws.send(buf);
    append(`-> binary seq=${seqRef.current} ${buf.byteLength}B (header ${HEADER_BYTES} + payload ${DUMMY_PAYLOAD_BYTES})`);
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
    const msg = JSON.stringify({ type: 'end' });
    ws.send(msg);
    append(`-> ${msg}`);
    setState('closing');
  };

  const disconnect = () => {
    const ws = wsRef.current;
    if (!ws) return;
    if (ws.readyState <= WebSocket.OPEN) {
      ws.close(1000, 'client disconnect');
      append('-> client-initiated close 1000');
      setState('closing');
    }
  };

  const clearLog = () => setLog([]);

  const connected = state === 'open';

  return (
    <div style={{ padding: 24, color: '#e7e7e7', maxWidth: 960 }}>
      <h1 style={{ marginTop: 0 }}>Streaming Test (Phase B.1)</h1>
      <p style={{ opacity: 0.7, marginTop: 4 }}>
        Scaffolding-only smoke test. Opens a WebSocket against{' '}
        <code>/ws/sessions/&lt;uuid&gt;/live</code>, sends a dummy 1 KB PCM16-formatted chunk
        wrapped in the 19-byte header the backend speaks, prints every frame in both
        directions. No microphone capture, no real STT. Real Parakeet 0.6B v3 streaming
        integration ships in Phase B.2 per <code>docs/phase-b-server-live-streaming.md</code>.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <button onClick={connect} disabled={connected || state === 'connecting'}>
          Connect
        </button>
        <button onClick={sendDummyChunk} disabled={!connected}>
          Send dummy chunk
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
        <button onClick={clearLog}>Clear log</button>
      </div>

      <div style={{ marginBottom: 8, fontSize: 13, opacity: 0.8 }}>
        state: <strong>{state}</strong>
        {sessionIdRef.current && (
          <>
            {' · '}
            session_id: <code>{sessionIdRef.current}</code>
          </>
        )}
        {' · '}
        seq: <code>{seqRef.current}</code>
      </div>

      <pre
        style={{
          background: '#0a0a0a',
          padding: 12,
          borderRadius: 6,
          fontSize: 12,
          maxHeight: 600,
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
