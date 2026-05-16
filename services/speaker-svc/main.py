"""speaker-svc — FastAPI wrapper around SpeechBrain ECAPA + optional Pyannote 3.1.

Endpoints
---------
GET  /health                — liveness, model status, GPU info
POST /embed                 — extract a 192-d ECAPA embedding from a clip
POST /diarize               — diarize an audio file (Pyannote if token, else ECAPA-cluster fallback)
POST /identify              — match a clip against a list of known embeddings (cosine sim)

The container runs inside the meet-internal Docker network on bigboy GPU 1.
Audio is sent as a file path (when caller and svc share a mount) or as bytes
in the multipart body (always supported).
"""
from __future__ import annotations

import io
import logging
import os
import time
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger("speaker-svc")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TARGET_SR = 16000  # ECAPA + Pyannote both expect 16 kHz mono
MIN_SECONDS = float(os.getenv("MIN_AUDIO_SECONDS", "0.5"))
MAX_SECONDS = float(os.getenv("MAX_AUDIO_SECONDS", "1800"))  # 30 min
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "").strip() or None

app = FastAPI(title="speaker-svc", version="0.1.0")

_ecapa = None
_diarizer = None
_diarizer_load_error: Optional[str] = None


def _load_ecapa():
    """Lazy-load the ECAPA encoder. Cached after first call."""
    global _ecapa
    if _ecapa is not None:
        return _ecapa
    from speechbrain.inference.speaker import EncoderClassifier
    logger.info("Loading SpeechBrain ECAPA on %s", DEVICE)
    _ecapa = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="/models/ecapa",
        run_opts={"device": DEVICE},
    )
    return _ecapa


