"""Tests for services.session_watchdog — the abandoned-recording auto-fail."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _make_session(*, db, org_id, user_id, status, hours_old):
    from database.models import RecordingSession
    when = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    s = RecordingSession(
        session_id=str(uuid.uuid4()),
        title=f"watchdog test {hours_old}h",
        name=f"watchdog test {hours_old}h",
        status=status,
        user_id=user_id,
        organization_id=org_id,
        created_at=when,
        updated_at=when,
        started_at=when,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def org_and_user(app):
    from database.database import SessionLocal
    from auth.models import User, Organization
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
        user = db.query(User).filter(User.username == "admin").first()
        return org.id, user.id
    finally:
        db.close()


def test_watchdog_marks_stale_recording_failed(org_and_user, monkeypatch):
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_HOURS", "6")
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.session_watchdog import mark_abandoned_recording_sessions

    db = SessionLocal()
    try:
        old = _make_session(db=db, org_id=org_id, user_id=user_id, status="recording", hours_old=10)
        old_id = old.id
    finally:
        db.close()

    res = mark_abandoned_recording_sessions()
    assert res["enabled"] is True
    assert res["marked_failed"] >= 1
    db = SessionLocal()
    try:
        row = db.get(RecordingSession, old_id)
        assert row.status == "failed"
        assert row.ended_at is not None
        assert (row.processing_metadata or {}).get("auto_failed_reason", "").startswith("abandoned")
    finally:
        db.close()


def test_watchdog_skips_recent_recording(org_and_user, monkeypatch):
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_HOURS", "6")
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.session_watchdog import mark_abandoned_recording_sessions

    db = SessionLocal()
    try:
        recent = _make_session(db=db, org_id=org_id, user_id=user_id, status="recording", hours_old=1)
        recent_id = recent.id
    finally:
        db.close()

    mark_abandoned_recording_sessions()
    db = SessionLocal()
    try:
        row = db.get(RecordingSession, recent_id)
        assert row.status == "recording", "watchdog must not touch sessions younger than threshold"
    finally:
        db.close()


def test_watchdog_skips_non_recording_status(org_and_user, monkeypatch):
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_HOURS", "6")
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.session_watchdog import mark_abandoned_recording_sessions

    db = SessionLocal()
    try:
        # status='processing' is its own thing (server reprocess running);
        # watchdog only targets 'recording'.
        proc = _make_session(db=db, org_id=org_id, user_id=user_id, status="processing", hours_old=10)
        proc_id = proc.id
    finally:
        db.close()

    mark_abandoned_recording_sessions()
    db = SessionLocal()
    try:
        row = db.get(RecordingSession, proc_id)
        assert row.status == "processing", "watchdog must only flip 'recording', not other statuses"
    finally:
        db.close()


def test_watchdog_dry_run_does_not_mutate(org_and_user, monkeypatch):
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_HOURS", "6")
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.session_watchdog import mark_abandoned_recording_sessions

    db = SessionLocal()
    try:
        old = _make_session(db=db, org_id=org_id, user_id=user_id, status="recording", hours_old=24)
        old_id = old.id
    finally:
        db.close()

    res = mark_abandoned_recording_sessions(dry_run=True)
    assert res["dry_run"] is True
    assert res["marked_failed"] >= 1
    db = SessionLocal()
    try:
        row = db.get(RecordingSession, old_id)
        assert row.status == "recording", "dry-run must not mutate"
    finally:
        db.close()


def test_watchdog_disabled_flag(monkeypatch):
    monkeypatch.setenv("SESSION_WATCHDOG_ENABLED", "false")
    from services.session_watchdog import mark_abandoned_recording_sessions
    res = mark_abandoned_recording_sessions()
    assert res == {"enabled": False}
