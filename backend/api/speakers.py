"""Speaker Library API.

Endpoints
---------
GET    /api/speakers                              — list speakers in active org
POST   /api/speakers                              — create a speaker (admin)
GET    /api/speakers/{id}                         — get one speaker + samples
PATCH  /api/speakers/{id}                         — update display_name / email / notes (admin)
DELETE /api/speakers/{id}                         — delete a speaker + cascade samples (admin)
POST   /api/speakers/{id}/voice-samples           — upload a .wav clip, embed it, update centroid (admin)
DELETE /api/speakers/{id}/voice-samples/{sid}     — drop a sample, recompute centroid (admin)
GET    /api/sessions/{session_id}/speaker-links   — list raw_label -> speaker mappings
PATCH  /api/sessions/{session_id}/speaker-links/{link_id}
                                                  — confirm / change / clear a mapping (any user with org access)
POST   /api/sessions/{session_id}/identify-speakers
                                                  — re-run identification for a finished session

All routes are org-scoped via ActiveOrganization. Mutating endpoints
require admin role except for the link-confirm endpoint, which any org
member can use (it's the inline tagger workflow).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_organization, get_current_user
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import get_db
from database.models import (
    RecordingSession,
    SpeakerProfile,
    SpeakerSessionLink,
    SpeakerVoiceSample,
)
from services.providers.registry import get_provider_registry
from services.speaker_service import (
    DEFAULT_EMBEDDING_MODEL,
    STORE_SPEAKER_AUDIO,
    add_voice_sample,
    decode_embedding,
    encode_embedding,
    identify_speakers,
    update_centroid,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Speakers"])

VOICE_SAMPLE_DIR = os.getenv("SPEAKER_AUDIO_DIR", "/app/recordings/speakers")


# ---------- response / request models ----------


class SpeakerResponse(BaseModel):
    id: int
    organization_id: int
    display_name: str
    email: Optional[str] = None
    notes: Optional[str] = None
    embedding_dim: Optional[int] = None
    embedding_model: Optional[str] = None
    sample_count: int = 0
    has_centroid: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SpeakerCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    notes: Optional[str] = None


class SpeakerUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    notes: Optional[str] = None


class VoiceSampleResponse(BaseModel):
    id: int
    speaker_id: int
    source: str
    source_session_id: Optional[int] = None
    embedding_dim: int
    embedding_model: str
    duration_seconds: Optional[float] = None
    similarity_to_centroid: Optional[float] = None
    has_audio: bool = False
    created_at: Optional[str] = None


class SpeakerDetailResponse(SpeakerResponse):
    voice_samples: list[VoiceSampleResponse] = Field(default_factory=list)
    session_count: int = 0


class SpeakerLinkResponse(BaseModel):
    id: int
    session_id: int
    raw_label: str
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None
    similarity: Optional[float] = None
    source: str
    confirmed: bool


class SpeakerLinkUpdate(BaseModel):
    speaker_id: Optional[int] = None  # None / 0 to clear
    confirmed: bool = True


class IdentifyResponse(BaseModel):
    session_id: int
    linked: int
    unmatched: int
    skipped_reason: Optional[str] = None
    backend: Optional[str] = None


# ---------- helpers ----------


def _to_response(speaker: SpeakerProfile) -> SpeakerResponse:
    return SpeakerResponse(
        id=speaker.id,
        organization_id=speaker.organization_id,
        display_name=speaker.display_name,
        email=speaker.email,
        notes=speaker.notes,
        embedding_dim=speaker.embedding_dim,
        embedding_model=speaker.embedding_model,
        sample_count=speaker.sample_count or 0,
        has_centroid=speaker.centroid_embedding is not None,
        created_at=speaker.created_at.isoformat() if speaker.created_at else None,
        updated_at=speaker.updated_at.isoformat() if speaker.updated_at else None,
    )


def _to_sample_response(sample: SpeakerVoiceSample) -> VoiceSampleResponse:
    return VoiceSampleResponse(
        id=sample.id,
        speaker_id=sample.speaker_id,
        source=sample.source,
        source_session_id=sample.source_session_id,
        embedding_dim=sample.embedding_dim,
        embedding_model=sample.embedding_model,
        duration_seconds=sample.duration_seconds,
        similarity_to_centroid=sample.similarity_to_centroid,
        has_audio=bool(sample.audio_path),
        created_at=sample.created_at.isoformat() if sample.created_at else None,
    )


def _require_admin(active_org: ActiveOrganization, current_user: User) -> None:
    if current_user.is_superuser:
        return
    if active_org.role not in ("admin", "superuser"):
        raise HTTPException(status_code=403, detail="Speaker library management requires admin role.")


def _get_speaker_or_404(db: Session, organization_id: int, speaker_id: int) -> SpeakerProfile:
    speaker = (
        db.query(SpeakerProfile)
        .filter(
            SpeakerProfile.organization_id == organization_id,
            SpeakerProfile.id == speaker_id,
        )
        .first()
    )
    if not speaker:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return speaker


def _get_session_or_404(db: Session, organization_id: int, session_id: int | str) -> RecordingSession:
    q = db.query(RecordingSession).filter(RecordingSession.organization_id == organization_id)
    try:
        sid = int(session_id)
        session = q.filter(RecordingSession.id == sid).first()
    except (TypeError, ValueError):
        session = q.filter(RecordingSession.session_id == str(session_id)).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ---------- speaker library ----------


@router.get("/api/speakers", response_model=list[SpeakerResponse])
async def list_speakers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    rows = (
        db.query(SpeakerProfile)
        .filter(SpeakerProfile.organization_id == active_org.organization.id)
        .order_by(SpeakerProfile.display_name.asc())
        .all()
    )
    return [_to_response(r) for r in rows]


@router.post("/api/speakers", response_model=SpeakerResponse, status_code=201)
async def create_speaker(
    payload: SpeakerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    _require_admin(active_org, current_user)
    existing = (
        db.query(SpeakerProfile)
        .filter(
            SpeakerProfile.organization_id == active_org.organization.id,
            SpeakerProfile.display_name == payload.display_name,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Speaker '{payload.display_name}' already exists")
    speaker = SpeakerProfile(
        organization_id=active_org.organization.id,
        display_name=payload.display_name,
        email=payload.email,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(speaker)
    db.commit()
    db.refresh(speaker)
    return _to_response(speaker)


@router.get("/api/speakers/{speaker_id}", response_model=SpeakerDetailResponse)
async def get_speaker(
    speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    speaker = _get_speaker_or_404(db, active_org.organization.id, speaker_id)
    samples = (
        db.query(SpeakerVoiceSample)
        .filter(SpeakerVoiceSample.speaker_id == speaker.id)
        .order_by(SpeakerVoiceSample.id.desc())
        .all()
    )
    session_count = (
        db.query(SpeakerSessionLink)
        .filter(
            SpeakerSessionLink.speaker_id == speaker.id,
            SpeakerSessionLink.organization_id == active_org.organization.id,
        )
        .count()
    )
    base = _to_response(speaker).model_dump()
    return SpeakerDetailResponse(
        **base,
        voice_samples=[_to_sample_response(s) for s in samples],
        session_count=session_count,
    )


@router.patch("/api/speakers/{speaker_id}", response_model=SpeakerResponse)
async def update_speaker(
    speaker_id: int,
    payload: SpeakerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    _require_admin(active_org, current_user)
    speaker = _get_speaker_or_404(db, active_org.organization.id, speaker_id)
    if payload.display_name is not None:
        speaker.display_name = payload.display_name
    if payload.email is not None:
        speaker.email = payload.email or None
    if payload.notes is not None:
        speaker.notes = payload.notes or None
    db.commit()
    db.refresh(speaker)
    return _to_response(speaker)


@router.delete("/api/speakers/{speaker_id}", status_code=204)
async def delete_speaker(
    speaker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    _require_admin(active_org, current_user)
    speaker = _get_speaker_or_404(db, active_org.organization.id, speaker_id)
    # Detach session links so the deletion is a pure soft-unlink for transcripts.
    db.query(SpeakerSessionLink).filter(SpeakerSessionLink.speaker_id == speaker.id).update(
        {"speaker_id": None, "similarity": None, "confirmed": False}
    )
    db.query(SpeakerVoiceSample).filter(SpeakerVoiceSample.speaker_id == speaker.id).delete()
    db.delete(speaker)
    db.commit()


# ---------- voice sample enrollment ----------


@router.post("/api/speakers/{speaker_id}/voice-samples", response_model=VoiceSampleResponse, status_code=201)
async def upload_voice_sample(
    speaker_id: int,
    audio: UploadFile = File(..., description="3-30s clean speech sample (wav/flac/ogg/mp3)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    _require_admin(active_org, current_user)
    speaker = _get_speaker_or_404(db, active_org.organization.id, speaker_id)

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload")

    registry = get_provider_registry(db)
    provider = registry.get_speaker_svc(active_org.organization.id)
    embed_result = await provider.embed_bytes(audio_bytes, filename=audio.filename or "sample.wav")
    embedding = embed_result.get("embedding") or []
    if not embedding:
        raise HTTPException(status_code=502, detail="speaker-svc returned no embedding (check service health)")

    embedding_model = embed_result.get("model") or DEFAULT_EMBEDDING_MODEL
    duration = embed_result.get("duration_seconds")

    audio_path: Optional[str] = None
    if STORE_SPEAKER_AUDIO:
        os.makedirs(VOICE_SAMPLE_DIR, exist_ok=True)
        ext = (os.path.splitext(audio.filename or "")[1] or ".wav").lower()
        audio_path = os.path.join(VOICE_SAMPLE_DIR, f"speaker_{speaker.id}_{int((duration or 0) * 1000)}_{os.urandom(4).hex()}{ext}")
        try:
            with open(audio_path, "wb") as fh:
                fh.write(audio_bytes)
        except OSError as exc:
            logger.warning("Failed to persist voice sample audio: %s", exc)
            audio_path = None

    sample = add_voice_sample(
        db,
        speaker,
        embedding,
        source="enrollment",
        embedding_model=embedding_model,
        audio_path=audio_path,
        duration_seconds=duration,
    )
    db.commit()
    db.refresh(sample)
    return _to_sample_response(sample)


@router.delete("/api/speakers/{speaker_id}/voice-samples/{sample_id}", status_code=204)
async def delete_voice_sample(
    speaker_id: int,
    sample_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    _require_admin(active_org, current_user)
    speaker = _get_speaker_or_404(db, active_org.organization.id, speaker_id)
    sample = (
        db.query(SpeakerVoiceSample)
        .filter(
            SpeakerVoiceSample.id == sample_id,
            SpeakerVoiceSample.speaker_id == speaker.id,
        )
        .first()
    )
    if not sample:
        raise HTTPException(status_code=404, detail="Voice sample not found")

    if sample.audio_path and os.path.exists(sample.audio_path):
        try:
            os.remove(sample.audio_path)
        except OSError:
            pass
    db.delete(sample)
    db.flush()

    # Recompute centroid from remaining samples (or clear it if none remain).
    remaining = (
        db.query(SpeakerVoiceSample)
        .filter(SpeakerVoiceSample.speaker_id == speaker.id)
        .all()
    )
    if not remaining:
        speaker.centroid_embedding = None
        speaker.embedding_dim = None
        speaker.embedding_model = None
        speaker.sample_count = 0
    else:
        new_centroid: Optional[list[float]] = None
        for i, s in enumerate(remaining):
            vec = decode_embedding(s.embedding, s.embedding_dim)
            new_centroid = update_centroid(new_centroid, i, vec)
        if new_centroid is not None:
            speaker.centroid_embedding = encode_embedding(new_centroid)
            speaker.embedding_dim = len(new_centroid)
        speaker.sample_count = len(remaining)
    db.commit()


# ---------- session linking ----------


def _link_to_response(db: Session, link: SpeakerSessionLink) -> SpeakerLinkResponse:
    name = None
    if link.speaker_id:
        sp = db.query(SpeakerProfile).filter(SpeakerProfile.id == link.speaker_id).first()
        if sp:
            name = sp.display_name
    return SpeakerLinkResponse(
        id=link.id,
        session_id=link.session_id,
        raw_label=link.raw_label,
        speaker_id=link.speaker_id,
        speaker_name=name,
        similarity=link.similarity,
        source=link.source,
        confirmed=link.confirmed,
    )


@router.get("/api/sessions/{session_id}/speaker-links", response_model=list[SpeakerLinkResponse])
async def list_speaker_links(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """List speaker-session links for this session.

    If no links exist yet but the diarized transcript has labeled
    segments (SPEAKER_01, SPEAKER_02, etc.), auto-create one unconfirmed
    link per unique label so the inline tagger has something to attach
    names to. This makes the UI immediately useful after a fresh upload
    without first having to click Re-identify.
    """
    session = _get_session_or_404(db, active_org.organization.id, session_id)
    links = (
        db.query(SpeakerSessionLink)
        .filter(SpeakerSessionLink.session_id == session.id)
        .order_by(SpeakerSessionLink.raw_label.asc())
        .all()
    )

    if not links:
        diarized = session.transcript_diarized if isinstance(session.transcript_diarized, dict) else {}
        segs = diarized.get("segments", []) if isinstance(diarized, dict) else []
        seen: set[str] = set()
        ordered_labels: list[str] = []
        for seg in segs:
            label = (seg.get("raw_label") or seg.get("speaker") or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            ordered_labels.append(label)

        for label in ordered_labels:
            link = SpeakerSessionLink(
                session_id=session.id,
                organization_id=session.organization_id,
                raw_label=label,
            )
            db.add(link)
        if ordered_labels:
            db.commit()
            links = (
                db.query(SpeakerSessionLink)
                .filter(SpeakerSessionLink.session_id == session.id)
                .order_by(SpeakerSessionLink.raw_label.asc())
                .all()
            )

    return [_link_to_response(db, link) for link in links]


@router.patch("/api/sessions/{session_id}/speaker-links/{link_id}", response_model=SpeakerLinkResponse)
async def update_speaker_link(
    session_id: str,
    link_id: int,
    payload: SpeakerLinkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Confirm (or change) the mapping from a raw_label to a Speaker.
    Accessible to any org member — this is the inline-tagger workflow."""
    session = _get_session_or_404(db, active_org.organization.id, session_id)
    link = (
        db.query(SpeakerSessionLink)
        .filter(
            SpeakerSessionLink.id == link_id,
            SpeakerSessionLink.session_id == session.id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Speaker link not found")

    if payload.speaker_id:
        speaker = _get_speaker_or_404(db, active_org.organization.id, payload.speaker_id)
        link.speaker_id = speaker.id
    else:
        link.speaker_id = None

    link.source = "manual"
    link.confirmed = payload.confirmed
    link.confirmed_by_user_id = current_user.id if payload.confirmed else None
    db.flush()

    # Rewrite the diarized transcript so the SessionDetails page picks up
    # the new label without an extra API roundtrip.
    diarized = session.transcript_diarized or {}
    if isinstance(diarized, dict):
        new_name: Optional[str] = None
        if link.speaker_id:
            sp = db.query(SpeakerProfile).filter(SpeakerProfile.id == link.speaker_id).first()
            if sp:
                new_name = sp.display_name
        new_segments = []
        for seg in diarized.get("segments", []):
            label_now = seg.get("speaker", "")
            raw = seg.get("raw_label", label_now)
            if raw == link.raw_label:
                new_seg = {**seg, "raw_label": raw, "speaker": new_name or raw}
            else:
                new_seg = seg
            new_segments.append(new_seg)
        diarized["segments"] = new_segments
        if "speakers" in diarized:
            seen, ordered = set(), []
            for seg in new_segments:
                s = seg.get("speaker", "Unknown")
                if s not in seen:
                    seen.add(s)
                    ordered.append(s)
            diarized["speakers"] = ordered
        session.transcript_diarized = diarized
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(session, "transcript_diarized")

    db.commit()
    db.refresh(link)
    return _link_to_response(db, link)


@router.post("/api/sessions/{session_id}/identify-speakers", response_model=IdentifyResponse)
async def identify_speakers_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    """Re-run speaker identification on a finished session. Useful after
    enrolling new speakers or to refresh stale mappings."""
    session = _get_session_or_404(db, active_org.organization.id, session_id)
    summary = identify_speakers(session, db)
    return IdentifyResponse(**summary)
