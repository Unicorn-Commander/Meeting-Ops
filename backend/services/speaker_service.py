"""Speaker service — embedding (de)serialization, centroid math, and the
core identify_speakers(session) entry point used by the recording lifecycle.

Embeddings are stored as raw little-endian float32 bytes alongside an
embedding_dim INT, so the same row layout works for ECAPA 192-d today and
ECAPA-XL 256-d / WavLM 768-d tomorrow.

This module is sync (not async) on purpose — it's called from a
BackgroundTasks worker on the request thread, so we use the provider's
sync-friendly httpx call patterns. The provider exposes async methods, so
we run them via asyncio.run when called from sync context.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from database.models import (
    RecordingSession,
    SpeakerProfile,
    SpeakerSessionLink,
    SpeakerVoiceSample,
)

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = os.getenv("SPEAKER_EMBEDDING_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
DEFAULT_IDENTIFY_THRESHOLD = float(os.getenv("SPEAKER_IDENTIFY_THRESHOLD", "0.55"))
STORE_SPEAKER_AUDIO = os.getenv("STORE_SPEAKER_AUDIO", "false").lower() in ("1", "true", "yes")


# ---------- (de)serialization ----------


def encode_embedding(vec: list[float]) -> bytes:
    """Pack a python list[float] into raw little-endian float32 bytes."""
    return np.asarray(vec, dtype="<f4").tobytes()


def decode_embedding(buf: bytes, dim: Optional[int] = None) -> list[float]:
    """Unpack stored bytes back into list[float]. dim is informational only —
    we always use the byte length to derive the actual count."""
    arr = np.frombuffer(buf, dtype="<f4")
    if dim is not None and arr.shape[0] != dim:
        logger.warning("decode_embedding: stored dim=%d does not match column dim=%d", arr.shape[0], dim)
    return arr.tolist()


def update_centroid(
    old_centroid: Optional[list[float]],
    old_count: int,
    new_embedding: list[float],
) -> list[float]:
    """Online running-mean centroid. L2 normalization keeps cosine sim
    well-behaved for ECAPA."""
    new = np.asarray(new_embedding, dtype="float32")
    if old_centroid is None or old_count <= 0:
        avg = new
    else:
        old = np.asarray(old_centroid, dtype="float32")
        avg = (old * old_count + new) / (old_count + 1)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg.tolist()


# ---------- DB helpers ----------


def list_org_speakers(db: Session, organization_id: int) -> list[SpeakerProfile]:
    return (
        db.query(SpeakerProfile)
        .filter(SpeakerProfile.organization_id == organization_id)
        .order_by(SpeakerProfile.display_name.asc())
        .all()
    )


def get_speaker(db: Session, organization_id: int, speaker_id: int) -> Optional[SpeakerProfile]:
    return (
        db.query(SpeakerProfile)
        .filter(
            SpeakerProfile.organization_id == organization_id,
            SpeakerProfile.id == speaker_id,
        )
        .first()
    )


def candidates_for_org(db: Session, organization_id: int) -> list[dict]:
    """Build the candidate list expected by speaker-svc /identify — only
    returns speakers that already have at least one enrollment."""
    rows = (
        db.query(SpeakerProfile)
        .filter(
            SpeakerProfile.organization_id == organization_id,
            SpeakerProfile.centroid_embedding.isnot(None),
            SpeakerProfile.embedding_dim.isnot(None),
        )
        .all()
    )
    out: list[dict] = []
    for row in rows:
        try:
            out.append({
                "speaker_id": row.id,
                "embedding": decode_embedding(row.centroid_embedding, row.embedding_dim),
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping speaker %d (decode failed): %s", row.id, exc)
    return out


def add_voice_sample(
    db: Session,
    speaker: SpeakerProfile,
    embedding: list[float],
    *,
    source: str,
    embedding_model: str,
    audio_path: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    source_session_id: Optional[int] = None,
    source_segment_idx: Optional[int] = None,
) -> SpeakerVoiceSample:
    """Persist a sample, refresh the centroid, and bump sample_count."""
    if not embedding:
        raise ValueError("empty embedding")
    sample = SpeakerVoiceSample(
        speaker_id=speaker.id,
        organization_id=speaker.organization_id,
        source=source,
        source_session_id=source_session_id,
        source_segment_idx=source_segment_idx,
        embedding=encode_embedding(embedding),
        embedding_dim=len(embedding),
        embedding_model=embedding_model,
        audio_path=audio_path if STORE_SPEAKER_AUDIO else None,
        duration_seconds=duration_seconds,
    )
    db.add(sample)

    old_centroid = (
        decode_embedding(speaker.centroid_embedding, speaker.embedding_dim)
        if speaker.centroid_embedding else None
    )
    new_centroid = update_centroid(old_centroid, speaker.sample_count, embedding)
    speaker.centroid_embedding = encode_embedding(new_centroid)
    speaker.embedding_dim = len(new_centroid)
    speaker.embedding_model = embedding_model
    speaker.sample_count = (speaker.sample_count or 0) + 1

    # Annotate sample with cosine sim to the new centroid for diagnostics
    try:
        n = np.asarray(new_centroid, dtype="float32")
        e = np.asarray(embedding, dtype="float32")
        denom = np.linalg.norm(n) * np.linalg.norm(e)
        sample.similarity_to_centroid = float(np.dot(n, e) / denom) if denom > 0 else None
    except Exception:  # noqa: BLE001
        pass

    db.flush()
    return sample


# ---------- the lifecycle hook ----------


def _run_async(coro):
    """Bridge a coroutine into a sync caller.

    Three call sites:
      1. BackgroundTasks worker / Alembic / scripts — no running loop, asyncio.run works
      2. FastAPI request handler — a loop is already running on this thread
         (`asyncio.run` raises RuntimeError). Run the coroutine on a fresh
         loop in a worker thread so we don't try to nest loops.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # We're inside a running event loop — offload to a worker thread.
        import concurrent.futures
        def _runner():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_runner).result()


