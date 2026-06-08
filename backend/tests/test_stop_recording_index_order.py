"""Ordering guard for the primary record->stop completion path (v3.29.2).

`simple_recording_db.process_recording` is the main record->stop pipeline. It
used to call `semantic_search.index_session` BEFORE `identify_speakers`, so the
vector copy of every normal meeting embedded raw SPEAKER_xx labels instead of
real names — degrading cross-meeting RAG attribution until a reprocess healed
it — even though the inline comment claimed "rewrite labels BEFORE embedding".
v3.29.2 swapped them (identify first, then index built FROM the now
speaker-named diarized segments, mirroring reprocess Stage-5.9).

The equivalent SERVICE-LEVEL behavior (index_session called with a
speaker-named transcript after identify) is already pinned end-to-end for the
reprocess pipeline in test_reprocess_indexing.py. Driving the full
process_recording here would need ~6 stubbed leaf calls (STT, diarize, assign,
vocab, summary LLM, identify, index), most of them function-local imports — a
brittle harness for what is fundamentally an ordering invariant. So this guard
pins the invariant directly + cheaply: in process_recording's source, the
identify_speakers() call must precede the index_session() call. If a future
refactor reintroduces the bug by moving the blocks, this goes red.
"""
from __future__ import annotations

import inspect


def test_process_recording_identifies_speakers_before_indexing():
    import api.simple_recording_db as srdb

    src = inspect.getsource(srdb.process_recording)

    # The actual call sites (not the imports, which lack the trailing "(").
    identify_pos = src.find("identify_speakers(")
    index_pos = src.find("index_session(")

    assert identify_pos != -1, "identify_speakers() call not found in process_recording"
    assert index_pos != -1, "index_session() call not found in process_recording"
    assert identify_pos < index_pos, (
        "process_recording must call identify_speakers() BEFORE index_session() "
        "so the embedded transcript carries real speaker names (v3.29.2 fix)"
    )


def test_process_recording_indexes_from_diarized_segments():
    """The index transcript is built speaker-aware from transcript_diarized
    segments ('{speaker}: {text}'), not from the label-less transcript_simple
    — same shape as reprocess Stage-5.9."""
    import api.simple_recording_db as srdb

    src = inspect.getsource(srdb.process_recording)
    # The speaker-aware join lives right before the index_session call.
    index_pos = src.find("index_session(")
    window = src[max(0, index_pos - 800):index_pos]
    assert "transcript_diarized" in window, (
        "index transcript should be built from transcript_diarized segments"
    )
    assert "speaker" in window.lower(), (
        "index transcript should prefix each line with the segment speaker"
    )
