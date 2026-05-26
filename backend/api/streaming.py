"""Phase B.2 server-live streaming WebSocket endpoint (tier-gated in B.4).

This module implements the meet-backend side of the Phase B server-live
audio pipeline described in `docs/phase-b-server-live-streaming.md`.

B.2 ships:
  - real per-session audio buffering (PCM16 ring),
  - periodic forwarding (every ~2.5 s of speech OR on ``{"type": "flush"}``)
    of the buffered audio to ``meet-parakeet-stream-svc`` on midboy2,
  - emission of partial / final transcript frames back to the WS client,
  - control-frame ``end`` triggers one last flush + a final transcript.

B.4 layers on top:
  - tier gate on the ``server_live`` capability. Free-tier users get a
    JSON ``{"type": "error", "reason": "tier_insufficient", ...}`` frame
    followed by close code 4003 (RFC 6455 application-specific range).
    Pro / Enterprise / superuser-overridden proceed normally.

This is **near-streaming**: chunked offline transcription over short
windows. True NeMo streaming (draft + finalize tokens) lands in B.3.
The wire contract from Section 4 of the design doc is forward-compatible
with the B.3 protocol; the only thing that changes is that the partials
will come faster + finer-grained when the streaming model is wired in.

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

Tier gate (B.4)
---------------
After the user is resolved (DB row, not just email), we check
``get_tier_features(user)['server_live']``. If False:

  - ``await websocket.accept()`` so we can send a clean payload,
  - emit ``{"type": "error", "reason": "tier_insufficient", ...}``,
  - close with code 4003, reason "tier_insufficient".

``get_user_tier()`` (in ``auth/tier.py``) treats ``is_superuser=True``
as enterprise regardless of the tier column, so support/dev accounts
keep server-live access without per-tier toggling.

Frame protocol (canonical as of B.2 reconciliation 2026-05-22)
--------------------------------------------------------------
The 19-byte fixed big-endian header carries every binary audio frame::

    bytes 0-3   uint32 BE  sequence_number   (per-stream monotonic)
    bytes 4-11  uint64 BE  client_timestamp_us
    bytes 12-15 4-char ASCII  payload_format  ("PC16" = 16 kHz mono PCM16)
    bytes 16-17 uint16 BE  sample_rate / 100  (160 = 16000 Hz)
    byte 18     uint8       flags  (bit 0: is_final)
    bytes 19..N audio payload (PCM16 little-endian by convention)

The design doc originally drafted a variable-length little-endian header
with a leading version byte; Phase B.2 reconciled to this fixed
big-endian form because it's simpler to parse correctly in both Python
and TypeScript and carries identical information. See section 4 of
``docs/phase-b-server-live-streaming.md`` for the full rationale.

Control frames (text/JSON)
--------------------------
- ``{"type": "end"}``    — client done; one final flush + close.
- ``{"type": "flush"}``  — force-transcribe the current buffer now.
- ``{"type": "ping"}``   — keepalive; server replies with ``pong``.
- anything else          — echoed as ``ack_control`` (forward-compat).

Server-emitted frames
---------------------
- ``{"type": "ready", ...}``         — sent immediately after accept.
- ``{"type": "ack",   ...}``         — per binary frame (header echo).
- ``{"type": "partial", ...}``       — chunked transcript while audio flows.
- ``{"type": "final", ...}``         — last transcript on session end.
- ``{"type": "ack_control", ...}``   — per unknown control frame.
- ``{"type": "error", ...}``         — per malformed frame / upstream fail.
- ``{"type": "pong"}``               — per ``{"type":"ping"}`` control.
- ``{"type": "closed", ...}``        — server-initiated close.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from prometheus_client import Counter, Histogram
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import DetachedInstanceError

from auth.models import User
from auth.service import AuthService
from auth.tier import get_tier_features, get_user_tier
from database.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])

# ---------------------------------------------------------------------------
# Phase B.5 Prometheus metrics
# ---------------------------------------------------------------------------
#
# Exposed via /metrics in backend/main.py. Labels stay low-cardinality so
# the Prometheus scrape doesn't blow up. We don't put session_id on any
# label - it's per-connection unique. Tier values are bounded by
# TIER_FEATURES (free/pro/enterprise), result values are enumerated below.

ws_connections_total = Counter(
    "meeting_ops_ws_connections_total",
    "WebSocket connection attempts on /ws/sessions/{id}/live",
    ["tier", "result"],  # tier=free/pro/enterprise/unknown,
                          # result=accepted/tier_rejected/auth_rejected/rate_limited
)

ws_audio_frames_forwarded_total = Counter(
    "meeting_ops_ws_audio_frames_forwarded_total",
    "Audio frames forwarded to parakeet-stream-svc",
)

ws_partial_transcripts_emitted_total = Counter(
    "meeting_ops_ws_partial_transcripts_emitted_total",
    "Partial transcripts emitted back to clients",
)

ws_close_codes_total = Counter(
    "meeting_ops_ws_close_codes_total",
    "WebSocket close codes seen",
    ["code"],
)

parakeet_stream_request_duration_seconds = Histogram(
    "meeting_ops_parakeet_stream_request_duration_seconds",
    "Round-trip time for parakeet-stream-svc /transcribe-stream calls",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)


# ---------------------------------------------------------------------------
# Phase B.5 backpressure + rate limit state
# ---------------------------------------------------------------------------
#
# Active sessions: registry of currently-open WS handlers, indexed by
# session_id. Used by the SIGTERM drain hook in main.py to send a
# "server_shutdown" frame + close-1001 to each active client before exit.
# Also used by the per-org rate-limit logic to count concurrent live
# sessions per org.

active_sessions: dict[str, WebSocket] = {}
# Per-org concurrent session count. Indexed by str(org_id) - org_id can be
# None for users without an org assignment, in which case we use the
# user email as the bucket so the limit still applies somewhere meaningful.
_org_session_counts: dict[str, int] = defaultdict(int)
# Slow-parakeet threshold. If a flush takes longer than this, we skip the
# next N forwards to give the GPU breathing room.
STREAM_SLOW_THRESHOLD_S = float(os.getenv("STREAM_SLOW_THRESHOLD_S", "2.0"))
STREAM_SKIP_NEXT_ON_SLOW = int(os.getenv("STREAM_SKIP_NEXT_ON_SLOW", "2"))
# Per-org concurrent live-session cap. Excess connections get close 4429.
STREAMING_MAX_SESSIONS_PER_ORG = int(
    os.getenv("STREAMING_MAX_SESSIONS_PER_ORG", "5")
)


def _resolve_org_bucket(user: User) -> str:
    """Pick a stable bucket key for per-org rate limiting.

    Prefer the user's organization id if available (auth.models.User may
    expose it via .organization_id, .org_id, .organizations[0].id, etc.,
    depending on the schema). Fall back to the email so the limit still
    has a meaningful unit even for users without an org.

    Wrapped in a DetachedInstanceError-safe try/except because
    ``_resolve_ws_user`` closes its DB session before returning the User
    object (Starlette's WebSocket handlers don't compose cleanly with
    ``Depends(get_db)`` yield-style sessions). Accessing the unloaded
    ``organizations`` relationship on a detached User triggers a
    lazy-load that raises DetachedInstanceError — falling back to the
    email-based bucket is the correct behavior in that case.
    """
    for attr in ("organization_id", "org_id"):
        val = getattr(user, attr, None)
        if val:
            return f"org:{val}"
    try:
        orgs = getattr(user, "organizations", None)
    except DetachedInstanceError:
        orgs = None
    if orgs:
        try:
            first = orgs[0]
            oid = getattr(first, "id", None) or getattr(first, "organization_id", None)
            if oid:
                return f"org:{oid}"
        except (IndexError, TypeError, AttributeError, DetachedInstanceError):
            pass
    return f"user:{user.email}"

# Frame layout — see module docstring.
HEADER_SIZE = 19
HEADER_STRUCT = ">IQ4sHB"
PROTOCOL_VERSION = "0.2.0"  # bumped from 0.1.0-scaffold (B.1) for real forwarding.

# Where the streaming STT service lives. midboy2 over Tailscale by default,
# matching the existing PARAKEET_SERVER_URL convention. Overridable via env
# so dev / smoke-test setups can point at a local stub.
PARAKEET_STREAM_URL = os.getenv(
    "PARAKEET_STREAM_URL",
    "http://100.66.42.57:8895",
).rstrip("/")

# Window flush cadence. Every 2.5 s of audio (or on explicit flush) we
# build a WAV from the accumulated PCM16 frames and POST it. Shorter
# windows give snappier partials at the cost of more upstream load;
# longer windows give better word-level continuity. 2.5 s is the
# starting compromise; B.3 will replace this with NeMo native streaming.
FLUSH_AUDIO_SECONDS = float(os.getenv("STREAM_FLUSH_AUDIO_SECONDS", "2.5"))

# Upper bound on retained PCM audio per session. We never need more than
# this on the live path — the canonical transcript comes from the chunks
# upload pipeline that runs in parallel. 60 s is generous; the live
# rolling window is intentionally short.
MAX_PCM_BUFFER_SECONDS = 60.0

# Upstream HTTP timeouts. The model on midboy2 takes ~200-600 ms for a
# 2.5 s window at fp16 on the 3060 once warmed; cold start is up to
# ~30 s while NeMo loads. We give /transcribe-stream 30 s of grace
# during warm-up and 10 s once warm — both controllable via env.
STREAM_UPSTREAM_TIMEOUT_S = float(os.getenv("STREAM_UPSTREAM_TIMEOUT_S", "30.0"))

# ---------------------------------------------------------------------------
# Phase B.3 integration flags
# ---------------------------------------------------------------------------
# All default OFF — production behavior is identical to v1.0.0/v1.1.0. Flip
# per env after the corresponding B.3 chunk lands and is verified.
# See docs/phase-b3-integration-plan.md for the integration target spec.
#
# These are read at module import; the integration PR that follows B.3 agent
# completion will reference them in _flush_to_stt() to route audio per flag.
STREAMING_USE_V2_PARAKEET = os.getenv("STREAMING_USE_V2_PARAKEET", "0") not in (
    "0", "false", "False", "no", "",
)
STREAMING_USE_SORTFORMER = os.getenv("STREAMING_USE_SORTFORMER", "0") not in (
    "0", "false", "False", "no", "",
)
# Where the streaming Sortformer service will live once Phase B.3 chunk D
# ships. midboy2 over Tailscale, parallel port to parakeet-stream-svc (8895)
# and parakeet-svc (8881). Overridable via env so dev / smoke-test setups
# can point at a local stub.
SORTFORMER_URL = os.getenv(
    "SORTFORMER_URL",
    "http://100.66.42.57:8896",
).rstrip("/")


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


def _resolve_ws_user(websocket: WebSocket) -> Optional[User]:
    """Resolve a DB User from oauth2-proxy headers on the WS upgrade.

    Returns None if no email-shaped header is present OR if the email
    doesn't map to an active User row. Looks the user up directly so the
    caller has access to the tier/is_superuser columns for the B.4 gate.

    We open + close our own ``SessionLocal()`` since ``Depends(get_db)``
    doesn't compose cleanly with WebSocket handlers (Starlette doesn't
    run dependencies that yield for a WS upgrade). The session is closed
    before we return — we hold the User object, not the session, for the
    rest of the WS lifecycle.

    Overridable for tests via ``app.dependency_overrides`` on the module-
    level callable (see ``test_streaming_tier_gate.py``).
    """
    email = _resolve_ws_user_email(websocket)
    if not email:
        return None

    db: Session = SessionLocal()
    try:
        # Lookup is case-insensitive on email; mirror service.get_user_by_email.
        user = AuthService.get_user_by_email(db, email)
        if user and user.is_active:
            # Detach: we want to read attributes after the session closes.
            db.expunge(user)
            return user
        return None
    except Exception:
        logger.exception("[B.4 WS] user lookup failed email=%s", email)
        return None
    finally:
        db.close()


@dataclass
class _SessionState:
    """Per-WS server-side state.

    The PCM buffer is a list of raw PCM16 little-endian frames the client
    sent. We concatenate when it's time to flush (no need to keep a
    contiguous bytearray hot — this is run rarely).

    last_seq is the highest sequence number we've received; the client
    can use ``ack`` echoes to detect drops. last_flush_at_audio_ms tracks
    cumulative audio (in ms) at the time of the last upstream call so we
    can fire when ``cumulative - last_flush >= FLUSH_AUDIO_SECONDS * 1000``.

    Phase B.5 additions:
      - ``bytes_dropped_backpressure`` records how much PCM we dropped due
        to the 60 s cap, exposed in close-frame diagnostics.
      - ``skip_next_n`` counts down forwards to skip because the previous
        flush exceeded ``STREAM_SLOW_THRESHOLD_S``. While > 0, ``should_flush``
        keeps returning False until the GPU catches up.
      - ``org_bucket`` is the key into ``_org_session_counts`` so we can
        decrement on disconnect.
    """
    session_id: str
    user_email: str
    org_bucket: str = ""
    sample_rate: int = 16000  # filled from first audio frame
    pcm_chunks: list[bytes] = field(default_factory=list)
    cumulative_audio_ms: int = 0
    last_flush_at_audio_ms: int = 0
    last_seq: int = 0
    flush_counter: int = 0  # increments per upstream transcribe call
    last_partial_text: str = ""  # de-dup empty/identical partials
    in_flight: bool = False  # one upstream call at a time per session
    bytes_dropped_backpressure: int = 0  # cumulative PCM dropped due to 60s cap
    skip_next_n: int = 0  # remaining flushes to skip after a slow upstream

    def append_pcm(self, payload: bytes, sample_rate: int) -> None:
        """Append a PCM16 payload and update the cumulative-audio bookkeeping.

        Phase B.5: enforces the 60 s cap as a hard ceiling. If the
        incoming payload would push us over, we drop the oldest data and
        log a structured warning so operators can see backpressure
        kicking in.
        """
        if not payload:
            return
        self.sample_rate = sample_rate or self.sample_rate
        # PCM16 = 2 bytes per sample, mono.
        samples = len(payload) // 2
        ms = int(round((samples / float(self.sample_rate)) * 1000.0))
        self.pcm_chunks.append(payload)
        self.cumulative_audio_ms += ms

        # Trim the front of the buffer if we'd exceed MAX_PCM_BUFFER_SECONDS.
        # We keep flushes small + recent; older audio is the chunks-upload
        # pipeline's job.
        max_bytes = int(MAX_PCM_BUFFER_SECONDS * self.sample_rate * 2)
        total = sum(len(c) for c in self.pcm_chunks)
        dropped_this_call = 0
        while total > max_bytes and len(self.pcm_chunks) > 1:
            dropped = self.pcm_chunks.pop(0)
            total -= len(dropped)
            dropped_this_call += len(dropped)

        if dropped_this_call > 0:
            self.bytes_dropped_backpressure += dropped_this_call
            logger.warning(
                "[streaming-backpressure] session=%s dropped %d bytes "
                "(buffer exceeded %ds cap, total_dropped=%d)",
                self.session_id, dropped_this_call,
                int(MAX_PCM_BUFFER_SECONDS), self.bytes_dropped_backpressure,
            )

    def should_flush(self) -> bool:
        """True when we have at least FLUSH_AUDIO_SECONDS of new audio since the
        last flush. Uses cumulative bookkeeping, not buffer size, so a slow
        client doesn't gate us on calendar time.

        Phase B.5: respects ``skip_next_n``. When the previous flush took
        longer than ``STREAM_SLOW_THRESHOLD_S`` we decrement skip_next_n
        instead of flushing, giving the GPU breathing room. We still
        advance ``last_flush_at_audio_ms`` so we don't accumulate a
        firehose of pending audio while we wait."""
        delta_ms = self.cumulative_audio_ms - self.last_flush_at_audio_ms
        if delta_ms < int(FLUSH_AUDIO_SECONDS * 1000):
            return False
        if self.skip_next_n > 0:
            self.skip_next_n -= 1
            # Advance the watermark so we don't run away with backlog -
            # the trim-to-25 s window in take_pcm keeps the actual buffer
            # bounded; this just keeps the cadence honest.
            self.last_flush_at_audio_ms = self.cumulative_audio_ms
            logger.info(
                "[streaming-backpressure] session=%s skipping flush "
                "(skip_next_n remaining=%d, audio_ms=%d)",
                self.session_id, self.skip_next_n, self.cumulative_audio_ms,
            )
            return False
        return True

    def take_pcm(self, max_seconds: float = 25.0) -> bytes:
        """Return up to ``max_seconds`` of the most recent PCM16 (does NOT clear).

        We keep the buffer around so the next flush includes overlap with the
        prior window — this gives the model a tiny bit of continuity context
        across windows without needing a streaming state machine. The cheap
        trim in ``append_pcm`` keeps the long-term buffer bounded to
        MAX_PCM_BUFFER_SECONDS, but for each upstream call we send only the
        most recent ``max_seconds`` so the streaming service stays inside its
        own per-call window limit (default 30 s on parakeet-stream-svc).

        The model will see each window with overlap from the previous one —
        the partial transcript "grows" sentence-by-sentence as more audio
        arrives, which matches the design doc's transcript_partial semantics.
        """
        joined = b"".join(self.pcm_chunks)
        max_bytes = int(max_seconds * self.sample_rate * 2)
        if len(joined) <= max_bytes:
            return joined
        return joined[-max_bytes:]


def _pcm16_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM16 LE mono in a minimal WAV/RIFF container so the
    transcribe service can ``soundfile.read()`` it without us shipping
    audio metadata in the request body.

    We do this in-memory (no temp file) because the buffers are small
    (~80 KB for 2.5 s of 16 kHz PCM16) and we want the call to be
    allocation-cheap on each flush.
    """
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # PCM16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


