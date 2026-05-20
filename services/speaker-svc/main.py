"""speaker-svc — FastAPI wrapper around pyannote wespeaker + diarization.

Endpoints
---------
GET  /health                — liveness, model status, GPU info
POST /embed                 — extract a 256-d wespeaker embedding from a clip
POST /diarize               — diarize an audio file (Pyannote if token, else whole-clip fallback)
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
EMBEDDER_DEVICE = os.getenv("SPEAKER_EMBEDDER_DEVICE", "cpu").strip().lower() or "cpu"
DIARIZER_DEVICE = os.getenv("PYANNOTE_DIARIZER_DEVICE", "cpu").strip().lower() or "cpu"
EAGER_LOAD_EMBEDDER = os.getenv("SPEAKER_EAGER_LOAD_EMBEDDER", "false").lower() in ("1", "true", "yes")
EAGER_LOAD_DIARIZER = os.getenv("SPEAKER_EAGER_LOAD_DIARIZER", "false").lower() in ("1", "true", "yes")
TARGET_SR = 16000  # wespeaker + Pyannote both expect 16 kHz mono
MIN_SECONDS = float(os.getenv("MIN_AUDIO_SECONDS", "0.5"))
MAX_SECONDS = float(os.getenv("MAX_AUDIO_SECONDS", "1800"))  # 30 min
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "").strip() or None
# Task #79 v2: call torch.cuda.empty_cache() after every Nth /diarize. Set to
# 0 to disable. Default 1 (every request) — measure throughput impact and
# bump to 5/10 if material. The caching allocator legitimately holds memory
# across calls; periodic clearing reduces peak reservation in a long-running
# service and is the primary leak-mitigation knob.
EMPTY_CACHE_EVERY = int(os.getenv("SPEAKER_EMPTY_CACHE_EVERY", "1"))
EMBEDDING_MODEL = "pyannote/wespeaker-voxceleb-resnet34-LM"
DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
DIARIZATION_FALLBACK_MODEL = "pyannote/speaker-diarization-3.1"

app = FastAPI(title="speaker-svc", version="0.1.0")

_embedder = None
_diarizer = None
_diarizer_backend: Optional[str] = None
_diarizer_load_error: Optional[str] = None
# Task #79 v2: /diarize request counter, used to gate periodic empty_cache().
_diarize_request_count: int = 0


def _load_embedder():
    """Lazy-load the wespeaker embedder. Cached after first call."""
    global _embedder
    if _embedder is not None:
        return _embedder
    if not HF_TOKEN:
        raise RuntimeError(f"HUGGINGFACE_TOKEN not set; {EMBEDDING_MODEL} unavailable")
    from pyannote.audio import Inference, Model
    logger.info("Loading %s on %s", EMBEDDING_MODEL, EMBEDDER_DEVICE)
    try:
        embedding_model = Model.from_pretrained(EMBEDDING_MODEL, token=HF_TOKEN)
    except TypeError:
        embedding_model = Model.from_pretrained(EMBEDDING_MODEL, use_auth_token=HF_TOKEN)
    _embedder = Inference(embedding_model, window="whole")
    if EMBEDDER_DEVICE == "cuda":
        _embedder = _embedder.to(torch.device("cuda"))
        torch.cuda.empty_cache()
    return _embedder


def _load_diarizer():
    """Lazy-load Pyannote community-1 with a 3.1 fallback."""
    global _diarizer, _diarizer_backend, _diarizer_load_error
    if _diarizer is not None:
        return _diarizer
    if not HF_TOKEN:
        _diarizer_load_error = f"HUGGINGFACE_TOKEN not set; {DIARIZATION_MODEL} unavailable"
        return None
    try:
        from pyannote.audio import Pipeline
        loaded_model = DIARIZATION_MODEL
        logger.info("Loading %s on %s", DIARIZATION_MODEL, DIARIZER_DEVICE)
        try:
            try:
                pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=HF_TOKEN)
            except TypeError:
                pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=HF_TOKEN)
            _diarizer_backend = "pyannote-community-1"
        except Exception as community_exc:  # noqa: BLE001
            logger.warning(
                "%s load failed, falling back to %s: %s",
                DIARIZATION_MODEL,
                DIARIZATION_FALLBACK_MODEL,
                community_exc,
            )
            loaded_model = DIARIZATION_FALLBACK_MODEL
            try:
                pipeline = Pipeline.from_pretrained(DIARIZATION_FALLBACK_MODEL, token=HF_TOKEN)
            except TypeError:
                pipeline = Pipeline.from_pretrained(DIARIZATION_FALLBACK_MODEL, use_auth_token=HF_TOKEN)
            _diarizer_backend = "pyannote-3.1"
        if DIARIZER_DEVICE == "cuda":
            pipeline.to(torch.device("cuda"))
            torch.cuda.empty_cache()
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
        logger.info("Loaded %s as %s", loaded_model, _diarizer_backend)
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
    embedder = _load_embedder()
    with torch.no_grad():
        signal = torch.from_numpy(wav).unsqueeze(0)
        emb = embedder({"waveform": signal, "sample_rate": TARGET_SR})
    emb = np.asarray(emb, dtype="float32").flatten()
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
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
    embedder_loaded: bool
    diarizer_available: bool
    diarizer_error: Optional[str] = None
    embedding_dim: int = 256
    embedder_device: str = EMBEDDER_DEVICE
    diarizer_device: str = DIARIZER_DEVICE


class EmbedResponse(BaseModel):
    embedding: list[float]
    embedding_dim: int
    duration_seconds: float
    model: str = EMBEDDING_MODEL


class DiarizeSegment(BaseModel):
    start: float
    end: float
    speaker: str  # e.g. "SPEAKER_00"
    embedding: Optional[list[float]] = None  # wespeaker embedding for the segment


class DiarizeResponse(BaseModel):
    segments: list[DiarizeSegment]
    num_speakers: int
    backend: str  # "pyannote-community-1", "pyannote-3.1", or "ecapa-cluster-fallback"
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
    diarizer_available = HF_TOKEN is not None
    return HealthResponse(
        status="ok",
        device=DEVICE,
        cuda_available=torch.cuda.is_available(),
        gpu_name=gpu_name,
        embedder_loaded=_embedder is not None,
        diarizer_available=diarizer_available,
        diarizer_error=_diarizer_load_error,
        embedding_dim=256,
        embedder_device=EMBEDDER_DEVICE,
        diarizer_device=DIARIZER_DEVICE,
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed(
    audio: Optional[UploadFile] = File(default=None),
    audio_path: Optional[str] = Form(default=None),
):
    """Embed a single short clip (typically 3-30s) into a 256-d wespeaker vector."""
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
    """Diarize. Uses Pyannote community-1 if HUGGINGFACE_TOKEN is set; otherwise
    falls back to single-speaker pseudo-diarization (one segment for
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
        # Graceful degradation — one segment, one wespeaker embedding for the
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

    # Task #79 v2: per-request clustering threshold overrides are no longer
    # supported. Calling pipeline.instantiate() per request appears to retain
    # the previous parameter graph in pyannote 3.1/4.x and contributes to the
    # VRAM accumulation that necessitates the 8h restart workaround. The
    # threshold is now fixed at startup via PYANNOTE_CLUSTERING_THRESHOLD env
    # var (default 0.72; midboy2 deploy sets 0.78). Callers who need a
    # different value must redeploy the service with the new env value.
    if clustering_threshold is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "per-request clustering_threshold override is no longer supported "
                "(task #79 v2: prevents pyannote VRAM accumulation). "
                "Set PYANNOTE_CLUSTERING_THRESHOLD env on the speaker-svc deploy."
            ),
        )

    diarize_kwargs: dict[str, int] = {}
    if num_speakers is not None:
        diarize_kwargs["num_speakers"] = int(num_speakers)
    else:
        if min_speakers is not None:
            diarize_kwargs["min_speakers"] = int(min_speakers)
        if max_speakers is not None:
            diarize_kwargs["max_speakers"] = int(max_speakers)
    logger.info(
        "/diarize duration=%.1fs hints=%s threshold=env-default",
        duration,
        diarize_kwargs or "auto",
    )
    # Task #79 v2: wrap the top-level pipeline call in torch.inference_mode().
    # Pyannote uses inference_mode() internally at the Inference.infer() layer
    # but the top-level Pipeline.__call__ in 3.1 does not — this is
    # belt-and-suspenders against any autograd state pyannote may build during
    # diarization (clustering, segmentation post-processing). inference_mode()
    # is strictly more memory-efficient than no_grad() since it also disables
    # view tracking.
    with torch.inference_mode():
        result = pipeline(
            {"waveform": waveform, "sample_rate": TARGET_SR},
            **diarize_kwargs,
        )
    if hasattr(result, "exclusive_speaker_diarization"):
        diarization = result.exclusive_speaker_diarization
    elif hasattr(result, "speaker_diarization"):
        diarization = result.speaker_diarization
    else:
        diarization = result

    segments: list[DiarizeSegment] = []
    speakers_seen: set[str] = set()

    def add_segment(turn, speaker: str) -> None:
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

    try:
        for turn, speaker in diarization:
            add_segment(turn, speaker)
    except (TypeError, ValueError):
        segments = []
        speakers_seen = set()
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            add_segment(turn, speaker)

    response = DiarizeResponse(
        segments=segments,
        num_speakers=len(speakers_seen),
        backend=_diarizer_backend or "pyannote-3.1",
        duration_seconds=duration,
    )

    # Task #79 v2: periodic empty_cache() to release the caching allocator's
    # held memory back to the device. Pyannote 3.1 + autograd state legitimately
    # grows the allocator's reserved pool across calls; explicitly clearing
    # after every Nth request keeps the reserved pool from monotonically
    # growing in a long-running service. Set SPEAKER_EMPTY_CACHE_EVERY=0 to
    # disable, or raise N if throughput is impacted >10%.
    global _diarize_request_count
    _diarize_request_count += 1
    if (
        EMPTY_CACHE_EVERY > 0
        and torch.cuda.is_available()
        and _diarize_request_count % EMPTY_CACHE_EVERY == 0
    ):
        torch.cuda.empty_cache()

    return response


