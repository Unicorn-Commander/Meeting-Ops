"""Atomic authored content replacement for completed, detached text sessions.

No inference, recording, federation or notification is invoked here. The parent
and existing child rows are locked before revision comparison. PostgreSQL replacement additionally locks the transcription table against all
DML because its legacy session_id column has no foreign key.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import inspect, or_, text

from auth.models import AuditLog
from database.models import (
    RecordingSession, Transcription, ActionItem, Speaker, AudioFile, ChatHistory,
    SessionCollaborator, SessionGroupMember, UploadJob, SpeakerSessionLink,
    SpeakerVoiceSample, TtsJob, SessionAttachment, SummarizationLease, BulkImportFile,
)

from models.agent_system import AgentSession
from models.vocabulary import SessionVocabulary

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ManualLine(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    speaker: Annotated[Text, Field(max_length=100)]
    text: Annotated[Text, Field(max_length=10000)]


class ManualAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: Annotated[Text, Field(max_length=2000)]
    owner: Annotated[str, Field(max_length=200)] | None = None
    due_date: str | None = None

    @model_validator(mode="after")
    def checked(self):
        if self.due_date is not None:
            if date.fromisoformat(self.due_date).isoformat() != self.due_date:
                raise ValueError("due_date must be YYYY-MM-DD")
        return self


class ManualContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    title: Annotated[Text, Field(max_length=200)]
    description: Annotated[str, Field(max_length=4000)] = ""
    lines: Annotated[list[ManualLine], Field(min_length=1, max_length=2000)]
    summary: Annotated[Text, Field(max_length=20000)]
    decisions: Annotated[list[Annotated[Text, Field(max_length=2000)]], Field(max_length=100)] = []
    topics: Annotated[list[Annotated[Text, Field(max_length=200)]], Field(max_length=100)] = []
    actions: Annotated[list[ManualAction], Field(max_length=100)] = []

    @model_validator(mode="after")
    def bounded(self):
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 250000:
            raise ValueError("Manual content exceeds 250 KB")
        return self


def _normal(value):
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normal(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normal(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _columns(row):
    return {c.key: _normal(getattr(row, c.key)) for c in inspect(type(row)).columns}


def digest(value):
    return hashlib.sha256(json.dumps(_normal(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def lock_transcription_writes(db):
    """Rare bounded edit: serialize even legacy raw/bulk inserts before row locks.

    Existing writers may already hold a parent row; taking this lock first can
    encounter an inverse lock order. The local timeout makes that contention
    fail closed, releasing all locks through the route rollback.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '1500ms'"))
        db.execute(text("LOCK TABLE transcriptions IN SHARE ROW EXCLUSIVE MODE"))


def _load(db, session):
    lines = db.query(Transcription).filter(Transcription.session_id == session.id).order_by(Transcription.id).with_for_update().all()
    actions = db.query(ActionItem).filter(ActionItem.session_id == session.id).order_by(ActionItem.id).with_for_update().all()
    return lines, actions


def revision(session, lines, actions):
    snapshot = {"session": _columns(session), "transcriptions": [_columns(r) for r in lines], "actions": [_columns(r) for r in actions]}
    if len(json.dumps(snapshot, ensure_ascii=False).encode()) > 1000000:
        raise HTTPException(409, "Existing content exceeds the manual replacement bound")
    return digest(snapshot)


def legacy_participant_labels(session):
    """Legacy display strings are not verified participants or identity links."""
    value = session.participants
    if value is None or value == []:
        return []
    if not isinstance(value, list) or len(value) > 100 or any(
        not isinstance(label, str) or not label.strip() or len(label) > 200
        for label in value
    ):
        raise HTTPException(409, "Structured or unbounded participant data requires separate review")
    return list(value)


def _assert_detached(db, session, actions):
    if session.status != "completed" or any((session.audio_file, session.audio_object_key,
        session.audio_storage_backend, session.processing_job_id, session.external_source,
        session.external_id, session.meeting_key, session.external_room_id, session.is_combined,
        session.source_device_id, session.room_id, session.room_source_id, session.project_app,
        session.project_id, session.project_slug, session.brigade_graph_node_id,
        session.brigade_synced_at, session.brigade_sync_status)):
        raise HTTPException(409, "Manual replacement requires a completed detached session without audio, jobs, verified roster or external projections")
    legacy_participant_labels(session)
    checks = [
        (AgentSession, AgentSession.meeting_session_id == session.id),
        (Speaker, Speaker.session_id == session.id),
        (AudioFile, AudioFile.session_id.in_([str(session.id), session.session_id])),
        (ChatHistory, ChatHistory.session_key.in_([str(session.id), session.session_id])),
        (SessionCollaborator, SessionCollaborator.session_id == session.id),
        (SessionGroupMember, or_(SessionGroupMember.member_session_id == session.id, SessionGroupMember.combined_session_id == session.id)),
        (UploadJob, UploadJob.session_id == session.id),
        (SpeakerSessionLink, SpeakerSessionLink.session_id == session.id),
        (SpeakerVoiceSample, SpeakerVoiceSample.source_session_id == session.id),
        (TtsJob, TtsJob.session_id == session.id),
        (SessionAttachment, SessionAttachment.session_id == session.id),
        (SummarizationLease, SummarizationLease.session_id.in_([str(session.id), session.session_id])),
    ]
    try:
        wire_uuid = UUID(session.session_id or "")
    except ValueError:
        wire_uuid = None
    if wire_uuid:
        checks.extend([(BulkImportFile, BulkImportFile.session_id_when_created == wire_uuid),
                       (SessionVocabulary, SessionVocabulary.session_id == wire_uuid)])
    if any(db.query(model).filter(predicate).first() is not None for model, predicate in checks):
        raise HTTPException(409, "Dependent artifacts require separate review before content replacement")
    for item in actions:
        if item.organization_id != session.organization_id or item.status != "todo" or item.completed_at or item.source not in {"final_summary", "ai_insights"} or item.project_ops_link_state != "local_only" or any((item.project_ops_task_id, item.project_ops_proposal_id, item.project_ops_task_url, item.project_ops_submitted_at)):
            raise HTTPException(409, "Manual, progressed or externally linked action items cannot be replaced")


