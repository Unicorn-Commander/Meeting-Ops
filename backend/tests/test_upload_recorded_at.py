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


# ---------------------------------------------------------------------------
# Cause 1 (2026-09-07 over-the-wire failure): the provenance probe ran on the
# ffmpeg-extracted WAV, which carries no container tags, so creation_time was
# never seen. It must run on the ORIGINAL upload.
# ---------------------------------------------------------------------------

import shutil
import subprocess
from pathlib import Path

import pytest

import api.uploads as up
from api.uploads import provenance_probe_path


def test_probe_path_prefers_original_when_present(tmp_path):
    src = tmp_path / "Call with Rohan Mehta 25Jun2026.m4a"
    wav = tmp_path / "extracted.wav"
    src.write_bytes(b"\x00" * 64)
    wav.write_bytes(b"\x00" * 64)
    assert provenance_probe_path(wav, src) == src


def test_probe_path_falls_back_to_wav_when_original_gone_or_empty(tmp_path):
    src = tmp_path / "orig.m4a"
    wav = tmp_path / "extracted.wav"
    wav.write_bytes(b"\x00" * 64)
    assert provenance_probe_path(wav, src) == wav          # missing
    src.write_bytes(b"")
    assert provenance_probe_path(wav, src) == wav          # empty
    assert provenance_probe_path(wav, None) == wav
    assert provenance_probe_path(None, None) is None


class _FakeDB:
    def add(self, obj): pass
    def flush(self): pass
    def commit(self): pass
    def refresh(self, obj): pass


@pytest.mark.asyncio
async def test_create_upload_session_probes_original_not_wav(monkeypatch, tmp_path):
    """The call site hands build_meeting_provenance the original file, and the
    resulting started_at follows its creation_time."""
    import services.meeting_provenance as mp

    src = tmp_path / "Call with Rohan Mehta 25Jun2026.m4a"
    wav = tmp_path / "extracted.wav"
    src.write_bytes(b"\x00" * 64)
    wav.write_bytes(b"\x00" * 64)

    seen = {}

    def fake_build(**kw):
        seen["audio_path"] = kw.get("audio_path")
        return {
            "schema": "test",
            "when": {
                "recorded_at": {"value": "2026-06-25T04:14:04+00:00",
                                 "source": "audio_metadata.creation_time", "confidence": 0.95},
                "uploaded_at": {"value": kw["uploaded_at"].isoformat(), "source": "server_ingest", "confidence": 1.0},
                "candidates": [],
            },
            "where": {}, "who": {},
        }

    monkeypatch.setattr(mp, "build_meeting_provenance", fake_build)
    monkeypatch.setattr(up, "_persist_upload_audio_to_garage", lambda *a, **k: None)

    job = SimpleNamespace(
        filename=src.name, client_modified_at=datetime(2026, 9, 7, 18, 47, 15, tzinfo=timezone.utc),
        user_id=1, organization_id=9, upload_id="11111111-1111-1111-1111-111111111111",
        audio_sha256="abc", content_type="audio/mp4", session_id=None, action="transcribe",
    )
    session = await up._create_upload_session(_FakeDB(), job, wav, source_path=src)

    assert Path(seen["audio_path"]) == src, "probe must target the ORIGINAL upload"
    assert session.started_at == datetime(2026, 6, 25, 4, 14, 4, tzinfo=timezone.utc)
    assert session.meeting_date == datetime(2026, 6, 25).date()
    assert session.processing_metadata["provenance_probe_file"] == src.name
    assert session.audio_file == str(wav), "the WAV stays the pipeline audio"


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                    reason="ffmpeg/ffprobe not on PATH")
def test_extracted_wav_drops_creation_time_but_original_keeps_it(tmp_path):
    """Pins the mechanism behind cause 1 with real ffmpeg: the m4a carries the
    tag, the 16 kHz mono PCM WAV the pipeline extracts does not."""
    from services.meeting_provenance import probe_recorded_at

    src = tmp_path / "orig.m4a"
    wav = tmp_path / "extracted.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1",
         "-c:a", "aac", "-metadata", "creation_time=2026-06-25T04:14:04Z", str(src)],
        check=True, timeout=60,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "quiet", "-i", str(src), "-vn", "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(wav)],
        check=True, timeout=60,
    )
    assert probe_recorded_at(src) == datetime(2026, 6, 25, 4, 14, 4, tzinfo=timezone.utc)
    assert probe_recorded_at(wav) is None
