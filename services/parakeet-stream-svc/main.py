"""meet-parakeet-stream-svc — real Parakeet 0.6B v3 streaming-ish ASR.

Phase B.2 of the server-live pipeline. This service is the upstream the
meet-backend WS handler in ``backend/api/streaming.py`` POSTs chunked
audio windows to. It returns the transcript for the window as JSON.

Endpoints
---------
GET  /healthz             — liveness + model-loaded flag.
GET  /readyz              — same shape, semantic alias.
POST /transcribe-stream   — accept audio bytes (WAV / raw PCM16 / etc),
                            return ``{text, segments, confidence, model, rtf,
                            duration, sequence}``.

The container layers on top of the existing ``meet-parakeet-svc:local``
image so we inherit NeMo 2.4.1 + torch 2.4.1 + CUDA 12.4 + audio tooling.
The only differences from parakeet-svc are:
  - default model is ``nvidia/parakeet-tdt-0.6b-v3`` (the 2026-vintage
    multilingual 0.6 B variant we use for the streaming path), with a
    fallback to ``nvidia/parakeet-tdt-0.6b-v2``,
  - endpoint shape matches what the meet-backend ws handler expects
    (binary body + per-call ``X-Session-Id`` / ``X-Flush-Sequence`` headers
    for correlation),
  - we do **not** do whole-meeting chunking — every POST is already a
    short window from the WS handler.

This is "near-streaming": each window is a small offline transcribe call,
which is good enough for sub-1.5 s p95 partial latency at our 2.5 s
window cadence. True NeMo native streaming (draft + finalize tokens via
``model.streaming_step()``) is Phase B.3 and only changes this file —
the wire contract to the WS handler stays the same.
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
from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("parakeet-stream-svc")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TARGET_SR = 16000

# The 0.6B v3 (multilingual, 2026-vintage) is the canonical streaming
# variant per docs/phase-b-server-live-streaming.md. v2 is the fallback —
# it's English-only but ships ~6 weeks earlier so HF cache hits are
# common in dev. The fp32 0.6B family sits ~2.4 GB resident, fp16 ~1.4 GB
# resident on the 3060 alongside the existing 1.1B batch container (~4 GB).
DEFAULT_MODEL = os.getenv(
    "PARAKEET_STREAM_MODEL", "nvidia/parakeet-tdt-0.6b-v3"
)
FALLBACK_MODEL = os.getenv(
    "PARAKEET_STREAM_FALLBACK_MODEL", "nvidia/parakeet-tdt-0.6b-v2"
)
MODEL_PRECISION = os.getenv("PARAKEET_STREAM_PRECISION", "fp16").strip().lower()

# Window sizing safety rails. Real windows from the WS handler are 2.5 s
# nominal; we reject anything wildly outside the expected range so a
# misbehaving client can't pin the GPU on a 10-min clip on the streaming
# port. The batch endpoint at parakeet-svc:8881 is the right surface
# for long audio.
MIN_AUDIO_SECONDS = float(os.getenv("STREAM_MIN_AUDIO_SECONDS", "0.05"))
MAX_AUDIO_SECONDS = float(os.getenv("STREAM_MAX_AUDIO_SECONDS", "30.0"))

SERVICE_VERSION = "0.2.0"  # B.2 (real model). B.1 stub was 0.1.0-scaffold.

# Module-level model state — single instance, kept warm across calls.
_model: Any = None
_model_name: str = ""
_model_load_error: Optional[str] = None
_model_load_seconds: Optional[float] = None


def _load_model() -> Any:
    """Eager-load Parakeet 0.6B v3 at startup. Tries DEFAULT_MODEL first,
    falls back to FALLBACK_MODEL on any exception. Idempotent; cheap to
    call repeatedly once warm.
    """
    global _model, _model_name, _model_load_error, _model_load_seconds
    if _model is not None:
        return _model

    from nemo.collections.asr.models import ASRModel  # deferred import

    candidates = [DEFAULT_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != DEFAULT_MODEL:
        candidates.append(FALLBACK_MODEL)

    last_exc: Optional[Exception] = None
    for name in candidates:
        try:
            logger.info("Loading Parakeet stream model %s on %s", name, DEVICE)
            t0 = time.time()
            model = ASRModel.from_pretrained(model_name=name)
            model = model.to(DEVICE)
            if MODEL_PRECISION in ("fp16", "half", "float16"):
                if DEVICE == "cuda":
                    model = model.half()
                    logger.info("Parakeet stream precision = fp16")
                else:
                    logger.warning("Ignoring fp16 precision on non-CUDA device")
            try:
                model.eval()
            except Exception:
                pass
            _model = model
            _model_name = name
            _model_load_error = None
            _model_load_seconds = time.time() - t0
            logger.info(
                "Parakeet stream ready: %s (load took %.1f s)",
                name, _model_load_seconds,
            )
            return _model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err = f"{type(exc).__name__}: {exc}"
            logger.warning("Failed to load %s: %s", name, err)
            _model_load_error = err
            _model = None
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    msg = f"All Parakeet stream candidates failed; last error: {last_exc}"
    logger.error(msg)
    _model_load_error = str(last_exc) if last_exc else "unknown error"
    raise RuntimeError(msg)


def _decode_audio(buf: bytes) -> tuple[np.ndarray, float]:
    """Accept raw bytes that should be WAV-wrapped audio (what the
    meet-backend WS handler sends after wrapping PCM16 in a RIFF header).

    Falls back to treating the input as raw PCM16 at 16 kHz mono if WAV
    parsing fails — the streaming path is fast and we'd rather emit a
    best-effort transcript than 400.

    Returns (mono float32 waveform at TARGET_SR, duration seconds).
    """
    wav: Optional[np.ndarray] = None
    sr: int = 0

    # Try WAV first.
    try:
        wav, sr = sf.read(io.BytesIO(buf), dtype="float32", always_2d=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("WAV parse failed (%s); trying raw PCM16", exc)

    # Raw PCM16 fallback. The WS handler always wraps in WAV today, but
    # this keeps us forgiving of clients that POST raw PCM directly during
    # B.2 manual tests.
    if wav is None or wav.size == 0:
        try:
            i16 = np.frombuffer(buf, dtype=np.int16)
            wav = (i16.astype(np.float32) / 32768.0)
            sr = TARGET_SR
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"audio decode failed (not WAV, not PCM16): {exc}",
            )

    if wav.ndim > 1:
        wav = wav.mean(axis=1)

    if sr != TARGET_SR:
        wav_t = torch.from_numpy(wav).unsqueeze(0)
        wav_t = torchaudio.functional.resample(wav_t, sr, TARGET_SR)
        wav = wav_t.squeeze(0).numpy()

    duration = float(len(wav)) / float(TARGET_SR)
    return wav, duration


def _transcribe_window(wav: np.ndarray) -> dict[str, Any]:
    """Run one short-window transcribe via NeMo. Returns a dict with
    text + per-segment list + the model name used. RTF + confidence are
    set by the caller (we need elapsed wall-clock from the request entry).
    """
    model = _load_model()

    # NeMo's transcribe() takes a list of file paths today. The cheapest
    # way to feed in-memory audio is via a tempfile WAV — soundfile writes
    # PCM16 in ~1 ms for our window sizes.
    fd, path = tempfile.mkstemp(prefix="parakeet_stream_", suffix=".wav")
    os.close(fd)
    try:
        sf.write(path, wav, TARGET_SR, subtype="PCM_16")
        try:
            results = model.transcribe(
                [path], timestamps=True, batch_size=1,
            )
        except TypeError:
            # Older NeMo signature variant — fall back.
            try:
                results = model.transcribe(
                    [path], return_hypotheses=True, batch_size=1,
                )
            except TypeError:
                results = model.transcribe([path])

        if isinstance(results, tuple):
            results = results[0]
        if not results:
            return {"text": "", "segments": [], "words": [], "model": _model_name}

        hyp = results[0]
        text = ""
        segments: list[dict[str, Any]] = []
        words: list[dict[str, Any]] = []

        if isinstance(hyp, str):
            text = hyp.strip()
        elif hasattr(hyp, "text"):
            text = (hyp.text or "").strip()
            ts = getattr(hyp, "timestamp", None) or {}
            seg_ts = ts.get("segment") if isinstance(ts, dict) else None
            if seg_ts:
                for s in seg_ts:
                    segments.append({
                        "start": float(s.get("start", 0.0)),
                        "end": float(s.get("end", 0.0)),
                        "text": (s.get("segment") or s.get("text") or "").strip(),
                        "confidence": float(s.get("confidence", 0.95)),
                        "speaker": None,
                    })
            word_ts = ts.get("word") if isinstance(ts, dict) else None
            if word_ts:
                for w in word_ts:
                    words.append({
                        "start": float(w.get("start", 0.0)),
                        "end": float(w.get("end", 0.0)),
                        "word": (w.get("word") or w.get("text") or "").strip(),
                        "confidence": float(w.get("confidence", 0.97)),
                    })
        else:
            text = str(hyp).strip()

        return {
            "text": text,
            "segments": segments,
            "words": words,
            "model": _model_name,
        }
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------- request / response shapes ----------

class HealthResponse(BaseModel):
    status: str
    version: str
    model_loaded: bool
    model: Optional[str] = None
    requested_model: str = DEFAULT_MODEL
    fallback_model: Optional[str] = FALLBACK_MODEL
    load_error: Optional[str] = None
    load_seconds: Optional[float] = None
    device: str = DEVICE
    cuda_available: bool = False
    precision: str = MODEL_PRECISION
    phase: str = "B.2"


class TranscribeSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: float = 0.95
    speaker: Optional[str] = None


class TranscribeWord(BaseModel):
    start: float
    end: float
    word: str
    confidence: float = 0.97


class TranscribeStreamResponse(BaseModel):
    text: str
    segments: list[TranscribeSegment] = Field(default_factory=list)
    words: list[TranscribeWord] = Field(default_factory=list)
    duration: float
    model: str
    rtf: float
    confidence: float = 0.95
    sequence: Optional[int] = None
    is_final: bool = False
    service_version: str = SERVICE_VERSION


# ---------- routes ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the model at startup so the first /transcribe-stream isn't
    # gated on ~20 s of NeMo init. If load fails we still come up so
    # /healthz can report the error.
    try:
        _load_model()
    except Exception as exc:  # noqa: BLE001
        logger.error("Startup model load failed: %s", exc)
    yield


app = FastAPI(
    title="meet-parakeet-stream-svc",
    version=SERVICE_VERSION,
    description=(
        "Phase B.2 streaming-ish ASR using NeMo Parakeet 0.6B v3 (or v2 "
        "fallback). Counterpart to the batch parakeet-svc at :8881."
    ),
    lifespan=lifespan,
)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    cuda = torch.cuda.is_available()
    status = "ok" if _model is not None else ("loading" if _model_load_error is None else "degraded")
    return HealthResponse(
        status=status,
        version=SERVICE_VERSION,
        model_loaded=_model is not None,
        model=_model_name or None,
        requested_model=DEFAULT_MODEL,
        fallback_model=FALLBACK_MODEL,
        load_error=_model_load_error,
        load_seconds=_model_load_seconds,
        device=DEVICE,
        cuda_available=cuda,
        precision=MODEL_PRECISION,
        phase="B.2",
    )


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Same body as /healthz; convention alias."""
    return healthz()