async def _flush_to_stt(
    state: _SessionState,
    websocket: WebSocket,
    *,
    is_final: bool,
    http_client: httpx.AsyncClient,
) -> None:
    """Build the current window into a WAV, POST to the streaming service,
    and emit a ``partial`` / ``final`` JSON frame back to the WS client.

    Concurrency: only one flush at a time per session (gated by
    ``state.in_flight``). If a flush is already in flight and the cadence
    fires again, we skip — the in-flight call already covers the window
    we'd be sending. Final flushes (on ``end``) override the gate so the
    last segment never gets dropped.
    """
    if not state.pcm_chunks:
        return

    if state.in_flight and not is_final:
        # Already a call in flight; skip this cadence tick.
        return

    state.in_flight = True
    state.flush_counter += 1
    seq = state.flush_counter
    pcm_at_call = state.take_pcm()
    cumulative_at_call = state.cumulative_audio_ms
    state.last_flush_at_audio_ms = cumulative_at_call

    # Metric: every flush call counts as one audio-frame forward to the
    # upstream. Increment before the call so a hard crash mid-call still
    # leaves a trace in the counter.
    ws_audio_frames_forwarded_total.inc()
    started = time.time()

    try:
        wav_bytes = _pcm16_to_wav_bytes(pcm_at_call, state.sample_rate)

        url = f"{PARAKEET_STREAM_URL}/transcribe-stream"
        headers = {
            "Content-Type": "audio/wav",
            "X-Session-Id": state.session_id,
            "X-Flush-Sequence": str(seq),
            "X-Is-Final": "1" if is_final else "0",
        }

        # Phase B.3 chunk D: fire sortformer in parallel with parakeet when
        # the flag is on. Sortformer is fast (~175 ms warm on RTX 3060) so
        # collecting its result after parakeet usually adds zero latency.
        # Failures here are non-blocking — we only annotate the partial JSON
        # with empty speakers, and the user gets the same transcript.
        sortformer_task: Optional[asyncio.Task] = None
        if STREAMING_USE_SORTFORMER:
            window_duration_ms = int(
                len(pcm_at_call) / 2 / state.sample_rate * 1000
            )
            window_start_ms = max(0, cumulative_at_call - window_duration_ms)
            sortformer_headers = {
                **headers,
                "X-Window-Start-Ms": str(window_start_ms),
            }
            sortformer_task = asyncio.create_task(
                http_client.post(
                    f"{SORTFORMER_URL}/diarize-stream",
                    content=wav_bytes,
                    headers=sortformer_headers,
                    timeout=STREAM_UPSTREAM_TIMEOUT_S,
                )
            )

        try:
            with parakeet_stream_request_duration_seconds.time():
                resp = await http_client.post(
                    url,
                    content=wav_bytes,
                    headers=headers,
                    timeout=STREAM_UPSTREAM_TIMEOUT_S,
                )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            logger.warning(
                "[B.2 WS] upstream_unreachable session=%s seq=%d err=%s",
                state.session_id, seq, exc,
            )
            # Cancel sortformer if it's still running — no point computing
            # speaker labels for a partial we won't emit.
            if sortformer_task is not None and not sortformer_task.done():
                sortformer_task.cancel()
            await websocket.send_json({
                "type": "error",
                "reason": "upstream_unreachable",
                "sequence": seq,
                "detail": str(exc)[:200],
                "retryable": True,
            })
            return

        if resp.status_code >= 400:
            logger.warning(
                "[B.2 WS] upstream_http_error session=%s seq=%d status=%d body=%s",
                state.session_id, seq, resp.status_code, resp.text[:200],
            )
            if sortformer_task is not None and not sortformer_task.done():
                sortformer_task.cancel()
            await websocket.send_json({
                "type": "error",
                "reason": "upstream_http_error",
                "sequence": seq,
                "status": resp.status_code,
                "detail": resp.text[:200],
            })
            return

        try:
            data = resp.json()
        except json.JSONDecodeError:
            if sortformer_task is not None and not sortformer_task.done():
                sortformer_task.cancel()
            await websocket.send_json({
                "type": "error",
                "reason": "upstream_bad_json",
                "sequence": seq,
                "detail": resp.text[:200],
            })
            return

        text = (data.get("text") or "").strip()
        segments = data.get("segments") or []
        confidence = data.get("confidence")
        model = data.get("model")
        rtf = data.get("rtf")

        # Phase B.3 chunk D: collect sortformer result if it was dispatched.
        # By this point parakeet has finished; sortformer is usually faster
        # (~175 ms vs parakeet's 200-600 ms) so the await is typically a
        # no-op. Failures are logged and silently dropped — sortformer is
        # an enhancement, not a blocking dependency.
        speakers: list = []
        sortformer_model: Optional[str] = None
        sortformer_rtf: Optional[float] = None
        sortformer_distinct_speakers: Optional[int] = None
        if sortformer_task is not None:
            try:
                sf_resp = await sortformer_task
                if sf_resp.status_code < 400:
                    sf_data = sf_resp.json()
                    speakers = sf_data.get("speakers") or []
                    sortformer_model = sf_data.get("model")
                    sortformer_rtf = sf_data.get("rtf")
                    sortformer_distinct_speakers = sf_data.get(
                        "distinct_speaker_count"
                    )
                else:
                    logger.warning(
                        "[B.3 WS] sortformer_http_error session=%s seq=%d "
                        "status=%d body=%s",
                        state.session_id, seq, sf_resp.status_code,
                        sf_resp.text[:200],
                    )
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
                json.JSONDecodeError,
                asyncio.CancelledError,
            ) as sf_exc:
                logger.warning(
                    "[B.3 WS] sortformer_unreachable session=%s seq=%d err=%s",
                    state.session_id, seq, sf_exc,
                )

        # De-dup empty / identical partials. Real model output won't usually
        # repeat verbatim across windows once audio actually arrives, but
        # zero-payload smoke tests produce empty text every time — flooding
        # the client with empty partials is noise.
        if not is_final and not text:
            return
        if not is_final and text == state.last_partial_text:
            return
        state.last_partial_text = text

        frame_type = "final" if is_final else "partial"
        await websocket.send_json({
            "type": frame_type,
            "sequence": seq,
            "text": text,
            "segments": segments,
            "confidence": confidence,
            "model": model,
            "rtf": rtf,
            "covers_through_ms": cumulative_at_call,
            "is_final": is_final,
            "upstream_elapsed_ms": int((time.time() - started) * 1000),
            # Phase B.3 chunk D: speaker labels from sortformer (empty when
            # STREAMING_USE_SORTFORMER is off or sortformer call failed).
            "speakers": speakers,
            "sortformer_model": sortformer_model,
            "sortformer_rtf": sortformer_rtf,
            "sortformer_distinct_speakers": sortformer_distinct_speakers,
        })
        # Phase B.5 metric: count emitted partial/final back to client.
        ws_partial_transcripts_emitted_total.inc()

        logger.info(
            "[B.2 WS] flush ok session=%s seq=%d type=%s chars=%d "
            "audio_ms=%d elapsed_ms=%d",
            state.session_id, seq, frame_type, len(text),
            cumulative_at_call, int((time.time() - started) * 1000),
        )
    finally:
        # Phase B.5 slow-upstream check. If this call took longer than the
        # threshold, tell the next few cadence ticks to skip so the GPU
        # has room to catch up. Final flushes don't trigger the skip;
        # they're one-shot and we want the close path to complete cleanly.
        elapsed = time.time() - started
        if elapsed > STREAM_SLOW_THRESHOLD_S and not is_final:
            state.skip_next_n = max(state.skip_next_n, STREAM_SKIP_NEXT_ON_SLOW)
            logger.warning(
                "[streaming-backpressure] session=%s slow upstream "
                "elapsed=%.2fs threshold=%.2fs; skip_next_n=%d",
                state.session_id, elapsed, STREAM_SLOW_THRESHOLD_S,
                state.skip_next_n,
            )
        state.in_flight = False


