"""Grounding and rendering helpers for structured meeting summaries.

The summary JSON columns are intentionally additive: older rows may not have
``cites`` or ``participants`` at all.  New summaries are checked here before
they are persisted or rendered as facts.
"""

from __future__ import annotations

import bisect
import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any


MAX_CITATION_QUOTE_CHARS = 160
_GENERIC_SPEAKER_RE = re.compile(r"^(?:speaker|spk|s)[ _-]?\d+$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]+")
_NON_PERSON_NAMES = {
    "none",
    "none identified",
    "not specified",
    "unknown",
    "unknown speaker",
    "unicorn stable transcript bridge",
}


def normalize_grounding_text(value: Any) -> str:
    """Normalize case, whitespace and punctuation for transcript membership checks.

    Speech-to-text punctuation is a guess, so a model that quotes the same words
    with a different comma is still quoting them. The words must all match.
    """
    words = _PUNCTUATION_RE.sub(" ", str(value or "").casefold())
    return _WHITESPACE_RE.sub(" ", words).strip()


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_citation_time(value: Any) -> str | None:
    """Return a citation clock in the API/MCP ``mm:ss`` form."""
    seconds = _number(value)
    if seconds is None:
        return None
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _citation_values(item: Any) -> tuple[bool, Any]:
    if not isinstance(item, Mapping):
        return False, None
    if "cites" in item:
        return True, item.get("cites")
    if "citations" in item:
        return True, item.get("citations")
    return False, None


def get_item_cites(item: Any) -> list[dict[str, Any]]:
    """Read the additive citation list, tolerating one legacy citation dict."""
    present, raw = _citation_values(item)
    if not present:
        return []
    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [dict(cite) for cite in raw if isinstance(cite, Mapping)]


