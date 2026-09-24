"""Parakeet sparse-speech retry (2026-09-24).

Parakeet TDT 1.1B returned NOTHING for a 116 s Stable call holding one 2 s
line ("Rook, say ready, please"); the same line in a 30 s window came back
exact. LocalParakeetProvider now re-runs an empty pass on a file longer than
one window in ~30 s windows cut at quiet points. These tests pin when the
retry runs, what it keeps, and that timestamps land back on the whole file.
The HTTP call is faked; the fake behaves like the measured service: long
input -> empty, a window holding the line -> the line.
"""
from __future__ import annotations

import asyncio
import wave

import numpy as np
import pytest

from services.providers import impl_stt
from services.providers.impl_stt import LocalParakeetProvider, _quiet_cut_points

RATE = 16000
LINE = "rook say ready please"


def _write(path, samples):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(samples.astype("<i2").tobytes())


def _call(seconds, *, line_at=None, noise_from=None):
    """Digital silence, a loud 'spoken line' at ``line_at`` (2 s), and faint
    noise (peak 50, above the silence floor) from ``noise_from`` on."""
    samples = np.zeros(int(seconds * RATE), dtype=np.int16)
    if noise_from is not None:
        start = int(noise_from * RATE)
        samples[start:] = (np.random.default_rng(1).uniform(-50, 50, len(samples) - start)).astype(np.int16)
    if line_at is not None:
        start = int(line_at * RATE)
        tone = 8000 * np.sin(np.linspace(0, 2 * np.pi * 220 * 2, 2 * RATE))
        samples[start:start + 2 * RATE] = tone.astype(np.int16)
    return samples


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


def _fake_service(calls, *, window_text=LINE, full_text=None, error=None):
    async def post(*, url, audio_path, **_kw):
        with wave.open(audio_path, "rb") as handle:
            data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
        duration = len(data) / RATE
        calls.append(round(duration, 1))
        if error:
            return None, error
        if duration > 60:  # the measured failure: long mostly-silent input -> nothing
            text = full_text
        else:
            text = window_text if np.abs(data.astype(np.int32)).max() > 4000 else None
        if not text:
            return _Resp({"text": "", "segments": [], "words": [], "duration": duration}), None
        at = float(np.argmax(np.abs(data.astype(np.int32)) > 4000)) / RATE
        return _Resp({
            "text": text,
            "segments": [{"start": at, "end": at + 1.7, "text": text, "confidence": 0.97}],
            "words": [{"word": w, "start": at + i * 0.3, "end": at + i * 0.3 + 0.2} for i, w in enumerate(text.split())],
            "duration": duration,
            "model": "nvidia/parakeet-tdt-1.1b",
        }), None
    return post


def _run(provider, path):
    return asyncio.run(provider.transcribe(str(path)))


def test_an_empty_pass_on_a_long_file_recovers_the_line_from_windows(tmp_path, monkeypatch):
    path = tmp_path / "call.wav"
    _write(path, _call(116, line_at=31.0, noise_from=0.5))
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls))
    result = _run(LocalParakeetProvider(), path)
    assert [s["text"] for s in result["segments"]] == [LINE]
    # The window's own timestamp is shifted back onto the whole file.
    assert result["segments"][0]["start"] == pytest.approx(31.0, abs=0.05)
    assert result["words"][0]["start"] == pytest.approx(31.0, abs=0.05)
    assert result["text"] == LINE
    assert result["sparse_retry"]["windows"] == 4
    assert calls[0] == pytest.approx(116, abs=0.1)
    assert all(d <= 30.0 for d in calls[1:])


def test_speech_found_by_the_full_pass_is_returned_untouched(tmp_path, monkeypatch):
    path = tmp_path / "meeting.wav"
    _write(path, _call(90, line_at=10.0))
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls, full_text="we shipped it today"))
    result = _run(LocalParakeetProvider(), path)
    assert result["segments"][0]["text"] == "we shipped it today"
    assert "sparse_retry" not in result
    assert len(calls) == 1


def test_a_service_error_is_not_retried_and_keeps_its_reason(tmp_path, monkeypatch):
    path = tmp_path / "call.wav"
    _write(path, _call(116, line_at=31.0))
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls, error="Parakeet unreachable"))
    result = _run(LocalParakeetProvider(), path)
    assert result["segments"] == []
    assert result["error"] == "Parakeet unreachable"
    assert len(calls) == 1


def test_one_and_two_word_fragments_do_not_count_as_speech(tmp_path, monkeypatch):
    """Music and clicks gave "four", "five five", "mhm" in the measured windows."""
    path = tmp_path / "music.wav"
    _write(path, _call(116, line_at=31.0, noise_from=0.5))
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls, window_text="five five"))
    result = _run(LocalParakeetProvider(), path)
    assert result["segments"] == []
    assert result.get("error") is None
    assert "sparse_retry" not in result


def test_a_file_no_longer_than_one_window_is_not_retried(tmp_path, monkeypatch):
    path = tmp_path / "short.wav"
    _write(path, _call(25, noise_from=0.0))
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls))
    result = _run(LocalParakeetProvider(), path)
    assert result["segments"] == []
    assert len(calls) == 1


def test_digital_silence_windows_are_never_sent(tmp_path, monkeypatch):
    path = tmp_path / "silent.wav"
    _write(path, _call(116))  # all zeros
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls))
    result = _run(LocalParakeetProvider(), path)
    assert result["segments"] == []
    assert len(calls) == 1  # the full pass only


def test_the_retry_can_be_switched_off(tmp_path, monkeypatch):
    path = tmp_path / "call.wav"
    _write(path, _call(116, line_at=31.0, noise_from=0.5))
    calls: list[float] = []
    monkeypatch.setattr(impl_stt, "_post_audio_with_retry", _fake_service(calls))
    monkeypatch.setenv("PARAKEET_SPARSE_RETRY", "0")
    result = _run(LocalParakeetProvider(), path)
    assert result["segments"] == []
    assert len(calls) == 1


def test_cuts_land_in_the_quietest_slice_and_no_window_is_too_long():
    samples = (np.random.default_rng(2).uniform(-3000, 3000, 70 * RATE)).astype(np.int16)
    samples[int(27.0 * RATE):int(27.4 * RATE)] = 0  # a pause between words
    cuts = _quiet_cut_points(samples, RATE, 30.0)
    assert cuts[0] == 0 and cuts[-1] == len(samples)
    assert 27.0 <= cuts[1] / RATE <= 27.4
    assert all((b - a) / RATE <= 30.0 for a, b in zip(cuts, cuts[1:]))
