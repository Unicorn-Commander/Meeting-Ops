"""An upload's session gets its terminal state the moment the pipeline fails.

Before 2026-09-24 only the UploadJob was marked failed; the session sat at
"processing" until the 6-hour watchdog flipped it with a generic
"stuck-processing" reason (34 of 45 no-speech Stable uploads, measured).
"""
from __future__ import annotations

import uuid

import pytest


def _session(db, status="processing", **extra):
    from auth.models import Organization, User
    from database.models import RecordingSession

    org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
    user = db.query(User).filter(User.username == "admin").first()
    row = RecordingSession(
        session_id=f"test-{uuid.uuid4()}",
        name="upload",
        title="upload",
        status=status,
        user_id=user.id,
        organization_id=org.id,
        **extra,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_no_speech_marks_the_session_failed_with_a_plain_reason(app):
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        row = _session(db, processing_metadata={"kept": 1})
        uploads._mark_session_failed(db, row.id, uploads.NoSpeechDetected(uploads.NO_SPEECH_MESSAGE))
        fresh = db.query(RecordingSession).filter(RecordingSession.id == row.id).first()
        assert fresh.status == "failed"
        assert fresh.processing_metadata["no_speech"] is True
        assert fresh.processing_metadata["skip_reason"] == "no_speech"
        assert fresh.processing_metadata["upload_error"] == uploads.NO_SPEECH_MESSAGE
        assert fresh.processing_metadata["kept"] == 1
        assert fresh.processing_metadata["upload_failed_at"]
    finally:
        db.close()


def test_a_service_error_keeps_its_real_reason(app):
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        row = _session(db)
        uploads._mark_session_failed(db, row.id, RuntimeError("Transcription service error 500: boom"))
        fresh = db.query(RecordingSession).filter(RecordingSession.id == row.id).first()
        assert fresh.status == "failed"
        assert fresh.processing_metadata["no_speech"] is False
        assert "500" in fresh.processing_metadata["upload_error"]
    finally:
        db.close()


def test_a_finished_session_is_never_touched(app):
    from api import uploads
    from database.database import SessionLocal
    from database.models import RecordingSession

    db = SessionLocal()
    try:
        row = _session(db, status="completed")
        uploads._mark_session_failed(db, row.id, RuntimeError("late failure"))
        fresh = db.query(RecordingSession).filter(RecordingSession.id == row.id).first()
        assert fresh.status == "completed"
        assert not (fresh.processing_metadata or {}).get("upload_error")
        uploads._mark_session_failed(db, None, RuntimeError("no session yet"))  # no-op, no raise
    finally:
        db.close()


@pytest.mark.asyncio
async def test_an_empty_pass_raises_no_speech_and_a_provider_error_raises_its_reason(app, monkeypatch, tmp_path):
    from api import uploads

    class _Stt:
        def __init__(self, result):
            self.result = result

        async def transcribe(self, *_a, **_kw):
            return self.result

    class _Registry:
        def __init__(self, result):
            self.result = result

        def get_stt(self, *_a, **_kw):
            return _Stt(self.result)

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    monkeypatch.setattr("services.providers.registry.get_provider_registry", lambda _db: _Registry({"segments": [], "error": None}))
    with pytest.raises(uploads.NoSpeechDetected):
        await uploads._transcribe_audio(audio, 1, None)
    monkeypatch.setattr("services.providers.registry.get_provider_registry", lambda _db: _Registry({"segments": [], "error": "Transcription service error 503"}))
    with pytest.raises(RuntimeError) as err:
        await uploads._transcribe_audio(audio, 1, None)
    assert not isinstance(err.value, uploads.NoSpeechDetected)
    assert "503" in str(err.value)
