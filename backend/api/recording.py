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
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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


@router.post("/sessions/{session_id}/finalize-audio")
async def finalize_audio(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark all audio chunks delivered and kick off the reprocess pipeline.

    Returns ``{ reprocessing_started: bool, ... }``. The frontend polls
    ``GET /api/simple/recording-sessions/{id}`` (via SessionDetails) and
    reads ``metadata.reprocess_status`` to render the progress banner.

    Idempotent: if a reprocess is already in flight (in_progress), the
    second call is a no-op and we return the current status. If the
    session has zero audio chunks (e.g. privacy mode never uploaded), we
    skip the reprocess and return ``reprocessing_started: false`` — the
    live transcript stays as the final transcript.

    Auth: user-only. Internal callers (room_recorder) don't currently
    use this path; if we ever ship browser audio capture from a non-user
    context we can flip this to dual-auth like /audio-chunks.
    """
    session = _find_session(db, session_id, active_org.organization.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if getattr(session, "mode", "upload") != "always_on":
        raise HTTPException(status_code=409, detail="Session is not an always-on session.")

    canonical_id = session.session_id or str(session.id)
    chunks_dir = _audio_chunks_dir(active_org.organization.slug, canonical_id)

    metadata = dict(session.processing_metadata or {})
    audio_state = dict(metadata.get("full_audio") or {})

    # No chunks delivered (privacy mode, or upload failed for every chunk).
    # Bail with a friendly response — the live transcript stays canonical.
    if not chunks_dir.exists() or not any(
        p.is_file() for p in chunks_dir.iterdir() if not p.name.startswith("concat")
    ):
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
        "session_id": canonical_id,
        "job_id": str(uuid.uuid4()),  # informational; status lives on the session row
        "status": "queued",
    }
