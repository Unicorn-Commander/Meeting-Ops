"""parakeet-svc — FastAPI wrapper around NVIDIA NeMo Parakeet-TDT ASR.

Endpoints
---------
GET  /health      — liveness, model status, GPU info
POST /transcribe  — transcribe an audio file (multipart upload). Returns
                    text + segments + word-level timestamps + RTF.

Response shape matches services/whisper_server_client.py for the overlapping
fields (text / segments / duration / language) so the backend's STT provider
can swap whisper for parakeet without other changes.

Container layout
----------------
- Default model: nvidia/parakeet-tdt-1.1b (PARAKEET_MODEL env var to override)
- Auto-falls-back to nvidia/parakeet-tdt-0.6b if the 1.1B model fails to
  load (typically OOM on a shared GPU). The actual model is reported back
  via /health and on every /transcribe response.
- 16 kHz mono internally — anything else is resampled with torchaudio.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger("parakeet-svc")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TARGET_SR = 16000  # Parakeet expects 16 kHz mono
DEFAULT_MODEL = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-1.1b")
FALLBACK_MODEL = os.getenv("PARAKEET_FALLBACK_MODEL", "nvidia/parakeet-tdt-0.6b")
MIN_SECONDS = float(os.getenv("MIN_AUDIO_SECONDS", "0.1"))
MAX_SECONDS = float(os.getenv("MAX_AUDIO_SECONDS", "7200"))  # 2 hours
SERVICE_VERSION = "0.1.0"

# Module-level model state
_model: Any = None
_model_name: str = ""
_model_load_error: Optional[str] = None


def _load_model() -> Any:
    """Eager-load Parakeet at startup. Tries DEFAULT_MODEL first, falls back
    to FALLBACK_MODEL on any exception (typically OOM with the 1.1B variant
    when the GPU is shared with whisper.cpp + speaker-svc)."""
    global _model, _model_name, _model_load_error
    if _model is not None:
        return _model

    # Defer the import so /health stays cheap even if NeMo has issues.
    from nemo.collections.asr.models import ASRModel

    candidates = [DEFAULT_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != DEFAULT_MODEL:
        candidates.append(FALLBACK_MODEL)

    last_exc: Optional[Exception] = None
    for name in candidates:
        try:
            logger.info("Loading Parakeet model %s on %s", name, DEVICE)
            t0 = time.time()
            model = ASRModel.from_pretrained(model_name=name)
            model = model.to(DEVICE)
            try:
                model.eval()
            except Exception:
                pass
            _model = model
            _model_name = name
            _model_load_error = None
            logger.info("Parakeet ready: %s (load took %.1fs)", name, time.time() - t0)
            return _model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err = f"{type(exc).__name__}: {exc}"
            logger.warning("Failed to load %s: %s", name, err)
            _model_load_error = err
            # Free anything that might have been partially allocated before retrying
            _model = None
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    msg = f"All Parakeet candidates failed; last error: {last_exc}"
    logger.error(msg)
    _model_load_error = str(last_exc) if last_exc else "unknown error"
    raise RuntimeError(msg)


def _read_audio_to_wav(buf: bytes | str) -> tuple[str, float]:
    """Read audio bytes/path -> mono 16kHz wav file on disk.
    NeMo's transcribe() expects a list of file paths, so we always
    materialize the input as a temp file. Returns (path, duration_seconds)."""
    if isinstance(buf, str):
        if not os.path.exists(buf):
            raise HTTPException(status_code=400, detail=f"audio_path not found: {buf}")
        wav, sr = sf.read(buf, dtype="float32", always_2d=False)
    else:
        wav, sr = sf.read(io.BytesIO(buf), dtype="float32", always_2d=False)

    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != TARGET_SR:
        wav_t = torch.from_numpy(wav).unsqueeze(0)
        wav_t = torchaudio.functional.resample(wav_t, sr, TARGET_SR)
        wav = wav_t.squeeze(0).numpy()

    duration = float(len(wav)) / float(TARGET_SR)
    if duration < MIN_SECONDS:
        raise HTTPException(status_code=400, detail=f"audio too short ({duration:.2f}s < {MIN_SECONDS}s)")
    if duration > MAX_SECONDS:
        raise HTTPException(status_code=400, detail=f"audio too long ({duration:.1f}s > {MAX_SECONDS}s)")

    # Write a 16-bit PCM wav so NeMo's data layer doesn't have to guess.
    fd, path = tempfile.mkstemp(prefix="parakeet_", suffix=".wav")
    os.close(fd)
    sf.write(path, wav, TARGET_SR, subtype="PCM_16")
    return path, duration


def _transcribe_with_timestamps(audio_path: str) -> dict[str, Any]:
    """Call NeMo transcribe() with timestamp output enabled.

    NeMo 2.0+ Parakeet-TDT exposes timestamps via the `timestamps` kwarg
    when calling `transcribe()`. The result objects expose per-segment and
    per-word timing metadata directly. Older signatures and fallbacks are
    handled defensively so this works against several minor NeMo versions.
    """
    model = _load_model()

    # Newer NeMo: returns a list of Hypothesis objects with `.text` and
    # `.timestamp` populated. We try kwargs that work on 2.0.0; older paths
    # fall back to plain text.
    try:
        results = model.transcribe([audio_path], timestamps=True, batch_size=1)
    except TypeError:
        # Older NeMo signatures — no `timestamps` kwarg.
        try:
            results = model.transcribe([audio_path], return_hypotheses=True, batch_size=1)
        except TypeError:
            results = model.transcribe([audio_path])

    # NeMo can return either:
    #   * a flat list (RNN-T / CTC, no timestamps) of strings, OR
    #   * a tuple/list of [hypotheses, all_hypotheses] from beam search, OR
    #   * a list of Hypothesis objects with .text / .timestamp
    if isinstance(results, tuple):
        results = results[0]

    if not results:
        raise HTTPException(status_code=500, detail="model returned no results")

    first = results[0]
    text = ""
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []

    if isinstance(first, str):
        text = first.strip()
    elif hasattr(first, "text"):
        text = (first.text or "").strip()
        ts = getattr(first, "timestamp", None) or {}
        # NeMo 2.0 layout: ts has keys like "segment", "word", "char" (each is a
        # list of dicts with start/end + the corresponding token).
        seg_ts = ts.get("segment") if isinstance(ts, dict) else None
        if seg_ts:
            for s in seg_ts:
                segments.append({
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                    "text": (s.get("segment") or s.get("text") or "").strip(),
                    "confidence": float(s.get("confidence", 0.97)),
                    "speaker": None,
                })
        word_ts = ts.get("word") if isinstance(ts, dict) else None
        if word_ts:
            for w in word_ts:
                words.append({
                    "start": float(w.get("start", 0.0)),
                    "end": float(w.get("end", 0.0)),
                    "word": (w.get("word") or w.get("text") or "").strip(),
                    "confidence": float(w.get("confidence", 0.99)),
                })
    else:
        # Last-ditch coercion — stringify whatever came back.
        text = str(first).strip()

    return {
        "text": text,
        "segments": segments,
        "words": words,
    }


# ---------- request / response models ----------


class HealthResponse(BaseModel):
    ok: bool
    status: str
    device: str
    cuda_available: bool
    gpu_name: Optional[str] = None
    model_loaded: bool
    model: str
    requested_model: str
    fallback_model: Optional[str] = None
    load_error: Optional[str] = None
    version: str = SERVICE_VERSION


class TranscribeSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: float = 0.97
    speaker: Optional[str] = None


class TranscribeWord(BaseModel):
    start: float
    end: float
    word: str
    confidence: float = 0.99


class TranscribeResponse(BaseModel):
    text: str
    segments: list[TranscribeSegment] = Field(default_factory=list)
    words: list[TranscribeWord] = Field(default_factory=list)
    duration: float
    language: str = "en"
    model: str
    rtf: float  # realtime factor (processing_time / audio_duration)
    confidence: float = 0.97  # legacy compat with whisper_server_client


# ---------- routes ----------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the model on startup so the first /transcribe is fast.
    try:
        _load_model()
    except Exception as exc:  # noqa: BLE001
        logger.error("Startup model load failed: %s", exc)
    yield


app = FastAPI(title="parakeet-svc", version=SERVICE_VERSION, lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    gpu_name: Optional[str] = None
    if torch.cuda.is_available():
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001
            gpu_name = None
    return HealthResponse(
        ok=_model is not None,
        status="ok" if _model is not None else "loading",
        device=DEVICE,
        cuda_available=torch.cuda.is_available(),
        gpu_name=gpu_name,
        model_loaded=_model is not None,
        model=_model_name or "",
        requested_model=DEFAULT_MODEL,
        fallback_model=FALLBACK_MODEL,
        load_error=_model_load_error,
        version=SERVICE_VERSION,
    )


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Query(default="en", max_length=8),
    return_word_timestamps: bool = Query(default=True),
):
    """Transcribe a multipart audio upload. The model is loaded once at startup
    and kept warm. The first call after startup may still pay a small JIT cost
    for any kernels NeMo lazily compiles."""
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio body")

    started = time.time()
    wav_path, duration = _read_audio_to_wav(raw)
    try:
        result = _transcribe_with_timestamps(wav_path)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass

    elapsed = time.time() - started
    rtf = elapsed / duration if duration > 0 else 0.0

    segments = result.get("segments") or []
    words = result.get("words") or [] if return_word_timestamps else []

    # If NeMo gave us text but no segments (older versions w/o timestamps), fall
    # back to a single segment covering the whole clip so the response stays
    # drop-in compatible with the whisper-server response shape.
    if not segments and result.get("text"):
        segments = [{
            "start": 0.0,
            "end": duration,
            "text": result["text"],
            "confidence": 0.97,
            "speaker": None,
        }]

    logger.info("/transcribe duration=%.2fs elapsed=%.2fs rtf=%.3f model=%s words=%d segments=%d",
                duration, elapsed, rtf, _model_name, len(words), len(segments))

    return TranscribeResponse(
        text=result.get("text", ""),
        segments=[TranscribeSegment(**s) for s in segments],
        words=[TranscribeWord(**w) for w in words],
        duration=duration,
        language=language or "en",
        model=_model_name or DEFAULT_MODEL,
        rtf=rtf,
        confidence=0.97,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8881, reload=False)
