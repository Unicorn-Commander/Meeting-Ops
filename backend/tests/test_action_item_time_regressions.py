"""Regression coverage for date-only action-item due dates."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from api.action_items import _date_only_or_none
from api.simple_recording_db import _safe_date_only_or_none
from services.action_items_extractor import _coerce_due
from services.projectops_client import _normalize_due_date
from utils.time import stored_business_date


BUSINESS_ZONE = ZoneInfo("America/New_York")


def test_action_item_date_is_stored_at_business_noon_and_federated_as_date():
    due = _coerce_due({"due_date": "2026-10-16"})
    assert due == datetime(2026, 10, 16, 12, tzinfo=BUSINESS_ZONE)
    assert _date_only_or_none(due) == "2026-10-16"
    assert _safe_date_only_or_none(due) == "2026-10-16"
    assert _normalize_due_date(due) == "2026-10-16"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (
            datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc),
            date(2026, 10, 16),
        ),
        (
            datetime(2026, 10, 16, 16, 0, tzinfo=timezone.utc),
            date(2026, 10, 16),
        ),
        (
            datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc),
            date(2026, 10, 16),
        ),
    ],
    ids=["legacy-utc-midnight", "business-noon", "real-eastern-instant"],
)
def test_all_action_item_date_readers_preserve_the_calendar_date(stored, expected):
    expected_text = expected.isoformat()

    assert stored_business_date(stored) == expected
    assert _date_only_or_none(stored) == expected_text
    assert _safe_date_only_or_none(stored) == expected_text
    assert _normalize_due_date(stored) == expected_text
