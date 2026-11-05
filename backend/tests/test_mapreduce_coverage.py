"""Map-reduce summary coverage honesty (audit: long-meeting summary correctness).

`_summarize_mapreduce` reduces whatever chunk digests succeed. Previously the
caller then stamped `summary_truncated=False` even when a chunk's map call
failed — silently omitting a time range while claiming full coverage. The
function now returns the dropped chunks so the caller can stamp truncation +
the missing ranges. These tests exercise that contract directly with a mock LLM
(no network).
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _reloaded_app(app):
    """Run the conftest model-reload (the session ``app`` fixture, which reloads
    the model graph and imports ``main`` → all routers) BEFORE these tests touch
    ``api.uploads``. Without it a pure-unit test that runs first would bind the
    app modules to the pre-reload Base, causing a mapper split in later DB tests."""
    return app


class _MockLLM:
    """chat() succeeds for CHUNK_OK map prompts, raises for CHUNK_FAIL, and
    returns a non-empty synthesis for the reduce prompt."""

    async def chat(self, *, system_prompt, user_prompt, max_tokens, temperature, extra_params=None):
        if "CHUNK_FAIL" in user_prompt:
            raise RuntimeError("simulated chunk map failure")
        if "CHUNK_OK" in user_prompt:
            return (
                '{"key_points": ["a point"], "decisions": [], "action_items": [], '
                '"quotes": [], "open_questions": [], "notable": []}'
            )
        return "## Summary\nFinal synthesized notes covering the meeting."


def _run(chunks):
    from api import uploads  # lazy: avoid binding app modules at collection time
    return asyncio.run(
        uploads._summarize_mapreduce(
            _MockLLM(),
            system_prompt="sys",
            speaker_context="",
            chunks=chunks,
            style_prefix="",
        )
    )


def test_mapreduce_reports_dropped_chunk():
    chunks = [
        {"index": 0, "start": 0.0, "end": 60.0, "text": "CHUNK_OK one", "speakers": ["Alice"]},
        {"index": 1, "start": 60.0, "end": 120.0, "text": "CHUNK_FAIL two", "speakers": ["Bob"]},
    ]
    text, missing = _run(chunks)
    assert text.strip()
    assert len(missing) == 1
    assert missing[0]["index"] == 1
    assert "–" in missing[0]["range"]  # a clock range was recorded


def test_mapreduce_full_coverage_when_all_succeed():
    chunks = [
        {"index": 0, "start": 0.0, "end": 60.0, "text": "CHUNK_OK a", "speakers": []},
        {"index": 1, "start": 60.0, "end": 120.0, "text": "CHUNK_OK b", "speakers": []},
    ]
    text, missing = _run(chunks)
    assert text.strip()
    assert missing == []


def test_chunk_budget_counts_each_line_prefix():
    # The measured failure: 14,000-token chunks reached 35,600 real tokens because
    # the budget counted the words and not the prefix on every line.
    from api import uploads

    segments = [
        {"start_s": float(i * 4), "end_s": float(i * 4 + 3), "speaker": "Avery Quimby", "text": "short words here"}
        for i in range(4000)
    ]
    chunks = uploads._chunk_segments(segments, None, chunk_tokens=2000, overlap_tokens=0)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk["text"]) // 4 <= 2200


class _ContextLimitedLLM:
    def __init__(self, limit):
        self.limit = limit
        self.map_calls = 0

    async def chat(self, *, system_prompt, user_prompt, max_tokens, temperature, extra_params=None):
        if "CHUNK DIGESTS" in user_prompt:
            return "## Summary\nFinal synthesized notes covering the meeting."
        self.map_calls += 1
        if user_prompt.count("LINE") > self.limit:
            raise RuntimeError("LLM request failed: Client error '400 Bad Request'")
        return '{"key_points": ["a point"], "decisions": [], "action_items": []}'


def test_oversized_chunk_is_split_and_counted_as_covered():
    from api import uploads

    llm = _ContextLimitedLLM(limit=30)
    body = "\n".join(f"LINE {i}" for i in range(100))
    chunks = [
        {"index": 0, "start": 0.0, "end": 60.0, "text": body, "speakers": []},
        {"index": 1, "start": 60.0, "end": 120.0, "text": "LINE one", "speakers": []},
    ]
    text, missing = asyncio.run(
        uploads._summarize_mapreduce(llm, system_prompt="s", speaker_context="", chunks=chunks)
    )
    assert text.strip() and missing == []
    assert llm.map_calls > 2


def test_chunk_still_oversized_after_splitting_is_reported_missing():
    from api import uploads

    llm = _ContextLimitedLLM(limit=5)
    body = "\n".join(f"LINE {i}" for i in range(100))
    chunks = [
        {"index": 0, "start": 0.0, "end": 60.0, "text": body, "speakers": []},
        {"index": 1, "start": 60.0, "end": 120.0, "text": "LINE one", "speakers": []},
    ]
    text, missing = asyncio.run(
        uploads._summarize_mapreduce(llm, system_prompt="s", speaker_context="", chunks=chunks)
    )
    assert text.strip()
    assert [m["index"] for m in missing] == [0]


class _ProseLLM:
    def __init__(self, reply):
        self.reply = reply

    async def chat(self, *, system_prompt, user_prompt, max_tokens, temperature, extra_params=None):
        if "CHUNK DIGESTS" in user_prompt:
            return "## Summary\nFinal synthesized notes covering the meeting."
        return self.reply


def test_unreadable_digest_is_not_coverage():
    from api import uploads

    chunks = [
        {"index": 0, "start": 0.0, "end": 60.0, "text": "only one line", "speakers": []},
        {"index": 1, "start": 60.0, "end": 120.0, "text": "another line", "speakers": []},
    ]
    with pytest.raises(RuntimeError, match="no usable chunk digests"):
        asyncio.run(
            uploads._summarize_mapreduce(
                _ProseLLM('{"key_points": ["cut off here'),
                system_prompt="s",
                speaker_context="",
                chunks=chunks,
            )
        )


def test_only_empty_digests_refuse_to_reduce():
    from api import uploads

    chunks = [
        {"index": 0, "start": 0.0, "end": 60.0, "text": "only one line", "speakers": []},
        {"index": 1, "start": 60.0, "end": 120.0, "text": "another line", "speakers": []},
    ]
    with pytest.raises(RuntimeError, match="only empty chunk digests"):
        asyncio.run(
            uploads._summarize_mapreduce(
                _ProseLLM('{"key_points": [], "decisions": [], "action_items": []}'),
                system_prompt="s",
                speaker_context="",
                chunks=chunks,
            )
        )
