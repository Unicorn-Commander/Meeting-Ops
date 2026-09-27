"""Tier-1 quality gate for extracted meeting action items.

Pure functions only. No model call lives here. Every producer should run
``apply_quality_gate`` (or ``gate_summary_lists``) on the items it is about
to store, and the Project-Ops writer should run it again before a push.

A drop is logged on its own line (``reason=``, ``confidence=``, ``source=``,
``text=``) and counted in a batch line. Items that already carry the same
drop reason are counted again but not logged a second time.

Kept dicts gain an additive ``quality`` object ``{kept, reason, confidence}``
on the item and, when present, on ``raw_payload``. String items cannot carry
that object; the log is the record.

``tier2_llm_verifier`` is an unwired hook. Do not call it from tier 1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional


logger = logging.getLogger(__name__)


# Shared wording for extraction prompts. No braces: several callers run
# ``str.format`` on the surrounding template.
COMMITMENT_EXTRACTION_RULES = """
Commitments only: who will do what, by when.
A commitment is a concrete deliverable (a verb and an object). Put the owner in the owner or assignee field as a real name when the transcript gives one; otherwise use the speaker label. Include a deadline only when one was stated.
Do not include in-call navigation or meeting mechanics: sharing, closing, or opening a window, scrolling, clicking, muting, refreshing, pulling a screen up, stopping or starting the recording, typing in chat, playing a track, setting a recording format, or any request aimed at the screen, the session, or the recording.
Do not include a third party's own to-do when it is not a company deliverable.
Do not include someone else's personal errand.
Do not include vague non-commitments such as "remain available", "wait for" something, "discuss", or "think about", unless that same item also names a concrete deliverable.
Do not include a restatement of the meeting topic.
When nothing qualifies, return an empty list. Do not invent items.
""".strip()


# "update" as a noun ("a partner's update", "status update") must not count
# as a commitment verb. Only an imperative or an auxiliary-led verb does.
_COMMIT_VERB = (
    r"set up|setup|break down|send|e-mail|email|draft|write|create|compile|"
    r"collect|add|update|file|deliver|ship|implement|fix|deploy|build|"
    r"invoice|prepare|document|finalize|schedule|book|publish|submit|"
    r"configure|migrate|amend|revise|pull|provide|share|review|"
    r"investigate|debug|export|import|integrate|install"
)
_COMMIT_RE = re.compile(
    rf"(?:^|[\n.;]|\b(?:will|to|and|please|must|should)\s+)(?:{_COMMIT_VERB})\b",
    re.IGNORECASE,
)
_CONTENT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "onto", "that", "this",
    "these", "those", "our", "their", "his", "her", "its", "your", "you",
    "will", "please", "must", "should", "not", "specified", "after", "before",
    "when", "what", "who", "how", "then", "than", "also", "just", "about",
}

_NAV_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bshare\s+(?:your\s+|the\s+|my\s+|his\s+|her\s+)?screen\b",
        r"\bscreen[\s-]?shar(?:e|ing)\b",
        r"\bstop sharing\b",
        r"\b(?:close|open|minimize|maximize)\s+(?:the\s+|a\s+|your\s+)?(?:[\w'-]+\s+){0,4}(?:window|tab|browser|slide)\b",
        r"\bscroll\s+(?:to|up|down|left|right)\b",
        r"\bclick\s+(?:on\s+)?(?:the\s+)?(?:button|link|menu|mute|icon|tab|window)\b",
        r"\b(?:mute|unmute)\s+(?:yourself|your\s+mic(?:rophone)?|the\s+mic(?:rophone)?|the\s+call|audio)\b",
        r"\brefresh\s+(?:the\s+)?(?:page|screen|browser|window|tab)\b",
        r"\bpull\s+up\b",
        r"\brecord\s+the\s+screen\b",
        r"\bset\s+(?:the\s+)?format\b",
        r"\btype\s+(?:it|that|this)\s+in(?:to)?\s+the\s+chat\b",
        r"\b(?:put|paste|drop)\s+(?:it|that|this)\s+in(?:to)?\s+the\s+chat\b",
        r"\bplay\b.{0,40}?\b(?:track|song|clip)\b",
        r"\bplay\s+the\s+(?:second|first)\s+half\b",
        r"\bsee\s+(?:my\s+|the\s+)?screen\b",
        r"\bzoom\s+(?:in|out)\s+on\s+the\s+(?:screen|window|slide|page)\b",
        r"\bshow\s+(?:me\s+|us\s+)?(?:your\s+|the\s+)?screen\b",
        r"\bturn\s+(?:on|off)\s+(?:your\s+|the\s+)?(?:camera|mic|microphone)\b",
    )
]

_MECHANICS_RECORDING_RE = re.compile(
    r"\b(?:stop|start|pause|resume)\s+(?:the\s+)?recording\b"
    r"|\bsave the segment\b"
    r"|\bcutting off at the phrase\b",
    re.IGNORECASE,
)
_STATUS_UPDATE_RE = re.compile(r"\bstatus update\b", re.IGNORECASE)
_IN_CALL_CONTEXT_RE = re.compile(
    r"\b(?:episode|segment|script|tonight|this meeting|the call|the session|the recording)\b",
    re.IGNORECASE,
)
# A status note that is actually sent or filed is a deliverable. An in-call
# "provide a status update on tonight's episode" is not.
_OUTBOUND_STATUS_RE = re.compile(
    r"\b(?:send|e-mail|email|publish|deliver|file|submit|write)\b",
    re.IGNORECASE,
)

_PERSONAL_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\btake the car\b",
        r"\bcar to (?:the )?service\b",
        r"\brelative(?:'s)?\s+funeral\b",
        r"\battend\b.{0,50}?\bfuneral\b",
        r"\binstall shelves\b.{0,40}?\b(?:garage|friend|home)\b",
        r"\bshelves in the garage\b",
        r"\b(?:pick up|pickup|buy)\s+(?:the\s+)?(?:groceries|grocery)\b",
        r"\b(?:her|his|their) new home\b",
        r"\binvite\b.{0,100}?\b(?:her|his|their) (?:new )?home\b",
        r"\bvisit (?:her|his|their) (?:new )?home\b",
        r"\bconfirm (?:the )?trip details\b",
        r"\bwhen the trip is done\b",
        r"\b(?:dentist|haircut|doctor'?s appointment)\b",
    )
]

# The third party is the grammatical actor ("a vendor contact will call
# back"). "Email the vendor the contract" is our deliverable and does not match.
_THIRD_PARTY_RE = re.compile(
    r"\b(?:vendor|supplier|contractor)(?:\s+contact)?\b.{0,100}?\bwill\s+"
    r"(?:call|ring|phone|email|reach out|get back|follow up|text)\b",
    re.IGNORECASE,
)

_VAGUE_RE = re.compile(
    r"\b(?:remain|stay|be)\s+available\b"
    r"|\bwait\s+for\b"
    r"|\bstand\s+by\b"
    r"|\bthink\s+about\b"
    r"|\bthink\s+through\b"
    r"|\bkeep\s+in\s+mind\b"
    r"|\bcircle\s+back\b"
    r"|\btouch\s+base\b"
    r"|\bdiscuss\b"
    r"|\bponder\b",
    re.IGNORECASE,
)

_TOPIC_RE = re.compile(
    r"^(?:the\s+)?(?:meeting|call|discussion|conversation)\s+"
    r"(?:is|was|about|topic|covered|concerns)\b"
    r"|^(?:recap|summary)\s+of\s+(?:the\s+)?(?:meeting|call)\b"
    r"|^(?:continue|resumed?)\s+(?:the\s+)?(?:discussion|meeting|conversation)\b"
    r"|^(?:talked|spoke|chatted)\s+about\b",
    re.IGNORECASE,
)

_GENERIC_OWNERS = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "unassigned",
    "tbd",
    "not specified",
    "speaker",
    "owner not stated",
}
_SPEAKER_LABEL_RE = re.compile(r"^speaker\s*\d+$", re.IGNORECASE)
_DUE_RE = re.compile(
    r"\b(?:by|before|on)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"tomorrow|tonight|next week|eod|end of day)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    re.IGNORECASE,
)
_NOT_A_DUE = {"not specified", "n/a", "na", "tbd", "none", "null", "unknown"}

_LIST_KEYS = ("action_items", "actions", "tasks", "action-items", "actionItems")
_TEXT_KEYS = ("text", "action", "task", "title", "description")
_OWNER_KEYS = ("owner", "assignee", "assigned_to", "responsible")
_DUE_KEYS = ("due_date", "dueDate", "deadline", "due")


@dataclass(frozen=True)
class QualityRecord:
    kept: bool
    reason: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "kept": self.kept,
            "reason": self.reason,
            "confidence": round(float(self.confidence), 2),
        }


@dataclass
class GateResult:
    kept: list[Any]
    dropped: list[Any]
    counts: dict[str, int]

    @property
    def dropped_count(self) -> int:
        return sum(self.counts.values())


def _normalize(text: str) -> str:
    cleaned = (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^(?:[-*•]+|\d+[.)])\s+", "", cleaned)
    return cleaned.strip()


def item_text(item: Any) -> str:
    if isinstance(item, str):
        return _normalize(item)
    if isinstance(item, dict):
        for key in _TEXT_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize(value)
    return ""


def item_owner(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    for source in (item, item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else {}):
        for key in _OWNER_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _due_hint(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    sources = [item]
    raw = item.get("raw_payload")
    if isinstance(raw, dict):
        sources.append(raw)
    for source in sources:
        for key in _DUE_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                token = value.strip()
                if token.lower() in _NOT_A_DUE:
                    continue
                return token
            if value is not None and not isinstance(value, (str, bool, int, float, list, dict)):
                return "dated"
    return None


def _has_commitment(text: str) -> bool:
    """True when a real verb has an object after it.

    "a partner's update" is a noun and must not qualify. "Update the
    compliance report" and "and send the invoice" do.
    """
    match = _COMMIT_RE.search(text)
    if not match:
        return False
    tail = text[match.end():]
    words = [
        word
        for word in _CONTENT_WORD_RE.findall(tail)
        if word.lower() not in _STOPWORDS
    ]
    return len(words) >= 1


def _real_owner(owner: Optional[str]) -> bool:
    if not owner:
        return False
    token = owner.strip().lower()
    if token in _GENERIC_OWNERS or _SPEAKER_LABEL_RE.match(token):
        return False
    return True


def _real_due(due: Optional[str], text: str) -> bool:
    if isinstance(due, str):
        token = due.strip().lower()
        # "dated" is the sentinel for a real datetime on the item.
        if token and token not in _NOT_A_DUE:
            return True
    return _DUE_RE.search(text) is not None


def _keep_confidence(text: str, owner: Optional[str], due: Optional[str], *, committed: bool) -> float:
    score = 0.84 if committed else 0.62
    if _real_owner(owner):
        score += 0.05
    if _real_due(due, text):
        score += 0.04
    cap = 0.96 if committed else 0.74
    return min(score, cap)


def _is_meeting_mechanics(text: str) -> bool:
    if _MECHANICS_RECORDING_RE.search(text):
        return True
    if _STATUS_UPDATE_RE.search(text) and _IN_CALL_CONTEXT_RE.search(text):
        if _OUTBOUND_STATUS_RE.search(text):
            return False
        return True
    return False


def _matches_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def classify_action_item(
    text: str,
    *,
    owner: Optional[str] = None,
    due: Optional[str] = None,
) -> QualityRecord:
    """Classify one extracted line. Does not log and does not call a model."""
    normalized = _normalize(text or "")
    if not normalized:
        return QualityRecord(False, "empty", 0.99)

    if _is_meeting_mechanics(normalized):
        return QualityRecord(False, "meeting_mechanics", 0.90)
    if _matches_any(_NAV_RES, normalized):
        return QualityRecord(False, "in_call_navigation", 0.93)
    if _matches_any(_PERSONAL_RES, normalized):
        return QualityRecord(False, "personal_errand", 0.91)
    committed = _has_commitment(normalized)
    if _THIRD_PARTY_RE.search(normalized) and not committed:
        return QualityRecord(False, "third_party_todo", 0.88)
    if _VAGUE_RE.search(normalized) and not committed:
        return QualityRecord(False, "vague_non_commitment", 0.86)
    if _TOPIC_RE.search(normalized) and not committed:
        return QualityRecord(False, "topic_restatement", 0.80)
    if committed:
        return QualityRecord(
            True,
            "commitment",
            _keep_confidence(normalized, owner, due, committed=True),
        )
    return QualityRecord(
        True,
        "retained",
        _keep_confidence(normalized, owner, due, committed=False),
    )


def _existing_quality(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    quality = item.get("quality")
    if isinstance(quality, dict):
        return quality
    raw = item.get("raw_payload")
    if isinstance(raw, dict) and isinstance(raw.get("quality"), dict):
        return raw["quality"]
    return None


def _with_quality(item: Any, record: QualityRecord) -> Any:
    if not isinstance(item, dict):
        return item
    stamped = dict(item)
    quality = record.as_dict()
    stamped["quality"] = quality
    raw = stamped.get("raw_payload")
    if isinstance(raw, dict):
        raw_copy = dict(raw)
        raw_copy["quality"] = dict(quality)
        stamped["raw_payload"] = raw_copy
    return stamped


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ",".join(f"{key}:{counts[key]}" for key in sorted(counts))


def apply_quality_gate(items: Any, *, source: str = "extract") -> GateResult:
    """Split extracted items into kept and dropped.

    Dicts gain a ``quality`` record. Strings stay strings. Empty input is a
    no-op. This function does not call ``tier2_llm_verifier``.
    """
    if not isinstance(items, list) or not items:
        return GateResult(kept=[], dropped=[], counts={})

    kept: list[Any] = []
    dropped: list[Any] = []
    counts: dict[str, int] = {}
    for item in items:
        text = item_text(item)
        owner = item_owner(item)
        due = _due_hint(item)
        record = classify_action_item(text, owner=owner, due=due)
        stamped = _with_quality(item, record)
        if record.kept:
            kept.append(stamped)
            continue
        dropped.append(stamped)
        counts[record.reason] = counts.get(record.reason, 0) + 1
        previous = _existing_quality(item)
        already_logged = (
            isinstance(previous, dict)
            and previous.get("kept") is False
            and previous.get("reason") == record.reason
        )
        if already_logged:
            continue
        logger.info(
            "action_item_quality dropped reason=%s confidence=%.2f source=%s owner=%s text=%s",
            record.reason,
            record.confidence,
            source,
            owner or "",
            (text or "")[:500],
        )

    if counts:
        logger.info(
            "action_item_quality gate source=%s kept=%d dropped=%d by_reason=%s",
            source,
            len(kept),
            len(dropped),
            _format_counts(counts),
        )
    return GateResult(kept=kept, dropped=dropped, counts=counts)


def gate_summary_lists(payload: Any, *, source: str = "summary") -> Any:
    """Filter action-item lists inside a summary dict, in place.

    Keys: ``action_items``, ``actions``, ``tasks``, ``action-items``,
    ``actionItems``. Other fields are left alone. Returns ``payload``.
    """
    if not isinstance(payload, dict):
        return payload
    for key in _LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list) and value:
            payload[key] = apply_quality_gate(value, source=f"{source}.{key}").kept
    return payload


def tier2_llm_verifier(items: list[Any], transcript: Optional[str] = None) -> list[Any]:
    """TODO(tier-2): optional LLM verifier. Not built. Not called by tier 1.

    A later pass may re-check items ``apply_quality_gate`` kept, and
    borderline drops, against ``transcript``. Wire it only behind an explicit
    flag. Tier 1 must stay a pure function with no model call.
    """
    del transcript
    return list(items)


__all__ = [
    "COMMITMENT_EXTRACTION_RULES",
    "GateResult",
    "QualityRecord",
    "apply_quality_gate",
    "classify_action_item",
    "gate_summary_lists",
    "item_owner",
    "item_text",
    "tier2_llm_verifier",
]
