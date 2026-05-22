"""Phase B.1 server-live streaming WebSocket endpoint.

This module implements the meet-backend side of the Phase B server-live
audio pipeline described in `docs/phase-b-server-live-streaming.md` section
4. B.1 is scaffolding-only — we accept the upgrade, log binary frames per
the 19-byte header protocol, and ack them. The real forward path to
`meet-parakeet-stream-svc` + partial-transcript emission lands in B.2.

Endpoint
--------
``ws[s]://<host>/ws/sessions/{session_id}/live``

Auth
----
oauth2-proxy in front of meet-backend forwards ``X-Auth-Request-Email`` /
``X-Auth-Request-Preferred-Username`` headers to upstream on every request,
including the HTTP upgrade that initiates a WebSocket. We inspect those
headers off ``websocket.headers``, look up the user, and reject with close
code 4001 if no user matches.

Frame protocol (B.1 scaffold)
-----------------------------
The user-supplied design directive for B.1 uses a 19-byte big-endian header
on every binary frame::

    bytes 0-3   uint32 BE  sequence_number
    bytes 4-11  uint64 BE  client_timestamp_us (microseconds)
    bytes 12-15 4-char ASCII  payload_format  ("PC16" = 16 kHz mono PCM16)
    bytes 16-17 uint16 BE  sample_rate / 100  (160 = 16000 Hz)
    byte 18     uint8       flags  (bit 0: is_final)

This differs from the Phase B design doc section 4's framing (1-byte
version + uint64 LE sequence + uint64 LE timestamp_ms + uint16 LE
payload_format + payload) — the doc's wider framing is what we'll likely
adopt in B.2 once the protocol is finalized. For B.1 we follow the user
spec verbatim so the frontend test page and backend agree, and so the
Python+TypeScript struct definitions are testable end-to-end. The B.2
implementer should resolve the framing question in the design doc before
shipping real-model traffic.

Control frames (text/JSON)
--------------------------
- ``{"type": "end"}``       — client done; server closes with 1000.
- ``{"type": "ping"}``      — keepalive; server replies ``{"type": "pong"}``.
- anything else             — echoed back as ``{"type":"ack_control"}``.

Server-emitted frames
---------------------
- ``{"type": "ready", ...}``         — sent immediately after accept.
- ``{"type": "ack",   ...}``         — per binary frame.
- ``{"type": "ack_control", ...}``   — per unknown control frame.
- ``{"type": "error", ...}``         — per malformed frame.
- ``{"type": "pong"}``               — per ``{"type":"ping"}`` control.
- ``{"type": "closed", ...}``        — server-initiated close.
"""
from __future__ import annotations

import json
import logging
import struct
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])

# Frame layout — see module docstring.
HEADER_SIZE = 19
HEADER_STRUCT = ">IQ4sHB"
PROTOCOL_VERSION = "0.1.0-scaffold"


def _resolve_ws_user_email(websocket: WebSocket) -> Optional[str]:
    """Read oauth2-proxy forward-auth email off the WebSocket upgrade headers.

    Mirrors the trust order in ``auth.dependencies.get_current_user_optional``
    so a user authenticated against the REST API the same way is recognised
    here. Returns the first non-empty email-shaped value, else None.
    """
    candidates = [
        websocket.headers.get("x-auth-request-email"),
        websocket.headers.get("x-forwarded-email"),
        websocket.headers.get("x-auth-request-preferred-username"),
        websocket.headers.get("x-forwarded-preferred-username"),
        websocket.headers.get("x-auth-request-user"),
        websocket.headers.get("x-forwarded-user"),
    ]
    for raw in candidates:
        if not raw:
            continue
        value = raw.strip()
        if value:
            return value
    return None


