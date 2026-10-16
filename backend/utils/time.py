"""Explicit business-calendar time helpers.

Storage and comparisons remain UTC. Calendar values that describe Meeting-Ops
business time are resolved in New York, including the DST transition.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = "America/New_York"
BUSINESS_ZONE = ZoneInfo(BUSINESS_TIMEZONE)


def utc_to_business(value: datetime) -> datetime:
    """Convert a UTC instant to the business zone.

    Legacy SQLAlchemy ``DateTime`` columns can return a naive value even
    though the application writes UTC. Treat that boundary value as UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BUSINESS_ZONE)


def business_date_from_utc(value: datetime) -> date:
    """Return the New York calendar date represented by a UTC timestamp."""
    return utc_to_business(value).date()


def business_today(now: Optional[datetime] = None) -> date:
    """Return today's date in the business zone."""
    return business_date_from_utc(now or datetime.now(timezone.utc))


def business_date_noon(value: date) -> datetime:
    """Encode a date-only value in the existing timestamp column.

    Action-item ``due_date`` is semantically a calendar date, but the existing
    schema is ``DateTime``. Local noon is safely inside the date in every
    New York DST offset and renders as the same calendar date to the business
    viewer without a migration.
    """
    return datetime.combine(value, time(hour=12), tzinfo=BUSINESS_ZONE)


def normalize_business_date(value: date | datetime) -> datetime:
    """Normalize a date/date-time input to the date's business-zone noon."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=BUSINESS_ZONE)
        else:
            value = value.astimezone(BUSINESS_ZONE)
        value = value.date()
    return business_date_noon(value)


def stored_business_date(value: datetime) -> date:
    """Read the calendar date represented by a stored date-only timestamp.

    New values are stored at business noon. A naive value therefore means
    business-local wall time at this boundary (as SQLite returns it), while an
    aware value is converted from its stored instant.
    """
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(BUSINESS_ZONE).date()


def business_window_utc(start: date, end: date) -> tuple[datetime, datetime]:
    """Convert a half-open local-date window to aware UTC instants."""
    start_local = datetime.combine(start, time.min, tzinfo=BUSINESS_ZONE)
    end_local = datetime.combine(end, time.min, tzinfo=BUSINESS_ZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
