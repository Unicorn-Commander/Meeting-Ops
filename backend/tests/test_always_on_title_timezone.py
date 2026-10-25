"""Regression tests for the always-on title timezone data migration."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/066_backfill_always_on_titles_timezone.py"
    )
    spec = importlib.util.spec_from_file_location("always_on_title_migration", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def test_always_on_title_backfill_is_exact_and_preserves_user_titles():
    migration = _load_migration()
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
                title TEXT,
                name TEXT,
                title_user_set BOOLEAN
            )"""
        ))
        conn.execute(
            sa.text("INSERT INTO organizations (id, settings) VALUES (:id, :settings)"),
            [
                {"id": 1, "settings": json.dumps({"timezone": "America/New_York"})},
                {"id": 2, "settings": json.dumps({"timezone": "America/Chicago"})},
            ],
        )
        conn.execute(
            sa.text(
                """INSERT INTO recording_sessions
                (id, organization_id, source_type, started_at, created_at,
                 title, name, title_user_set)
                VALUES (:id, :org, :source, :started, :created, :title, :name, :set)"""
            ),
            [
                {
                    "id": 1,
                    "org": 1,
                    "source": "browser_always_on",
                    "started": datetime(2026, 10, 22, 1, 11),
                    "created": datetime(2026, 10, 22, 1, 11),
                    "title": "Always-on 2026-10-22 01:11",
                    "name": "Always-on 2026-10-22 01:11",
                    "set": False,
                },
                {
                    "id": 2,
                    "org": 2,
                    "source": "browser_always_on",
                    "started": datetime(2026, 8, 31, 20, 51),
                    "created": datetime(2026, 8, 31, 20, 51),
                    "title": "Always-on 2026-08-31 20:51",
                    "name": "Always-on 2026-08-31 20:51",
                    "set": False,
                },
                {
                    "id": 3,
                    "org": 1,
                    "source": "browser_always_on",
                    "started": datetime(2026, 10, 22, 1, 11),
                    "created": datetime(2026, 10, 22, 1, 11),
                    "title": "Renamed call",
                    "name": "Always-on 2026-10-22 01:11",
                    "set": True,
                },
                {
                    "id": 4,
                    "org": 1,
                    "source": "browser_always_on",
                    "started": datetime(2026, 10, 22, 1, 11),
                    "created": datetime(2026, 10, 22, 1, 11),
                    "title": "Always-on 2026-10-22 01:12",
                    "name": "Always-on 2026-10-22 01:12",
                    "set": False,
                },
                {
                    "id": 5,
                    "org": 1,
                    "source": "upload",
                    "started": datetime(2026, 10, 22, 1, 11),
                    "created": datetime(2026, 10, 22, 1, 11),
                    "title": "Always-on 2026-10-22 01:11",
                    "name": "Always-on 2026-10-22 01:11",
                    "set": False,
                },
            ],
        )

        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

        rows = conn.execute(
            sa.text("SELECT id, title, name FROM recording_sessions ORDER BY id")
        ).mappings().all()
        assert rows[0] == {
            "id": 1,
            "title": "Always-on 2026-10-21 21:11",
            "name": "Always-on 2026-10-21 21:11",
        }
        assert rows[1] == {
            "id": 2,
            "title": "Always-on 2026-08-31 15:51",
            "name": "Always-on 2026-08-31 15:51",
        }
        # A user title is untouched, while its still-default Original value is
        # repaired so the detail page cannot display a UTC subtitle.
        assert rows[2] == {
            "id": 3,
            "title": "Renamed call",
            "name": "Always-on 2026-10-21 21:11",
        }
        assert rows[3]["title"] == "Always-on 2026-10-22 01:12"
        assert rows[4]["title"] == "Always-on 2026-10-22 01:11"

        # Running the data migration again is a no-op.
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        again = conn.execute(
            sa.text("SELECT id, title, name FROM recording_sessions ORDER BY id")
        ).mappings().all()
        assert again == rows
