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
import tempfile
import wave
from typing import Any, Optional

import httpx

from .protocols import STTProvider  # noqa: F401  (re-exported)
from utils.url_redaction import redact_text, redact_url

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
            last_error = (
                "Could not reach the transcription service: "
                f"{redact_text(str(exc))}"
            )
            logger.error(
                "%s client error (attempt %s/%s): %s",
                label, attempt, STT_MAX_ATTEMPTS, redact_text(str(exc)),
            )
        else:
            if resp.status_code == 200 or not _is_transient_status(resp.status_code):
                # Success, or a permanent failure the caller must surface as-is.
                return resp, None
            detail = redact_text((resp.text or "").strip()[:300])
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


def _endpoint_for_log(endpoint: str) -> str:
    """Identify the serving endpoint without exposing URL credentials/tokens."""
    return redact_url(endpoint)


async def _post_audio_with_fallback(
    *,
    endpoint: str,
    route: str,
    **kwargs: Any,
) -> tuple[httpx.Response | None, str | None]:
    """Try compatible endpoint bases in operator-configured order.

    MEETING_OPS_STT_FALLBACK_URLS is a comma-separated list of bases using the
    selected provider's protocol: native /transcribe or OpenAI-compatible
    /audio/transcriptions (include /v1 in each OpenAI base when required).
    Model, headers, multipart fields, timeouts and retries are unchanged.
    Only exhausted transient failures advance to the next endpoint; permanent
    request errors and successful silence retain their existing semantics.
    """
    fallbacks = [
        value.strip().rstrip("/")
        for value in os.getenv("MEETING_OPS_STT_FALLBACK_URLS", "").split(",")
        if value.strip()
    ]
    if not fallbacks:
        # Preserve legacy requests, results and logs exactly when not enabled.
        return await _post_audio_with_retry(url=f"{endpoint}{route}", **kwargs)

    endpoints = list(dict.fromkeys([endpoint, *fallbacks]))
    for index, candidate in enumerate(endpoints):
        response, error = await _post_audio_with_retry(
            url=f"{candidate}{route}", **kwargs
        )
        if response is not None:
            if response.status_code == 200:
                logger.info(
                    "STT served audio=%s endpoint=%s",
                    kwargs["audio_path"],
                    _endpoint_for_log(candidate),
                )
            return response, error
        if index + 1 < len(endpoints):
            logger.warning(
                "STT endpoint=%s unavailable for audio=%s; trying endpoint=%s",
                _endpoint_for_log(candidate),
                kwargs["audio_path"],
                _endpoint_for_log(endpoints[index + 1]),
            )
    return response, error


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
            detail = redact_text((resp.text or "").strip()[:300])
            logger.error("Whisper returned %s: %s", resp.status_code, detail)
            return _empty_result(
                self.model, language or "en",
                error=f"Transcription service error {resp.status_code}: {detail}",
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


# --- Parakeet sparse-speech retry (2026-09-24) ------------------------------
#
# Parakeet TDT 1.1B returns NOTHING for a long file that is mostly silence.
# Measured on a 116 s Stable call holding one 2 s line ("Rook, say ready,
# please"): whole file -> "", 60 s windows -> "rock say what he please", 30 s
# windows -> "rook say ready please" (0.97). So an empty pass on a file longer
# than one window is re-run in ~30 s windows cut at quiet points.
#
# Gate: Parakeet does not invent sentences on noise the way Whisper does, but
# music and clicks still produce one- and two-word fragments ("four", "mhm").
# The retry only counts when some line carries PARAKEET_SPARSE_MIN_WORDS (3)
# or more words; otherwise the empty pass stands. PARAKEET_SPARSE_RETRY=0
# switches it off.

#: Peak below which a window is digital silence (about -60 dBFS for int16).
_SILENCE_PEAK = 33


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _sparse_retry_enabled() -> bool:
    return os.getenv("PARAKEET_SPARSE_RETRY", "1").strip().lower() not in ("0", "false", "no", "off")


def _read_pcm16_mono(path: str):
    """A 16-bit PCM WAV as ``(int16 mono samples, rate)``; None for anything else."""
    import numpy as np

    try:
        with wave.open(path, "rb") as handle:
            if handle.getsampwidth() != 2:
                return None
            channels, rate = handle.getnchannels(), handle.getframerate()
            data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
    except (wave.Error, EOFError, OSError):
        return None
    if channels > 1:
        data = data[: len(data) - len(data) % channels].reshape(-1, channels).mean(axis=1).astype("<i2")
    return data, rate


async def _decode_pcm16_mono(path: str, rate: int = 16000):
    """Anything ffmpeg can read, as 16 kHz mono int16 — for non-WAV inputs."""
    import numpy as np

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-v", "error", "-i", path,
            "-ac", "1", "-ar", str(rate), "-f", "s16le", "-",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
    except (OSError, ValueError):
        return None
    if proc.returncode != 0 or not out:
        return None
    return np.frombuffer(out, dtype="<i2"), rate


def _write_pcm16_wav(path: str, samples, rate: int) -> None:
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.astype("<i2").tobytes())


