"""Regression coverage for the meeting-date timestamp fallback."""

from datetime import datetime, timezone
from types import SimpleNamespace

from api.simple_recording_db import _effective_meeting_date


def test_meeting_date_fallback_converts_utc_timestamp_to_business_date():
    session = SimpleNamespace(
        meeting_date=None,
        started_at=datetime(2026, 10, 17, 3, 30, tzinfo=timezone.utc),
        created_at=datetime(2026, 10, 17, 3, 31, tzinfo=timezone.utc),
    )
    assert _effective_meeting_date(session).isoformat() == "2026-10-16"
