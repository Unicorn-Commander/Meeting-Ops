"""Regression coverage for business-zone digest API windows."""

from datetime import datetime, timezone

from api.digests import _get_date_range


def test_digest_day_window_uses_business_midnight_and_dst_transition():
    start, end = _get_date_range("day", "2026-10-16")
    assert start == datetime(2026, 10, 16, 4, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 17, 4, tzinfo=timezone.utc)

    fall_back_start, fall_back_end = _get_date_range("day", "2026-11-01")
    assert fall_back_start == datetime(2026, 11, 1, 4, tzinfo=timezone.utc)
    assert fall_back_end == datetime(2026, 11, 2, 5, tzinfo=timezone.utc)


def test_digest_periods_snap_to_business_calendar_boundaries():
    expected = {
        "week": (datetime(2026, 10, 12, 4, tzinfo=timezone.utc), datetime(2026, 10, 19, 4, tzinfo=timezone.utc)),
        "month": (datetime(2026, 10, 1, 4, tzinfo=timezone.utc), datetime(2026, 11, 1, 4, tzinfo=timezone.utc)),
        "quarter": (datetime(2026, 10, 1, 4, tzinfo=timezone.utc), datetime(2027, 1, 1, 5, tzinfo=timezone.utc)),
        "year": (datetime(2026, 1, 1, 5, tzinfo=timezone.utc), datetime(2027, 1, 1, 5, tzinfo=timezone.utc)),
    }
    for period, bounds in expected.items():
        assert _get_date_range(period, "2026-10-16") == bounds
