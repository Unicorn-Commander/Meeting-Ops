"""parakeet-stream-svc — Phase B.1 scaffolding.

This service is the streaming counterpart to the existing parakeet-svc
(batch transcription of completed audio files). The B.1 scaffold here
exposes the surface area the meet-backend will call into; the real
Parakeet 0.6B v3 streaming integration lands in Phase B.2 per
docs/phase-b-server-live-streaming.md sections 5-7.

Endpoints
---------
GET  /healthz            — liveness + scaffold-version + model_loaded flag
POST /transcribe-stream  — stub returning a dummy partial transcript

The scaffold's job is to prove the network seam:
    Cloudflare -> oauth2-proxy -> Traefik -> meet-backend WS endpoint
    -> (B.2 will add: forward audio frames to meet-parakeet-stream-svc
    over the meet-internal docker network -> emit partials back)

For B.1 the meet-backend WS endpoint logs/acks frames without forwarding
to this service. The /transcribe-stream stub is here so the contract is
visible to whoever picks up B.2.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("parakeet-stream-svc")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

SERVICE_VERSION = "0.1.0-scaffold"

app = FastAPI(
    title="meet-parakeet-stream-svc",
    version=SERVICE_VERSION,
    description=(
        "Phase B.1 scaffolding for server-live streaming. Real Parakeet 0.6B v3 "
        "streaming integration lands in Phase B.2 per "
        "docs/phase-b-server-live-streaming.md."
    ),
)


class HealthResponse(BaseModel):
    status: str = Field(..., description="ok | degraded")
    version: str = Field(..., description="service version, '-scaffold' suffix while B.1")
    model_loaded: bool = Field(..., description="false in B.1 — no Parakeet weights yet")
    phase: str = Field(..., description="B.1 | B.2 | B.3 — which design phase this build implements")


class TranscribeStreamResponse(BaseModel):
    partial: str = Field(..., description="dummy partial transcript in B.1")
    is_final: bool = Field(..., description="true when this segment is closed; B.1 always false")
    sequence: int = Field(..., description="monotonic sequence number per request")
    scaffold: bool = Field(True, description="reminder that this is the B.1 stub, not real STT")
    received_bytes: int = Field(0, description="payload byte count, for end-to-end byte accounting")
    service_version: str = Field(SERVICE_VERSION, description="echoed for client-side compat checks")


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness probe. HTTP-up only in B.1; B.2 will add a synthetic-WAV probe."""
    return HealthResponse(
        status="ok",
        version=SERVICE_VERSION,
        model_loaded=False,
        phase="B.1",
    )


# Per-process monotonic counter so the stub can return something less
# trivially constant than `sequence=1`. The real B.2 implementation will
# carry per-stream sequence numbers from the client-supplied frame header.
_seq_counter: int = 0


@app.post("/transcribe-stream", response_model=TranscribeStreamResponse)
async def transcribe_stream(request: Request) -> TranscribeStreamResponse:
    """Stub: accepts any payload (binary audio bytes or JSON), returns a dummy partial.

    In Phase B.2 this becomes the streaming transcribe endpoint:
      - request body is a binary audio frame (16 kHz mono PCM16) prefixed
        with the same 19-byte header the WS uses
      - response is the rolling partial transcript for the current segment
      - separate "final" events are emitted as segment boundaries close

    For B.1 we just count bytes, log, and return a fixed string so the
    meet-backend WS endpoint can later forward to us without code change.
    """
    global _seq_counter
    _seq_counter += 1
    seq = _seq_counter

    body = await request.body()
    payload_len = len(body)

    logger.info(
        "[B.1 stub] /transcribe-stream call seq=%d bytes=%d ts=%.3f",
        seq,
        payload_len,
        time.time(),
    )

    return TranscribeStreamResponse(
        partial="[B.1 scaffold] stub transcript",
        is_final=False,
        sequence=seq,
        scaffold=True,
        received_bytes=payload_len,
        service_version=SERVICE_VERSION,
    )


@app.get("/")
async def root() -> dict:
    """Root — points operators at /healthz and /docs."""
    return {
        "service": "meet-parakeet-stream-svc",
        "version": SERVICE_VERSION,
        "phase": "B.1",
        "scaffold": True,
        "docs": "/docs",
        "healthz": "/healthz",
        "design_doc": "docs/phase-b-server-live-streaming.md",
    }