def _canonical_citation(cite: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(cite, Mapping):
        return None, "citation is not an object"

    quote = cite.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        # Accept the common ``text`` spelling only as an input convenience;
        # storage always uses the contract's ``quote`` key.
        quote = cite.get("text")
    if not isinstance(quote, str) or not quote.strip():
        return None, "citation quote is missing"
    quote = quote.strip()

    start = cite.get("start_s", cite.get("start", cite.get("start_time")))
    end = cite.get("end_s", cite.get("end", cite.get("end_time")))
    speaker = cite.get("speaker") or cite.get("speaker_id") or ""
    start_value = _number(start)
    end_value = _number(end)
    # The quote is what gets checked against the transcript. Times are only a
    # pointer into it, and a flat transcript has none to offer, so a verified
    # quote without them stays a fact; it just renders no marker.
    canonical: dict[str, Any] = {
        "speaker": str(speaker).strip(),
        "quote": quote,
    }
    if start_value is not None:
        canonical["start_s"] = start_value
    if end_value is not None:
        canonical["end_s"] = end_value
    return canonical, None


def _shorten_quote(quote: str) -> str:
    """The leading part of a verified quote, cut at a word, within the limit."""
    if len(quote) <= MAX_CITATION_QUOTE_CHARS:
        return quote
    head = quote[:MAX_CITATION_QUOTE_CHARS]
    return head.rsplit(" ", 1)[0] if " " in head else head


def validate_item_cites(
    item: Any,
    transcript_text: str,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Validate an item's explicit cites against normalized transcript text.

    ``None`` means the item is an old, citation-less item and is retained for
    backward compatibility.  A non-None empty result is invalid and carries a
    reason, so a newly emitted but malformed citation cannot become a fact.
    """
    present, raw = _citation_values(item)
    if not present:
        # Some model versions put a single quote on the item itself. Normalize
        # that shape when it is clearly a citation-bearing object.
        if isinstance(item, Mapping) and "quote" in item:
            raw = [{
                "start_s": item.get("start_s", item.get("start")),
                "end_s": item.get("end_s", item.get("end")),
                "speaker": item.get("speaker", ""),
                "quote": item.get("quote"),
            }]
            present = True
        else:
            return None, None

    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None, "citation list is empty"

    normalized_transcript = normalize_grounding_text(transcript_text)
    normalized: list[dict[str, Any]] = []
    for raw_cite in raw:
        cite, reason = _canonical_citation(raw_cite)
        if cite is None:
            return None, reason or "citation is invalid"
        if normalize_grounding_text(cite["quote"]) not in normalized_transcript:
            return None, "citation quote was not found in the transcript"
        # A true quote that ran long is still true: keep the commitment and store
        # a shorter span of it. Only a quote the transcript lacks loses the item.
        cite["quote"] = _shorten_quote(cite["quote"])
        normalized.append(cite)
    return normalized, None


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        for key in ("text", "action", "task", "decision", "title", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(item)


def citation_markers(cites: Any) -> list[str]:
    """Return unique ``[mm:ss]`` markers in citation order."""
    if isinstance(cites, Mapping):
        cites = [cites]
    if not isinstance(cites, list):
        return []
    markers: list[str] = []
    seen: set[str] = set()
    for cite in cites:
        if not isinstance(cite, Mapping):
            continue
        stamp = format_citation_time(
            cite.get("start_s", cite.get("start", cite.get("start_time")))
        )
        if stamp is None or stamp in seen:
            continue
        seen.add(stamp)
        markers.append(f"[{stamp}]")
    return markers


def render_cited_item(item: Any, *, plain: bool = False) -> str:
    """Render an item with citation markers, or leave old items unchanged.

    Plain renderings include the requested ``(cited: mm:ss)`` suffix.  The
    marker form is used by structured/API-adjacent text renderers.
    """
    text = _item_text(item)
    markers = citation_markers(get_item_cites(item))
    if not markers:
        return text
    times = [marker[1:-1] for marker in markers]
    if plain:
        return f"{text} {' '.join(markers)} (cited: {', '.join(times)})"
    return f"{text} {' '.join(markers)}"


def _participant_fields(entry: Any) -> tuple[str, str, bool]:
    if isinstance(entry, str):
        return entry.strip(), "", False
    if not isinstance(entry, Mapping):
        return "", "", False
    name = ""
    for key in ("name", "display_name", "full_name", "person"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            name = value.strip()
            break
    if normalize_grounding_text(name) in _NON_PERSON_NAMES:
        name = ""
    speaker_id = ""
    for key in ("speaker_id", "speakerId", "raw_label", "speaker", "id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            speaker_id = value.strip()
            break
    voice_matched = any(
        entry.get(key) is True
        for key in ("voice_matched", "voiceMatch", "voice_match", "matched_by_voice")
    ) or str(entry.get("match_source") or "").casefold() in {
        "voice",
        "voice_match",
        "speaker_service",
    }
    return name, speaker_id, voice_matched


def _names_no_person(entry: Any) -> bool:
    """A recorder or placeholder row is not a participant, whatever ids it carries."""
    if not isinstance(entry, Mapping):
        return False
    return any(
        isinstance(entry.get(key), str)
        and normalize_grounding_text(entry.get(key)) in _NON_PERSON_NAMES
        for key in ("name", "display_name", "full_name", "person")
    )


def dedupe_participants(entries: Any) -> list[Any]:
    """Dedupe participants by normalized name and/or diarized speaker id.

    Generic diarized labels are speakers, not people. They are excluded from
    this participant list unless the voice-match path supplied a named person.
    The first row wins, with missing fields filled from later duplicates.
    """
    if not isinstance(entries, list):
        return []
    output: list[Any] = []
    key_to_index: dict[str, int] = {}
    for raw in entries:
        name, speaker_id, voice_matched = _participant_fields(raw)
        if not name and not speaker_id:
            continue
        if _names_no_person(raw):
            continue
        if (
            _GENERIC_SPEAKER_RE.fullmatch(name or "")
            or (not name and _GENERIC_SPEAKER_RE.fullmatch(speaker_id or ""))
        ) and not voice_matched:
            continue

        keys = {
            f"name:{normalize_grounding_text(name)}" if name else "",
            f"speaker:{normalize_grounding_text(speaker_id)}" if speaker_id else "",
        } - {""}
        existing_index = next(
            (key_to_index[key] for key in keys if key in key_to_index),
            None,
        )
        if existing_index is None:
            value = copy.deepcopy(raw)
            if isinstance(value, str):
                value = {"name": value}
            output.append(value)
            existing_index = len(output) - 1
        elif isinstance(output[existing_index], dict) and isinstance(raw, Mapping):
            for key, value in raw.items():
                if not output[existing_index].get(key) and value:
                    output[existing_index][key] = copy.deepcopy(value)
        for key in keys:
            key_to_index[key] = existing_index
    return _merge_first_names(output)


def _merge_first_names(rows: list[Any]) -> list[Any]:
    """Fold "Paul" into "Paul Trappitt" when he is the only full name it could be.

    A voice match and a transcript label often name one person two ways. Two
    full names sharing the first name stay apart, along with the bare one, since
    nothing says which of them it was.
    """
    names = [_participant_fields(row)[0] for row in rows]
    folded: set[int] = set()
    for index, name in enumerate(names):
        parts = normalize_grounding_text(name).split(" ")
        if len(parts) != 1 or not parts[0]:
            continue
        fuller = [
            other
            for other, candidate in enumerate(names)
            if other != index
            and len(tokens := normalize_grounding_text(candidate).split(" ")) > 1
            and tokens[0] == parts[0]
        ]
        if len(fuller) != 1:
            continue
        target = rows[fuller[0]]
        source = rows[index]
        if isinstance(target, dict) and isinstance(source, Mapping):
            for key, value in source.items():
                if key != "name" and not target.get(key) and value:
                    target[key] = copy.deepcopy(value)
        folded.add(index)
    return [row for index, row in enumerate(rows) if index not in folded]


def _unverified_entry(kind: str, item: Any, reason: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": kind,
        "item": copy.deepcopy(item),
        "reason": reason,
    }
    if isinstance(item, Mapping):
        for key in ("text", "action", "task", "decision", "owner", "assignee"):
            if key in item:
                entry[key] = copy.deepcopy(item[key])
    else:
        entry["text"] = str(item)
    return entry


def _ground_list(
    summary: dict[str, Any],
    key: str,
    transcript_text: str,
    unverified: list[dict[str, Any]],
    kind: str,
) -> None:
    values = summary.get(key)
    if not isinstance(values, list):
        return
    kept: list[Any] = []
    for item in values:
        cites, reason = validate_item_cites(item, transcript_text)
        if reason:
            unverified.append(_unverified_entry(kind, item, reason))
            continue
        if cites is not None:
            stamped = copy.deepcopy(item)
            if isinstance(stamped, dict):
                stamped["cites"] = cites
                stamped.pop("citations", None)
                kept.append(stamped)
            else:
                # A citation-bearing primitive is not a valid storage shape;
                # retain the fact only when it had no explicit cites.
                kept.append(item)
        else:
            kept.append(item)
    summary[key] = kept


def _project_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("name", "project", "title", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def ground_summary(
    summary: Any,
    transcript_text: str,
    *,
    participants: Any = None,
    speakers: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a summary with unverifiable facts removed from fact lists."""
    if not isinstance(summary, dict):
        return {}
    grounded = copy.deepcopy(summary)
    unverified = [
        copy.deepcopy(item)
        for item in (grounded.get("unverified") or [])
        if isinstance(item, dict)
    ]

    _ground_list(grounded, "decisions", transcript_text, unverified, "decision")
    _ground_list(grounded, "key_decisions", transcript_text, unverified, "decision")
    for key in ("actions", "action_items", "commitments"):
        _ground_list(grounded, key, transcript_text, unverified, "commitment")

    normalized_transcript = normalize_grounding_text(transcript_text)
    for key in ("projects", "project_names", "mentioned_projects"):
        values = grounded.get(key)
        if not isinstance(values, list):
            continue
        grounded[key] = [
            value
            for value in values
            if (name := _project_name(value))
            and normalize_grounding_text(name) in normalized_transcript
        ]

    if participants is not None:
        supplied = list(participants) if isinstance(participants, list) else []
        generated = grounded.get("participants")
        if isinstance(generated, list):
            supplied.extend(generated)
        grounded["participants"] = dedupe_participants(supplied)
    elif "participants" in grounded:
        grounded["participants"] = dedupe_participants(grounded.get("participants"))

    grounded["unverified"] = unverified
    return grounded


def render_timestamped_segments(
    segments: Sequence[Mapping[str, Any]],
    label_map: Mapping[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Render one prompt line per segment: ``[start-end] Speaker: words``.

    Times are whole seconds. Digits tokenize badly and this prefix repeats on
    every line, so it stays as short as a usable citation allows.
    """
    lines: list[str] = []
    speakers: list[str] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text or segment.get("kind") == "marker":
            continue
        raw_speaker = str(segment.get("speaker") or "").strip()
        speaker = (label_map or {}).get(raw_speaker, raw_speaker) or "Speaker"
        if speaker not in speakers:
            speakers.append(speaker)
        start = _number(segment.get("start_s", segment.get("start", segment.get("start_time"))))
        end = _number(segment.get("end_s", segment.get("end", segment.get("end_time"))))
        start_s = start if start is not None else 0.0
        end_s = end if end is not None else start_s
        lines.append(f"[{start_s:.0f}-{end_s:.0f}] {speaker}: {text}")
    return "\n".join(lines), speakers


def spoken_text(segments: Sequence[Mapping[str, Any]]) -> str:
    """The words alone, for checking quotes.

    A quote that runs across two lines must still verify, and a time prefix or
    speaker label must never count as something that was said.
    """
    return "\n".join(
        text
        for segment in segments
        if segment.get("kind") != "marker"
        and (text := str(segment.get("text") or "").strip())
    )


def stamp_cites_from_segments(
    summary: dict[str, Any],
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Point each verified quote at the segment it is really in.

    A model can copy a true quote and still get the numbers wrong, which would
    send the reader to the wrong minute. When a phrase recurs, the occurrence
    nearest the model's own time wins. A quote that cannot be located keeps
    whatever the model gave.
    """
    starts: list[int] = []
    spans: list[tuple[float | None, float | None]] = []
    parts: list[str] = []
    cursor = 0
    for segment in segments:
        text = normalize_grounding_text(segment.get("text"))
        if not text or segment.get("kind") == "marker":
            continue
        starts.append(cursor)
        spans.append((
            _number(segment.get("start_s", segment.get("start", segment.get("start_time")))),
            _number(segment.get("end_s", segment.get("end", segment.get("end_time")))),
        ))
        parts.append(text)
        cursor += len(text) + 1
    if not parts:
        return summary
    joined = " ".join(parts)

    def locate(quote: str, hint: float | None) -> tuple[float | None, float | None] | None:
        best: tuple[float, float | None, float | None] | None = None
        position = joined.find(quote)
        while position >= 0:
            first = bisect.bisect_right(starts, position) - 1
            last = bisect.bisect_right(starts, position + len(quote) - 1) - 1
            start, end = spans[first][0], spans[last][1]
            distance = abs((start or 0.0) - hint) if hint is not None else 0.0
            if best is None or distance < best[0]:
                best = (distance, start, end)
            if hint is None:
                break
            position = joined.find(quote, position + 1)
        return (best[1], best[2]) if best else None

    for key in ("decisions", "key_decisions", "actions", "action_items", "commitments"):
        values = summary.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            cites = item.get("cites") if isinstance(item, dict) else None
            if not isinstance(cites, list):
                continue
            for cite in cites:
                if not isinstance(cite, dict):
                    continue
                found = locate(
                    normalize_grounding_text(cite.get("quote")),
                    _number(cite.get("start_s")),
                )
                if found is None:
                    continue
                if found[0] is not None:
                    cite["start_s"] = found[0]
                if found[1] is not None:
                    cite["end_s"] = found[1]
    return summary


__all__ = [
    "MAX_CITATION_QUOTE_CHARS",
    "citation_markers",
    "dedupe_participants",
    "format_citation_time",
    "get_item_cites",
    "ground_summary",
    "normalize_grounding_text",
    "render_cited_item",
    "render_timestamped_segments",
    "spoken_text",
    "stamp_cites_from_segments",
    "validate_item_cites",
]