@app.post("/identify", response_model=IdentifyResponse)
def identify(req: IdentifyRequest):
    """Score a query embedding against candidate enrolled-speaker embeddings.

    Pure cosine similarity. Caller is responsible for picking the right
    threshold for their environment (we default to 0.55 which is a reasonable
    starting point for conference-room mics)."""
    if not req.embedding:
        raise HTTPException(status_code=400, detail="empty embedding")
    if not req.candidates:
        return IdentifyResponse(matches=[])

    q = np.asarray(req.embedding, dtype="float32")
    matches: list[IdentifyMatch] = []
    for cand in req.candidates:
        c = np.asarray(cand.embedding, dtype="float32")
        if c.shape != q.shape:
            # Skip mismatched-dim embeddings (e.g. legacy ECAPA enrollments)
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
    if EAGER_LOAD_EMBEDDER:
        try:
            _load_embedder()
            logger.info("wespeaker warmed on %s", EMBEDDER_DEVICE)
        except Exception as exc:  # noqa: BLE001
            logger.error("wespeaker warm failed: %s", exc)
    else:
        logger.info("wespeaker warm skipped; lazy load enabled")
    if HF_TOKEN and EAGER_LOAD_DIARIZER:
        _load_diarizer()  # warm pyannote if explicitly requested
    elif HF_TOKEN:
        logger.info("pyannote warm skipped; lazy load enabled")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8889, reload=False)
