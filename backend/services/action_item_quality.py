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

``ACTION_ITEM_GATE_MODE`` is ``shadow`` (the default) or ``enforce``, read
from the environment on each call via ``config.features.action_item_gate_mode``.
Shadow annotates every item, logs and counts what it would drop, and drops
nothing. Enforce removes the rejected items. Re-summary must not delete a
stored machine row only because the gate would now reject it; that guard
lives in the extractor, and it holds in both modes.

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
    r"investigate|debug|export|import|integrate|install|confirm|countersign"
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
        r"\bscroll\b",
        r"\bclick\s+(?:on\s+)?(?:the\s+)?(?:button|link|menu|mute|icon|tab|window)\b",
        r"\b(?:mute|unmute)\s+(?:yourself|your\s+mic(?:rophone)?|the\s+mic(?:rophone)?|the\s+call|audio)\b",
        r"\brefresh\s+(?:the\s+)?(?:[\w'-]+\s+){0,3}(?:page|screen|browser|window|tab)\b",
        r"\bpull\s+up\b",
        r"\brecord\s+the\s+screen\b",
        r"\bset\s+(?:the\s+)?format\b",
        r"\btype\s+(?:it|that|this)\s+in(?:to)?\s+(?:the\s+)?chat\b",
        r"\bgo\s+back\s+(?:a\s+|one\s+|to\s+(?:the\s+)?)?slide\b",
        r"\b(?:put|paste|drop)\s+(?:it|that|this)\s+in(?:to)?\s+the\s+chat\b",
        r"\bplay\b.{0,40}?\b(?:track|song|clip)\b",
        r"\bplay\s+the\s+(?:second|first)\s+half\b",
        r"\bsee\s+(?:my\s+|the\s+)?screen\b",
        r"\bzoom\s+(?:in|out)\s+on\s+the\s+(?:screen|window|slide|page)\b",
        r"\bshow\s+(?:me\s+|us\s+)?(?:your\s+|the\s+)?screen\b",
        r"\bturn\s+(?:on|off)\s+(?:your\s+|the\s+)?(?:camera|mic|microphone)\b",
    )
]

# "start the recording of the training video" is a deliverable. "start the
# recording" with nothing after it is the live session. Exporting the WAV
# is the same mechanic; exporting a report is not.
_MECHANICS_RECORDING_RE = re.compile(
    r"\b(?:stop|start|pause|resume|end)\s+(?:the\s+)?recording\b(?!\s+of\b)"
    r"|\bsave\s+(?:the|this|that)\s+segment\b"
    r"|\bcutting off at the phrase\b",
    re.IGNORECASE,
)
_NON_RECORDING_DELIVERABLE_RE = re.compile(
    r"\b(?:and|then)\s+(?:send|e-mail|email|file|document|countersign|submit|"
    r"publish|deliver|write|draft|prepare|review|switch)\b"
    r"|\b(?:and|then)\s+export\b(?!\s+(?:the\s+)?(?:wav|recording|audio|segment)\b)",
    re.IGNORECASE,
)
_STATUS_UPDATE_RE = re.compile(r"\bstatus update\b", re.IGNORECASE)
_IN_CALL_CONTEXT_RE = re.compile(
    r"\b(?:episode|segment|script|tonight|this meeting|the call|the session|the recording)\b",
    re.IGNORECASE,
)
# A status note that is actually sent, filed, drafted, prepared, or written
# is a deliverable. An in-call "provide a status update on tonight's episode"
# is not.
_OUTBOUND_STATUS_RE = re.compile(
    r"\b(?:send|e-mail|email|publish|deliver|file|submit|write)\b",
    re.IGNORECASE,
)
_STATUS_DELIVERABLE_RE = re.compile(
    r"\b(?:draft|prepare|write)\b(?:\s+\S+){0,8}?\s+status\s+update\b",
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
        r"\bbook\s+(?:a\s+|my\s+)?flight\b",
        r"\bfor my vacation\b",
        r"\bdry[\s-]?cleaning\b",
    )
]

# Our deliverable, not someone's private errand and not a third party's own
# to-do. "the client dinner" is a social event, not this shield.
_COMPANY_DELIVERABLE_RE = re.compile(
    r"\b(?:proposal|sow|invoice|invoices|contract|portal|retainer|payroll)\b"
    r"|\bclient(?:'s|s')\b"
    r"|\bfor the client\b(?!\s+(?:dinner|lunch|breakfast)\b)"
    r"|\b(?:the|a|our)\s+client\b(?!\s+(?:dinner|lunch|breakfast|meeting|call|demo)\b)"
    r"|\bclient\s+(?:portal|template|onsite|account|showroom)\b",
    re.IGNORECASE,
)

