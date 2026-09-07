"""started_at / ended_at for uploaded recordings follow the recorded-at
provenance signal (audio creation_time > filename > client mtime), never the
upload-time floor, never the future."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from api.uploads import ended_at_from_started, started_at_from_recorded

NOW = datetime(2026, 9, 7, 18, 0, 0, tzinfo=timezone.utc)


def _rec(value, source="audio_metadata.creation_time"):
    return {"value": value, "source": source, "confidence": 0.95}


def test_audio_metadata_wins():
    got = started_at_from_recorded(_rec("2026-09-05T00:54:26+00:00"), NOW)
    assert got == datetime(2026, 9, 5, 0, 54, 26, tzinfo=timezone.utc)


def test_client_mtime_used_when_that_is_the_best_signal():
    got = started_at_from_recorded(_rec("2026-09-02T18:01:16Z", "client_file_mtime"), NOW)
    assert got == datetime(2026, 9, 2, 18, 1, 16, tzinfo=timezone.utc)


def test_upload_time_floor_falls_back_to_ingest():
    assert started_at_from_recorded(_rec(NOW.isoformat(), "upload_time"), NOW) is NOW


def test_missing_or_garbage_falls_back_to_ingest():
    assert started_at_from_recorded(None, NOW) is NOW
    assert started_at_from_recorded({}, NOW) is NOW
    assert started_at_from_recorded(_rec("not a date"), NOW) is NOW


def test_future_and_zeroed_tags_fall_back_to_ingest():
    assert started_at_from_recorded(_rec("2027-01-01T00:00:00Z"), NOW) is NOW
    assert started_at_from_recorded(_rec("1904-01-01T00:00:00Z"), NOW) is NOW


def test_naive_value_treated_as_utc():
    got = started_at_from_recorded(_rec("2026-09-05 00:54:26"), NOW)
    assert got.tzinfo is not None and got.hour == 0 and got.minute == 54


def test_ended_at_is_start_plus_duration():
    s = SimpleNamespace(started_at=datetime(2026, 9, 5, 0, 54, 26), duration=938.1)
    assert ended_at_from_started(s) == datetime(2026, 9, 5, 0, 54, 26, tzinfo=timezone.utc) + timedelta(seconds=938.1)


def test_ended_at_none_without_inputs():
    assert ended_at_from_started(SimpleNamespace(started_at=None, duration=10)) is None
    assert ended_at_from_started(SimpleNamespace(started_at=NOW, duration=0)) is None
