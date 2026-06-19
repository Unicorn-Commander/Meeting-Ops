from datetime import datetime, timedelta, timezone
import uuid


def test_retention_is_off_by_default(monkeypatch):
    from services.data_retention import run_data_retention_purge

    monkeypatch.delenv("MEETING_RETENTION_ENABLED", raising=False)
    assert run_data_retention_purge() == {"enabled": False, "deleted": 0}


def test_retention_deletes_only_expired_completed_sessions(app, monkeypatch):
    from auth.models import Organization, User
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.data_retention import run_data_retention_purge
    from services.semantic_search_service import semantic_search

    monkeypatch.setenv("MEETING_RETENTION_ENABLED", "true")
    monkeypatch.setenv("MEETING_RETENTION_DAYS", "30")
    monkeypatch.setattr(semantic_search, "delete_session", lambda session_id: True)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
        org.settings = {**(org.settings or {}), "retention_days": 30}
        user = db.query(User).filter(User.username == "admin").first()
        old = RecordingSession(
            session_id=str(uuid.uuid4()), name="expired", status="completed",
            organization_id=org.id, user_id=user.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=45),
        )
        recent = RecordingSession(
            session_id=str(uuid.uuid4()), name="recent", status="completed",
            organization_id=org.id, user_id=user.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        db.add_all([old, recent])
        db.commit()
        old_id, recent_id = old.id, recent.id
    finally:
        db.close()

    result = run_data_retention_purge()
    assert result["deleted"] >= 1
    db = SessionLocal()
    try:
        assert db.get(RecordingSession, old_id) is None
        assert db.get(RecordingSession, recent_id) is not None
    finally:
        db.close()