# The third party is the grammatical actor ("the vendor will email the SOW",
# "their lawyer will review"). "Email the vendor the contract" is our
# deliverable and does not match, even when the object is a company artifact.
_THIRD_PARTY_RE = re.compile(
    r"\b(?:vendor|supplier|contractor|lawyer)(?:\s+\w+){0,5}\s+will\s+"
    r"(?:call|ring|phone|e-mail|email|send|review|install|reach out|get back|"
    r"follow up|text|deliver|ship|provide|share)\b",
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
    r"|\bponder\b"
    r"|\blet(?:'s|\s+us)\s+sync\b"
    r"|\bsync\s+later\b",
    re.IGNORECASE,
)

_TOPIC_RE = re.compile(
    r"^(?:this\s+|the\s+)?(?:meeting|call|discussion|conversation)\s+"
    r"(?:is|was|about|topic|covered|concerns)\b"
    r"|^(?:recap|summary)\s+of\s+(?:the\s+)?(?:meeting|call)\b"
    r"|^(?:continue|resumed?)\s+(?:the\s+)?(?:discussion|meeting|conversation)\b"
    r"|^(?:today|yesterday)\s+we\s+(?:talked|spoke|discussed|covered)\b"
    r"|^(?:we\s+)?(?:talked|spoke|chatted)\s+about\b",
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


def _matches_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


# A coordinated work product. "and pull up" is still navigation. Exporting the
# recording WAV is the mechanic itself, so it does not count here.
_DELIVERABLE_CLAUSE_RE = re.compile(
    r"\b(?:and|then)\s+(?:send|e-mail|email|file|document|countersign|submit|"
    r"publish|deliver|write|draft|prepare|review)\b"
    r"|\b(?:and|then)\s+export\b(?!\s+(?:the\s+)?(?:wav|recording|audio|segment)\b)",
    re.IGNORECASE,
)
_RESCUE_DATE_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next week)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    re.IGNORECASE,
)
_NAMED_RECIPIENT_RE = re.compile(
    r"\b(?:to|for|with)\s+(?:the\s+|our\s+|a\s+)?(?:client|board|sponsor|customer|bookkeeper)\b",
    re.IGNORECASE,
)
# "Open a window for the new hire" is a payroll slot, not a UI window.
_JOB_WINDOW_RE = re.compile(r"\bopen\s+(?:a|an)\s+window\s+for\b", re.IGNORECASE)
_INDEPENDENT_DELIVERABLE_RE = re.compile(
    rf"\b(?:and|then|,)\s+(?:{_COMMIT_VERB})\b",
    re.IGNORECASE,
)
_LEADING_COMMIT_RE = re.compile(
    rf"^(?:please\s+)?(?:{_COMMIT_VERB})\b",
    re.IGNORECASE,
)


def _names_company_deliverable(text: str) -> bool:
    return _COMPANY_DELIVERABLE_RE.search(text) is not None


def _has_deliverable_clause(text: str) -> bool:
    return _DELIVERABLE_CLAUSE_RE.search(text) is not None


def _has_nav_rescue(text: str) -> bool:
    """A pure in-call imperative has none of these. Any one of them keeps the line."""
    if _has_deliverable_clause(text):
        return True
    if _RESCUE_DATE_RE.search(text):
        return True
    if _STATUS_DELIVERABLE_RE.search(text):
        return True
    if _NAMED_RECIPIENT_RE.search(text):
        return True
    if _JOB_WINDOW_RE.search(text):
        return True
    return False


def _is_pure_in_call_navigation(text: str) -> bool:
    if not _matches_any(_NAV_RES, text):
        return False
    if _has_nav_rescue(text):
        return False
    return True


def _is_pure_meeting_mechanics(text: str) -> bool:
    if _MECHANICS_RECORDING_RE.search(text):
        # "for the client" does not turn "end the recording and export the WAV"
        # into a deliverable. A separate and-send / and-document clause does.
        if _NON_RECORDING_DELIVERABLE_RE.search(text):
            return False
        return True
    if _STATUS_UPDATE_RE.search(text) and _IN_CALL_CONTEXT_RE.search(text):
        if _STATUS_DELIVERABLE_RE.search(text) or _OUTBOUND_STATUS_RE.search(text):
            return False
        return True
    return False


def _is_personal_errand(text: str) -> bool:
    if not _matches_any(_PERSONAL_RES, text):
        return False
    if _names_company_deliverable(text):
        return False
    return True


def _has_independent_deliverable(text: str) -> bool:
    """A deliverable we will do, not the infinitive inside "wait for X to send"."""
    if _INDEPENDENT_DELIVERABLE_RE.search(text):
        return True
    return _LEADING_COMMIT_RE.search(text) is not None