@router.websocket("/ws/sessions/{session_id}/live")
async def session_live(websocket: WebSocket, session_id: str) -> None:
    """Phase B.1 scaffold WS endpoint.

    Accepts the upgrade if oauth2-proxy forwarded an authenticated email
    header, echoes a ``ready`` frame, then loops:
      - on binary frames: parse the 19-byte header, log fields, ack.
      - on text frames: parse JSON, handle ``end`` / ``ping`` / unknown.

    No audio is forwarded anywhere in B.1. The /api/ws/sessions/<id>/live
    URL is mounted under the same Traefik + oauth2-proxy ingress as the
    existing /ws/audio-levels WebSocket, so the auth + WS-upgrade path is
    already production-proven (see reference note in design doc section 4).
    """
    # Auth gate. Reject before accept() so the client sees a clean 4001
    # close rather than an opened-then-dropped socket. oauth2-proxy strips
    # the headers if the user isn't authenticated, so absence == not authed.
    user_email = _resolve_ws_user_email(websocket)
    if not user_email:
        # Per RFC 6455 §7.4.1, 4001 is in the application range. We pick it
        # to match the satellite + remote-audio convention used elsewhere
        # in the backend for "auth failed at handshake".
        logger.warning(
            "[B.1 WS] unauthenticated connection attempt session_id=%s "
            "headers_present=%s",
            session_id,
            sorted(k for k in websocket.headers.keys() if k.startswith("x-")),
        )
        await websocket.close(code=4001)
        return

    await websocket.accept()
    logger.info(
        "[B.1 WS] connected session_id=%s user=%s",
        session_id,
        user_email,
    )

    # The "ready" frame announces the protocol version + server time so a
    # client can sanity-check its struct layout matches before sending
    # audio. The B.2 implementation should add `model_status`, `provider`,
    # and an entitlement echo so tier-gating decisions are auditable from
    # the client side.
    await websocket.send_json({
        "type": "ready",
        "session_id": session_id,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "protocol_version": PROTOCOL_VERSION,
        "phase": "B.1",
        "scaffold": True,
    })

    try:
        while True:
            message = await websocket.receive()

            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                logger.info(
                    "[B.1 WS] disconnect frame session_id=%s code=%s",
                    session_id,
                    message.get("code"),
                )
                return

            if "bytes" in message and message["bytes"] is not None:
                data: bytes = message["bytes"]
                if len(data) < HEADER_SIZE:
                    logger.warning(
                        "[B.1 WS] frame_too_short session_id=%s got=%d expected>=%d",
                        session_id,
                        len(data),
                        HEADER_SIZE,
                    )
                    await websocket.send_json({
                        "type": "error",
                        "reason": "frame_too_short",
                        "got_bytes": len(data),
                        "expected_min_bytes": HEADER_SIZE,
                    })
                    continue

                try:
                    seq, ts_us, fmt_bytes, sr100, flags = struct.unpack(
                        HEADER_STRUCT, data[:HEADER_SIZE]
                    )
                except struct.error as exc:
                    logger.warning(
                        "[B.1 WS] header_unpack_failed session_id=%s err=%s",
                        session_id,
                        exc,
                    )
                    await websocket.send_json({
                        "type": "error",
                        "reason": "header_unpack_failed",
                        "detail": str(exc),
                    })
                    continue

                fmt_str = fmt_bytes.decode("ascii", errors="replace")
                payload_len = len(data) - HEADER_SIZE
                is_final = bool(flags & 0x01)

                logger.info(
                    "[B.1 WS] frame session=%s seq=%d ts_us=%d fmt=%s "
                    "sr=%d payload_bytes=%d final=%s",
                    session_id,
                    seq,
                    ts_us,
                    fmt_str,
                    sr100 * 100,
                    payload_len,
                    is_final,
                )

                # In Phase B.2 this is the seam where we forward the
                # payload to meet-parakeet-stream-svc and emit
                # "partial" / "final" transcript frames back to the
                # client as transcripts arrive. For B.1 we just ack so
                # the client can verify round-trip latency.
                await websocket.send_json({
                    "type": "ack",
                    "sequence": seq,
                    "received_bytes": len(data),
                    "header_bytes": HEADER_SIZE,
                    "payload_bytes": payload_len,
                    "format": fmt_str,
                    "sample_rate": sr100 * 100,
                    "is_final": is_final,
                })
                continue

            if "text" in message and message["text"] is not None:
                raw_text = message["text"]
                try:
                    ctrl = json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "[B.1 WS] bad_json session_id=%s err=%s preview=%r",
                        session_id,
                        exc,
                        raw_text[:80],
                    )
                    await websocket.send_json({
                        "type": "error",
                        "reason": "bad_json",
                        "detail": str(exc),
                    })
                    continue

                ctrl_type = ctrl.get("type") if isinstance(ctrl, dict) else None

                if ctrl_type == "end":
                    logger.info(
                        "[B.1 WS] client requested end session_id=%s",
                        session_id,
                    )
                    await websocket.send_json({
                        "type": "closed",
                        "reason": "client_end",
                    })
                    await websocket.close(code=1000)
                    return

                if ctrl_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                # Unknown control type — echo + log. Keeps the socket
                # alive so future protocol extensions can be probed
                # without crashing existing servers.
                logger.info(
                    "[B.1 WS] unknown_control session_id=%s ctrl=%s",
                    session_id,
                    ctrl,
                )
                await websocket.send_json({
                    "type": "ack_control",
                    "echo": ctrl,
                })

    except WebSocketDisconnect as exc:
        logger.info(
            "[B.1 WS] client disconnected session_id=%s code=%s",
            session_id,
            getattr(exc, "code", "?"),
        )
    except Exception:
        # Don't swallow — log full traceback and let FastAPI close the
        # socket. Silent kill is the worst possible UX for live captions
        # debugging in B.2.
        logger.exception(
            "[B.1 WS] unexpected error session_id=%s user=%s",
            session_id,
            user_email,
        )
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
