"""Uploads-path reprocess must clear stale full-audio failure flags.

The 2026-07-28 prod incident: a session whose always-on finalize STT failed
stored BOTH ``processing_metadata.reprocess_status = "failed"`` and
``processing_metadata.full_audio.{status,error,failed_at}`` (written by
api/recording.py ``_set_status``). Aaron's later uploads-path reprocess
(POST /api/uploads/sessions/{id}/reprocess) re-transcribed everything
successfully — 222 rows / 2219 words — but never touched either flag, so
SessionDetails kept the red "Reprocess failed" banner (keyed purely on
``reprocess_status === 'failed'``) on a 100% healthy session, and no number
of successful re-runs could ever clear it.

These tests pin ``api.uploads._advance_stale_reprocess_flags``: on pipeline
success it advances stale non-terminal states to the terminal ``"complete"``
(the value workers/reprocess_workers.py's recovery scan checks) and drops the
stale ``error`` / ``failed_at`` keys — while leaving sessions that never had
a reprocess, and already-terminal states, byte-for-byte untouched.
"""
from __future__ import annotations

import uuid as _uuid

import pytest


def _models():
    from auth.models import Organization
    from database.database import SessionLocal
    from database.models import RecordingSession
    return Organization, SessionLocal, RecordingSession


def _seed_org(slug: str) -> int:
    Organization, SessionLocal, _ = _models()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            org = Organization(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
            db.add(org)
            db.commit()
            db.refresh(org)
        return org.id
    finally:
        db.close()


def _make_session(org_id: int, processing_metadata):
    _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        session_uuid = str(_uuid.uuid4())
        session = RecordingSession(
            session_id=session_uuid,
            name=f"banner-{session_uuid[:8]}",
            title=f"banner-{session_uuid[:8]}",
            status="processing",
            duration=10.0,
            organization_id=org_id,
            processing_metadata=processing_metadata,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id
    finally:
        db.close()


def _run_advance(session_pk: int) -> tuple[bool, dict | None]:
    """Run the helper inside a live ORM session + commit, then re-read the
    metadata through a FRESH session so we assert on what actually persisted
    (the JSON-column flag_modified gotcha is exactly what bites here)."""
    from api.uploads import _advance_stale_reprocess_flags

    _, SessionLocal, RecordingSession = _models()
    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == session_pk).first()
        changed = _advance_stale_reprocess_flags(session)
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.id == session_pk).first()
        return changed, session.processing_metadata
    finally:
        db.close()


def test_stale_failure_flags_are_advanced_to_complete(client):
    """The exact 2026-07-28 shape: both flags failed + error/failed_at set."""
    org_id = _seed_org("banner-stale")
    session_pk = _make_session(org_id, {
        "reprocess_status": "failed",
        "full_audio": {
            "status": "failed",
            "error": "OpenAIException - transcription backend error 500",
            "failed_at": "2026-07-28T04:14:00+00:00",
            "updated_at": "2026-07-28T04:14:00+00:00",
        },
        "word_count": 2219,
    })

    changed, metadata = _run_advance(session_pk)

    assert changed is True
    assert metadata["reprocess_status"] == "complete"
    assert metadata["full_audio"]["status"] == "complete"
    assert "error" not in metadata["full_audio"]
    assert "failed_at" not in metadata["full_audio"]
    # Unrelated metadata survives.
    assert metadata["word_count"] == 2219
    # updated_at advanced past the stale failure timestamp.
    assert metadata["full_audio"]["updated_at"] > "2026-07-28T04:14:00+00:00"


def test_non_terminal_states_are_advanced(client):
    """queued / in_progress left behind by a crashed run also advance —
    recover_reprocess_jobs treats only 'complete' as terminal."""
    org_id = _seed_org("banner-nonterminal")
    for stale in ("queued", "in_progress"):
        session_pk = _make_session(org_id, {"reprocess_status": stale})
        changed, metadata = _run_advance(session_pk)
        assert changed is True, stale
        assert metadata["reprocess_status"] == "complete", stale


def test_sessions_without_reprocess_history_are_untouched(client):
    """Fresh uploads must NOT get stamped with a reprocess_status they never
    had — the helper only advances existing non-terminal state."""
    org_id = _seed_org("banner-fresh")

    for metadata in (None, {}, {"word_count": 42, "transcription_model": "parakeet-tdt-1.1b"}):
        session_pk = _make_session(org_id, metadata)
        changed, persisted = _run_advance(session_pk)
        assert changed is False, metadata
        assert (persisted or {}).get("reprocess_status") is None
        assert "full_audio" not in (persisted or {})


def test_already_complete_is_left_alone(client):
    org_id = _seed_org("banner-complete")
    original = {
        "reprocess_status": "complete",
        "full_audio": {"status": "complete", "updated_at": "2026-08-01T00:00:00+00:00"},
    }
    session_pk = _make_session(org_id, dict(original))
    changed, metadata = _run_advance(session_pk)
    assert changed is False
    assert metadata == original


def test_failure_keys_alone_are_cleared_even_if_status_already_complete(client):
    """Belt-and-suspenders: a manual SQL fix that flipped status but forgot
    error/failed_at still converges to clean state on the next success."""
    org_id = _seed_org("banner-residue")
    session_pk = _make_session(org_id, {
        "reprocess_status": "complete",
        "full_audio": {
            "status": "complete",
            "error": "stale residue",
            "failed_at": "2026-07-28T04:14:00+00:00",
        },
    })
    changed, metadata = _run_advance(session_pk)
    assert changed is True
    assert metadata["reprocess_status"] == "complete"
    assert "error" not in metadata["full_audio"]
    assert "failed_at" not in metadata["full_audio"]


def test_non_dict_full_audio_is_tolerated(client):
    org_id = _seed_org("banner-weird")
    session_pk = _make_session(org_id, {
        "reprocess_status": "failed",
        "full_audio": "corrupted-scalar",
    })
    changed, metadata = _run_advance(session_pk)
    assert changed is True
    assert metadata["reprocess_status"] == "complete"
    assert metadata["full_audio"] == "corrupted-scalar"
