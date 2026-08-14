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

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

from .protocols import STTProvider  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


# Retry policy for the STT hop. Mirrors the transient/permanent split in
# ``services.transient_errors.is_transient_error`` (timeouts, network errors,
# 429, and 5xx are transient) and the bounded-backoff shape already used by
# ``services.projectops_client``. Kept env-tunable so an operator can widen or
# disable it without a redeploy.
STT_MAX_ATTEMPTS = max(1, _env_int("STT_MAX_ATTEMPTS", 3))
STT_INITIAL_BACKOFF_SECONDS = _env_float("STT_INITIAL_BACKOFF_SECONDS", 2.0)
STT_BACKOFF_MULTIPLIER = _env_float("STT_BACKOFF_MULTIPLIER", 3.0)
STT_MAX_BACKOFF_SECONDS = _env_float("STT_MAX_BACKOFF_SECONDS", 30.0)


def _is_transient_status(status_code: int) -> bool:
    """True when the STT service's response warrants another attempt.

    429 and 5xx mean "the service could not serve this right now"; 4xx (other
    than 429) means "this request will never succeed" — e.g. audio too long —
    and must fail fast so the user sees the real reason immediately.
    """
    return status_code == 429 or status_code >= 500


async def _post_audio_with_retry(
    *,
    url: str,
    audio_path: str,
    file_field: str,
    timeout: float,
    label: str,
    content_type: str = "audio/wav",
    params: Optional[dict] = None,
    data: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> tuple[Optional[httpx.Response], Optional[str]]:
    """POST an audio file, retrying transient failures with backoff.

    Returns ``(response, error)``. Exactly one is non-None: a response that is
    either a 2xx or a permanent (non-retryable) status, or an error string
    describing the final transient failure after the attempt budget is spent.

    The file handle is re-opened per attempt — httpx consumes the stream on
    send, so a retry that reused it would upload zero bytes.
    """
    backoff = STT_INITIAL_BACKOFF_SECONDS
    last_error: str = f"{label} failed before any attempt was made"

    for attempt in range(1, STT_MAX_ATTEMPTS + 1):
        try:
            with open(audio_path, "rb") as f:
                files = {file_field: (os.path.basename(audio_path), f, content_type)}
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        url, files=files, params=params, data=data, headers=headers
                    )
        except httpx.TimeoutException:
            last_error = (
                f"Transcription timed out after {timeout:.0f}s — "
                "the recording may be too long for the current limit."
            )
            logger.error(
                "%s timeout transcribing %s (timeout=%ss, attempt %s/%s)",
                label, audio_path, timeout, attempt, STT_MAX_ATTEMPTS,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"Could not reach the transcription service: {exc}"
            logger.error(
                "%s client error (attempt %s/%s): %s",
                label, attempt, STT_MAX_ATTEMPTS, exc,
            )
        else:
            if resp.status_code == 200 or not _is_transient_status(resp.status_code):
                # Success, or a permanent failure the caller must surface as-is.
                return resp, None
            detail = (resp.text or "").strip()[:300]
            last_error = f"Transcription service error {resp.status_code}: {detail}"
            logger.error(
                "%s returned %s (attempt %s/%s): %s",
                label, resp.status_code, attempt, STT_MAX_ATTEMPTS, detail,
            )

        if attempt < STT_MAX_ATTEMPTS:
            logger.info("%s retrying in %.1fs", label, backoff)
            await asyncio.sleep(backoff)
            backoff = min(STT_MAX_BACKOFF_SECONDS, backoff * STT_BACKOFF_MULTIPLIER)

    logger.error(
        "%s exhausted %s attempt(s) transcribing %s; giving up",
        label, STT_MAX_ATTEMPTS, audio_path,
    )
    return None, last_error


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
        resp, error = await _post_audio_with_retry(
            url=f"{self.endpoint}/inference",
            audio_path=audio_path,
            file_field="file",
            timeout=timeout,
            label="Whisper",
            data={
                "response_format": "verbose_json",
                "language": language or "en",
                "temperature": "0.0",
            },
        )
        if resp is None:
            return _empty_result(self.model, language or "en", error=error)

        if resp.status_code != 200:
            logger.error("Whisper returned %s: %s", resp.status_code, resp.text[:200])
            return _empty_result(
                self.model, language or "en",
                error=f"Transcription service error {resp.status_code}: {(resp.text or '').strip()[:300]}",
            )

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
        resp, error = await _post_audio_with_retry(
            url=f"{self.endpoint}/transcribe",
            audio_path=audio_path,
            file_field="audio",
            timeout=timeout,
            label="Parakeet",
            params=params,
        )
        if resp is None:
            return _empty_result(self.model, language or "en", error=error)

        if resp.status_code != 200:
            detail = (resp.text or "").strip()[:300]
            logger.error("Parakeet returned %s: %s", resp.status_code, detail)
            return _empty_result(
                self.model, language or "en",
                error=f"Transcription service error {resp.status_code}: {detail}",
            )

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


class OpenAITranscriptionProvider:
    """Calls an OpenAI-Whisper-compatible /v1/audio/transcriptions endpoint.

    Drop-in for LocalParakeetProvider (same signature + normalized return
    shape) but speaks the OpenAI audio API, so MO can route STT through the
    commander LiteLLM gateway (model ``parakeet`` → the midboy1
    parakeet-openai-shim → meet-parakeet-svc) instead of calling the native
    /transcribe directly. Going through the gateway gives STT the same
    single-endpoint + per-call metering + cloud-failover-ready story as the LLM
    and embeddings. The native LocalParakeetProvider stays the default/fallback
    (STT_DEFAULT_PROVIDER), so the critical transcription path is never forced
    onto the gateway without an explicit opt-in.
    """

    def __init__(
        self,
        endpoint: str = "",
        model: str = "parakeet",
        api_key: str = "",
        return_word_timestamps: bool = True,
    ):
        # ``endpoint`` is the OpenAI base (…/v1); we POST {endpoint}/audio/transcriptions.
        self.endpoint = (endpoint or "").rstrip("/") or "http://unicorn-litellm:4000/v1"
        self.model = model
        self.api_key = api_key
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
        data = {
            "model": self.model,
            "language": language or "en",
            "response_format": "verbose_json",
        }
        if self.return_word_timestamps:
            # OpenAI word-level timestamps; the shim maps this to Parakeet's.
            data["timestamp_granularities[]"] = "word"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp, error = await _post_audio_with_retry(
            url=f"{self.endpoint}/audio/transcriptions",
            audio_path=audio_path,
            file_field="file",
            timeout=timeout,
            label="Gateway STT",
            data=data,
            headers=headers or None,
        )
        if resp is None:
            return _empty_result(self.model, language or "en", error=error)

        if resp.status_code != 200:
            detail = (resp.text or "").strip()[:300]
            logger.error("Gateway STT returned %s: %s", resp.status_code, detail)
            return _empty_result(
                self.model, language or "en",
                error=f"Transcription service error {resp.status_code}: {detail}",
            )

        payload = resp.json()
        # OpenAI verbose_json: {text, language, duration, segments:[{start,end,text,…}], words?}
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


def _empty_result(model: str, language: str, error=None) -> dict[str, Any]:
    # `error` (when set) carries the real reason transcription yielded nothing
    # — e.g. the STT service's "audio too long" / 500 / timeout — so the upload
    # pipeline can surface it instead of a generic "no segments" message.
    return {
        "text": "",
        "segments": [],
        "words": [],
        "duration": 0.0,
        "language": language,
        "confidence": 0.0,
        "model": model,
        "rtf": None,
        "error": error,
    }