def state(db, session):
    lines, actions = _load(db, session)
    _assert_detached(db, session, actions)
    return {"session_id": session.session_id or str(session.id), "revision": revision(session, lines, actions),
            "transcription_count": len(lines), "action_count": len(actions), "legacy_participant_labels": legacy_participant_labels(session), "content_source": "manually_authored" if (session.processing_metadata or {}).get("manual_content") else (session.source_type or "unknown"), "audio_available": False}


def replace(db, session, request, user):
    lines, actions = _load(db, session)
    before = revision(session, lines, actions)
    request_hash = digest(request.model_dump())
    prior = db.query(AuditLog).filter(AuditLog.organization_id == session.organization_id,
        AuditLog.resource_id == str(session.id), AuditLog.action == "manual_content_replace").order_by(AuditLog.id.desc()).first()
    if prior and isinstance(prior.details, dict) and prior.details.get("request_digest") == request_hash and prior.details.get("after_digest") == before:
        return {"status": "unchanged", "revision": before, "replayed": True}
    if request.expected_revision != before:
        raise HTTPException(409, "Content changed; fetch and review the current revision")
    _assert_detached(db, session, actions)
    # Delete only rows locked and included in the reviewed digest.
    for row in [*lines, *actions]:
        db.delete(row)
    db.flush()
    plain = "\n".join(f"{line.speaker}: {line.text}" for line in request.lines)
    speakers = list(dict.fromkeys(line.speaker for line in request.lines))
    segments = [{"speaker": line.speaker, "text": line.text, "start": None, "end": None} for line in request.lines]
    summary = {"summary": request.summary, "executive": request.summary, "bullets": request.topics,
               "decisions": request.decisions, "topics": request.topics,
               "action_items": [a.model_dump() for a in request.actions],
               "actions": [{**a.model_dump(), "action": a.text} for a in request.actions], "content_source": "manually_authored"}
    session.participants = []  # Invalidate legacy display labels, never invent attendees.
    session.title = session.name = request.title
    session.title_user_set = True
    session.description = request.description
    session.transcript = session.transcript_simple = plain
    session.transcript_diarized = {"text": plain, "segments": segments, "speakers": speakers, "source": "manually_authored", "timing_verified": False}
    session.summary = json.dumps(summary, ensure_ascii=False)
    session.final_summary = summary
    session.ai_insights = {"content_source": "manually_authored", "insights": []}
    session.progressive_summaries = []
    session.generated_emails = []
    session.federation_summary_approved_at = None
    session.federation_summary_approved_by_user_id = None
    session.federation_summary_approved_digest = None
    session.processing_metadata = {**(session.processing_metadata or {}), "manual_content": {"version": 1, "author_user_id": user.id,
        "audio_available": False, "timing_verified": False, "inference_performed": False}}
    session.source_type = "manual_content"
    # Capture mode is a constrained historical transport field; preserve it.
    session.started_at = session.ended_at = None
    session.duration = 0
    session.updated_at = datetime.now(timezone.utc)
    for line in request.lines:
        db.add(Transcription(session_id=session.id, text=line.text, speaker=line.speaker,
            start_time=None, end_time=None, confidence=None))
    for index, action in enumerate(request.actions):
        db.add(ActionItem(session_id=session.id, organization_id=session.organization_id,
            text=action.text, owner=action.owner,
            due_date=datetime.combine(date.fromisoformat(action.due_date), datetime.min.time(), tzinfo=timezone.utc) if action.due_date else None,
            status="todo", sort_order=index, source="manual", project_ops_link_state="local_only",
            raw_payload={**action.model_dump(), "content_source": "manually_authored"}))
    db.flush()
    db.refresh(session)  # Hash persisted column representations, including float defaults.
    new_lines, new_actions = _load(db, session)
    after = revision(session, new_lines, new_actions)
    db.add(AuditLog(user_id=user.id, organization_id=session.organization_id,
        action="manual_content_replace", resource_type="recording_session", resource_id=str(session.id),
        details={"version": 1, "before_digest": before, "after_digest": after,
            "request_digest": request_hash, "line_count": len(new_lines), "action_count": len(new_actions),
            "content_source": "manually_authored", "inference_performed": False}))
    return {"status": "replaced", "revision": after, "replayed": False}
