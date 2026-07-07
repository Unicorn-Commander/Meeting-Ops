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


def test_watchdog_double_run_idempotent(org_and_user, monkeypatch):
    """A second consecutive run finds nothing to do — already-failed sessions
    must not be re-touched. Confirms the cron can fire on its 30-min schedule
    without churning the DB or stamping new auto_failed_reason values."""
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_HOURS", "6")
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.session_watchdog import mark_abandoned_recording_sessions

    db = SessionLocal()
    try:
        old = _make_session(db=db, org_id=org_id, user_id=user_id, status="recording", hours_old=12)
        old_id = old.id
    finally:
        db.close()

    res1 = mark_abandoned_recording_sessions()
    assert res1["marked_failed"] >= 1
    res2 = mark_abandoned_recording_sessions()
    assert res2["marked_failed"] == 0, "second run must not re-mark already-failed rows"

    db = SessionLocal()
    try:
        row = db.get(RecordingSession, old_id)
        assert row.status == "failed"
    finally:
        db.close()


def test_watchdog_respects_max_per_pass_cap(org_and_user, monkeypatch):
    """When more stale sessions exist than the per-pass cap, the watchdog
    marks at most N. Prevents a runaway state where a single pass touches
    thousands of rows and blocks for minutes."""
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_HOURS", "6")
    monkeypatch.setenv("SESSION_WATCHDOG_MAX_PER_PASS", "2")
    from database.database import SessionLocal
    from services.session_watchdog import mark_abandoned_recording_sessions

    db = SessionLocal()
    try:
        for _ in range(5):
            _make_session(db=db, org_id=org_id, user_id=user_id, status="recording", hours_old=12)
    finally:
        db.close()

    res = mark_abandoned_recording_sessions()
    # First pass takes at most the cap
    assert res["marked_failed"] <= 2, f"expected cap=2, got {res['marked_failed']}"
    # Second pass takes the next batch
    res2 = mark_abandoned_recording_sessions()
    assert res2["marked_failed"] <= 2


