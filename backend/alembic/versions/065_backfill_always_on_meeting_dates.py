"""Backfill browser always-on meeting dates in each organization's timezone.

Revision ID: 065_backfill_always_on_meeting_dates
Revises: 064_backfill_legacy_weekly_digest_email

The original always-on creation path left ``meeting_date`` and
``meeting_time`` NULL. This revision fills only those NULL fields for browser
always-on rows, using ``started_at`` and falling back to ``created_at`` as UTC
instants. The conversion delegates to the same ``wall_clock`` helper used by
the upload path; an unset/invalid organization timezone therefore has the
app's existing UTC fallback.

Downgrade is intentionally a no-op: the backfill is data repair, and clearing
user-editable meeting metadata would be destructive.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from alembic import op
import sqlalchemy as sa

from services.meeting_provenance import wall_clock


revision = "065_backfill_always_on_meeting_dates"
down_revision = "064_backfill_legacy_weekly_digest_email"
branch_labels = None
depends_on = None


def _timezone_from_settings(raw_settings: Any) -> Optional[str]:
    """Read the same top-level organization timezone used by the app."""
    settings = raw_settings
    if isinstance(settings, str):
        try:
            settings = json.loads(settings or "{}")
        except (TypeError, ValueError):
            return None
    if not isinstance(settings, dict):
        return None
    timezone_name = settings.get("timezone")
    return timezone_name if isinstance(timezone_name, str) else None


def _to_org_wall_clock(
    timestamp: Optional[datetime], timezone_name: Optional[str]
):
    """Convert a stored UTC timestamp using the upload-path wall-clock rule."""
    return wall_clock(timestamp, timezone_name)


def upgrade() -> None:
    bind = op.get_bind()
    sessions = sa.table(
        "recording_sessions",
        sa.column("id", sa.Integer),
        sa.column("organization_id", sa.Integer),
        sa.column("source_type", sa.String),
        sa.column("started_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("meeting_date", sa.Date),
        sa.column("meeting_time", sa.Time),
    )
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Integer),
        sa.column("settings", sa.JSON),
    )

    rows = bind.execute(
        sa.select(
            sessions.c.id,
            sessions.c.started_at,
            sessions.c.created_at,
            sessions.c.meeting_date,
            sessions.c.meeting_time,
            organizations.c.settings,
        )
        .select_from(
            sessions.outerjoin(
                organizations,
                organizations.c.id == sessions.c.organization_id,
            )
        )
        .where(
            sessions.c.source_type == "browser_always_on",
            sa.or_(
                sessions.c.meeting_date.is_(None),
                sessions.c.meeting_time.is_(None),
            ),
        )
    ).mappings().all()

    for row in rows:
        meeting_date, meeting_time = _to_org_wall_clock(
            row["started_at"] or row["created_at"],
            _timezone_from_settings(row["settings"]),
        )
        values = {}
        if row["meeting_date"] is None and meeting_date is not None:
            values["meeting_date"] = meeting_date
        if row["meeting_time"] is None and meeting_time is not None:
            values["meeting_time"] = meeting_time
        if not values:
            continue

        predicates = [
            sessions.c.id == row["id"],
            sessions.c.source_type == "browser_always_on",
        ]
        if "meeting_date" in values:
            predicates.append(sessions.c.meeting_date.is_(None))
        if "meeting_time" in values:
            predicates.append(sessions.c.meeting_time.is_(None))
        bind.execute(
            sessions.update().where(*predicates).values(**values)
        )


def downgrade() -> None:
    # This is a data backfill; do not erase user-editable metadata on rollback.
    pass
