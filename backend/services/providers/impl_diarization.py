"""Diarization + speaker-embedding providers.

`LocalSpeakerSvcProvider` talks to the speaker-svc container running on
bigboy GPU 1. It implements the full DiarizationProvider protocol —
diarize / embed / identify — so the backend can do everything via one
HTTP service instead of bundling SpeechBrain + Pyannote into the FastAPI
process.

The legacy `LocalDiarizationProvider` name is kept as an alias for back-compat
with code paths that haven't migrated yet.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from .protocols import DiarizationProvider  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

DEFAULT_SPEAKER_SVC_URL = os.getenv("SPEAKER_SVC_URL", "http://meet-speaker-svc:8889")
DEFAULT_TIMEOUT = float(os.getenv("SPEAKER_SVC_TIMEOUT", "300"))


class LocalSpeakerSvcProvider:
    """HTTP client for the speaker-svc container."""

    def __init__(self, endpoint: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        self.endpoint = (endpoint or DEFAULT_SPEAKER_SVC_URL).rstrip("/")
        self.timeout = timeout

    # ---------- diarize ----------

    async def diarize(
        self,
        audio_path: str,
        *,
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[dict]:
        """Return a list of diarized segments.

        Shape kept compatible with the legacy provider — list[dict] with at
        least start/end/speaker keys. Each segment may also carry an
        `embedding` key (192-d ECAPA float list) so the caller can pipe
        directly into /identify.

        num_speakers / min_speakers / max_speakers are forwarded to
        speaker-svc when set; the upstream pyannote diarizer respects them.
        Leave all three None for full auto-detection (the default).
        """
        data: dict[str, str] = {"audio_path": audio_path, "return_embeddings": "true"}
        if num_speakers is not None:
            data["num_speakers"] = str(num_speakers)
        if min_speakers is not None:
            data["min_speakers"] = str(min_speakers)
        if max_speakers is not None:
            data["max_speakers"] = str(max_speakers)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.endpoint}/diarize", data=data)
                resp.raise_for_status()
                payload = resp.json()
                segments = payload.get("segments", []) or []
                # Annotate with backend so callers can branch
                for seg in segments:
                    seg.setdefault("backend", payload.get("backend", "unknown"))
                return segments
        except httpx.HTTPStatusError as exc:
            logger.error("speaker-svc /diarize HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        except Exception as exc:  # noqa: BLE001
            logger.error("speaker-svc /diarize failed: %s", exc)
        return []

    # ---------- embed ----------

    async def embed(self, audio_path: str) -> dict:
        """Return a single ECAPA embedding for an audio clip."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.endpoint}/embed",
                    data={"audio_path": audio_path},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("speaker-svc /embed HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        except Exception as exc:  # noqa: BLE001
            logger.error("speaker-svc /embed failed: %s", exc)
        return {"embedding": [], "embedding_dim": 0, "duration_seconds": 0.0, "model": ""}

    async def embed_bytes(self, audio_bytes: bytes, filename: str = "clip.wav") -> dict:
        """Embed raw audio bytes (used by enrollment uploads from the UI)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {"audio": (filename, audio_bytes, "application/octet-stream")}
                resp = await client.post(f"{self.endpoint}/embed", files=files)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("speaker-svc /embed (bytes) HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        except Exception as exc:  # noqa: BLE001
            logger.error("speaker-svc /embed (bytes) failed: %s", exc)
        return {"embedding": [], "embedding_dim": 0, "duration_seconds": 0.0, "model": ""}

    # ---------- identify ----------

    async def identify(self, embedding: list[float], candidates: list[dict], threshold: float = 0.55) -> dict:
        """Score a query embedding against enrolled-speaker centroids."""
        if not embedding:
            return {"matches": [], "best_match": None}
        try:
            payload = {
                "embedding": embedding,
                "candidates": candidates,
                "threshold": threshold,
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.endpoint}/identify", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("speaker-svc /identify HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        except Exception as exc:  # noqa: BLE001
            logger.error("speaker-svc /identify failed: %s", exc)
        return {"matches": [], "best_match": None}

    # ---------- health ----------

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.endpoint}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("speaker-svc /health failed: %s", exc)
            return {"status": "unreachable", "error": str(exc)}


# Back-compat alias. New code should use LocalSpeakerSvcProvider.
LocalDiarizationProvider = LocalSpeakerSvcProvider