def _make_needs_summary_session(
    *, db, org_id, user_id, minutes_stale=30, transcript="hello world transcript",
    redrive_count=None, processing_job_id="dead-job-A", status="processing",
):
    """Seed a session in the wedged state a failed finalize leaves behind:
    status='processing' + needs_summary, a transcript, and processing_job_id
    still pointing at the dead finalize job. ``updated_at`` is set in the same
    INSERT (no onupdate on INSERT) so the cooldown gate sees it as stale."""
    from database.models import RecordingSession
    when = datetime.now(timezone.utc) - timedelta(minutes=minutes_stale)
    md = {"needs_summary": True, "summary_error": "gateway unavailable"}
    if redrive_count is not None:
        md["summary_redrive_count"] = redrive_count
    s = RecordingSession(
        session_id=str(uuid.uuid4()),
        title="redrive test",
        name="redrive test",
        status=status,
        user_id=user_id,
        organization_id=org_id,
        created_at=when,
        updated_at=when,
        started_at=when,
        transcript_simple=transcript,
        processing_metadata=md,
        processing_job_id=processing_job_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_summary_redrive_reenqueues_and_clears_drift(org_and_user, monkeypatch):
    """The core fix: a wedged needs_summary row gets its drift-guard cleared
    (processing_job_id -> NULL) and finalize re-enqueued."""
    org_id, user_id = org_and_user
    import services.session_watchdog as sw
    calls = []
    monkeypatch.setattr(
        sw, "_enqueue_finalize_retry",
        lambda pk, uid, oid: (calls.append((pk, uid, oid)), "new-job-B")[1],
    )
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        s = _make_needs_summary_session(db=db, org_id=org_id, user_id=user_id)
        sid = s.id
    finally:
        db.close()

    res = sw.redrive_stuck_summary_sessions()
    assert res["enabled"] is True
    assert res["redriven"] >= 1
    assert calls and calls[0][0] == sid

    db = SessionLocal()
    try:
        row = db.get(RecordingSession, sid)
        assert row.processing_job_id is None, "drift-guard must be cleared to NULL"
        assert row.status == "processing"
        md = row.processing_metadata or {}
        assert md.get("summary_redrive_count") == 1
        assert md.get("summary_redrive_at")
        assert md.get("summary_redrive_job_id") == "new-job-B"
        assert md.get("needs_summary") is True
    finally:
        db.close()


def test_summary_redrive_caps_after_max_attempts(org_and_user, monkeypatch):
    """A genuinely-broken LLM must NOT re-enqueue forever: once the attempt
    count hits the cap, the row is given up on and never re-enqueued."""
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_SUMMARY_REDRIVE_MAX", "5")
    import services.session_watchdog as sw
    calls = []
    monkeypatch.setattr(
        sw, "_enqueue_finalize_retry", lambda pk, uid, oid: calls.append(pk) or "x",
    )
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        s = _make_needs_summary_session(
            db=db, org_id=org_id, user_id=user_id, redrive_count=5,
        )
        sid = s.id
    finally:
        db.close()

    res = sw.redrive_stuck_summary_sessions()
    assert res["given_up"] >= 1
    assert res["redriven"] == 0
    assert calls == [], "exhausted sessions must never be re-enqueued"

    db = SessionLocal()
    try:
        row = db.get(RecordingSession, sid)
        assert row.processing_job_id == "dead-job-A", "no re-drive -> untouched"
        assert (row.processing_metadata or {}).get("summary_redrive_given_up_at")
    finally:
        db.close()


def test_summary_redrive_respects_cooldown(org_and_user, monkeypatch):
    """A row touched within the cooldown window is not re-driven."""
    org_id, user_id = org_and_user
    monkeypatch.setenv("SESSION_WATCHDOG_SUMMARY_REDRIVE_COOLDOWN_MINUTES", "10")
    import services.session_watchdog as sw
    calls = []
    monkeypatch.setattr(
        sw, "_enqueue_finalize_retry", lambda pk, uid, oid: calls.append(pk) or "x",
    )
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        # 2 min stale -> inside the 10-min cooldown, so filtered out.
        _make_needs_summary_session(
            db=db, org_id=org_id, user_id=user_id, minutes_stale=2,
        )
    finally:
        db.close()

    res = sw.redrive_stuck_summary_sessions()
    assert res["redriven"] == 0
    assert calls == []


def test_summary_redrive_skips_when_no_transcript(org_and_user, monkeypatch):
    """No transcript -> nothing to summarize -> must not re-drive."""
    org_id, user_id = org_and_user
    import services.session_watchdog as sw
    calls = []
    monkeypatch.setattr(
        sw, "_enqueue_finalize_retry", lambda pk, uid, oid: calls.append(pk) or "x",
    )
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        _make_needs_summary_session(
            db=db, org_id=org_id, user_id=user_id, transcript="",
        )
    finally:
        db.close()

    res = sw.redrive_stuck_summary_sessions()
    assert res["redriven"] == 0
    assert res["skipped_no_transcript"] >= 1
    assert calls == []


def test_summary_redrive_ignores_completed_sessions(org_and_user, monkeypatch):
    """Already-completed sessions (transcript visible) are out of scope."""
    org_id, user_id = org_and_user
    import services.session_watchdog as sw
    calls = []
    monkeypatch.setattr(
        sw, "_enqueue_finalize_retry", lambda pk, uid, oid: calls.append(pk) or "x",
    )
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        _make_needs_summary_session(
            db=db, org_id=org_id, user_id=user_id, status="completed",
        )
    finally:
        db.close()

    res = sw.redrive_stuck_summary_sessions()
    assert res["redriven"] == 0
    assert calls == []


def test_summary_redrive_double_run_is_idempotent(org_and_user, monkeypatch):
    """Re-driving bumps updated_at, so an immediate second pass finds the row
    inside its cooldown and does not re-enqueue again."""
    org_id, user_id = org_and_user
    import services.session_watchdog as sw
    calls = []
    monkeypatch.setattr(
        sw, "_enqueue_finalize_retry", lambda pk, uid, oid: calls.append(pk) or "job-x",
    )
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        _make_needs_summary_session(db=db, org_id=org_id, user_id=user_id)
    finally:
        db.close()

    r1 = sw.redrive_stuck_summary_sessions()
    r2 = sw.redrive_stuck_summary_sessions()
    assert r1["redriven"] == 1
    assert r2["redriven"] == 0, "second pass is inside the cooldown after the bump"
    assert len(calls) == 1


def test_summary_redrive_disabled_flag(monkeypatch):
    monkeypatch.setenv("SESSION_WATCHDOG_ENABLED", "false")
    from services.session_watchdog import redrive_stuck_summary_sessions
    assert redrive_stuck_summary_sessions() == {"enabled": False}


def test_watchdog_marks_stalled_upload_failed_and_retryable(org_and_user, monkeypatch):
    org_id, user_id = org_and_user
    monkeypatch.setenv("UPLOAD_WATCHDOG_MINUTES", "30")
    from database.database import SessionLocal
    from database.models import UploadJob
    from services.session_watchdog import mark_abandoned_uploads

    db = SessionLocal()
    try:
        when = datetime.now(timezone.utc) - timedelta(hours=2)
        job = UploadJob(
            organization_id=org_id,
            user_id=user_id,
            upload_id=uuid.uuid4(),
            filename="meeting.wav",
            action="transcribe",
            total_size=4,
            bytes_received=4,
            chunks_received=1,
            total_chunks=1,
            stage="transcribing",
            created_at=when,
            updated_at=when,
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    result = mark_abandoned_uploads()
    assert result["marked_failed"] >= 1
    db = SessionLocal()
    try:
        job = db.get(UploadJob, job_id)
        assert job.stage == "failed"
        assert "retry is available" in job.error_message
        assert job.job_completed_at is not None
    finally:
        db.close()
