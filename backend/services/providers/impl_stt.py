"""STT provider implementations.

Both providers implement the same shape so the upload pipeline (and live
transcription) can swap between them via the Provider Registry without
caring about the engine.

Return type is a normalized dict matching `services.whisper_server_client`:

    {
        "text": str,
        "segments": [{"start", "end", "text", "confidence", "speaker"}],
        "words":    [{"start", "end", "word", "confidence"}]   (optional, parakeet),
        "duration": float,
        "language": str,
        "model":    str,                  # used to set processing_metadata.transcription_model
        "confidence": float,
        "rtf":      float | None,         # realtime factor (parakeet only)
    }
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from .protocols import STTProvider  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)


def _http_timeout_for_path(file_path: str, base: float = 120.0, per_mb: float = 20.0) -> float:
    """Scale request timeout with file size.

    The defaults are tuned for compressed audio (mp3/m4a/ogg) where 1 MB
    can hold roughly 1 minute of audio. whisper-large-v3-turbo on an
    RTX 6000 Turing runs around 9x realtime, so a 1-minute clip needs
    around 7s of inference plus a few seconds of model warmup. 20 s/MB
    covers that with margin and base=120 keeps short clips healthy even
    with cold-cache overhead.

    Pre-extracted PCM WAV is much larger per minute (around 1.9 MB/min
    at 16 kHz mono), so the same formula gives WAV uploads even more
    headroom — that overshoots safely rather than killing transcription
    mid-way.
    """
    try:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
    except OSError:
        size_mb = 0.0
    return max(base, base + size_mb * per_mb)


class LocalWhisperProvider:
    """Calls the in-cluster whisper.cpp HTTP server.

    Default endpoint is the live container address used in the bigboy
    deployment. The legacy default of `:8080` is preserved as a fallback
    when callers explicitly opt in.
    """

    def __init__(
        self,
        endpoint: str = "http://meet-whisper:8178",
        model: str = "whisper.cpp-large-v3-turbo",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = "en",
    ) -> dict[str, Any]:
        if not os.path.exists(audio_path):
            logger.error("Audio file not found: %s", audio_path)
            return _empty_result(self.model, language or "en")

        timeout = _http_timeout_for_path(audio_path)
        try:
            with open(audio_path, "rb") as f:
                files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
                data = {
                    "response_format": "verbose_json",
                    "language": language or "en",
                    "temperature": "0.0",
                }
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{self.endpoint}/inference", files=files, data=data)
        except httpx.TimeoutException:
            logger.error("Whisper timeout transcribing %s (timeout=%ss)", audio_path, timeout)
            return _empty_result(self.model, language or "en")
        except Exception as exc:  # noqa: BLE001
            logger.error("Whisper client error: %s", exc)
            return _empty_result(self.model, language or "en")

        if resp.status_code != 200:
            logger.error("Whisper returned %s: %s", resp.status_code, resp.text[:200])
            return _empty_result(self.model, language or "en")

        result = resp.json()
        segments: list[dict[str, Any]] = []
        for seg in result.get("segments", []) or []:
            segments.append({
                "text": (seg.get("text") or "").strip(),
                "start": float(seg.get("start") or 0),
                "end": float(seg.get("end") or 0),
                "confidence": 1.0 - float(seg.get("no_speech_prob") or 0.0),
                "speaker": None,
            })
        return {
            "text": (result.get("text") or "").strip(),
            "segments": segments,
            "words": [],  # whisper.cpp doesn't return word-level
            "duration": float(result.get("duration") or 0.0),
            "language": result.get("language", language or "en") or (language or "en"),
            "confidence": 0.95,
            "model": self.model,
            "rtf": None,
        }


class LocalParakeetProvider:
    """Calls the in-cluster meet-parakeet-svc container.

    Same response shape as LocalWhisperProvider, plus optional `words`
    word-level timestamps. The `model` field reflects the actual model the
    parakeet container loaded (1.1B by default, 0.6B if it had to fall back).
    """

    def __init__(
        self,
        endpoint: str = "http://meet-parakeet-svc:8881",
        model: str = "parakeet-tdt-1.1b",
        return_word_timestamps: bool = True,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.return_word_timestamps = return_word_timestamps

    async def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = "en",
    ) -> dict[str, Any]:
        if not os.path.exists(audio_path):
            logger.error("Audio file not found: %s", audio_path)
            return _empty_result(self.model, language or "en")

        timeout = _http_timeout_for_path(audio_path, base=60.0, per_mb=2.0)
        params = {
            "language": language or "en",
            "return_word_timestamps": "true" if self.return_word_timestamps else "false",
        }
        try:
            with open(audio_path, "rb") as f:
                files = {"audio": (os.path.basename(audio_path), f, "audio/wav")}
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{self.endpoint}/transcribe",
                        files=files,
                        params=params,
                    )
        except httpx.TimeoutException:
            logger.error("Parakeet timeout transcribing %s (timeout=%ss)", audio_path, timeout)
            return _empty_result(self.model, language or "en")
        except Exception as exc:  # noqa: BLE001
            logger.error("Parakeet client error: %s", exc)
            return _empty_result(self.model, language or "en")

        if resp.status_code != 200:
            logger.error("Parakeet returned %s: %s", resp.status_code, resp.text[:200])
            return _empty_result(self.model, language or "en")

        payload = resp.json()
        # Normalize. The svc already speaks the unified shape, but defensively
        # coerce the fields we depend on.
        segments = []
        for seg in payload.get("segments") or []:
            segments.append({
                "text": (seg.get("text") or "").strip(),
                "start": float(seg.get("start") or 0),
                "end": float(seg.get("end") or 0),
                "confidence": float(seg.get("confidence") or 0.97),
                "speaker": seg.get("speaker"),
            })
        words = []
        for w in payload.get("words") or []:
            words.append({
                "word": (w.get("word") or w.get("text") or "").strip(),
                "start": float(w.get("start") or 0),
                "end": float(w.get("end") or 0),
                "confidence": float(w.get("confidence") or 0.99),
            })
        # Trust the service's reported model name (so 0.6B fallback shows up
        # accurately in processing_metadata.transcription_model).
        actual_model = payload.get("model") or self.model
        return {
            "text": (payload.get("text") or "").strip(),
            "segments": segments,
            "words": words,
            "duration": float(payload.get("duration") or 0.0),
            "language": payload.get("language", language or "en") or (language or "en"),
            "confidence": float(payload.get("confidence") or 0.97),
            "model": actual_model,
            "rtf": payload.get("rtf"),
        }


def _empty_result(model: str, language: str) -> dict[str, Any]:
    return {
        "text": "",
        "segments": [],
        "words": [],
        "duration": 0.0,
        "language": language,
        "confidence": 0.0,
        "model": model,
        "rtf": None,
    }
