"""Shared transcript pagination and rendering for Meeting-Ops tools.

The MCP app receives the REST representation of a recording session while the
RAG agent receives the SQLAlchemy row.  This module keeps their transcript
contracts identical without making either caller know which storage alias
carried the transcript.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from services.speaker_labels import normalized_label_map


DEFAULT_MAX_CHARS = 10_000
MAX_MAX_CHARS = 200_000

_UNKNOWN_SPEAKERS = {"", "none", "null", "unknown", "unknown speaker"}
_SEGMENT_KEYS = ("segments",)


def _read(value: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a mapping or an ORM-style object."""
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _coerce_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_CHARS
    if limit <= 0:
        limit = DEFAULT_MAX_CHARS
    return min(MAX_MAX_CHARS, max(1, limit))


def _coerce_offset(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _speaker_value(segment: Any) -> str:
    speaker = _read(segment, "speaker")
    if isinstance(speaker, Mapping):
        speaker = (
            speaker.get("name")
            or speaker.get("display_name")
            or speaker.get("label")
        )
    if speaker is None:
        speaker = _read(segment, "speaker_name")
    if speaker is None:
        return ""
    speaker = str(speaker).strip()
    return "" if speaker.lower() in _UNKNOWN_SPEAKERS else speaker


def _number(segment: Any, *keys: str) -> float | None:
    for key in keys:
        value = _read(segment, key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _segment_list(value: Any) -> list[Any] | None:
    value = _parse_jsonish(value)
    if not isinstance(value, Mapping):
        return None
    for key in _SEGMENT_KEYS:
        segments = value.get(key)
        if isinstance(segments, list) and segments:
            return segments
    return None


def _candidate_segments(
    source: Any,
    fallback_segments: Sequence[Any] | None,
) -> list[Any] | None:
    """Find the most structured transcript representation available."""
    diarized = _parse_jsonish(_read(source, "transcript_diarized"))
    segments = _segment_list(diarized)
    if segments:
        return segments

    api_segments = _read(source, "transcription_segments")
    if isinstance(api_segments, list) and api_segments:
        return api_segments

    if fallback_segments:
        return list(fallback_segments)

    transcription = _parse_jsonish(_read(source, "transcription"))
    segments = _segment_list(transcription)
    if segments:
        return segments

    raw_transcript = _parse_jsonish(_read(source, "transcript"))
    segments = _segment_list(raw_transcript)
    if segments:
        return segments
    return None


def _normalise_segments(raw_segments: Sequence[Any]) -> list[dict[str, Any]]:
    """Copy transcript segments into a small, timing-aware internal shape."""
    raw_rows = [row for row in raw_segments if row is not None]
    labels = [label for label in (_speaker_value(row) for row in raw_rows) if label]
    label_map = normalized_label_map(labels)

    result: list[dict[str, Any]] = []
    for row in raw_rows:
        text = _read(row, "text", "")
        if text is None:
            text = ""
        text = str(text).strip()
        if not text:
            continue

        raw_speaker = _speaker_value(row)
        speaker = label_map.get(raw_speaker, raw_speaker) if raw_speaker else None
        result.append(
            {
                "start_s": _number(row, "start_s", "start", "start_time"),
                "end_s": _number(row, "end_s", "end", "end_time"),
                "speaker": speaker or None,
                "text": text,
            }
        )
    return result


def _blob_text(source: Any) -> str:
    """Return the best flat-text representation when no segments exist."""
    candidates: list[Any] = [_read(source, "transcript_simple")]

    diarized = _parse_jsonish(_read(source, "transcript_diarized"))
    if isinstance(diarized, Mapping):
        candidates.append(diarized.get("text"))

    transcription = _parse_jsonish(_read(source, "transcription"))
    if isinstance(transcription, Mapping):
        candidates.append(transcription.get("text"))

    raw_transcript = _parse_jsonish(_read(source, "transcript"))
    if isinstance(raw_transcript, Mapping):
        candidates.append(raw_transcript.get("text"))
    else:
        candidates.append(raw_transcript)

    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate)
        if text.strip():
            return text
    return ""


def _duration(source: Any, segments: Sequence[Mapping[str, Any]]) -> float:
    value = _read(source, "duration")
    if value is None:
        for key in ("transcript_diarized", "transcription"):
            nested = _parse_jsonish(_read(source, key))
            if isinstance(nested, Mapping) and nested.get("duration") is not None:
                value = nested.get("duration")
                break

    try:
        duration = float(value or 0)
    except (TypeError, ValueError):
        duration = 0.0

    max_end = max(
        (float(row["end_s"]) for row in segments if row.get("end_s") is not None),
        default=0.0,
    )
    return max(duration, max_end)


def _timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    total_seconds = max(0, int(seconds))
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def _render_segment(segment: Mapping[str, Any]) -> str:
    line = f"[{_timestamp(segment.get('start_s'))}] "
    if segment.get("speaker"):
        line += f"{segment['speaker']}: "
    return line + str(segment.get("text") or "")


def _segment_trailer(next_offset: int, total_segments: int) -> str:
    return (
        f"... truncated: call again with offset={next_offset} "
        f"(total_segments={total_segments})"
    )


def _select_segments(
    segments: Sequence[Mapping[str, Any]],
    *,
    offset: int,
    max_chars: int,
    include_trailer: bool,
) -> tuple[list[Mapping[str, Any]], int | None, bool]:
    """Select complete segments, reserving room for the continuation note."""
    if offset >= len(segments):
        return [], None, False

    selected: list[Mapping[str, Any]] = []
    for segment in segments[offset:]:
        candidate = selected + [segment]
        body = "\n".join(_render_segment(item) for item in candidate)
        next_offset = offset + len(candidate)
        has_more = next_offset < len(segments)
        trailer = (
            _segment_trailer(next_offset, len(segments))
            if has_more and include_trailer
            else ""
        )
        rendered = f"{body}\n\n{trailer}" if trailer else body
        if len(rendered) <= max_chars or not selected:
            selected.append(segment)
            continue
        break

    next_offset = offset + len(selected)
    truncated = next_offset < len(segments)
    return selected, (next_offset if truncated else None), truncated


def _blob_trailer(next_offset: int) -> str:
    return (
        f"{_segment_trailer(next_offset, 0)}. "
        "This transcript is stored as one text blob without segments; "
        "offset is in characters."
    )


def _paginate_blob(
    blob: str,
    *,
    offset: int,
    max_chars: int,
    duration_s: float,
) -> dict[str, Any]:
    if offset >= len(blob):
        return {
            "text": "",
            "segments": [],
            "total_segments": 0,
            "next_offset": None,
            "truncated": False,
            "duration_s": duration_s,
            "transcript_chars": len(blob),
            "has_transcript": bool(blob),
            "blob_only": True,
        }

    prefix = "[--:--] "
    remaining = blob[offset:]
    if len(prefix) + len(remaining) <= max_chars:
        chunk = remaining
        next_offset = None
        truncated = False
    else:
        # Keep the continuation trailer inside the requested text budget when
        # possible. A single character is still emitted for very small limits
        # so every valid call makes progress.
        room = max(1, max_chars - len(prefix))
        end = min(len(blob), offset + room)
        while end > offset:
            trailer = _blob_trailer(end)
            rendered_len = len(prefix) + (end - offset) + 2 + len(trailer)
            if rendered_len <= max_chars:
                break
            end -= 1
        if end <= offset:
            end = min(len(blob), offset + 1)
        chunk = blob[offset:end]
        next_offset = end if end < len(blob) else None
        truncated = next_offset is not None

    text = prefix + chunk
    if truncated and next_offset is not None:
        text += f"\n\n{_blob_trailer(next_offset)}"
    return {
        "text": text,
        "segments": [],
        "total_segments": 0,
        "next_offset": next_offset,
        "truncated": truncated,
        "duration_s": duration_s,
        "transcript_chars": len(blob),
        "has_transcript": bool(blob),
        "blob_only": True,
    }


def paginate_transcript(
    source: Any,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    offset: int = 0,
    format: str = "text",
    fallback_segments: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Build one page of a segmented or blob-only transcript.

    ``offset`` is a segment index when structured segments are available. If
    the session has only flat text, it is a character offset and the returned
    text explicitly says so in its continuation trailer.
    """
    if format not in {"text", "segments"}:
        raise ValueError("format must be 'text' or 'segments'")

    limit = _coerce_limit(max_chars)
    start = _coerce_offset(offset)
    raw_segments = _candidate_segments(source, fallback_segments)
    segments = _normalise_segments(raw_segments) if raw_segments else []
    duration_s = _duration(source, segments)

    if segments:
        selected, next_offset, truncated = _select_segments(
            segments,
            offset=start,
            max_chars=limit,
            include_trailer=format == "text",
        )
        first_index = min(start, len(segments))
        payload = []
        for index, segment in enumerate(selected, first_index):
            item = {
                "index": index,
                "start_s": segment.get("start_s"),
                "end_s": segment.get("end_s"),
                "text": segment.get("text") or "",
            }
            if segment.get("speaker"):
                item["speaker"] = segment["speaker"]
            payload.append(item)

        body = "\n".join(_render_segment(segment) for segment in selected)
        if format == "text" and truncated and next_offset is not None:
            body += f"\n\n{_segment_trailer(next_offset, len(segments))}"
        return {
            "text": body,
            "segments": payload,
            "total_segments": len(segments),
            "next_offset": next_offset,
            "truncated": truncated,
            "duration_s": duration_s,
            "transcript_chars": len(" ".join(row["text"] for row in segments)),
            "has_transcript": True,
            "blob_only": False,
        }

    blob = _blob_text(source)
    return _paginate_blob(
        blob,
        offset=start,
        max_chars=limit,
        duration_s=duration_s,
    )


__all__ = [
    "DEFAULT_MAX_CHARS",
    "MAX_MAX_CHARS",
    "paginate_transcript",
]
