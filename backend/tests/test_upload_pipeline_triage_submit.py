"""The uploads pipeline (run_upload_pipeline) never called
services.projectops_writer.submit_action_items_to_triage, so sessions
finalized through api/uploads.py — including the Stable transcript bridge
uploads — silently skipped the Project-Ops triage inbox (P-00189, found
2026-09-24 during the backfill; 15 sessions had to be hand-backfilled). The
other finalize paths (api/recording.py ~1228 + ~2389,
workers/finalize_workers.py:321) already call it. This mirrors those calls:
same helper, same completion_mode-style best-effort posture, called once
after the semantic-index step.

These tests drive the real ``run_upload_pipeline`` end to end against the
SQLite test DB, monkeypatching only the heavy/networked stages (STT,
summarization, AI insights pre-warm, semantic indexing, participant
stamping) the same way the rest of the upload pipeline's failure modes are
exercised elsewhere in this suite. Diarization is turned off via
transcription_options so no pyannote call is attempted.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest


def _make_job(db, *, filename="meeting.wav"):
    from auth.models import Organization, User
    from database.models import UploadJob

    org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
    user = db.query(User).filter(User.username == "admin").first()
    job = UploadJob(
        organization_id=org.id,
        user_id=user.id,
        upload_id=uuid.uuid4(),
        filename=filename,
        action="transcribe",
        total_size=4,
        bytes_received=4,
        chunks_received=1,
        total_chunks=1,
        stage="uploaded",
        # Diarization off so the pipeline never reaches pyannote.
        transcription_options={"diarization_mode": "off"},
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _prep_job_dir(uploads, job, db):
    """Write the source file AND a non-empty extracted.wav so the pipeline
    skips the ffmpeg extraction subprocess entirely."""
    from auth.models import Organization

    org = db.query(Organization).filter(Organization.id == job.organization_id).first()
    job_dir = uploads._job_dir(org.slug, str(job.upload_id))
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / job.filename).write_bytes(b"RIFF....WAVEfmt ")
    (job_dir / "extracted.wav").write_bytes(b"RIFF....WAVEfmt ")
    return job_dir


def _patch_heavy_stages(monkeypatch, uploads):
    """Stub every networked/slow stage the pipeline touches on its way to
    the triage-submit call, without touching the DB-only stages (session
    creation, transcript persistence, participant stamping)."""

    async def _fake_transcribe(*_a, **_kw):
        return {
            "segments": [{"text": "hello world", "start": 0.0, "end": 1.0}],
            "language": "en",
            "model": "test-stt",
        }

    monkeypatch.setattr(uploads, "_transcribe_audio", _fake_transcribe)

    async def _fake_summarize(*_a, **_kw):
        return None

    monkeypatch.setattr(uploads, "_summarize_session", _fake_summarize)

    async def _fake_insights(*_a, **_kw):
        class _Insights:
            def model_dump(self):
                return {}

        return _Insights()

    monkeypatch.setattr("api.ai_insights._generate_ai_insights", _fake_insights)

    monkeypatch.setattr(
        "services.semantic_search_service.semantic_search.index_session",
        lambda **_kw: None,
    )

    async def _fake_autostamp(*_a, **_kw):
        return None

    monkeypatch.setattr("api.recording._autostamp_recorder_participant", _fake_autostamp)
    monkeypatch.setattr(uploads, "_stamp_speaker_contacts_fresh", lambda *_a, **_kw: None)


@pytest.mark.asyncio
async def test_successful_upload_pipeline_submits_action_items_to_triage_once(app, monkeypatch):
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    db = SessionLocal()
    try:
        job = _make_job(db)
        _prep_job_dir(uploads, job, db)
        _patch_heavy_stages(monkeypatch, uploads)

        from services.projectops_writer import ProjectOpsWriteResult

        triage_mock = AsyncMock(return_value=ProjectOpsWriteResult(ok=True, mode="triage"))
        monkeypatch.setattr(
            "services.projectops_writer.submit_action_items_to_triage", triage_mock
        )

        await uploads.run_upload_pipeline(str(job.upload_id))

        triage_mock.assert_awaited_once()
        _, kwargs = triage_mock.await_args
        # run_upload_pipeline commits through its OWN db session; expire
        # this session's identity-mapped objects so the re-query below
        # actually reflects those commits instead of stale cached state.
        db.expire_all()
        fresh_job = db.query(UploadJob).filter(UploadJob.id == job.id).first()
        fresh = db.query(RecordingSession).filter(RecordingSession.id == fresh_job.session_id).first()
        assert fresh is not None
        assert fresh.status == "completed"
        assert kwargs["session_pk"] == fresh.id
    finally:
        db.close()


@pytest.mark.asyncio
async def test_triage_exception_does_not_fail_the_session_or_the_upload(app, monkeypatch):
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession, UploadJob

    db = SessionLocal()
    try:
        job = _make_job(db)
        _prep_job_dir(uploads, job, db)
        _patch_heavy_stages(monkeypatch, uploads)

        async def _boom(**_kw):
            raise RuntimeError("Project-Ops unreachable")

        monkeypatch.setattr("services.projectops_writer.submit_action_items_to_triage", _boom)

        await uploads.run_upload_pipeline(str(job.upload_id))

        db.expire_all()
        fresh_job = db.query(UploadJob).filter(UploadJob.upload_id == job.upload_id).first()
        assert fresh_job.stage == "done"
        assert fresh_job.error_message in (None, "")

        fresh_session = db.query(RecordingSession).filter(RecordingSession.id == fresh_job.session_id).first()
        assert fresh_session.status == "completed"
    finally:
        db.close()


def test_upload_triage_call_reuses_the_shared_helper():
    """Guard against a reimplementation: uploads.py must import and call the
    exact same function object services.projectops_writer exposes to
    api/recording.py and workers/finalize_workers.py."""
    import inspect

    from api import uploads
    from services import projectops_writer

    source = inspect.getsource(uploads.run_upload_pipeline)
    assert "from services.projectops_writer import submit_action_items_to_triage" in source
    assert "submit_action_items_to_triage(" in source
    # Idempotency + gating live in the helper itself — already covered by
    # backend/tests/test_projectops_writer.py (replay-skip via the
    # po_triage_submitted_at stamp); this just asserts uploads.py doesn't
    # reimplement that logic.
    assert hasattr(projectops_writer, "submit_action_items_to_triage")