def _quiet_cut_points(samples, rate: int, window_s: float, *, search_s: float = 5.0, hop_s: float = 0.1) -> list[int]:
    """Sample offsets to cut at: one per ``window_s``, each moved back to the
    quietest ``hop_s`` slice in the ``search_s`` before its boundary so a cut
    never lands inside a word. Starts at 0, ends at ``len(samples)``; no
    window is longer than ``window_s``."""
    import numpy as np

    total = len(samples)
    window = max(1, int(window_s * rate))
    hop = max(1, int(hop_s * rate))
    search = int(search_s * rate)
    cuts = [0]
    while total - cuts[-1] > window:
        boundary = cuts[-1] + window
        best, best_energy = boundary, None
        for start in range(max(cuts[-1] + hop, boundary - search), boundary - hop + 1, hop):
            piece = samples[start:start + hop].astype(np.float64)
            energy = float(np.mean(piece * piece))
            if best_energy is None or energy < best_energy:
                best, best_energy = start + hop // 2, energy
        cuts.append(best)
    cuts.append(total)
    return cuts


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
        result = await self._transcribe_once(audio_path, language=language)
        # Only a pass that SUCCEEDED and came back empty is retried: a service
        # error keeps its real reason, and speech found stays as it is.
        if result.get("segments") or result.get("error") or not _sparse_retry_enabled():
            return result
        try:
            retried = await self._transcribe_windows(audio_path, language=language)
        except Exception:  # noqa: BLE001 — the retry must never break the pass
            logger.exception("Parakeet sparse-speech retry failed for %s", audio_path)
            return result
        if retried:
            logger.info(
                "Parakeet sparse-speech retry recovered %d segment(s) from %s (%d windows)",
                len(retried["segments"]), audio_path, retried["sparse_retry"]["windows"],
            )
            return retried
        return result

    async def _transcribe_windows(
        self,
        audio_path: str,
        *,
        language: str | None = "en",
    ) -> dict[str, Any] | None:
        """Re-run an empty pass in short windows cut at quiet points.

        Returns a normal result with timestamps shifted back into the whole
        file, or None when the windows hold no speech (or the service failed
        part-way, in which case the original empty pass stands).
        """
        import numpy as np

        loaded = _read_pcm16_mono(audio_path) or await _decode_pcm16_mono(audio_path)
        if loaded is None:
            return None
        samples, rate = loaded
        window_s = _env_float("PARAKEET_SPARSE_WINDOW_SECONDS", 30.0)
        duration = len(samples) / float(rate) if rate else 0.0
        if duration <= window_s:
            return None  # the full pass already was one window
        min_words = _env_int("PARAKEET_SPARSE_MIN_WORDS", 3)
        cuts = _quiet_cut_points(samples, rate, window_s)
        segments: list[dict[str, Any]] = []
        words: list[dict[str, Any]] = []
        texts: list[str] = []
        model = self.model
        with tempfile.TemporaryDirectory(prefix="parakeet-sparse-") as tmp:
            for index in range(len(cuts) - 1):
                chunk = samples[cuts[index]:cuts[index + 1]]
                # Digital silence has nothing to find; don't spend a GPU call on it.
                if not len(chunk) or int(np.abs(chunk.astype(np.int32)).max()) < _SILENCE_PEAK:
                    continue
                window_path = os.path.join(tmp, f"window-{index}.wav")
                _write_pcm16_wav(window_path, chunk, rate)
                part = await self._transcribe_once(window_path, language=language)
                if part.get("error"):
                    logger.warning(
                        "Parakeet sparse-speech retry stopped at window %d: %s", index, part["error"]
                    )
                    return None
                offset = cuts[index] / float(rate)
                for seg in part["segments"]:
                    segments.append({**seg, "start": seg["start"] + offset, "end": seg["end"] + offset})
                for word in part["words"]:
                    words.append({**word, "start": word["start"] + offset, "end": word["end"] + offset})
                if part.get("text"):
                    texts.append(part["text"])
                model = part.get("model") or model
        if not any(len((seg.get("text") or "").split()) >= min_words for seg in segments):
            logger.info(
                "Parakeet sparse-speech retry found no line of %d+ words in %s (%d fragment(s) dropped)",
                min_words, audio_path, len(segments),
            )
            return None
        return {
            "text": " ".join(texts).strip(),
            "segments": segments,
            "words": words,
            "duration": duration,
            "language": language or "en",
            "confidence": 0.97,
            "model": model,
            "rtf": None,
            "sparse_retry": {"windows": len(cuts) - 1, "window_seconds": window_s},
        }

    async def _transcribe_once(
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
        resp, error = await _post_audio_with_fallback(
            endpoint=self.endpoint,
            route="/transcribe",
            audio_path=audio_path,
            file_field="audio",
            timeout=timeout,
            label="Parakeet",
            params=params,
        )
        if resp is None:
            return _empty_result(self.model, language or "en", error=error)

        if resp.status_code != 200:
            detail = redact_text((resp.text or "").strip()[:300])
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
        resp, error = await _post_audio_with_fallback(
            endpoint=self.endpoint,
            route="/audio/transcriptions",
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
            detail = redact_text((resp.text or "").strip()[:300])
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
