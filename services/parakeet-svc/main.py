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


CHUNK_SECONDS = float(os.getenv("PARAKEET_CHUNK_SECONDS", "600"))   # 10 min default
CHUNK_GRACE = float(os.getenv("PARAKEET_CHUNK_GRACE", "30"))        # allow up to 10:30 in a single call


def _split_wav_chunks(audio_path: str, chunk_seconds: float = CHUNK_SECONDS) -> list[tuple[float, str]]:
    """Slice a 16 kHz mono wav into ~chunk_seconds segments via ffmpeg.

    Returns a list of (start_time_offset, chunk_path) tuples in time order.
    Caller is responsible for unlinking the chunk files.
    """
    import math
    import subprocess

    # ffprobe duration is authoritative; we already have it from _read_audio_to_wav
    # but ffmpeg's stream-copy split needs a clean slice spec anyway.
    probe = subprocess.run(
        ["ffprobe", "-i", audio_path, "-show_entries", "format=duration",
         "-v", "quiet", "-of", "csv=p=0"],
        capture_output=True, text=True,
    )
    try:
        total = float(probe.stdout.strip())
    except ValueError:
        total = 0.0

    if total <= 0:
        return [(0.0, audio_path)]

    num_chunks = max(1, math.ceil(total / chunk_seconds))
    chunks: list[tuple[float, str]] = []
    for i in range(num_chunks):
        offset = i * chunk_seconds
        fd, path = tempfile.mkstemp(prefix=f"parakeet_chunk{i:02d}_", suffix=".wav")
        os.close(fd)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{offset:.3f}",
            "-t", f"{chunk_seconds:.3f}",
            "-i", audio_path,
            "-ar", str(TARGET_SR), "-ac", "1",
            "-c:a", "pcm_s16le",
            path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) == 0:
            try:
                os.remove(path)
            except OSError:
                pass
            logger.warning(
                "ffmpeg split chunk %d/%d failed: %s",
                i + 1, num_chunks, res.stderr.decode("utf-8", "replace")[:200],
            )
            continue
        chunks.append((offset, path))
    return chunks


def _transcribe_chunked(audio_path: str, duration_seconds: float) -> dict[str, Any]:
    """Dispatch wrapper: short audio goes straight to NeMo; long audio is
    split into CHUNK_SECONDS-sized pieces, transcribed independently, and
    merged with timestamp offsets so the response shape stays drop-in
    compatible with the single-shot path.

    Mirrors the chunking pattern in the Cognitive Companion / Meeting
    Minutes Mac app (scripts/transcribe_parakeet.py) — Parakeet's
    conformer attention matrix grows quadratically with audio length, so
    full-length forward passes over multi-hour audio OOM even on 24 GB
    GPUs.
    """
    if duration_seconds <= CHUNK_SECONDS + CHUNK_GRACE:
        return _transcribe_with_timestamps(audio_path)

    chunks = _split_wav_chunks(audio_path, CHUNK_SECONDS)
    if not chunks:
        raise HTTPException(status_code=500, detail="audio split into 0 chunks")

    merged_segments: list[dict[str, Any]] = []
    merged_words: list[dict[str, Any]] = []
    merged_text: list[str] = []
    used_model = None
    try:
        for idx, (offset, chunk_path) in enumerate(chunks):
            logger.info("transcribing chunk %d/%d (offset=%.1fs)", idx + 1, len(chunks), offset)
            part = _transcribe_with_timestamps(chunk_path)
            used_model = part.get("model") or used_model
            for seg in (part.get("segments") or []):
                merged_segments.append({
                    **seg,
                    "start": float(seg.get("start", 0)) + offset,
                    "end": float(seg.get("end", 0)) + offset,
                })
            for w in (part.get("words") or []):
                merged_words.append({
                    **w,
                    "start": float(w.get("start", 0)) + offset,
                    "end": float(w.get("end", 0)) + offset,
                })
            if part.get("text"):
                merged_text.append(part["text"])
            # Drop GPU caches between chunks so attention buffers from
            # chunk N don't strand memory for chunk N+1.
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
    finally:
        for _, p in chunks:
            try:
                os.remove(p)
            except OSError:
                pass

    return {
        "text": " ".join(merged_text).strip(),
        "segments": merged_segments,
        "words": merged_words,
        "model": used_model or _model_name,
        "duration": duration_seconds,
        "language": "en",
    }


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
        result = _transcribe_chunked(wav_path, duration)
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
