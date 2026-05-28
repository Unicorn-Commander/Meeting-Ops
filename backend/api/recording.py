"""Always-on browser recording API.

The browser owns mic capture and VAD. The backend stays responsible for
Parakeet STT, diarization, final summaries, and session persistence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from auth.dependencies import get_current_organization, get_current_user
from auth.internal import InternalServiceCaller, get_internal_or_user
from auth.models import Organization, User
from auth.organization import ActiveOrganization, resolve_active_organization
from auth.tier import gate_feature_for_caller
from database.database import get_db
from database.models import AudioFile, RecordingSession, Transcription
from services.summary_slices import (
    MAX_SLICES_PER_SESSION,
    ROOM_SLICE_TRIGGER_WORDS,
    generate_slice,
    get_slices,
    maybe_auto_trigger_slice,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recordings", tags=["always-on-recording"])

# Brigade integration Phase 2 — read-side router for the in-page 3D
# graph viewer on SessionDetails. Lives alongside the always-on router
# in this module but uses no prefix so the URL shape matches the
# /api/sessions/{session_id}/... pattern the frontend already uses for
# TTS + speaker-links + other per-session reads. Registered as a second
# router in main.py via _load_router(..., router_attr='brigade_graph_router').
brigade_graph_router = APIRouter(tags=["brigade-graph"])

# In-process TTL cache for /api/sessions/{id}/brigade-graph responses.
# The graph doesn't change often after a meeting completes (only on
# reprocess re-runs which are minutes-scale events) so a 30s cache
# absorbs the page-refresh / browser-tab-flip pattern without going
# stale on real updates. Per-session key; the cache is process-local
# (single uvicorn worker today; we'll move to redis when we add
# replicas — see also _maybe_persist_slice_after_chunk for the same
# single-worker assumption).
_BRIGADE_GRAPH_CACHE_TTL_SECONDS = 30
_brigade_graph_cache: dict[str, tuple[float, dict[str, Any]]] = {}

RECORDINGS_DIR = Path(os.getenv("RECORDINGS_DIR", "/app/recordings"))
ALWAYS_ON_DIR = RECORDINGS_DIR / "always_on"


class StartAlwaysOnRequest(BaseModel):
    org_id: Optional[int] = None
    source_label: Optional[str] = Field(default=None, max_length=200)


class ServerSummaryRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=250000)
    model_id: Optional[str] = None
    session_id: Optional[str] = None


class SummarizeSliceRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=250000)
    previous_summary: Optional[str] = Field(default=None, max_length=20000)
    session_id: Optional[str] = None


class ClientTextChunkRequest(BaseModel):
    """Transcript text produced by the browser-side Parakeet model.

    The browser ran STT locally (zero server GPU cost), so we don't need
    the audio bytes — we just persist the text in the same
    transcript_diarized + processing_metadata shape the audio path produces,
    and tag the provenance so analytics can attribute tier later.
    """
    text: str = Field(min_length=1, max_length=20000)
    duration_seconds: float = Field(default=0.0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0)
    provenance: str = Field(default="client-parakeet-0.6b-int8", max_length=120)
    skip_diarization: bool = Field(default=False)


class ParseFilenameRequest(BaseModel):
    """Request body for POST /api/recordings/parse-filename."""

    filename: str = Field(min_length=0, max_length=2048)


class ParseFilenameResponse(BaseModel):
    """Result of parsing a filename for meeting metadata."""

    title: Optional[str] = None
    meeting_date: Optional[str] = None  # ISO YYYY-MM-DD
    meeting_time: Optional[str] = None  # HH:MM:SS (24h)
    source: Optional[str] = None        # notes | downloads | generic | None
    confidence: float = 0.0
    raw_filename: str = ""


@router.post(
    "/parse-filename",
    response_model=ParseFilenameResponse,
    summary="Parse a filename into meeting metadata (title / date / time / source)",
)
async def parse_filename_endpoint(
    request: ParseFilenameRequest,
    current_user: User = Depends(get_current_user),
):
    """Expose the shared filename parser to clients.

    Used by the single-file upload preview ("This looks like a meeting
    from 2024-11-05 with Nate Ellison — use these values?") and the
    upcoming /import page that ingests Aaron's 526-file Voice Memos
    archive. Pure compute, no I/O, no DB write — auth-gated so we don't
    accidentally turn it into an open-internet regex utility.
    """
    from utils.filename_parser import parse_filename

    parsed = parse_filename(request.filename or "")
    return ParseFilenameResponse(
        title=parsed.title,
        meeting_date=parsed.meeting_date.isoformat() if parsed.meeting_date else None,
        meeting_time=parsed.meeting_time.isoformat() if parsed.meeting_time else None,
        source=parsed.source,
        confidence=parsed.confidence,
        raw_filename=parsed.raw_filename,
    )




def _org_diarization_off(db: Session, organization_id: int) -> bool:
    """Return True when the org has promoted diarization "off" as its default
    provider via PipelineStatusPicker "Save as default". Every chunk in that
    org then skips diarization unless the caller passes skip_diarization
    explicitly. Safe-fails to False on any DB or import error so a transient
    glitch never *adds* diarization the user didn't ask for, but also doesn't
    cause chunk upload to 500."""
    try:
        from database.models import OrgProviderSettings

        row = (
            db.query(OrgProviderSettings)
            .filter(
                OrgProviderSettings.organization_id == organization_id,
                OrgProviderSettings.service_kind == "diarization",
            )
            .first()
        )
        if not row:
            return False
        return (row.provider_name or "").strip().lower() == "off"
    except Exception:
        return False


SLICE_SYSTEM_PROMPT = (
    "You are a live meeting summarizer. The user is currently in a meeting and "
    "wants a running summary that updates as new conversation happens. Given the "
    "transcript so far and the previous summary, produce an updated summary that:\n"
    "- Leads with what is NEW since the previous summary\n"
    "- Preserves key context, decisions, and action items from before\n"
    "- Stays under 200 words\n"
    "- Reads naturally, like notes a thoughtful attendee would take\n\n"
    "Do not list speakers verbatim. Do not repeat the previous summary word-for-word."
)


def _slice_user_prompt(transcript: str, previous_summary: Optional[str]) -> str:
    tail = transcript[-60000:]
    if previous_summary and previous_summary.strip():
        return (
            "Previous running summary:\n"
            f"{previous_summary.strip()}\n\n"
            "New transcript since that summary (most recent at the bottom):\n"
            f"{tail}"
        )
    return (
        "Transcript so far (most recent at the bottom):\n"
        f"{tail}"
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _session_dir(org_slug: str, session_id: str) -> Path:
    return ALWAYS_ON_DIR / org_slug / session_id


def _find_session(db: Session, session_id: str, org_id: int) -> Optional[RecordingSession]:
    query = db.query(RecordingSession).filter(RecordingSession.organization_id == org_id)
    session = query.filter(RecordingSession.session_id == session_id).first()
    if session:
        return session
    try:
        return query.filter(RecordingSession.id == int(session_id)).first()
    except (TypeError, ValueError):
        return None


def _find_session_by_id(db: Session, session_id: str) -> Optional[RecordingSession]:
    """Org-agnostic session lookup. Internal-service callers (room_recorder)
    own a single session and own the trust to write to it regardless of org;
    they cannot present an org context the way a user can, so we look up by
    session id alone and derive the org from the row itself."""
    query = db.query(RecordingSession)
    session = query.filter(RecordingSession.session_id == session_id).first()
    if session:
        return session
    try:
        return query.filter(RecordingSession.id == int(session_id)).first()
    except (TypeError, ValueError):
        return None


def _synthetic_org_for_internal_caller(
    db: Session, session: RecordingSession
) -> ActiveOrganization:
    """Build an ``ActiveOrganization`` from the session row so the rest of
    the chunks endpoint body (which expects a populated ``active_org``)
    stays unchanged for internal-service callers. The role is set to
    ``"system"`` so any future permission check that inspects it can
    distinguish loopback writes from real user roles."""
    org = (
        db.query(Organization)
        .filter(Organization.id == session.organization_id)
        .first()
    )
    if not org:
        # Session has an org_id that doesn't resolve — treat as a corrupt
        # row rather than a 200, and don't fall through into the user
        # branch.
        raise HTTPException(
            status_code=500,
            detail="Session organization could not be resolved for internal write.",
        )
    return ActiveOrganization(organization=org, membership=None, role="system")


def _session_payload(session: RecordingSession) -> dict[str, Any]:
    return {
        "id": session.session_id or str(session.id),
        "pk": session.id,
        "title": session.title or session.name or f"Always-on Session {session.id}",
        "name": session.name or session.title or f"Always-on Session {session.id}",
        "status": session.status,
        "mode": getattr(session, "mode", "upload"),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "duration": float(session.duration or 0),
        "transcript_simple": session.transcript_simple or "",
        "transcript_diarized": session.transcript_diarized or {"segments": []},
        "final_summary": session.final_summary,
        "ai_insights": session.ai_insights,
        "summary": session.summary,
    }


def _safe_ext(upload: UploadFile) -> str:
    name = Path(upload.filename or "").name
    ext = Path(name).suffix.lower()
    if ext in {".wav", ".webm", ".ogg", ".mp3", ".m4a", ".aac", ".flac"}:
        return ext
    ctype = (upload.content_type or "").lower()
    if "wav" in ctype:
        return ".wav"
    if "webm" in ctype:
        return ".webm"
    return ".wav"


async def _extract_to_wav(source_path: Path, wav_path: Path) -> None:
    if source_path.suffix.lower() == ".wav":
        if source_path != wav_path:
            shutil.copy2(source_path, wav_path)
        return

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
        detail = stderr.decode(errors="ignore")[-500:] if stderr else ""
        raise RuntimeError(f"Audio extraction failed. {detail}")


def _offset_segments(
    result: dict[str, Any],
    *,
    offset_seconds: float,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for seg in result.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start") or 0) + offset_seconds
        end = float(seg.get("end") or 0) + offset_seconds
        segments.append({
            "text": text,
            "speaker": seg.get("speaker"),
            "start": start,
            "end": end,
            "confidence": float(seg.get("confidence") or 0.95),
        })
    return segments


def _speaker_for_segment(
    seg: dict[str, Any], diar_segments: list[dict[str, Any]]
) -> tuple[Optional[str], Optional[list[float]]]:
    """Pick the diarization turn that overlaps `seg` the most.

    Returns (speaker_label, embedding). The embedding is the per-turn
    voiceprint from speaker-svc (return_embeddings=true) — preserving it
    onto the transcript segment is what lets identify_speakers match the
    speaker to enrolled voices downstream.
    """
    start = float(seg.get("start") or 0)
    end = float(seg.get("end") or 0)
    best_label: Optional[str] = None
    best_overlap = 0.0
    best_embedding: Optional[list[float]] = None
    for diar in diar_segments:
        diar_start = float(diar.get("start") or 0)
        diar_end = float(diar.get("end") or 0)
        overlap = max(0.0, min(end, diar_end) - max(start, diar_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = diar.get("speaker")
            best_embedding = diar.get("embedding")
    return best_label, best_embedding


async def _diarize_chunk(
    db: Session,
    session: RecordingSession,
    wav_path: Path,
    segments: list[dict[str, Any]],
    *,
    offset_seconds: float,
) -> None:
    if not segments:
        return
    try:
        from services.providers.registry import get_provider_registry

        registry = get_provider_registry(db)
        diar_provider = registry.get_diarization(session.organization_id)
        raw_diar = await diar_provider.diarize(str(wav_path))
        diar_segments = []
        for diar in raw_diar or []:
            diar_segments.append({
                **diar,
                "start": float(diar.get("start") or 0) + offset_seconds,
                "end": float(diar.get("end") or 0) + offset_seconds,
            })
        for seg in segments:
            label, embedding = _speaker_for_segment(seg, diar_segments)
            if label:
                seg["speaker"] = label
                # Preserve the per-segment embedding so identify_speakers
                # can match against enrolled voices. The chunked always-on
                # pipeline runs diarization per chunk, so the embedding
                # already lines up with this segment's local time range.
                if embedding:
                    seg["embedding"] = embedding
    except Exception as exc:  # noqa: BLE001
        logger.warning("Always-on diarization failed for session %s: %s", session.id, exc)


def _append_transcription(
    db: Session,
    session: RecordingSession,
    segments: list[dict[str, Any]],
    result: dict[str, Any],
    *,
    offset_seconds: float,
) -> None:
    if not segments:
        return

    diarized = session.transcript_diarized if isinstance(session.transcript_diarized, dict) else {}
    existing_segments = list(diarized.get("segments") or [])
    existing_segments.extend(segments)
    existing_segments.sort(key=lambda s: float(s.get("start") or 0))

    speakers: list[str] = []
    for seg in existing_segments:
        speaker = seg.get("speaker")
        if speaker and speaker not in speakers:
            speakers.append(speaker)

    diarized.update({
        "segments": existing_segments,
        "speakers": speakers,
        "model": result.get("model"),
        "language": result.get("language", "en"),
        "updated_at": _now().isoformat(),
    })
    session.transcript_diarized = diarized
    flag_modified(session, "transcript_diarized")

    session.transcript_simple = " ".join(
        seg.get("text", "").strip()
        for seg in existing_segments
        if seg.get("text")
    ).strip()
    session.transcript = json.dumps(diarized)
    session.duration = max(
        float(session.duration or 0),
        max((float(seg.get("end") or 0) for seg in existing_segments), default=0.0),
    )
    session.updated_at = _now()

    for seg in segments:
        db.add(Transcription(
            session_id=session.id,
            text=seg["text"],
            speaker=seg.get("speaker"),
            start_time=float(seg.get("start") or 0),
            end_time=float(seg.get("end") or 0),
            confidence=float(seg.get("confidence") or 0.95),
        ))

    metadata = dict(session.processing_metadata or {})
    words = result.get("words") or []
    if words:
        existing_words = list(metadata.get("word_timestamps") or [])
        for word in words:
            existing_words.append({
                "word": word.get("word") or word.get("text") or "",
                "start": float(word.get("start") or 0) + offset_seconds,
                "end": float(word.get("end") or 0) + offset_seconds,
                "confidence": float(word.get("confidence") or 0.99),
            })
        metadata["word_timestamps"] = existing_words
        metadata["has_word_timestamps"] = True
    metadata.update({
        "word_count": len((session.transcript_simple or "").split()),
        "transcription_model": result.get("model", "parakeet"),
        "transcription_language": result.get("language", "en"),
        "last_chunk_received_at": _now().isoformat(),
    })
    session.processing_metadata = metadata
    flag_modified(session, "processing_metadata")


def _record_audio_file(
    db: Session,
    session: RecordingSession,
    current_user: Optional[User],
    active_org: ActiveOrganization,
    path: Path,
    upload: UploadFile,
) -> None:
    try:
        db.add(AudioFile(
            file_id=str(uuid.uuid4()),
            session_id=session.session_id or str(session.id),
            user_id=current_user.id if current_user is not None else None,
            filename=Path(upload.filename or path.name).name,
            file_path=str(path),
            file_size=path.stat().st_size,
            file_format=path.suffix.lstrip("."),
            mime_type=upload.content_type or "audio/wav",
            organization_id=active_org.organization.id,
        ))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not create AudioFile row for always-on chunk: %s", exc)


async def _broadcast_segments(session: RecordingSession, segments: list[dict[str, Any]]) -> None:
    if not segments:
        return
    try:
        from api.websocket_transcription import broadcast_transcription_update

        session_key = session.session_id or str(session.id)
        for segment in segments:
            await broadcast_transcription_update(session_key, segment)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not broadcast always-on transcription segments: %s", exc)


async def _maybe_persist_slice_after_chunk(
    db: Session, session: RecordingSession
) -> None:
    """Server-roll a summary slice when the transcript grows past the
    trigger threshold.

    Fires for ALL session types as of 2026-05-21 (browser always-on
    used to roll its own slices with Qwen 3 0.6B in the browser, which
    couldn't sustain incremental summarization with previous-summary
    context). On success it persists the slice and broadcasts on the
    same websocket the transcript stream uses, so multiple viewers see
    the new slice without polling delay.

    Failures are logged inside the trigger helper and never raised — a
    transient LLM outage must not block chunk ingest.
    """
    slice_obj: Optional[dict[str, Any]] = None
    try:
        slice_obj = await maybe_auto_trigger_slice(db, session)
    except Exception:  # noqa: BLE001 — defensive belt-and-suspenders
        logger.exception(
            "maybe_auto_trigger_slice raised for session=%s", session.id
        )
        return
    if not slice_obj:
        return
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to commit auto-triggered slice for session=%s", session.id
        )
        return
    await _broadcast_slice(session, slice_obj)


async def _broadcast_slice(
    session: RecordingSession, slice_obj: dict[str, Any]
) -> None:
    """Push a new slice to any websocket subscribers on this session.

    Reuses the existing transcript-stream broadcast channel — same key,
    different envelope. Clients distinguish slices by the
    ``type: "summary_slice"`` discriminator in the payload. If the
    broadcast helper isn't available (legacy bundle), we silently skip;
    the GET polling fallback in ``RoomLiveSummary`` will catch up on the
    next tick.
    """
    try:
        from api.websocket_transcription import broadcast_transcription_update

        session_key = session.session_id or str(session.id)
        envelope = {
            "type": "summary_slice",
            "slice": slice_obj,
        }
        await broadcast_transcription_update(session_key, envelope)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "Slice broadcast skipped for session=%s: %s", session.id, exc
        )


@router.post("/start-always-on")
async def start_always_on(
    request: StartAlwaysOnRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if request.org_id is not None and request.org_id != active_org.organization.id:
        raise HTTPException(status_code=403, detail="org_id does not match the active organization.")

    started_at = _now()
    title = f"Always-on {started_at.strftime('%Y-%m-%d %H:%M')}"
    session = RecordingSession(
        session_id=str(uuid.uuid4()),
        name=title,
        title=title,
        description="Browser always-on recording",
        meeting_type="always_on",
        mode="always_on",
        created_at=started_at,
        started_at=started_at,
        status="recording",
        duration=0.0,
        user_id=current_user.id,
        organization_id=active_org.organization.id,
        source_type="browser_always_on",
        processing_metadata={
            "source_label": request.source_label,
            "created_by": "browser_always_on",
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    _session_dir(active_org.organization.slug, session.session_id or str(session.id)).mkdir(parents=True, exist_ok=True)
    return _session_payload(session)


@router.post("/sessions/{session_id}/chunks")
async def upload_always_on_chunk(
    request: Request,
    session_id: str,
    chunk: UploadFile = File(...),
    elapsed_seconds: Optional[float] = Form(None),
    skip_diarization: bool = Form(False),
    caller: Any = Depends(get_internal_or_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    gate_feature_for_caller(caller, "canonical_reprocess")  # v3.0.0 tier gate: paid-tier server processing
    # Dual-auth: real user OR room_recorder loopback. Internal callers
    # write to a session they already own by ID (the recorder spawned it
    # via the rooms API). We resolve org context from the session row
    # itself so the rest of this endpoint body doesn't have to branch.
    if isinstance(caller, InternalServiceCaller):
        session = _find_session_by_id(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_org = _synthetic_org_for_internal_caller(db, session)
        current_user = None  # type: ignore[assignment]
        logger.info(
            "[internal] chunks(audio) POST session_id=%s provenance=%s",
            session_id,
            caller.provenance or "unknown",
        )
    else:
        if not getattr(caller, "is_active", False):
            raise HTTPException(status_code=403, detail="Inactive user")
        current_user = caller
        active_org = resolve_active_organization(db, request, current_user)
        session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")
    if session.status not in {"recording", "processing", "paused"}:
        raise HTTPException(status_code=409, detail=f"Session is {session.status}.")

    body = await chunk.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty audio chunk.")

    root = _session_dir(active_org.organization.slug, session.session_id or str(session.id)) / "chunks"
    root.mkdir(parents=True, exist_ok=True)
    chunk_id = str(uuid.uuid4())
    source_path = root / f"{chunk_id}{_safe_ext(chunk)}"
    source_path.write_bytes(body)
    wav_path = root / f"{chunk_id}.wav"

    try:
        await _extract_to_wav(source_path, wav_path)
        from api.uploads import _transcribe_audio

        offset = (
            max(0.0, float(elapsed_seconds))
            if elapsed_seconds is not None
            else float(session.duration or 0)
        )
        result = await _transcribe_audio(
            wav_path,
            session.organization_id,
            db,
            provider_override="parakeet",
            language="en",
        )
        segments = _offset_segments(result, offset_seconds=offset)
        effective_skip = skip_diarization or _org_diarization_off(db, session.organization_id)
        if not effective_skip:
            await _diarize_chunk(db, session, wav_path, segments, offset_seconds=offset)
        _append_transcription(db, session, segments, result, offset_seconds=offset)
        _record_audio_file(db, session, current_user, active_org, wav_path, chunk)
        session.status = "recording"
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        logger.exception("Always-on chunk processing failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await _broadcast_segments(session, segments)

    # Roll a server-side summary slice when the transcript has grown
    # past the trigger threshold. Fires for room sessions AND browser
    # always-on as of 2026-05-21 — see services.summary_slices for the
    # rationale. Failures are logged and swallowed inside the helper —
    # never block chunk ingest on an LLM hiccup.
    await _maybe_persist_slice_after_chunk(db, session)

    return {
        "session": _session_payload(session),
        "segments": segments,
        "text": " ".join(seg["text"] for seg in segments),
        "chunk_id": chunk_id,
    }


@router.post("/sessions/{session_id}/chunks-text")
async def append_client_text_chunk(
    request: Request,
    session_id: str,
    payload: ClientTextChunkRequest,
    caller: Any = Depends(get_internal_or_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist a transcript chunk that was produced by the browser STT.

    Mirrors the side-effects of `/chunks` minus the audio path:
      - appends a single segment to `transcript_diarized.segments`
      - updates `transcript_simple`, `duration`, `updated_at`
      - bumps `processing_metadata.word_count`, `last_chunk_received_at`,
        `transcription_model`, and `last_chunk_provenance`
      - inserts a Transcription row so per-segment queries keep working
      - broadcasts on the same websocket so the live transcript stream stays
        single-channel for consumers

    Provenance lives in JSONB; no schema migration required.
    """
    gate_feature_for_caller(caller, "canonical_reprocess")  # v3.0.0 tier gate: paid-tier server processing
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty transcript text.")

    # Dual-auth: real user OR room_recorder loopback. Internal callers
    # write to a session they already own by ID; org context is derived
    # from the session row itself instead of the request headers.
    if isinstance(caller, InternalServiceCaller):
        session = _find_session_by_id(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_org = _synthetic_org_for_internal_caller(db, session)
        current_user = None  # type: ignore[assignment]
        logger.info(
            "[internal] chunks-text POST session_id=%s provenance=%s payload_provenance=%s",
            session_id,
            caller.provenance or "unknown",
            payload.provenance,
        )
    else:
        if not getattr(caller, "is_active", False):
            raise HTTPException(status_code=403, detail="Inactive user")
        current_user = caller
        active_org = resolve_active_organization(db, request, current_user)
        session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")
    if session.status not in {"recording", "processing", "paused"}:
        raise HTTPException(status_code=409, detail=f"Session is {session.status}.")

    offset = max(0.0, float(payload.elapsed_seconds or 0.0))
    duration = max(0.0, float(payload.duration_seconds or 0.0))
    end = offset + duration if duration > 0 else offset

    segment = {
        "text": text,
        "speaker": None,
        "start": float(offset),
        "end": float(end),
        "confidence": 0.93,  # placeholder; browser model is INT8 + no per-word probs
        "provenance": payload.provenance,
    }

    result_stub: dict[str, Any] = {
        "model": payload.provenance,
        "language": "en",
        "segments": [segment],
        "words": [],
    }

    try:
        _append_transcription(db, session, [segment], result_stub, offset_seconds=0.0)

        # _append_transcription stamps transcription_model with the value
        # it sees in result_stub, which is already the provenance string.
        # We add an explicit provenance counter so analytics can show the
        # split per session without re-deriving from transcription_model.
        metadata = dict(session.processing_metadata or {})
        prov_counts = dict(metadata.get("chunk_provenance_counts") or {})
        prov_counts[payload.provenance] = int(prov_counts.get(payload.provenance, 0)) + 1
        metadata["chunk_provenance_counts"] = prov_counts
        metadata["last_chunk_provenance"] = payload.provenance
        effective_skip = payload.skip_diarization or _org_diarization_off(db, session.organization_id)
        if effective_skip:
            metadata["diarization_skipped"] = True
        session.processing_metadata = metadata
        flag_modified(session, "processing_metadata")

        session.status = "recording"
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Always-on client-text chunk failed for session %s", session_id
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await _broadcast_segments(session, [segment])

    # Same auto-slice hook as /chunks above — fires for room sessions
    # AND browser always-on as of 2026-05-21.
    await _maybe_persist_slice_after_chunk(db, session)

    total_words = len((session.transcript_simple or "").split())
    return {
        "ok": True,
        "session": _session_payload(session),
        "segment": segment,
        "total_words": total_words,
    }


@router.post("/sessions/{session_id}/finalize")
async def finalize_always_on_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    gate_feature_for_caller(current_user, "canonical_reprocess")  # v3.0.0 tier gate: paid-tier server processing
    session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")

    ended_at = _now()
    session.status = "processing"
    session.ended_at = ended_at
    started_at = _aware(session.started_at)
    if started_at:
        session.duration = max(float(session.duration or 0), (ended_at - started_at).total_seconds())
    db.commit()
    db.refresh(session)

    try:
        from api.uploads import _summarize_session

        await _summarize_session(db, session, template="standard")
        try:
            from api.ai_insights import _generate_ai_insights

            transcriptions = (
                db.query(Transcription)
                .filter(Transcription.session_id == session.id)
                .order_by(Transcription.start_time.asc())
                .all()
            )
            full_text = (session.transcript_simple or session.transcript or "").strip()
            insights = await _generate_ai_insights(
                full_text,
                transcriptions,
                session,
                db,
                session.organization_id,
            )
            session.ai_insights = insights.model_dump()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Always-on ai_insights generation failed for %s: %s", session.id, exc)

        session.status = "completed"
        session.updated_at = _now()
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        session = _find_session(db, session_id, active_org.organization.id)
        if session:
            session.status = "completed"
            session.summary = json.dumps({
                "executive": "Session finalized, but final summary generation failed.",
                "bullets": [str(exc)[:200]],
                "actions": [],
                "decisions": [],
            })
            session.updated_at = _now()
            db.commit()
            db.refresh(session)
        logger.exception("Always-on finalize failed for session %s", session_id)

    # Brigade Phase 1.5: write from live/browser-only sessions
    # (the reprocess path already fires this in _run_session_reprocess)
    logger.info("[brigade-1.5] live write fired session=%s", session.id)

    async def _fire_brigade_live_write(session_pk: int):
        try:
            from services.brigade_client import BrigadeClient
            from services.brigade_writer import write_meeting_to_brigade

            brigade = BrigadeClient()
            from database.database import SessionLocal

            db_async = SessionLocal()
            try:
                await write_meeting_to_brigade(
                    session_pk,
                    db_async,
                    client=brigade,
                    completion_mode="live",
                )
            finally:
                db_async.close()
        except Exception as e:
            logger.error(
                "[brigade-1.5] live write failed session=%s: %s",
                session_pk,
                e,
            )

    background_tasks.add_task(_fire_brigade_live_write, session.id)

    # Project-Ops task bridge on the live/browser-only finalize path
    # (the reprocess path fires its own call in _run_session_reprocess).
    # Independent fire-and-forget task so a PO outage never blocks finalize
    # and never interferes with the Brigade write above.
    async def _fire_projectops_live_write(session_pk: int):
        from database.database import SessionLocal

        db_po = SessionLocal()
        try:
            from services.projectops_writer import write_action_items_to_projectops

            await write_action_items_to_projectops(
                db=db_po, session_pk=session_pk, completion_mode="live"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[projectops] live write failed session=%s: %s",
                session_pk,
                e,
            )
        finally:
            db_po.close()

    background_tasks.add_task(_fire_projectops_live_write, session.id)

    return _session_payload(session)


@router.delete("/sessions/{session_id}")
async def discard_always_on_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Hard-delete an always-on session and everything it produced.

    Cascade order (server-side equivalent of the user clicking Discard):
      1. DB rows: Transcription + AudioFile + RecordingSession itself
      2. Disk: the per-session chunk directory under ALWAYS_ON_DIR (audio
         blobs + any extracted WAVs)
      3. Vector store: Qdrant points for this session_id
         (semantic_search.delete_session)

    Best-effort on the file/vector cleanup — a failure in either path
    shouldn't strand the DB row. We log and proceed. The DB delete is
    the canonical "session is gone" signal.

    Org-scoped: only sessions belonging to the caller's active org are
    deletable. Returns 404 for missing or cross-org session ids so we
    don't leak existence.
    """
    session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Lock to always-on mode so this endpoint can't be used to wipe
    # uploaded meetings or legacy server-recorded sessions — those have
    # their own delete flows that expect different cleanup paths.
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(
            status_code=409,
            detail="This endpoint only deletes always-on sessions.",
        )

    canonical_id = session.session_id or str(session.id)
    org_slug = active_org.organization.slug
    chunk_dir = _session_dir(org_slug, canonical_id)

    # 1. DB rows. Transcription is keyed on the integer pk; AudioFile is
    #    keyed on the string session_id (legacy column convention).
    try:
        db.query(Transcription).filter(Transcription.session_id == session.id).delete()
        db.query(AudioFile).filter(
            AudioFile.session_id == canonical_id,
            AudioFile.organization_id == active_org.organization.id,
        ).delete()
        db.delete(session)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete always-on session rows for %s", session_id)
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc

    # 2. Disk cleanup — best-effort, errors logged but not surfaced.
    try:
        if chunk_dir.exists():
            shutil.rmtree(chunk_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chunk-dir cleanup failed for %s: %s", canonical_id, exc)

    # 3. Vector store — best-effort. semantic_search is import-on-use to
    #    avoid pulling qdrant into the recording hot path on cold start.
    try:
        from services.semantic_search_service import semantic_search

        semantic_search.delete_session(canonical_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Qdrant cleanup failed for %s: %s", canonical_id, exc)

    return {
        "deleted": True,
        "session_id": canonical_id,
    }


@router.post("/summarize")
async def summarize_with_server_llm(
    request: ServerSummaryRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    gate_feature_for_caller(current_user, "qwen36_summary")  # v3.0.0 tier gate: paid-tier server processing
    transcript = request.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required.")

    try:
        from services.providers.registry import get_provider_registry

        registry = get_provider_registry(db)
        llm = registry.get_llm(active_org.organization.id, task="quality")
        system_prompt = (
            "You summarize live meeting transcripts for Meeting-Ops. "
            "Only use facts in the transcript. Keep the summary concise, "
            "actionable, and update-friendly."
        )
        user_prompt = (
            "Create a rolling meeting summary with these sections: "
            "Current gist, decisions, action items, open questions. "
            "Use short paragraphs and preserve important names.\n\n"
            f"Transcript:\n{transcript[:60000]}"
        )
        text = await llm.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1400,
            temperature=0.3,
            extra_params={
                "top_p": 0.9,
                "presence_penalty": 0.4,
            },
        )
    except Exception as exc:
        logger.exception("Server-side always-on summary failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "summary": text,
        "model": getattr(llm, "model", None),
        "provider": llm.__class__.__name__,
    }


@router.post("/summarize-slice")
async def summarize_slice(
    request: SummarizeSliceRequest,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Stream a single Granola-style live summary slice via SSE.

    Used by the always-on live summary feature when the user has picked
    'Server' as their in-browser AI model (or when WebGPU is unavailable).
    """
    gate_feature_for_caller(current_user, "qwen36_summary")  # v3.0.0 tier gate: paid-tier server processing
    transcript = request.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required.")

    try:
        from services.providers.registry import get_provider_registry

        registry = get_provider_registry(db)
        llm = registry.get_llm(active_org.organization.id, task="quality")
    except Exception as exc:
        logger.exception("Failed to resolve LLM provider for live slice summary")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    user_prompt = _slice_user_prompt(transcript, request.previous_summary)
    session_id = request.session_id or ""

    async def event_stream():
        full = ""
        chunks = 0
        try:
            async for token in llm.chat_stream(
                system_prompt=SLICE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=600,
                temperature=0.3,
            ):
                if not token:
                    continue
                full += token
                chunks += 1
                yield f"data: {json.dumps({'token': token})}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Live slice summary stream failed (session=%s)", session_id)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        yield (
            "data: "
            + json.dumps({
                "done": True,
                "summary": full,
                "chunks": chunks,
                "model": getattr(llm, "model", None),
                "provider": llm.__class__.__name__,
                "session_id": session_id or None,
            })
            + "\n\n"
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# === Server-rolled summary slices (room recordings) =====================
#
# For browser always-on sessions the slice stack lives in the user's
# browser. For conference-room sessions there's no privileged user, so we
# persist the slices on the server (in ``processing_metadata.summary_slices``)
# and expose GET + POST so any viewer can see them live and reviewers can
# read them after the meeting ends.


def _serialize_slice(slice_obj: dict[str, Any]) -> dict[str, Any]:
    """Public shape for the GET/POST responses. We pass the JSONB through
    largely as-is — every field already has a documented contract in
    services.summary_slices. ``id`` is always a string for the frontend.
    """
    return {
        "id": str(slice_obj.get("id") or ""),
        "text": slice_obj.get("text") or "",
        "word_count": int(slice_obj.get("word_count") or 0),
        "word_range_start": int(slice_obj.get("word_range_start") or 0),
        "word_range_end": int(slice_obj.get("word_range_end") or 0),
        "model": slice_obj.get("model"),
        "provider": slice_obj.get("provider"),
        "created_at": slice_obj.get("created_at"),
        "triggered_by": slice_obj.get("triggered_by") or "unknown",
    }


@router.get("/sessions/{session_id}/summary-slices")
async def list_summary_slices(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the persisted slice stack for this session.

    Org-scoped — cross-org reads get a 404 indistinguishable from
    "no such session". Empty array for legacy sessions that never
    auto-triggered. The list is sorted oldest-first so the client can
    render the same chronological stack the auto-triggered + manual
    paths both append onto.
    """
    session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    slices = [_serialize_slice(s) for s in get_slices(session)]
    return {
        "session_id": session.session_id or str(session.id),
        "is_room_session": session.room_id is not None,
        "slices": slices,
        "trigger_words": ROOM_SLICE_TRIGGER_WORDS,
        "max_per_session": MAX_SLICES_PER_SESSION,
    }


@router.post("/sessions/{session_id}/summary-slices")
async def create_summary_slice(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate + persist a slice now ("Summarize now" button).

    Org-scoped via ``_find_session``. Works for any session, room or not —
    if the calling user wants the server to roll a slice on their behalf
    for a browser always-on session they can do that, it just won't
    auto-trigger going forward.

    Returns 422 when there isn't enough new transcript since the previous
    slice; 503 when the LLM provider fails.
    """
    session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    transcript = (session.transcript_simple or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=422,
            detail="Session has no transcript yet; nothing to summarize.",
        )

    try:
        slice_obj = await generate_slice(
            db,
            session,
            triggered_by="manual",
            organization_id=active_org.organization.id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Manual slice generation failed for session=%s", session.id
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not slice_obj:
        raise HTTPException(
            status_code=422,
            detail="No new transcript since the last slice.",
        )

    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Failed to persist manual slice for session=%s", session.id
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await _broadcast_slice(session, slice_obj)

    return {
        "slice": _serialize_slice(slice_obj),
        "session_id": session.session_id or str(session.id),
    }


# === Full session audio capture + server-side reprocess ==================
#
# The /chunks-text path (above) only delivers BROWSER-produced transcript
# text. That's great for low-latency live transcript + zero server STT
# cost, but it leaves the server unable to:
#   * run diarization (needs the audio)
#   * fingerprint-match enrolled speakers (needs per-segment embeddings)
#   * produce a high-quality final summary (browser STT is INT8 + Parakeet
#     0.6B, server-side is fp16 + Parakeet 1.1B)
#
# These endpoints let the browser stream the full session audio to disk in
# parallel with the existing chunks-text path, then re-run the upload
# pipeline against the reassembled WAV when the session ends. The browser
# /chunks-text path stays unchanged — it provides the live transcript
# the user sees during the meeting; the server-side reprocess overwrites
# the transcript + diarization + summary with higher-quality output on
# finalize.
#
# Privacy mode skips audio upload entirely (the browser never POSTs to
# /audio-chunks), so local-only sessions retain the same "nothing leaves
# the device" guarantee they already had.


def _audio_chunks_dir(org_slug: str, session_id: str) -> Path:
    """Where browser-streamed audio chunks land before reassembly."""
    return _session_dir(org_slug, session_id) / "full_audio"


@router.post("/sessions/{session_id}/audio-chunks")
async def append_audio_chunk(
    request: Request,
    session_id: str,
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    caller: Any = Depends(get_internal_or_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Receive a chunk of session audio for server-side reprocess.

    Each chunk is a continuous WebM/Opus (or whatever the browser's
    MediaRecorder produces) blob ~30s long. Stored under
    ``ALWAYS_ON_DIR/<org-slug>/<session-id>/full_audio/<idx>.<ext>``.

    Idempotent — re-uploading the same ``chunk_index`` overwrites. That's
    on purpose: the frontend uses exponential-backoff retry with capped
    retries, and a network hiccup that ACKed late shouldn't double-write
    the audio. The per-index file naming also keeps ffmpeg's concat
    step deterministic (no surprise interleaving when retries lag).

    Org-scoped via the same ``_find_session`` / ``_find_session_by_id``
    pattern ``chunks-text`` uses. Internal-service callers (room_recorder
    loopback) can also POST here — the room recorder doesn't currently
    use this path, but plumbing dual-auth in from day one means we don't
    have to retrofit when it grows audio export.
    """
    gate_feature_for_caller(caller, "canonical_reprocess")  # v3.0.0 tier gate: paid-tier server processing
    if isinstance(caller, InternalServiceCaller):
        session = _find_session_by_id(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_org = _synthetic_org_for_internal_caller(db, session)
        logger.info(
            "[internal] audio-chunks POST session_id=%s idx=%s provenance=%s",
            session_id,
            chunk_index,
            caller.provenance or "unknown",
        )
    else:
        if not getattr(caller, "is_active", False):
            raise HTTPException(status_code=403, detail="Inactive user")
        current_user = caller
        active_org = resolve_active_organization(db, request, current_user)
        session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")
    # We accept chunks while recording OR after stop — the frontend may
    # ship a few trailing chunks just after stop while finalize-audio
    # waits. We refuse on completed/cancelled.
    if session.status in {"completed", "cancelled", "error"}:
        raise HTTPException(status_code=409, detail=f"Session is {session.status}.")

    if chunk_index < 0:
        raise HTTPException(status_code=400, detail="chunk_index must be >= 0.")

    body = await chunk.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty audio chunk.")

    ext = _safe_ext(chunk)
    out_dir = _audio_chunks_dir(
        active_org.organization.slug, session.session_id or str(session.id)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    # Zero-padded index so a simple sort matches arrival order. 6 digits
    # is enough for 12+ hours of 30s chunks per session.
    out_path = out_dir / f"{chunk_index:06d}{ext}"
    out_path.write_bytes(body)

    metadata = dict(session.processing_metadata or {})
    audio_state = dict(metadata.get("full_audio") or {})
    chunks_state = dict(audio_state.get("chunks") or {})
    chunks_state[str(chunk_index)] = {
        "filename": out_path.name,
        "size": out_path.stat().st_size,
        "content_type": chunk.content_type or "audio/webm",
        "received_at": _now().isoformat(),
    }
    audio_state["chunks"] = chunks_state
    audio_state["last_chunk_at"] = _now().isoformat()
    metadata["full_audio"] = audio_state
    session.processing_metadata = metadata
    flag_modified(session, "processing_metadata")
    db.commit()

    return {
        "ok": True,
        "session_id": session.session_id or str(session.id),
        "chunk_index": chunk_index,
        "size": out_path.stat().st_size,
        "chunks_received": len(chunks_state),
    }


async def _reassemble_full_audio(
    chunks_dir: Path, target_wav: Path
) -> tuple[float, str]:
    """Concatenate all chunk files under ``chunks_dir`` into a single WAV.

    Uses ffmpeg's concat demuxer for the streams that share a codec
    (WebM/Opus from the same MediaRecorder instance) and falls back to a
    decode+re-encode pass when ffmpeg's concat refuses. Returns the
    output WAV duration in seconds + the source codec name.

    Why decode-then-mux: WebM containers from MediaRecorder don't always
    share segment boundaries, so a pure concat can leave un-decodable
    metadata at chunk boundaries. The decode pass normalizes to
    16 kHz mono PCM WAV, which is what every downstream STT provider
    we ship wants anyway.
    """
    # Sort by filename — naming is zero-padded chunk_index so lexicographic
    # order matches arrival order.
    chunks = sorted(p for p in chunks_dir.iterdir() if p.is_file())
    if not chunks:
        raise RuntimeError("No audio chunks to reassemble.")

    concat_list = chunks_dir / "concat.txt"
    # ffmpeg concat demuxer file format: one `file '<path>'` per line.
    # Paths are quoted; we use absolute paths so the demuxer doesn't need
    # to resolve relative to the concat.txt directory.
    concat_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in chunks) + "\n",
        encoding="utf-8",
    )

    # Single ffmpeg call: concat -> decode -> re-encode as 16 kHz mono PCM.
    # -safe 0 lets us point at absolute paths in the list file.
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(target_wav),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not target_wav.exists() or target_wav.stat().st_size == 0:
        detail = stderr.decode(errors="ignore")[-800:] if stderr else ""
        raise RuntimeError(f"Audio reassembly failed. ffmpeg stderr: {detail}")

    # Duration probe (ffprobe is part of the ffmpeg package shipped in our
    # backend container). We don't fail the reassembly on a missing probe
    # — duration is informational.
    duration_sec = 0.0
    try:
        probe = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(target_wav),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await probe.communicate()
        if out:
            duration_sec = float(out.decode(errors="ignore").strip() or 0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ffprobe failed (non-fatal): %s", exc)

    # Source codec hint — we use the first chunk's extension since they
    # should all share a codec from the same MediaRecorder instance.
    source_codec = chunks[0].suffix.lstrip(".") or "webm"
    return duration_sec, source_codec


async def _run_session_reprocess(session_pk: int) -> None:
    """Background task that re-runs the full upload pipeline against the
    reassembled session audio.

    Stages, mirroring api.uploads.run_upload_pipeline:
      1. Reassemble audio chunks into ``recordings/sessions/<id>/audio.wav``
      2. Parakeet 1.1B fp16 transcription via ``_transcribe_audio``
      3. Diarization with ``return_embeddings=true`` (org's configured
         provider; speaker-svc on bigboy by default)
      4. ``identify_speakers`` against the org's enrolled SpeakerProfile
         centroids (writes ``SpeakerSessionLink.source='auto'``)
      5. Final summary via ``_summarize_session`` (Qwen 3.6 35B-A3B-Vision
         on the org's configured LLM)

    Status is tracked in ``processing_metadata['reprocess_status']``:
        - in_progress  : pipeline running
        - complete     : success; transcript_simple/diarized + summary updated
        - failed       : error stored under ``reprocess_error``

    The original /chunks-text live transcript is overwritten on success;
    that's the whole point of reprocess. On failure we keep the live
    transcript so the user never loses data.
    """
    # We need a fresh DB session for the background task — the request
    # session is closed by FastAPI before the background runs.
    from database.database import SessionLocal

    def _set_status(state: str, **extra: Any) -> None:
        """Update reprocess_status + extras under processing_metadata.full_audio.

        Done in a fresh DB session each time so concurrent reads (the UI
        polling SessionDetails) see the latest state. We keep the helper
        sync because each call is bounded by a single small write.
        """
        db = SessionLocal()
        try:
            row = (
                db.query(RecordingSession)
                .filter(RecordingSession.id == session_pk)
                .first()
            )
            if row is None:
                return
            metadata = dict(row.processing_metadata or {})
            audio_state = dict(metadata.get("full_audio") or {})
            audio_state.update({"status": state, "updated_at": _now().isoformat()})
            audio_state.update(extra)
            metadata["full_audio"] = audio_state
            metadata["reprocess_status"] = state
            row.processing_metadata = metadata
            flag_modified(row, "processing_metadata")
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Reprocess status update failed for session_pk=%s state=%s",
                session_pk,
                state,
            )
        finally:
            db.close()

    _set_status("in_progress", started_at=_now().isoformat())

    db = SessionLocal()
    try:
        session = (
            db.query(RecordingSession)
            .filter(RecordingSession.id == session_pk)
            .first()
        )
        if session is None:
            return
        org = (
            db.query(Organization)
            .filter(Organization.id == session.organization_id)
            .first()
        )
        if org is None:
            raise RuntimeError("Session organization not found.")

        canonical_id = session.session_id or str(session.id)
        chunks_dir = _audio_chunks_dir(org.slug, canonical_id)
        # Park the reassembled WAV next to the chunk dir so cleanup is local
        # to the per-session directory.
        target_wav = _session_dir(org.slug, canonical_id) / "session.wav"

        duration_sec, source_codec = await _reassemble_full_audio(chunks_dir, target_wav)
        # Point session.audio_file at the reassembled WAV so identify_speakers
        # has an absolute audio path to fall back on if it ever needs to
        # re-extract embeddings (we already plumb per-segment embeddings,
        # but the helper still checks audio_file.exists()).
        session.audio_file = str(target_wav)
        # Register the reassembled audio in audio_files so the existing
        # /download/audio endpoint can serve it.
        try:
            db.add(AudioFile(
                file_id=str(uuid.uuid4()),
                session_id=canonical_id,
                user_id=session.user_id,
                filename=target_wav.name,
                file_path=str(target_wav),
                file_size=target_wav.stat().st_size,
                file_format="wav",
                mime_type="audio/wav",
                organization_id=session.organization_id,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not register reassembled AudioFile for session=%s: %s",
                session.id,
                exc,
            )
        db.commit()

        # Push the canonical reassembled audio to Garage (durable copy).
        # Best-effort + additive: the local session.wav stays the working
        # copy; a Garage hiccup just leaves the durability columns NULL.
        try:
            from services.session_media import persist_session_audio
            persist_session_audio(db, session, local_path=str(target_wav))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Garage persist failed for session=%s: %s", session.id, exc)

        # Stage 2 — Parakeet 1.1B fp16 transcription. Reuses the same
        # helper the upload pipeline uses; the org's STT provider defaults
        # to Parakeet 1.1B at meet-parakeet-svc:8881.
        from api.uploads import _transcribe_audio

        result = await _transcribe_audio(
            target_wav,
            session.organization_id,
            db,
            language="en",
        )
        # Overwrite transcript_simple + transcript_diarized with the
        # server-quality result. The browser STT path's segments were
        # appended into transcript_diarized.segments as the meeting
        # happened; we wipe them so the segments list is clean.
        segments = [
            {
                "text": (seg.get("text") or "").strip(),
                "speaker": seg.get("speaker"),
                "start": float(seg.get("start") or 0),
                "end": float(seg.get("end") or 0),
                "confidence": float(seg.get("confidence") or 0.95),
            }
            for seg in (result.get("segments") or [])
            if (seg.get("text") or "").strip()
        ]
        db.query(Transcription).filter(Transcription.session_id == session.id).delete()
        db.commit()

        diarized = {
            "segments": segments,
            "speakers": [],
            "model": result.get("model", "parakeet-tdt-1.1b"),
            "language": result.get("language", "en"),
            "updated_at": _now().isoformat(),
        }
        session.transcript_diarized = diarized
        flag_modified(session, "transcript_diarized")
        session.transcript_simple = " ".join(
            seg["text"] for seg in segments if seg.get("text")
        ).strip()
        session.transcript = json.dumps(diarized)
        if duration_sec > 0:
            session.duration = max(float(session.duration or 0), duration_sec)
        for seg in segments:
            db.add(Transcription(
                session_id=session.id,
                text=seg["text"],
                speaker=seg.get("speaker"),
                start_time=float(seg.get("start") or 0),
                end_time=float(seg.get("end") or 0),
                confidence=float(seg.get("confidence") or 0.95),
            ))
        db.commit()

        # Stage 3 — Diarization with per-segment embeddings. Use the
        # provider's diarize() (speaker-svc supports return_embeddings=true).
        try:
            from services.providers.registry import get_provider_registry

            registry = get_provider_registry(db)
            diar_provider = registry.get_diarization(session.organization_id)
            diar_segments = await diar_provider.diarize(str(target_wav))
            if diar_segments:
                # Overlay diarization labels + embeddings onto the
                # transcription segments using the same overlap rule as
                # _diarize_chunk does for live chunks. Embeddings are
                # preserved so identify_speakers() can match enrolled
                # voices without re-embedding from audio.
                for seg in segments:
                    label, embedding = _speaker_for_segment(seg, diar_segments)
                    if label:
                        seg["speaker"] = label
                    if embedding:
                        seg["embedding"] = embedding
                seen: list[str] = []
                for seg in segments:
                    spk = seg.get("speaker")
                    if spk and spk not in seen:
                        seen.append(spk)
                diarized["segments"] = segments
                diarized["speakers"] = seen
                session.transcript_diarized = diarized
                flag_modified(session, "transcript_diarized")
                db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reprocess diarization failed for session=%s: %s",
                session.id,
                exc,
            )

        # Stage 4 — Identify enrolled speakers. Best-effort — a transient
        # speaker-svc outage shouldn't fail the whole reprocess.
        try:
            from services.speaker_service import identify_speakers

            await asyncio.to_thread(identify_speakers, session, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reprocess identify_speakers failed for session=%s: %s",
                session.id,
                exc,
            )

        # Stage 5 — Final summary. Overwrites session.summary +
        # session.final_summary with the server-quality version that
        # supersedes the browser-rolled live summary slices.
        try:
            from api.uploads import _summarize_session

            await _summarize_session(db, session, template="standard")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reprocess summarize failed for session=%s: %s",
                session.id,
                exc,
            )

        # Pre-warm ai_insights so the side-panel doesn't trigger a fresh
        # LLM call on first view of the reprocessed session.
        try:
            from api.ai_insights import _generate_ai_insights

            transcriptions = (
                db.query(Transcription)
                .filter(Transcription.session_id == session.id)
                .order_by(Transcription.start_time.asc())
                .all()
            )
            full_text = (session.transcript_simple or "").strip()
            if full_text:
                insights = await _generate_ai_insights(
                    full_text,
                    transcriptions,
                    session,
                    db,
                    session.organization_id,
                )
                session.ai_insights = insights.model_dump()
                db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reprocess ai_insights generation failed for session=%s: %s",
                session.id,
                exc,
            )

        # Stage 6 — Brigade graph write. Best-effort fire-and-forget per
        # docs/brigade-integration-design.md Phase 1: Meeting + Speakers
        # + ActionItems + Topics + Decisions land as :Meeting /
        # :Speaker / :ActionItem / :Topic / :Decision nodes plus the
        # corresponding HAS_* / ASSIGNED_TO / DECIDED_BY edges in
        # Brigade's FalkorDB store. Idempotent — re-running the
        # reprocess pipeline updates the same graph nodes via Brigade's
        # MERGE-based store_entity. Failures NEVER raise into this
        # pipeline; the writer logs + swallows on every error path. If
        # BRIGADE_API_KEY is unset the writer runs in log-only mode and
        # returns success without making HTTP calls (dev environments
        # without Brigade still complete reprocess cleanly).
        try:
            from services.brigade_writer import write_meeting_to_brigade

            await write_meeting_to_brigade(session.id, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reprocess brigade graph write failed for session=%s: %s",
                session.id,
                exc,
            )

        # Stage 7 — Project-Ops task bridge. Best-effort one-way write:
        # each AI-extracted action item becomes a Project-Ops task on the
        # per-org target project (resolved from the session->PO link, a
        # per-meeting override, or the org default). Idempotent via a
        # po_task_id stamp on action_items.raw_payload, so reprocess
        # re-runs don't duplicate. Same swallow-all posture as the Brigade
        # block above: failures NEVER raise into the reprocess pipeline,
        # and an unconfigured PO (PROJECTOPS_API_KEY unset) is a clean
        # no-op.
        try:
            from services.projectops_writer import write_action_items_to_projectops

            await write_action_items_to_projectops(
                db=db, session_pk=session.id, completion_mode="reprocess"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Project-Ops write swallowed error session=%s: %s",
                session.id,
                exc,
            )

        _set_status(
            "complete",
            completed_at=_now().isoformat(),
            audio_path=str(target_wav),
            audio_duration_seconds=duration_sec,
            source_codec=source_codec,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Reprocess pipeline failed for session_pk=%s", session_pk
        )
        _set_status(
            "failed",
            failed_at=_now().isoformat(),
            error=str(exc)[:500],
        )
    finally:
        db.close()


class FinalizeAudioVerification(BaseModel):
    """Optional verification payload Phase A.5 desktop clients POST
    alongside finalize-audio. When all three fields match what the
    server has on disk, we proceed with the reprocess as usual and the
    client wipes its IndexedDB mirror. Mismatch returns a delta so the
    client can backfill the missing chunks or fall back to /full-audio.
    """

    client_chunk_count: int = Field(..., ge=0)
    client_bytes_total: int = Field(..., ge=0)
    client_sha256: str = Field(..., min_length=64, max_length=64)


def _list_chunk_files(chunks_dir: Path) -> list[Path]:
    """All chunk files in arrival order (sorted by filename, which is
    the zero-padded chunk_index produced by audio-chunks). Excludes
    the ffmpeg concat list + any reassembled WAV that may sit next to
    the chunks during reprocess."""
    if not chunks_dir.exists():
        return []
    return sorted(
        p
        for p in chunks_dir.iterdir()
        if p.is_file() and not p.name.startswith("concat") and p.suffix != ".wav"
    )


def _chunk_seq_from_filename(path: Path) -> int | None:
    """The append_audio_chunk handler writes chunks as ``000123.webm``.
    Pull the integer prefix back out for the missing-chunks delta we
    return to the client on a mismatch."""
    try:
        return int(path.stem)
    except (TypeError, ValueError):
        return None


async def _sha256_of_chunk_files(paths: list[Path]) -> str:
    """SHA-256 of the concatenated raw chunk bytes, in arrival order.
    Matches what the browser client computes before POSTing the
    verification payload — the client concats blobs in order and
    digests once. Async-friendly via to_thread for the read+update
    loop (sizes are small per chunk but we don't want to block the
    event loop on dozens of file reads)."""
    import hashlib

    def _digest() -> str:
        hasher = hashlib.sha256()
        for p in paths:
            with p.open("rb") as f:
                # 1MB read buffer — plenty for ~256KB chunks; uses small
                # constant memory regardless of chunk count.
                while True:
                    block = f.read(1 << 20)
                    if not block:
                        break
                    hasher.update(block)
        return hasher.hexdigest()

    return await asyncio.to_thread(_digest)


@router.post("/sessions/{session_id}/finalize-audio")
async def finalize_audio(
    session_id: str,
    background_tasks: BackgroundTasks,
    verification: FinalizeAudioVerification | None = None,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark all audio chunks delivered and kick off the reprocess pipeline.

    Returns ``{ reprocessing_started: bool, status: 'complete'|'incomplete'|..., ... }``.

    Phase A.5 verification: when the request body includes
    ``client_chunk_count`` / ``client_bytes_total`` / ``client_sha256``
    we recompute the server-side SHA-256 + total bytes from the chunk
    files on disk and compare. On match we proceed with the reprocess
    (``status='complete'``) and the client is free to wipe its
    IndexedDB mirror. On mismatch we return ``status='incomplete'``
    plus the list of chunk seq numbers actually received and (if the
    client passed a count) the missing ones — the client can either
    backfill those specific chunks via the existing /audio-chunks
    endpoint or fall back to /full-audio for a bulletproof recovery.

    Idempotent: if a reprocess is already in flight (in_progress), the
    second call is a no-op and we return the current status. If the
    session has zero audio chunks (e.g. privacy mode never uploaded), we
    skip the reprocess and return ``reprocessing_started: false`` — the
    live transcript stays as the final transcript.

    Auth: user-only. Internal callers (room_recorder) don't currently
    use this path; if we ever ship browser audio capture from a non-user
    context we can flip this to dual-auth like /audio-chunks.
    """
    gate_feature_for_caller(current_user, "canonical_reprocess")  # v3.0.0 tier gate: paid-tier server processing
    session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")

    canonical_id = session.session_id or str(session.id)
    chunks_dir = _audio_chunks_dir(active_org.organization.slug, canonical_id)

    metadata = dict(session.processing_metadata or {})
    audio_state = dict(metadata.get("full_audio") or {})

    chunk_files = _list_chunk_files(chunks_dir)

    # No chunks delivered (privacy mode, or upload failed for every chunk).
    # Bail with a friendly response — the live transcript stays canonical.
    if not chunk_files:
        audio_state.update({
            "status": "skipped",
            "skipped_reason": "no_chunks_uploaded",
            "updated_at": _now().isoformat(),
        })
        metadata["full_audio"] = audio_state
        metadata.setdefault("reprocess_status", None)
        session.processing_metadata = metadata
        flag_modified(session, "processing_metadata")
        db.commit()
        return {
            "reprocessing_started": False,
            "reason": "no_chunks_uploaded",
            "session_id": canonical_id,
        }

    # If a reprocess is already running, just return current state.
    if audio_state.get("status") == "in_progress":
        return {
            "reprocessing_started": False,
            "reason": "already_in_progress",
            "session_id": canonical_id,
            "status": "in_progress",
        }

    # Phase A.5 verification path. We compute the server-side state
    # (chunk count, total bytes, SHA-256 of concatenated chunk bytes)
    # and compare to the client's claim. On mismatch we DO NOT queue
    # the reprocess — the client gets the delta and decides whether to
    # backfill or whole-file.
    server_chunk_seqs: list[int] = sorted(
        seq for p in chunk_files if (seq := _chunk_seq_from_filename(p)) is not None
    )
    server_bytes_total = sum(p.stat().st_size for p in chunk_files)
    if verification is not None:
        server_sha = await _sha256_of_chunk_files(chunk_files)
        match_count = verification.client_chunk_count == len(chunk_files)
        match_bytes = verification.client_bytes_total == server_bytes_total
        match_sha = verification.client_sha256.lower() == server_sha.lower()
        if not (match_count and match_bytes and match_sha):
            missing: list[int] = []
            if verification.client_chunk_count > 0:
                expected = set(range(verification.client_chunk_count))
                missing = sorted(expected - set(server_chunk_seqs))
            audio_state.update({
                "status": "incomplete",
                "verification": {
                    "matched": False,
                    "match_count": match_count,
                    "match_bytes": match_bytes,
                    "match_sha": match_sha,
                    "client_chunk_count": verification.client_chunk_count,
                    "client_bytes_total": verification.client_bytes_total,
                    "client_sha256": verification.client_sha256,
                    "server_chunk_count": len(chunk_files),
                    "server_bytes_total": server_bytes_total,
                    "server_sha256": server_sha,
                    "verified_at": _now().isoformat(),
                },
                "updated_at": _now().isoformat(),
            })
            metadata["full_audio"] = audio_state
            session.processing_metadata = metadata
            flag_modified(session, "processing_metadata")
            db.commit()
            return {
                "reprocessing_started": False,
                "status": "incomplete",
                "session_id": canonical_id,
                "server_bytes": server_bytes_total,
                "server_chunks": server_chunk_seqs,
                "missing_chunks": missing,
                "expected_chunks": verification.client_chunk_count,
                "server_sha256": server_sha,
            }
        # Match — fall through to the queue path and stamp the
        # verification record so the audit trail is preserved.
        audio_state["verification"] = {
            "matched": True,
            "client_chunk_count": verification.client_chunk_count,
            "client_bytes_total": verification.client_bytes_total,
            "client_sha256": verification.client_sha256,
            "server_chunk_count": len(chunk_files),
            "server_bytes_total": server_bytes_total,
            "server_sha256": server_sha,
            "verified_at": _now().isoformat(),
        }

    audio_state.update({
        "status": "queued",
        "queued_at": _now().isoformat(),
        "finalize_chunks_received": len(audio_state.get("chunks") or {}),
    })
    metadata["full_audio"] = audio_state
    metadata["reprocess_status"] = "queued"
    session.processing_metadata = metadata
    flag_modified(session, "processing_metadata")
    db.commit()

    # Background task — fire-and-forget. The frontend polls
    # GET /api/simple/recording-sessions/{id} and reads
    # metadata.reprocess_status to display progress.
    session_pk = session.id
    background_tasks.add_task(_run_session_reprocess, session_pk)

    return {
        "reprocessing_started": True,
        "status": "complete",
        "session_id": canonical_id,
        "job_id": str(uuid.uuid4()),  # informational; status lives on the session row
    }


@router.post("/sessions/{session_id}/full-audio")
async def post_full_audio(
    request: Request,
    session_id: str,
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    caller: Any = Depends(get_internal_or_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Whole-file recovery upload. Replaces any existing reassembled
    chunk state for the session with a single client-assembled blob,
    then triggers the same reprocess pipeline /finalize-audio runs.

    Use case: chunked upload landed with gaps the server couldn't
    repair via per-chunk backfill, or the client's IndexedDB mirror
    holds bytes the server never saw (browser crashed before the last
    few chunks could upload). The desktop frontend computes a fresh
    SHA-256 from the IDB mirror, hits /finalize-audio for verification,
    and on mismatch falls back to this endpoint for guaranteed
    recovery.

    Wire shape mirrors /audio-chunks: multipart/form-data with a single
    file field. We label the blob ``000000.<ext>`` (zero-padded so the
    concat step still sees it as "first chunk") and clear the existing
    chunks dir before writing, so a single full-audio call is a clean
    state reset.

    Auth: dual-auth like /audio-chunks — internal services (room
    recorder loopback) can also POST here even though we don't ship
    that path today. Mirroring the chunks endpoint's auth means a
    future internal-only crash recovery path doesn't need an auth
    retrofit.
    """
    gate_feature_for_caller(caller, "canonical_reprocess")  # v3.0.0 tier gate: paid-tier server processing
    if isinstance(caller, InternalServiceCaller):
        session = _find_session_by_id(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_org = _synthetic_org_for_internal_caller(db, session)
        logger.info(
            "[internal] full-audio POST session_id=%s provenance=%s",
            session_id,
            caller.provenance or "unknown",
        )
    else:
        if not getattr(caller, "is_active", False):
            raise HTTPException(status_code=403, detail="Inactive user")
        current_user = caller
        active_org = resolve_active_organization(db, request, current_user)
        session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")
    if session.status in {"completed", "cancelled", "error"}:
        raise HTTPException(status_code=409, detail=f"Session is {session.status}.")

    body = await audio.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty audio body.")

    canonical_id = session.session_id or str(session.id)
    chunks_dir = _audio_chunks_dir(active_org.organization.slug, canonical_id)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # Clear any existing chunk files BEFORE writing the new whole-file
    # blob — otherwise ffmpeg's concat step would mix the old chunks
    # in front of the recovery audio. We keep the dir itself so file
    # permissions stay stable.
    for existing in chunks_dir.iterdir():
        if existing.is_file():
            try:
                existing.unlink()
            except OSError:
                logger.warning(
                    "full-audio could not clear existing chunk file: %s", existing
                )

    ext = _safe_ext(audio)
    out_path = chunks_dir / f"000000{ext}"
    out_path.write_bytes(body)

    metadata = dict(session.processing_metadata or {})
    audio_state = dict(metadata.get("full_audio") or {})
    audio_state.update({
        "status": "queued",
        "source": "full_audio_fallback",
        "queued_at": _now().isoformat(),
        "full_audio_bytes": len(body),
        "full_audio_received_at": _now().isoformat(),
        # Reset the per-chunk arrival map — the single recovery blob
        # is the whole truth now.
        "chunks": {
            "0": {
                "filename": out_path.name,
                "size": out_path.stat().st_size,
                "content_type": audio.content_type or "application/octet-stream",
                "received_at": _now().isoformat(),
                "via": "full_audio_fallback",
            },
        },
    })
    metadata["full_audio"] = audio_state
    metadata["reprocess_status"] = "queued"
    session.processing_metadata = metadata
    flag_modified(session, "processing_metadata")
    db.commit()

    session_pk = session.id
    background_tasks.add_task(_run_session_reprocess, session_pk)

    return {
        "reprocessing_started": True,
        "status": "complete",
        "session_id": canonical_id,
        "bytes_received": len(body),
        "source": "full_audio_fallback",
    }


# =====================================================================
# Brigade Phase 2 — read endpoint for the in-page 3D graph viewer.
# =====================================================================


def _brigade_graph_cache_get(key: str) -> Optional[dict[str, Any]]:
    """TTL-bounded cache lookup. Drops the row on read when expired so
    the dict never grows unboundedly."""
    import time

    row = _brigade_graph_cache.get(key)
    if not row:
        return None
    expires_at, payload = row
    if time.monotonic() > expires_at:
        _brigade_graph_cache.pop(key, None)
        return None
    return payload


def _brigade_graph_cache_put(key: str, payload: dict[str, Any]) -> None:
    import time

    _brigade_graph_cache[key] = (
        time.monotonic() + _BRIGADE_GRAPH_CACHE_TTL_SECONDS,
        payload,
    )


def _shape_brigade_graph(
    brigade_response: dict[str, Any],
    *,
    focus_node_id: str,
) -> dict[str, Any]:
    """Convert Brigade's /knowledge/context/{name} shape to the
    {nodes, links} shape react-force-graph-3d consumes.

    Brigade's context endpoint returns:
        {
          entity: {name, type, created_at, created_by, graph},
          relationships: [{from:{name,type}, relationship, to:{name,type},
                           confidence, learned_at, source_agent, graph}],
          related_entities: [{name, type, distance, graph}],
          context_text: "...",
        }

    We map every distinct entity (the focus + each related_entities row
    AND every endpoint of relationships) into one node, keyed by entity
    name. Brigade uses the entity ``name`` as the canonical ID across
    nodes + edges so we use it as the node ``id`` directly. The
    ``label`` field carries Brigade's ``type`` (Meeting / Speaker /
    ActionItem / Topic / Decision / Concept / Person / ...) so the
    frontend can color-code without re-resolving the type.

    Edges keep Brigade's ``relationship`` string as ``type`` (e.g.
    HAS_SPEAKER, ASSIGNED_TO) for hover labels.
    """
    nodes_by_id: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []

    def _add_node(raw: dict[str, Any], *, is_focus: bool = False) -> Optional[str]:
        name = raw.get("name")
        if not name:
            return None
        if name in nodes_by_id:
            return name
        # Drop graph metadata fields we don't need on the wire (graph
        # name leaks routing internals; created_by is server-side).
        properties = {
            k: v
            for k, v in raw.items()
            if k not in {"name", "type", "graph"}
        }
        nodes_by_id[name] = {
            "id": name,
            "label": raw.get("type") or "Concept",
            "name": name,
            "is_focus": is_focus,
            "properties": properties,
        }
        return name

    entity = brigade_response.get("entity") or {}
    _add_node(entity, is_focus=True)

    for rel in brigade_response.get("relationships") or []:
        from_raw = rel.get("from") or {}
        to_raw = rel.get("to") or {}
        from_id = _add_node(from_raw)
        to_id = _add_node(to_raw)
        if not from_id or not to_id:
            continue
        links.append(
            {
                "source": from_id,
                "target": to_id,
                "type": rel.get("relationship") or "RELATED_TO",
                "properties": {
                    k: v
                    for k, v in rel.items()
                    if k not in {"from", "to", "relationship", "graph"}
                    and v is not None
                },
            }
        )

    # related_entities may include nodes not touched by any relationship
    # (e.g. distance>1 hops the writer doesn't actually create edges
    # for). We surface them as floating nodes so the viewer can hint
    # at the larger graph context. Today depth=1 means this is rare.
    for related in brigade_response.get("related_entities") or []:
        _add_node(related)

    return {
        "nodes": list(nodes_by_id.values()),
        "links": links,
        "focus": focus_node_id,
    }


@brigade_graph_router.get("/api/sessions/{session_id}/brigade-graph")
async def get_brigade_graph(
    session_id: str,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Phase 2 read endpoint: returns the current session's :Meeting
    node + its 1-hop neighborhood (Speaker / ActionItem / Topic /
    Decision) from Brigade's FalkorDB store, shaped for
    react-force-graph-3d.

    Response shape:
        {
          "nodes": [{id, label, name, is_focus, properties}],
          "links": [{source, target, type, properties}],
          "graph_url": "https://brigade.../knowledge?graph=...&focus=...",
          "focus": "<meeting_node_id>",          # when synced
          "reason": "not_synced_yet" | "live_failed" | None,
          "synced_at": "<iso>" | None,
        }

    States:
      * Synced + Brigade reachable:    nodes + links populated, reason=None.
      * Not yet synced (column NULL): empty arrays + reason='not_synced_yet'.
      * Synced but Brigade down/404:  empty arrays + reason='live_failed'.

    Auth: user-scoped via the same path as the rest of the session
    detail API. Cross-org returns 404 (no existence leak). The
    response cache is keyed by (org_id, session_pk, synced_node_id)
    so a re-sync after a reprocess invalidates implicitly because the
    cache key includes the stamped node id.
    """
    # Local imports keep cold-start fast — this endpoint isn't on the
    # critical recording path.
    from services.brigade_client import BrigadeClient
    from services.brigade_writer import build_brigade_graph_url

    # 1. Resolve session within the active org. Cross-org returns 404.
    session_query = db.query(RecordingSession).filter(
        RecordingSession.organization_id == active_org.organization.id
    )
    session = session_query.filter(
        RecordingSession.session_id == session_id
    ).first()
    if not session:
        try:
            session = session_query.filter(
                RecordingSession.id == int(session_id)
            ).first()
        except (TypeError, ValueError):
            session = None
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2. Not-synced-yet: short-circuit with the empty payload. This is
    #    the expected state for new sessions or any deployment where
    #    BRIGADE_API_KEY isn't configured (writer ran in no-op mode and
    #    never stamped brigade_graph_node_id).
    node_id = getattr(session, "brigade_graph_node_id", None)
    synced_at = getattr(session, "brigade_synced_at", None)
    synced_at_iso = synced_at.isoformat() if synced_at else None
    if not node_id:
        return {
            "nodes": [],
            "links": [],
            "graph_url": None,
            "focus": None,
            "reason": "not_synced_yet",
            "synced_at": None,
        }

    # 3. Cache key includes org + session pk + node id + synced_at so a
    #    Brigade re-write (which bumps brigade_synced_at) implicitly
    #    invalidates without us tracking versions.
    cache_key = (
        f"{active_org.organization.id}:{session.id}:{node_id}:{synced_at_iso}"
    )
    cached = _brigade_graph_cache_get(cache_key)
    if cached is not None:
        return cached

    # 4. Live read. brigade_client returns None on noop / 404 / network
    #    error — we surface that to the frontend as 'live_failed' so it
    #    can render the empty-state with a retry button instead of a
    #    500. We do NOT cache the failure path so the next page load
    #    retries.
    graph_url = None
    try:
        graph_url = build_brigade_graph_url(session)
    except Exception as exc:  # noqa: BLE001
        logger.debug("brigade_graph build_url failed session=%s: %s", session.id, exc)
        graph_url = None

    brigade_client = BrigadeClient()
    try:
        raw = await brigade_client.fetch_entity_context(
            entity_name=node_id,
            include_relationships=True,
            include_related=True,
            max_depth=1,
        )
    finally:
        await brigade_client.aclose()

    if raw is None:
        # Either Brigade is unreachable, the API key isn't set in this
        # env, or the entity was deleted upstream. Don't cache —
        # next request retries.
        return {
            "nodes": [],
            "links": [],
            "graph_url": graph_url,
            "focus": node_id,
            "reason": "live_failed",
            "synced_at": synced_at_iso,
        }

    shaped = _shape_brigade_graph(raw, focus_node_id=node_id)
    payload: dict[str, Any] = {
        "nodes": shaped["nodes"],
        "links": shaped["links"],
        "graph_url": graph_url,
        "focus": node_id,
        "reason": None,
        "synced_at": synced_at_iso,
    }
    _brigade_graph_cache_put(cache_key, payload)
    return payload
