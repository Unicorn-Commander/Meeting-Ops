"""Backfill legacy always-on titles into each organization's timezone.

The original browser always-on path formatted the UTC ``started_at`` value
directly.  This revision repairs only the exact default title produced by
that path, leaving user-renamed titles untouched.  ``name`` is repaired when
it still contains the same default so SessionDetails does not show a stale
UTC value in its ``Original: ...`` subtitle.

Downgrade is intentionally a no-op: the repair is data-only and restoring the
UTC text would reintroduce the bug or overwrite a later user edit.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from alembic import op
import sqlalchemy as sa

from services.meeting_provenance import wall_clock


revision = "066_backfill_always_on_titles_timezone"
down_revision = "065_backfill_always_on_meeting_dates"
branch_labels = None
depends_on = None


_AUTO_TITLE_RE = re.compile(r"^Always-on \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def _timezone_from_settings(raw_settings: Any) -> Optional[str]:
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


def _wall_title(timestamp: datetime, timezone_name: Optional[str]) -> Optional[str]:
    meeting_date, meeting_time = wall_clock(timestamp, timezone_name)
    if meeting_date is None or meeting_time is None:
        return None
    return f"Always-on {meeting_date:%Y-%m-%d} {meeting_time:%H:%M}"


def _matching_timestamp(
    title: Any,
    started_at: Optional[datetime],
    created_at: Optional[datetime],
) -> Optional[datetime]:
    if not isinstance(title, str) or not _AUTO_TITLE_RE.fullmatch(title):
        return None

    # The live path used started_at; created_at is included for older rows and
    # internal creation paths where started_at was not populated.
    for timestamp in (started_at, created_at):
        if timestamp is None:
            continue
        utc_title = _wall_title(timestamp, "UTC")
        if utc_title == title:
            return timestamp
    return None


def upgrade() -> None:
    bind = op.get_bind()
    sessions = sa.table(
        "recording_sessions",
        sa.column("id", sa.Integer),
        sa.column("organization_id", sa.Integer),
        sa.column("source_type", sa.String),
        sa.column("started_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("title", sa.String),
        sa.column("name", sa.String),
        sa.column("title_user_set", sa.Boolean),
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
            sessions.c.title,
            sessions.c.name,
            sessions.c.title_user_set,
            organizations.c.settings,
        )
        .select_from(
            sessions.outerjoin(
                organizations,
                organizations.c.id == sessions.c.organization_id,
            )
        )
        .where(sessions.c.source_type == "browser_always_on")
    ).mappings().all()

    for row in rows:
        timezone_name = _timezone_from_settings(row["settings"])
        title_timestamp = _matching_timestamp(
            row["title"], row["started_at"], row["created_at"]
        )
        name_timestamp = _matching_timestamp(
            row["name"], row["started_at"], row["created_at"]
        )
        values = {}

        # A user-set title is never rewritten, even if it happens to look
        # exactly like the old default.  The name repair below is independent:
        # it only fixes a still-default Original subtitle.
        if title_timestamp is not None and not row["title_user_set"]:
            replacement = _wall_title(title_timestamp, timezone_name)
            if replacement and replacement != row["title"]:
                values["title"] = replacement

        if name_timestamp is not None:
            replacement = _wall_title(name_timestamp, timezone_name)
            if replacement and replacement != row["name"]:
                values["name"] = replacement

        if values:
            bind.execute(
                sessions.update()
                .where(sessions.c.id == row["id"])
                .values(**values)
            )


def downgrade() -> None:
    # Do not restore the buggy UTC labels or overwrite later edits.
    pass
