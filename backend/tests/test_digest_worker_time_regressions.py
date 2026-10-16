"""Regression coverage for business-zone scheduled digest dates."""

from datetime import datetime, timezone

from workers.weekly_digest_workers import _cron_should_run, _last_week_date_str


def test_scheduled_dates_use_the_completed_business_calendar_window():
    sunday_evening_utc = datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc)
    assert _last_week_date_str(sunday_evening_utc) == "2026-10-05"


def test_digest_cron_guard_tracks_nine_am_new_york_across_dst():
    assert _cron_should_run("day", datetime(2026, 10, 16, 13, 0, tzinfo=timezone.utc))
    assert _cron_should_run("day", datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc))
    assert _cron_should_run("week", datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc))
    assert not _cron_should_run("week", datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc))