def _is_vague(text: str) -> bool:
    if not _VAGUE_RE.search(text):
        return False
    if _has_independent_deliverable(text):
        return False
    return True


def classify_action_item(
    text: str,
    *,
    owner: Optional[str] = None,
    due: Optional[str] = None,
) -> QualityRecord:
    """Classify one extracted line. Does not log and does not call a model.

    Commitment is decided first. Navigation and mechanics then drop only a
    pure in-call instruction aimed at the screen, session, recording, or
    audio: no deliverable clause, no named recipient, no date, and not a
    status report someone will draft, prepare, or write. Personal errands
    do not fire on a company deliverable. A third party who will do the
    thing themselves is still their to-do.
    """
    normalized = _normalize(text or "")
    if not normalized:
        return QualityRecord(False, "empty", 0.99)

    committed = _has_commitment(normalized)
    if _is_pure_in_call_navigation(normalized):
        return QualityRecord(False, "in_call_navigation", 0.93)
    if _is_pure_meeting_mechanics(normalized):
        return QualityRecord(False, "meeting_mechanics", 0.90)
    if _is_personal_errand(normalized):
        return QualityRecord(False, "personal_errand", 0.91)
    if _THIRD_PARTY_RE.search(normalized):
        return QualityRecord(False, "third_party_todo", 0.88)
    if _is_vague(normalized):
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


def get_action_item_gate_mode() -> str:
    """``shadow`` or ``enforce``. Default ``shadow``. See ``config.features``."""
    from config.features import action_item_gate_mode

    return action_item_gate_mode()


def apply_quality_gate(items: Any, *, source: str = "extract") -> GateResult:
    """Fail-open wrapper: the gate is a filter, never a safety control.

    Any unexpected exception inside the classifier returns every item
    unchanged (``kept``), logs one WARNING with the source and exception
    type (no item text), and records ``counts["gate_error"] = 1`` so the
    caller's metadata shows the gate did not run (review round 2, MEDIUM).
    """
    try:
        return _apply_quality_gate(items, source=source)
    except Exception as exc:  # noqa: BLE001 - deliberate fail-open
        logger.warning(
            "action_item_quality gate_error source=%s exc=%s items=%d; kept all items unfiltered",
            source,
            type(exc).__name__,
            len(items) if isinstance(items, list) else 0,
        )
        kept = list(items) if isinstance(items, list) else []
        return GateResult(kept=kept, dropped=[], counts={"gate_error": 1})


def _apply_quality_gate(items: Any, *, source: str = "extract") -> GateResult:
    """Annotate extracted items, and drop them only in enforce mode.

    Dicts gain a ``quality`` record. Strings stay strings. Empty input is a
    no-op. This function does not call ``tier2_llm_verifier``.

    Shadow (the default) keeps every item, including ones the record marks
    ``kept: false``. It still logs and counts those as ``would_drop``.
    Enforce puts rejected items only in ``dropped``. ``counts`` is the
    would-drop tally in both modes.
    """
    if not isinstance(items, list) or not items:
        return GateResult(kept=[], dropped=[], counts={})

    mode = get_action_item_gate_mode()
    shadow = mode != "enforce"
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
        if shadow:
            kept.append(stamped)
        previous = _existing_quality(item)
        already_logged = (
            isinstance(previous, dict)
            and previous.get("kept") is False
            and previous.get("reason") == record.reason
        )
        if already_logged:
            continue
        logger.info(
            "action_item_quality %s reason=%s confidence=%.2f source=%s owner=%s text_len=%d mode=%s",
            "would_drop" if shadow else "dropped",
            record.reason,
            record.confidence,
            source,
            owner or "",
            len(text or ""),
            mode,
        )
        # Item text is transcript content: DEBUG only, never INFO (review round 2, MEDIUM).
        logger.debug("action_item_quality item source=%s reason=%s text=%s", source, record.reason, (text or "")[:500])

    if counts:
        logger.info(
            "action_item_quality gate source=%s mode=%s kept=%d %s=%d by_reason=%s",
            source,
            mode,
            len(kept),
            "would_drop" if shadow else "dropped",
            len(dropped),
            _format_counts(counts),
        )
    return GateResult(kept=kept, dropped=dropped, counts=counts)


def gate_summary_lists(payload: Any, *, source: str = "summary") -> Any:
    """Annotate action-item lists inside a summary dict, in place.

    Keys: ``action_items``, ``actions``, ``tasks``, ``action-items``,
    ``actionItems``. Other fields are left alone. Returns ``payload``.
    Enforce replaces each list with the survivors. Shadow leaves every
    item in the list and stamps the quality record on dict items.
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
    "get_action_item_gate_mode",
    "item_owner",
    "item_text",
    "tier2_llm_verifier",
]