@router.websocket("/ws/sessions/{session_id}/live")
async def session_live(websocket: WebSocket, session_id: str) -> None:
    """Phase B.2 WS endpoint with real forward path.

    Lifecycle:
      1. Auth-gate on oauth2-proxy headers, reject 4001 if missing.
      2. accept(), send ``ready`` frame with protocol version + upstream URL.
      3. Loop:
         - binary frame  -> parse 19-byte header, append PCM, maybe flush.
         - text {"type":"flush"} -> force flush.
         - text {"type":"end"}   -> final flush + close 1000.
         - text {"type":"ping"}  -> pong.
         - anything else         -> ack_control echo.
      4. On disconnect / exception: log + best-effort close.

    Upstream forwarding uses a single per-connection httpx.AsyncClient with
    HTTP keep-alive so we're not paying TCP setup on every flush.
    """
    user = _resolve_ws_user(websocket)
    if user is None:
        logger.warning(
            "[B.2 WS] unauthenticated connection attempt session_id=%s "
            "headers_present=%s",
            session_id,
            sorted(k for k in websocket.headers.keys() if k.startswith("x-")),
        )
        # Phase B.5 metric: log the rejection. tier=unknown because we
        # never resolved the user.
        ws_connections_total.labels(tier="unknown", result="auth_rejected").inc()
        ws_close_codes_total.labels(code="4001").inc()
        await websocket.close(code=4001)
        return

    user_email = user.email
    user_tier = get_user_tier(user)
    features = get_tier_features(user)

    # B.4 tier gate. Accept the upgrade so we can send a clean JSON error
    # frame, then close with the application-specific 4003 code.
    if not features.get("server_live"):
        logger.info(
            "[B.4 WS] tier_insufficient session_id=%s user=%s tier=%s",
            session_id, user_email, user_tier,
        )
        ws_connections_total.labels(tier=user_tier, result="tier_rejected").inc()
        ws_close_codes_total.labels(code="4003").inc()
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "reason": "tier_insufficient",
            "current_tier": user_tier,
            "required_feature": "server_live",
            "upgrade_hint": (
                "Pro or Enterprise tier required for live streaming"
            ),
        })
        await websocket.close(code=4003, reason="tier_insufficient")
        return

    # Phase B.5 per-org rate limit. Bucket the user by org id (or email
    # for orgless accounts) and reject with close 4429 if they already
    # have ``STREAMING_MAX_SESSIONS_PER_ORG`` live sessions open. We
    # check BEFORE accept so the rejected client gets a clean handshake-
    # reject + close, mirroring the unauth 4001 path. We also still
    # accept-and-send-JSON on the reject so clients that only listen on
    # onmessage see a structured error frame.
    org_bucket = _resolve_org_bucket(user)
    if _org_session_counts[org_bucket] >= STREAMING_MAX_SESSIONS_PER_ORG:
        logger.warning(
            "[streaming-rate-limit] rate_limited session_id=%s user=%s "
            "bucket=%s active=%d cap=%d",
            session_id, user_email, org_bucket,
            _org_session_counts[org_bucket], STREAMING_MAX_SESSIONS_PER_ORG,
        )
        ws_connections_total.labels(tier=user_tier, result="rate_limited").inc()
        ws_close_codes_total.labels(code="4429").inc()
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "reason": "rate_limited",
            "active_sessions": _org_session_counts[org_bucket],
            "max_sessions_per_org": STREAMING_MAX_SESSIONS_PER_ORG,
            "retryable": False,
        })
        await websocket.close(code=4429, reason="rate_limited")
        return

    await websocket.accept()
    ws_connections_total.labels(tier=user_tier, result="accepted").inc()
    # Register this session for the SIGTERM drain hook + bump the
    # per-org count. Both are torn down in the finally block below.
    active_sessions[session_id] = websocket
    _org_session_counts[org_bucket] += 1

    logger.info(
        "[B.2 WS] connected session_id=%s user=%s tier=%s upstream=%s "
        "bucket=%s org_active=%d",
        session_id, user_email, user_tier, PARAKEET_STREAM_URL,
        org_bucket, _org_session_counts[org_bucket],
    )

    await websocket.send_json({
        "type": "ready",
        "session_id": session_id,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "protocol_version": PROTOCOL_VERSION,
        "phase": "B.2",
        "upstream": PARAKEET_STREAM_URL,
        "flush_audio_seconds": FLUSH_AUDIO_SECONDS,
        "tier": user_tier,
    })

    state = _SessionState(
        session_id=session_id,
        user_email=user_email,
        org_bucket=org_bucket,
    )
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)

    async with httpx.AsyncClient(limits=limits) as http_client:
        try:
            while True:
                message = await websocket.receive()

                msg_type = message.get("type")
                if msg_type == "websocket.disconnect":
                    code = message.get("code", 1006)
                    logger.info(
                        "[B.2 WS] disconnect frame session_id=%s code=%s",
                        session_id, code,
                    )
                    ws_close_codes_total.labels(code=str(code)).inc()
                    return

                if "bytes" in message and message["bytes"] is not None:
                    data: bytes = message["bytes"]
                    if len(data) < HEADER_SIZE:
                        logger.warning(
                            "[B.2 WS] frame_too_short session_id=%s got=%d expected>=%d",
                            session_id, len(data), HEADER_SIZE,
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
                            "[B.2 WS] header_unpack_failed session_id=%s err=%s",
                            session_id, exc,
                        )
                        await websocket.send_json({
                            "type": "error",
                            "reason": "header_unpack_failed",
                            "detail": str(exc),
                        })
                        continue

                    fmt_str = fmt_bytes.decode("ascii", errors="replace")
                    payload = data[HEADER_SIZE:]
                    payload_len = len(payload)
                    is_final_bit = bool(flags & 0x01)
                    sample_rate = sr100 * 100

                    state.last_seq = seq

                    # Only PC16 is appended to the buffer in B.2; other formats
                    # would need a transcode step we deliberately defer (Opus
                    # support is B.3 along with the AudioWorklet fallback).
                    if fmt_str == "PC16" and payload_len > 0:
                        state.append_pcm(payload, sample_rate)

                    await websocket.send_json({
                        "type": "ack",
                        "sequence": seq,
                        "received_bytes": len(data),
                        "header_bytes": HEADER_SIZE,
                        "payload_bytes": payload_len,
                        "format": fmt_str,
                        "sample_rate": sample_rate,
                        "is_final": is_final_bit,
                        "cumulative_audio_ms": state.cumulative_audio_ms,
                    })

                    # Cadence-driven flush: fire when we have enough audio.
                    # The header-level is_final bit also forces a flush;
                    # distinct from {"type":"end"} which closes the WS.
                    if state.should_flush() or is_final_bit:
                        asyncio.create_task(
                            _flush_to_stt(
                                state, websocket,
                                is_final=is_final_bit, http_client=http_client,
                            )
                        )
                    continue

                if "text" in message and message["text"] is not None:
                    raw_text = message["text"]
                    try:
                        ctrl = json.loads(raw_text)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "[B.2 WS] bad_json session_id=%s err=%s preview=%r",
                            session_id, exc, raw_text[:80],
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
                            "[B.2 WS] client requested end session_id=%s audio_ms=%d",
                            session_id, state.cumulative_audio_ms,
                        )
                        await _flush_to_stt(
                            state, websocket, is_final=True, http_client=http_client,
                        )
                        await websocket.send_json({
                            "type": "closed",
                            "reason": "client_end",
                        })
                        ws_close_codes_total.labels(code="1000").inc()
                        await websocket.close(code=1000)
                        return

                    if ctrl_type == "flush":
                        logger.info(
                            "[B.2 WS] client requested flush session_id=%s "
                            "audio_ms=%d",
                            session_id, state.cumulative_audio_ms,
                        )
                        asyncio.create_task(
                            _flush_to_stt(
                                state, websocket,
                                is_final=False, http_client=http_client,
                            )
                        )
                        continue

                    if ctrl_type == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue

                    logger.info(
                        "[B.2 WS] unknown_control session_id=%s ctrl=%s",
                        session_id, ctrl,
                    )
                    await websocket.send_json({
                        "type": "ack_control",
                        "echo": ctrl,
                    })

        except WebSocketDisconnect as exc:
            code = getattr(exc, "code", 1006)
            logger.info(
                "[B.2 WS] client disconnected session_id=%s code=%s",
                session_id, code,
            )
            ws_close_codes_total.labels(code=str(code)).inc()
        except Exception:
            logger.exception(
                "[B.2 WS] unexpected error session_id=%s user=%s",
                session_id, user_email,
            )
            ws_close_codes_total.labels(code="1011").inc()
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
        finally:
            # Phase B.5: drop the session from the active registry + bring
            # the per-org concurrent count back down. Both are guarded so
            # a partial shutdown (raced with the drain hook below) doesn't
            # crash us.
            active_sessions.pop(session_id, None)
            if _org_session_counts.get(org_bucket, 0) > 0:
                _org_session_counts[org_bucket] -= 1
                if _org_session_counts[org_bucket] <= 0:
                    _org_session_counts.pop(org_bucket, None)
