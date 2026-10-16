"""Regression coverage for business-zone scheduled digest dates."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from workers import weekly_digest_workers as worker
from workers.weekly_digest_workers import _cron_should_run, _last_week_date_str

BUSINESS_ZONE = ZoneInfo("America/New_York")


def _utc(local_time: datetime) -> datetime:
    return local_time.astimezone(timezone.utc)


def test_scheduled_dates_use_the_completed_business_calendar_window():
    sunday_evening_utc = datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc)
    assert _last_week_date_str(sunday_evening_utc) == "2026-10-05"


@pytest.mark.parametrize("minute", [0, 1, 59])
def test_digest_cron_guard_accepts_the_entire_nine_am_business_hour(minute):
    assert _cron_should_run(
        "day", _utc(datetime(2026, 10, 16, 9, minute, tzinfo=BUSINESS_ZONE))
    )
    assert _cron_should_run(
        "week", _utc(datetime(2026, 10, 19, 9, minute, tzinfo=BUSINESS_ZONE))
    )


def test_digest_cron_guard_rejects_ten_am_and_non_monday_weekly_ticks():
    assert not _cron_should_run(
        "day", _utc(datetime(2026, 10, 16, 10, 0, tzinfo=BUSINESS_ZONE))
    )
    assert not _cron_should_run(
        "week", _utc(datetime(2026, 10, 19, 10, 0, tzinfo=BUSINESS_ZONE))
    )
    assert not _cron_should_run(
        "week", _utc(datetime(2026, 10, 18, 9, 59, tzinfo=BUSINESS_ZONE))
    )


@pytest.mark.parametrize("minute", [0, 1, 59])
def test_digest_cron_guard_tracks_nine_am_after_the_fall_back(minute):
    monday = _utc(datetime(2026, 11, 2, 9, minute, tzinfo=BUSINESS_ZONE))
    assert monday.hour == 14  # 09:xx ET is 14:xx UTC after the transition.
    assert _cron_should_run("day", monday)
    assert _cron_should_run("week", monday)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("period", "local_start", "expected_date"),
    [
        (
            "day",
            datetime(2026, 10, 16, 9, 59, tzinfo=BUSINESS_ZONE),
            "2026-10-15",
        ),
        (
            "week",
            datetime(2026, 11, 2, 9, 1, tzinfo=BUSINESS_ZONE),
            "2026-10-26",
        ),
    ],
)
async def test_cron_dates_are_derived_from_the_eastern_date_of_that_start(
    monkeypatch, period, local_start, expected_date
):
    start = _utc(local_start)

    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            return start

    monkeypatch.setattr(worker, "datetime", FrozenDateTime)
    scheduled = AsyncMock(return_value={"enabled": True, "period": period})
    if period == "day":
        monkeypatch.setattr(worker, "store_scheduled_digests", scheduled)
        result = await worker.daily_digest_cron({})
        scheduled.assert_awaited_once_with("day", date_str=expected_date)
    else:
        monkeypatch.setattr(worker, "send_weekly_digests_for_all_orgs", scheduled)
        result = await worker.weekly_digest_cron({})
        scheduled.assert_awaited_once_with(date_str=expected_date)
    assert result["period"] == period
