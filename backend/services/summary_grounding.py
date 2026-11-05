"""Grounding and rendering helpers for structured meeting summaries.

The summary JSON columns are intentionally additive: older rows may not have
``cites`` or ``participants`` at all.  New summaries are checked here before
they are persisted or rendered as facts.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any


MAX_CITATION_QUOTE_CHARS = 160
_GENERIC_SPEAKER_RE = re.compile(r"^(?:speaker|spk|s)[ _-]?\d+$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_NON_PERSON_NAMES = {
    "none",
    "none identified",
    "not specified",
    "unknown",
    "unknown speaker",
}


def normalize_grounding_text(value: Any) -> str:
    """Normalize only whitespace and case for transcript membership checks."""
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip().casefold()


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
    if len(quote) > MAX_CITATION_QUOTE_CHARS:
        return None, f"citation quote exceeds {MAX_CITATION_QUOTE_CHARS} characters"

    start = cite.get("start_s", cite.get("start", cite.get("start_time")))
    end = cite.get("end_s", cite.get("end", cite.get("end_time")))
    speaker = cite.get("speaker") or cite.get("speaker_id") or ""
    start_value = _number(start)
    end_value = _number(end)
    if start_value is None or end_value is None:
        return None, "citation start_s/end_s is missing or invalid"
    canonical: dict[str, Any] = {
        "start_s": start_value,
        "end_s": end_value,
        "speaker": str(speaker).strip(),
        "quote": quote,
    }
    return canonical, None


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
    return output


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
    """Render one prompt line per segment with its citation time span."""
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
        start_text = format_citation_time(start) or "--:--"
        end_text = format_citation_time(end) or start_text
        start_s = start if start is not None else 0.0
        end_s = end if end is not None else start_s
        lines.append(
            f"[{start_text}-{end_text}; start_s={start_s:g} end_s={end_s:g}] "
            f"{speaker}: {text}"
        )
    return "\n".join(lines), speakers


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
    "validate_item_cites",
]
