"""Regression tests for always-on meeting date/time wall-clock handling."""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path

import sqlalchemy as sa

from auth.utils import get_password_hash


def _seed_user_and_org():
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal

    slug = f"always-on-dates-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        org = Organization(
            name=slug,
            slug=slug,
            plan="enterprise",
            is_active=True,
            settings={"timezone": "America/New_York"},
        )
        user = User(
            email=f"{slug}@meeting-ops.local",
            username=slug,
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_verified=True,
            tier="enterprise",
        )
        db.add_all([org, user])
        db.flush()
        db.add(UserOrganization(user_id=user.id, organization_id=org.id, role="admin"))
        db.commit()
        return org.id, org.slug, user.username
    finally:
        db.close()


def _login_headers(client, username: str, org_slug: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-MeetingOps-Org": org_slug,
    }


def _load_backfill_migration():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/065_backfill_always_on_meeting_dates.py"
    )
    spec = importlib.util.spec_from_file_location("always_on_dates_migration", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def test_start_always_on_stamps_org_wall_clock_and_created_fallback(
    client, tmp_path, monkeypatch
):
    from api import recording
    from database.database import SessionLocal
    from database.models import RecordingSession

    org_id, org_slug, username = _seed_user_and_org()
    fixed_start = datetime(2026, 10, 22, 1, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(recording, "_now", lambda: fixed_start)
    monkeypatch.setattr(recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recording, "ALWAYS_ON_DIR", tmp_path / "always_on")

    response = client.post(
        "/api/recordings/start-always-on",
        headers=_login_headers(client, username, org_slug),
        json={"client_session_key": f"test-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 200, response.text

    db = SessionLocal()
    try:
        session = (
            db.query(RecordingSession)
            .filter(RecordingSession.session_id == response.json()["id"])
            .one()
        )
        # 01:15 UTC is 21:15 on the prior day in the org's timezone.
        assert session.meeting_date == date(2026, 10, 21)
        assert session.meeting_time == time(21, 15)

        # The helper keeps the creation-path fallback explicit for callers that
        # have a created_at but no started_at.
        assert recording._always_on_meeting_dates(
            db, org_id, None, fixed_start
        ) == (date(2026, 10, 21), time(21, 15))
    finally:
        db.close()


def test_always_on_backfill_converts_per_org_is_idempotent_and_preserves_values():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = _load_backfill_migration()
    assert migration._to_org_wall_clock(
        datetime(2026, 10, 22, 1, 15), "America/New_York"
    ) == (date(2026, 10, 21), time(21, 15))
    assert migration._to_org_wall_clock(
        datetime(2026, 10, 22, 1, 15), None
    ) == (date(2026, 10, 22), time(1, 15))

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE organizations (id INTEGER PRIMARY KEY, settings JSON)"
        ))
        conn.execute(sa.text(
            """CREATE TABLE recording_sessions (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER,
                source_type TEXT,
                started_at DATETIME,
                created_at DATETIME,
                meeting_date DATE,
                meeting_time TIME
            )"""
        ))
        conn.execute(
            sa.text("INSERT INTO organizations (id, settings) VALUES (:id, :settings)"),
            [
                {"id": 1, "settings": json.dumps({"timezone": "America/New_York"})},
                {"id": 2, "settings": json.dumps({})},
            ],
        )
        conn.execute(
            sa.text(
                """INSERT INTO recording_sessions
                (id, organization_id, source_type, started_at, created_at, meeting_date, meeting_time)
                VALUES
                (1, 1, 'browser_always_on', '2026-10-22 01:15:00', '2026-10-22 01:16:00', NULL, NULL),
                (2, 2, 'browser_always_on', NULL, '2026-10-22 01:15:00', NULL, NULL),
                (3, 1, 'browser_always_on', '2026-10-22 01:15:00', NULL, '2026-09-01', NULL),
                (4, 1, 'browser_always_on', '2026-10-22 01:15:00', NULL, NULL, '08:00:00'),
                (5, 1, 'upload', '2026-10-22 01:15:00', NULL, NULL, NULL)
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()

        values = {
            row["id"]: row
            for row in conn.execute(
                sa.text(
                    "SELECT id, meeting_date, meeting_time FROM recording_sessions"
                )
            ).mappings()
        }
        assert values[1]["meeting_date"] == "2026-10-21"
        assert values[1]["meeting_time"].startswith("21:15:00")
        assert values[2]["meeting_date"] == "2026-10-22"
        assert values[2]["meeting_time"].startswith("01:15:00")
        assert values[3]["meeting_date"] == "2026-09-01"
        assert values[3]["meeting_time"].startswith("21:15:00")
        assert values[4]["meeting_date"] == "2026-10-21"
        assert values[4]["meeting_time"].startswith("08:00:00")
        assert values[5]["meeting_date"] is None
        assert values[5]["meeting_time"] is None

        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        unchanged = conn.execute(
            sa.text(
                "SELECT meeting_date, meeting_time FROM recording_sessions WHERE id = 1"
            )
        ).one()
        assert unchanged[0] == "2026-10-21"
        assert unchanged[1].startswith("21:15:00")