@app.post("/transcribe-stream", response_model=TranscribeStreamResponse)
async def transcribe_stream(
    request: Request,
    return_word_timestamps: bool = Query(default=False),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    x_flush_sequence: Optional[str] = Header(default=None, alias="X-Flush-Sequence"),
    x_is_final: Optional[str] = Header(default=None, alias="X-Is-Final"),
) -> TranscribeStreamResponse:
    """Transcribe a single short audio window.

    Request body: WAV bytes (preferred — meet-backend WS handler wraps
    PCM16 in a minimal RIFF) or raw PCM16 LE at 16 kHz mono.

    Headers (all optional):
      X-Session-Id      — opaque per-WS session identifier for log correlation
      X-Flush-Sequence  — per-session monotonic counter from the WS handler
      X-Is-Final        — "1" if this is the last window of the segment

    Response: text + (optional) word/segment timestamps + the actual model
    used + the realtime factor for this window.
    """
    started = time.time()

    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio body")

    try:
        seq_i: Optional[int] = int(x_flush_sequence) if x_flush_sequence else None
    except ValueError:
        seq_i = None
    is_final = (x_is_final == "1")

    wav, duration = _decode_audio(raw)
    if duration < MIN_AUDIO_SECONDS:
        # Empty / sub-frame buffer — return an empty transcript rather
        # than 400 so the WS handler's de-dup logic stays simple.
        return TranscribeStreamResponse(
            text="",
            duration=duration,
            model=_model_name or DEFAULT_MODEL,
            rtf=0.0,
            confidence=0.0,
            sequence=seq_i,
            is_final=is_final,
        )
    if duration > MAX_AUDIO_SECONDS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"window too long ({duration:.1f}s > {MAX_AUDIO_SECONDS:.0f}s) — "
                "use the batch /transcribe endpoint on parakeet-svc:8881 for "
                "full meetings"
            ),
        )

    if _model is None and _model_load_error is None:
        # Still warming up; tell caller it's transient.
        raise HTTPException(
            status_code=503,
            detail="model still loading — retry in a few seconds",
        )

    if _model is None:
        raise HTTPException(
            status_code=503,
            detail=f"model load failed: {_model_load_error}",
        )

    try:
        result = _transcribe_window(wav)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("transcribe failed session=%s seq=%s", x_session_id, seq_i)
        raise HTTPException(status_code=500, detail=f"transcribe failed: {exc}")

    elapsed = time.time() - started
    rtf = elapsed / duration if duration > 0 else 0.0

    text = result.get("text", "") or ""
    segments = result.get("segments") or []
    words = result.get("words") or [] if return_word_timestamps else []
    # If the model gave text but no segments (some NeMo configs), synthesize
    # a single segment covering the whole window. This keeps the response
    # shape stable for the WS handler regardless of whether timestamps were
    # produced.
    if not segments and text:
        segments = [{
            "start": 0.0,
            "end": duration,
            "text": text,
            "confidence": 0.95,
            "speaker": None,
        }]

    # Confidence: NeMo doesn't surface a single-window confidence directly.
    # We mean-pool whatever segment-level numbers we got (defaults to 0.95
    # if none). The meet-backend WS handler passes this through verbatim.
    if segments:
        confs = [float(s.get("confidence", 0.95)) for s in segments]
        confidence = sum(confs) / len(confs) if confs else 0.95
    else:
        confidence = 0.0 if not text else 0.95

    logger.info(
        "/transcribe-stream session=%s seq=%s duration=%.2fs elapsed=%.2fs "
        "rtf=%.3f chars=%d final=%s",
        x_session_id, seq_i, duration, elapsed, rtf, len(text), is_final,
    )

    return TranscribeStreamResponse(
        text=text,
        segments=[TranscribeSegment(**s) for s in segments],
        words=[TranscribeWord(**w) for w in words],
        duration=duration,
        model=_model_name or DEFAULT_MODEL,
        rtf=rtf,
        confidence=float(confidence),
        sequence=seq_i,
        is_final=is_final,
    )


@app.get("/")
async def root() -> dict:
    return {
        "service": "meet-parakeet-stream-svc",
        "version": SERVICE_VERSION,
        "phase": "B.2",
        "model": _model_name or DEFAULT_MODEL,
        "model_loaded": _model is not None,
        "docs": "/docs",
        "healthz": "/healthz",
        "design_doc": "docs/phase-b-server-live-streaming.md",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8895, reload=False)