def _load_diarizer():
    """Lazy-load Pyannote 3.1 — only if HUGGINGFACE_TOKEN is set."""
    global _diarizer, _diarizer_load_error
    if _diarizer is not None:
        return _diarizer
    if not HF_TOKEN:
        _diarizer_load_error = "HUGGINGFACE_TOKEN not set; pyannote/speaker-diarization-3.1 unavailable"
        return None
    try:
        from pyannote.audio import Pipeline
        logger.info("Loading pyannote/speaker-diarization-3.1 on %s", DEVICE)
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HF_TOKEN,
        )
        if DEVICE == "cuda":
            pipeline.to(torch.device("cuda"))
        # Tune clustering + segmentation. Threshold has two failure modes:
        # - too low (e.g. 0.65 from Meeting Minutes): over-splits one
        #   speaker's varied speech into multiple clusters. Aaron's
        #   5-speaker Legacy 21 came back as 14 at 0.65.
        # - too high (~0.7045 model default): merges similar voices into
        #   one. The Citadel meeting came back as 1 speaker at default
        #   before this knob existed.
        # 0.72 sits a hair above the model default, biasing toward
        # merging when in doubt. Env-tunable so we can dial per deploy
        # without rebuilding.
        clustering_thr = float(os.getenv("PYANNOTE_CLUSTERING_THRESHOLD", "0.72"))
        min_off = float(os.getenv("PYANNOTE_MIN_DURATION_OFF", "0.5"))
        try:
            params = pipeline.parameters(instantiated=True)
            params["clustering"]["threshold"] = clustering_thr
            params["segmentation"]["min_duration_off"] = min_off
            pipeline.instantiate(params)
            logger.info(
                "Pyannote tuned: clustering.threshold=%.3f, segmentation.min_duration_off=%.3f",
                clustering_thr, min_off,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pyannote tuning skipped: %s", exc)
        _diarizer = pipeline
        return _diarizer
    except Exception as exc:  # noqa: BLE001
        _diarizer_load_error = f"{type(exc).__name__}: {exc}"
        logger.warning("Pyannote load failed: %s", _diarizer_load_error)
        return None


def _read_audio(buf: bytes | str) -> tuple[np.ndarray, int]:
    """Read audio from path or bytes -> mono float32 at TARGET_SR."""
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
    duration = len(wav) / TARGET_SR
    if duration < MIN_SECONDS:
        raise HTTPException(status_code=400, detail=f"audio too short ({duration:.2f}s < {MIN_SECONDS}s)")
    if duration > MAX_SECONDS:
        raise HTTPException(status_code=400, detail=f"audio too long ({duration:.1f}s > {MAX_SECONDS}s)")
    return wav, TARGET_SR


def _embed(wav: np.ndarray) -> list[float]:
    encoder = _load_ecapa()
    with torch.no_grad():
        signal = torch.from_numpy(wav).unsqueeze(0)
        if DEVICE == "cuda":
            signal = signal.to("cuda")
        emb = encoder.encode_batch(signal).squeeze().cpu().numpy().astype("float32")
    return emb.tolist()


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ---------- request / response models ----------


class HealthResponse(BaseModel):
    status: str
    device: str
    cuda_available: bool
    gpu_name: Optional[str] = None
    ecapa_loaded: bool
    diarizer_available: bool
    diarizer_error: Optional[str] = None
    embedding_dim: int = 192


class EmbedResponse(BaseModel):
    embedding: list[float]
    embedding_dim: int
    duration_seconds: float
    model: str = "speechbrain/spkrec-ecapa-voxceleb"


class DiarizeSegment(BaseModel):
    start: float
    end: float
    speaker: str  # e.g. "SPEAKER_00"
    embedding: Optional[list[float]] = None  # ECAPA embedding for the segment


class DiarizeResponse(BaseModel):
    segments: list[DiarizeSegment]
    num_speakers: int
    backend: str  # "pyannote-3.1" or "ecapa-cluster-fallback"
    duration_seconds: float


class IdentifyCandidate(BaseModel):
    speaker_id: int
    embedding: list[float]


class IdentifyRequest(BaseModel):
    embedding: list[float]
    candidates: list[IdentifyCandidate] = Field(default_factory=list)
    threshold: float = 0.55  # cosine similarity above this counts as a match


class IdentifyMatch(BaseModel):
    speaker_id: int
    similarity: float
    matched: bool


class IdentifyResponse(BaseModel):
    matches: list[IdentifyMatch]
    best_match: Optional[IdentifyMatch] = None


# ---------- routes ----------


@app.get("/health", response_model=HealthResponse)
def health():
    gpu_name = None
    if torch.cuda.is_available():
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001
            gpu_name = None
    diarizer_available = HF_TOKEN is not None and (_diarizer is not None or _load_diarizer() is not None)
    return HealthResponse(
        status="ok",
        device=DEVICE,
        cuda_available=torch.cuda.is_available(),
        gpu_name=gpu_name,
        ecapa_loaded=_ecapa is not None,
        diarizer_available=diarizer_available,
        diarizer_error=_diarizer_load_error,
        embedding_dim=192,
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed(
    audio: Optional[UploadFile] = File(default=None),
    audio_path: Optional[str] = Form(default=None),
):
    """Embed a single short clip (typically 3-30s) into a 192-d ECAPA vector."""
    if audio is None and not audio_path:
        raise HTTPException(status_code=400, detail="provide audio (multipart) or audio_path (form field)")
    started = time.time()
    raw: bytes | str
    if audio_path:
        raw = audio_path
    else:
        raw = await audio.read()
    wav, _ = _read_audio(raw)
    emb = _embed(wav)
    logger.info("/embed dim=%d took=%.2fs", len(emb), time.time() - started)
    return EmbedResponse(
        embedding=emb,
        embedding_dim=len(emb),
        duration_seconds=len(wav) / TARGET_SR,
    )


@app.post("/diarize", response_model=DiarizeResponse)
async def diarize(
    audio: Optional[UploadFile] = File(default=None),
    audio_path: Optional[str] = Form(default=None),
    return_embeddings: bool = Form(default=True),
    num_speakers: Optional[int] = Form(default=None),
    min_speakers: Optional[int] = Form(default=None),
    max_speakers: Optional[int] = Form(default=None),
    clustering_threshold: Optional[float] = Form(default=None),
):
    """Diarize. Uses Pyannote 3.1 if HUGGINGFACE_TOKEN is set; otherwise
    falls back to single-speaker ECAPA pseudo-diarization (one segment for
    the whole clip) so callers always get a usable response shape."""
    if audio is None and not audio_path:
        raise HTTPException(status_code=400, detail="provide audio or audio_path")

    raw: bytes | str
    if audio_path:
        raw = audio_path
    else:
        raw = await audio.read()
    wav, _ = _read_audio(raw)
    duration = len(wav) / TARGET_SR

    pipeline = _load_diarizer()
    if pipeline is None:
        # Graceful degradation — one segment, one ECAPA embedding for the
        # whole clip. Caller can still cluster across many segments using
        # /identify if they want.
        emb = _embed(wav) if return_embeddings else None
        return DiarizeResponse(
            segments=[DiarizeSegment(start=0.0, end=duration, speaker="SPEAKER_00", embedding=emb)],
            num_speakers=1,
            backend="ecapa-cluster-fallback",
            duration_seconds=duration,
        )

    # Pyannote path — write the resampled wav back to a temp file because
    # pyannote pipelines expect a file path or a torchaudio waveform tuple.
    waveform = torch.from_numpy(wav).unsqueeze(0)  # (1, T)

    # Per-call clustering threshold override. Re-instantiate the pipeline
    # only when the caller asked for a value different from what's
    # already loaded — re-instantiation is cheap (no model reload) but
    # not free, and most calls use the env default.
    if clustering_threshold is not None:
        try:
            params = pipeline.parameters(instantiated=True)
            current_thr = float(params.get("clustering", {}).get("threshold") or 0)
            if abs(current_thr - float(clustering_threshold)) > 1e-4:
                params["clustering"]["threshold"] = float(clustering_threshold)
                pipeline.instantiate(params)
                logger.info("Pyannote per-call threshold override: %.3f", clustering_threshold)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Per-call threshold override skipped: %s", exc)

    diarize_kwargs: dict[str, int] = {}
    if num_speakers is not None:
        diarize_kwargs["num_speakers"] = int(num_speakers)
    else:
        if min_speakers is not None:
            diarize_kwargs["min_speakers"] = int(min_speakers)
        if max_speakers is not None:
            diarize_kwargs["max_speakers"] = int(max_speakers)
    logger.info(
        "/diarize duration=%.1fs hints=%s threshold=%s",
        duration,
        diarize_kwargs or "auto",
        clustering_threshold if clustering_threshold is not None else "env-default",
    )
    diarization = pipeline(
        {"waveform": waveform, "sample_rate": TARGET_SR},
        **diarize_kwargs,
    )

    segments: list[DiarizeSegment] = []
    speakers_seen: set[str] = set()
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speakers_seen.add(speaker)
        seg_emb = None
        if return_embeddings:
            start_idx = max(0, int(turn.start * TARGET_SR))
            end_idx = min(len(wav), int(turn.end * TARGET_SR))
            if end_idx - start_idx >= int(MIN_SECONDS * TARGET_SR):
                try:
                    seg_emb = _embed(wav[start_idx:end_idx])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("segment embed failed: %s", exc)
        segments.append(DiarizeSegment(
            start=float(turn.start),
            end=float(turn.end),
            speaker=speaker,
            embedding=seg_emb,
        ))

    return DiarizeResponse(
        segments=segments,
        num_speakers=len(speakers_seen),
        backend="pyannote-3.1",
        duration_seconds=duration,
    )


@app.post("/identify", response_model=IdentifyResponse)
def identify(req: IdentifyRequest):
    """Score a query embedding against candidate enrolled-speaker embeddings.

    Pure cosine similarity. Caller is responsible for picking the right
    threshold for their environment (we default to 0.55 which is a reasonable
    starting point for ECAPA on conference-room mics)."""
    if not req.embedding:
        raise HTTPException(status_code=400, detail="empty embedding")
    if not req.candidates:
        return IdentifyResponse(matches=[])

    q = np.asarray(req.embedding, dtype="float32")
    matches: list[IdentifyMatch] = []
    for cand in req.candidates:
        c = np.asarray(cand.embedding, dtype="float32")
        if c.shape != q.shape:
            # Skip mismatched-dim embeddings (e.g. legacy 256-d enrollments)
            matches.append(IdentifyMatch(speaker_id=cand.speaker_id, similarity=0.0, matched=False))
            continue
        sim = _cos(q, c)
        matches.append(IdentifyMatch(
            speaker_id=cand.speaker_id,
            similarity=sim,
            matched=sim >= req.threshold,
        ))

    matches.sort(key=lambda m: m.similarity, reverse=True)
    best = matches[0] if matches else None
    return IdentifyResponse(matches=matches, best_match=best)


@app.on_event("startup")
def _warm():
    # Eagerly load ECAPA so the first /embed isn't a 30s cold start.
    try:
        _load_ecapa()
        logger.info("ECAPA warmed on %s", DEVICE)
    except Exception as exc:  # noqa: BLE001
        logger.error("ECAPA warm failed: %s", exc)
    if HF_TOKEN:
        _load_diarizer()  # warm pyannote if we can


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8889, reload=False)