def _segments_from_session(session: RecordingSession) -> list[dict]:
    """Return the list of diarized segments for a session, if any.
    Each segment: {"start": float, "end": float, "speaker": str}."""
    if session.transcript_diarized and isinstance(session.transcript_diarized, dict):
        return session.transcript_diarized.get("segments", []) or []
    return []


def identify_speakers(
    session: RecordingSession,
    db: Session,
    *,
    threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
) -> dict:
    """Post-completion hook: walk the diarized segments, embed the longest
    sample of each unique label, and try to match it against enrolled speakers.

    Writes a `speaker_session_link` row per unique raw_label and rewrites the
    `transcript_diarized.segments[*].speaker` field with the matched display
    name when confidence is above threshold. Falls through silently if the
    session has no diarized output, no audio file, or the speaker-svc is
    unreachable — this is a non-blocking enrichment step."""
    summary = {
        "session_id": session.id,
        "linked": 0,
        "unmatched": 0,
        "skipped_reason": None,
        "backend": None,
    }

    segments = _segments_from_session(session)
    if not segments:
        summary["skipped_reason"] = "no_diarized_segments"
        return summary

    # Audio file is only required if we need to re-extract embeddings
    # ourselves; if the diarizer already wrote embeddings into each
    # segment we can identify without ever touching the wav file.
    has_inline_embeddings = any(seg.get("embedding") for seg in segments)
    audio_path = session.audio_file
    if not has_inline_embeddings and (not audio_path or not os.path.exists(audio_path)):
        summary["skipped_reason"] = f"audio_missing:{audio_path}"
        logger.info("identify_speakers skipped: %s", summary["skipped_reason"])
        return summary

    # Group segments by raw label, keep the longest one per label for embedding
    by_label: dict[str, dict] = {}
    for idx, seg in enumerate(segments):
        label = (seg.get("speaker") or "").strip()
        if not label:
            continue
        duration = float(seg.get("end", 0)) - float(seg.get("start", 0))
        if duration < 0.5:
            continue
        existing = by_label.get(label)
        if existing is None or duration > existing["duration"]:
            by_label[label] = {"idx": idx, "duration": duration, "segment": seg, "embedding": seg.get("embedding")}

    if not by_label:
        summary["skipped_reason"] = "no_usable_segments"
        return summary

    # Resolve provider lazily so tests can monkeypatch it
    from services.providers.registry import get_provider_registry
    registry = get_provider_registry(db)
    provider = registry.get_speaker_svc(session.organization_id)

    # If the provider already returned per-segment embeddings, use them. If
    # not, embed each chosen segment via /embed (the slower path).
    candidates = candidates_for_org(db, session.organization_id)
    label_to_speaker: dict[str, dict] = {}

    for label, item in by_label.items():
        emb = item.get("embedding")
        if not emb:
            # The diarize() call didn't include embeddings (e.g. fallback
            # backend). Skip — we'd need to re-extract the segment audio,
            # which the speaker-svc /embed endpoint doesn't currently do
            # from a substring of an audio_path.
            label_to_speaker[label] = {"matched": False, "reason": "no_embedding"}
            continue

        if not candidates:
            label_to_speaker[label] = {"matched": False, "reason": "no_enrolled_speakers"}
            continue

        try:
            result = _run_async(provider.identify(emb, candidates, threshold))
        except Exception as exc:  # noqa: BLE001
            logger.warning("identify(label=%s) failed: %s", label, exc)
            label_to_speaker[label] = {"matched": False, "reason": str(exc)}
            continue

        best = result.get("best_match") if result else None
        if best and best.get("matched"):
            label_to_speaker[label] = {
                "matched": True,
                "speaker_id": best["speaker_id"],
                "similarity": best["similarity"],
            }
        else:
            label_to_speaker[label] = {"matched": False, "reason": "below_threshold"}

    # Persist links + rewrite diarized segments
    links_by_label: dict[str, SpeakerSessionLink] = {}
    for label, decision in label_to_speaker.items():
        link = (
            db.query(SpeakerSessionLink)
            .filter(
                SpeakerSessionLink.session_id == session.id,
                SpeakerSessionLink.raw_label == label,
            )
            .first()
        )
        if link is None:
            link = SpeakerSessionLink(
                session_id=session.id,
                organization_id=session.organization_id,
                raw_label=label,
            )
            db.add(link)
        if link.confirmed:
            # Manual override stays in place; we never overwrite a confirmed link.
            links_by_label[label] = link
            continue
        if decision.get("matched"):
            link.speaker_id = decision["speaker_id"]
            link.similarity = decision["similarity"]
            link.source = "auto"
            summary["linked"] += 1
        else:
            link.speaker_id = None
            link.similarity = None
            summary["unmatched"] += 1
        links_by_label[label] = link

    db.flush()

    # Build a label -> display_name map and rewrite the diarized transcript.
    name_map: dict[str, str] = {}
    for label, link in links_by_label.items():
        if link.speaker_id is None:
            continue
        sp = get_speaker(db, session.organization_id, link.speaker_id)
        if sp is not None:
            name_map[label] = sp.display_name

    if name_map:
        diarized = session.transcript_diarized or {}
        if isinstance(diarized, dict):
            new_segments = []
            for seg in diarized.get("segments", []):
                label = seg.get("speaker", "")
                if label in name_map:
                    new_seg = {**seg, "speaker": name_map[label], "raw_label": label}
                else:
                    new_seg = seg
                new_segments.append(new_seg)
            diarized["segments"] = new_segments
            # Refresh top-level speakers list if present
            if "speakers" in diarized:
                seen, ordered = set(), []
                for seg in new_segments:
                    s = seg.get("speaker", "Unknown")
                    if s not in seen:
                        seen.add(s)
                        ordered.append(s)
                diarized["speakers"] = ordered
            session.transcript_diarized = diarized
            # SQLAlchemy can't detect in-place mutations on JSON columns;
            # explicitly flag the column as dirty so the change persists.
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(session, "transcript_diarized")

    db.commit()
    backend_hint = (segments[0] or {}).get("backend") if segments else None
    summary["backend"] = backend_hint
    logger.info("identify_speakers: %s", summary)
    return summary
