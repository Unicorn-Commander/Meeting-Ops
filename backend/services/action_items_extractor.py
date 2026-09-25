"""Shared action-item extraction from the two JSON columns the
summarizer writes into (`final_summary` and `ai_insights`).

`persist_action_items` merges that parse into the `action_items` table.
It is called by:

 - api.uploads._summarize_session (upload pipeline, and every later
   summary that goes through it: finalize, reprocess, combine, the
   always-on stop fallback, speaker-rename refresh)
 - api.simple_recording_db (a second call after _summarize_session)
 - api.satellite_api (satellite transcript summarizer)

Digest jobs only read existing summaries. The live auto-summarizer
writes the JSON column and does not call this module. Alembic
021 inlines its own backfill.

Mirrors `frontend/src/components/dashboard/actionItems.ts` so the
`action_items` table contains the same items the dashboard parser
used to surface client-side.

Returns a list of dicts with the shape consumed by the new
`action_items` table:

    {
        "text": str,                # required, non-empty
        "owner": str | None,
        "due_date": datetime | None,
        "source": "final_summary" | "ai_insights",
        "raw_payload": dict,        # original LLM blob for audit
    }
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional


logger = logging.getLogger(__name__)


# Keys we will look at inside a bucket dict, in priority order. The
# summarizer is inconsistent: sometimes `actions`, sometimes
# `action_items`, sometimes (older) `tasks` / `action-items`.
_LIST_KEYS = ("action_items", "actions", "tasks", "action-items")


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for k in ("action", "text", "title", "description", "task"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def _pick_list(bucket: Any) -> List[Any]:
    if not isinstance(bucket, dict):
        return []
    for key in _LIST_KEYS:
        v = bucket.get(key)
        if isinstance(v, list) and v:
            return v
    return []


def _coerce_owner(raw: Any) -> Optional[str]:
    if not isinstance(raw, dict):
        return None
    for k in ("owner", "assignee", "assigned_to", "responsible"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:200]
    return None


_REL_DAY_RX = re.compile(
    r"\b(today|tonight|tomorrow|next\s+week|this\s+week|end\s+of\s+(?:week|month))\b",
    re.IGNORECASE,
)


def _coerce_due(raw: Any) -> Optional[datetime]:
    """Best-effort parse of LLM-extracted due strings into a timestamp.

    The summarizer emits "Not specified", "Next Thursday", "Friday",
    ISO dates, sometimes nothing. We accept ISO-shaped strings and
    leave the rest as NULL — the original phrasing is preserved in
    `raw_payload` for the UI to render verbatim if it wants."""
    if not isinstance(raw, dict):
        return None
    for k in ("due_date", "dueDate", "deadline", "due"):
        v = raw.get(k)
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s or s.lower() in {"not specified", "n/a", "tbd", "none", "null"}:
            continue
        # Try ISO 8601 first; tolerate trailing Z.
        try:
            iso = s[:-1] + "+00:00" if s.endswith("Z") else s
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        # Date-only YYYY-MM-DD
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        # Relative phrases get left as NULL; we keep the string in
        # raw_payload so the UI can render it as fallback copy.
        if _REL_DAY_RX.search(s):
            return None
    return None


def _iter_buckets(
    final_summary: Any, ai_insights: Any
) -> Iterable[tuple[str, dict]]:
    """Yield (source_label, bucket_dict) pairs to scan in order.

    Order matters for dedup: we keep the first occurrence of a given
    text key. final_summary wins over ai_insights because the
    summarizer writes structured `actions` with owner/priority there,
    while ai_insights tends to mirror the same items in a slightly
    different shape."""
    if isinstance(final_summary, dict):
        yield "final_summary", final_summary
    if isinstance(ai_insights, dict):
        yield "ai_insights", ai_insights


def extract_action_items(
    final_summary: Any,
    ai_insights: Any,
) -> List[dict]:
    """Return a deduplicated, ordered list of action-item dicts ready
    for INSERT into the `action_items` table.

    Dedup key is the first 120 chars of the text (lowercased + collapsed
    whitespace), matching the frontend parser's behavior."""
    out: List[dict] = []
    seen: set[str] = set()

    for source_label, bucket in _iter_buckets(final_summary, ai_insights):
        for raw in _pick_list(bucket):
            text = _coerce_text(raw)
            if not text:
                continue
            key = _dedup_key(text)
            if key in seen:
                continue
            seen.add(key)

            owner = _coerce_owner(raw)
            due = _coerce_due(raw)
            payload: dict = raw if isinstance(raw, dict) else {"text": text}

            out.append(
                {
                    "text": text[:4000],
                    "owner": owner,
                    "due_date": due,
                    "source": source_label,
                    "raw_payload": payload,
                }
            )

    return out


def _dedup_key(text: str) -> str:
    """Extract-time dedup key. First 120 chars, lowercase, whitespace collapsed.

    Kept separate from `_match_key`: two different tasks can share a prefix,
    and the merge must not treat that as the same row.
    """
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:120]


def _match_key(text: str) -> str:
    """Identity of an action sentence for re-summary matching.

    The whole normalized text, not a prefix and not a fuzzy similarity.
    Case and internal whitespace do not make a new row; a different
    sentence does.
    """
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _due_matches(stored: Optional[datetime], extracted: Optional[datetime]) -> bool:
    if stored is None and extracted is None:
        return True
    if stored is None or extracted is None:
        return False
    try:
        return abs((_as_utc(stored) - _as_utc(extracted)).total_seconds()) < 1
    except (TypeError, ValueError, OverflowError):
        return False


def _stored_owner(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()[:200]
    return stripped or None


def _row_is_human(row: Any) -> bool:
    """True when a person created or changed this row, so a re-summary
    must not delete or overwrite it.

    The PATCH path writes `text` / `owner` / `due_date` / `status` and
    leaves the original LLM blob in `raw_payload`. A machine insert
    stores those columns as the extraction of that blob, with
    status `todo` and no `completed_at`. Manual creates use
    `source='manual'`. No separate edited-at column: the diff against
    the blob is the edit signal. A missing blob cannot prove the row
    is untouched, so it is kept.
    """
    if getattr(row, "source", None) == "manual":
        return True
    if (getattr(row, "status", None) or "todo") != "todo":
        return True
    if getattr(row, "completed_at", None) is not None:
        return True
    payload = getattr(row, "raw_payload", None)
    if not isinstance(payload, dict):
        return True
    if (getattr(row, "text", None) or "") != _coerce_text(payload)[:4000]:
        return True
    if _stored_owner(getattr(row, "owner", None)) != _coerce_owner(payload):
        return True
    if not _due_matches(getattr(row, "due_date", None), _coerce_due(payload)):
        return True
    return False


def _with_stamps(row: Any, fresh: Any) -> dict:
    """New LLM blob plus the Project-Ops stamps already on this row.

    Legacy readers still look at `po_*` keys inside `raw_payload`.
    Columns from migration 054 are copied back into those keys when
    the blob lost them, so a matched row cannot be proposed again.
    """
    merged = dict(fresh) if isinstance(fresh, dict) else {}
    previous = getattr(row, "raw_payload", None)
    if isinstance(previous, dict):
        for key, value in previous.items():
            if isinstance(key, str) and key.startswith("po_"):
                merged[key] = value
    if not merged.get("po_task_id") and getattr(row, "project_ops_task_id", None):
        merged["po_task_id"] = row.project_ops_task_id
    project_number = getattr(row, "project_ops_project_number", None)
    if not merged.get("po_project_number") and project_number:
        merged["po_project_number"] = project_number
    if not merged.get("po_proposal_id") and getattr(row, "project_ops_proposal_id", None):
        merged["po_proposal_id"] = row.project_ops_proposal_id
    submitted = getattr(row, "project_ops_submitted_at", None)
    if not merged.get("po_triage_submitted_at") and isinstance(submitted, datetime):
        merged["po_triage_submitted_at"] = submitted.isoformat().replace("+00:00", "Z")
    return merged


def _apply_machine_update(row: Any, item: dict, sort_order: int) -> None:
    """Refresh LLM fields on an untouched row. Id, status, completed_at,
    and the Project-Ops columns stay so the bridge still sees the same item.
    """
    row.text = item["text"]
    row.owner = item["owner"]
    row.due_date = item["due_date"]
    row.source = item["source"]
    row.sort_order = sort_order
    row.raw_payload = _with_stamps(row, item["raw_payload"])


def persist_action_items(db, session) -> int:
    """Merge a fresh extraction into the session's action-item rows.

    Human-owned rows are never deleted or overwritten. An untouched
    machine row whose normalized text matches a new item is updated in
    place. An untouched machine row with no match is deleted. Anything
    left over is inserted.

    A machine row wins a shared text over a human row, so a hand-added
    duplicate cannot consume the match and drop the stamped machine row.
    The human row still consumes a leftover with its text, which stops
    the same sentence being inserted again.

    Returns how many rows the session has after the merge. The caller
    commits; this function only flushes.
    """
    # Local import keeps the extractor importable from alembic
    # migrations (which don't have a fully wired models package on
    # the path during early upgrades).
    from database.models import ActionItem

    if session is None or getattr(session, "id", None) is None:
        return 0
    if getattr(session, "organization_id", None) is None:
        # Org-scoping is enforced at the table level; without an org
        # id we can't write rows. Older sessions predate multi-org.
        logger.debug(
            "persist_action_items: skipping session %s with no organization_id",
            getattr(session, "id", "?"),
        )
        return 0

    incoming = extract_action_items(
        getattr(session, "final_summary", None),
        getattr(session, "ai_insights", None),
    )
    existing = (
        db.query(ActionItem)
        .filter(ActionItem.session_id == session.id)
        .order_by(ActionItem.sort_order.asc(), ActionItem.id.asc())
        .all()
    )

    pending: dict[str, list] = {}
    for idx, item in enumerate(incoming):
        key = _match_key(item["text"])
        if not key:
            continue
        pending.setdefault(key, []).append((idx, item))

    def _take(text: str):
        key = _match_key(text or "")
        bucket = pending.get(key) if key else None
        if not bucket:
            return None
        found = bucket.pop(0)
        if not bucket:
            pending.pop(key, None)
        return found

    human = []
    machine = []
    for row in existing:
        if _row_is_human(row):
            human.append(row)
        else:
            machine.append(row)

    kept = updated = removed = 0
    for row in machine:
        match = _take(getattr(row, "text", "") or "")
        if match is None:
            db.delete(row)
            removed += 1
            continue
        idx, item = match
        _apply_machine_update(row, item, idx)
        updated += 1

    for row in human:
        _take(getattr(row, "text", "") or "")
        kept += 1

    inserted = 0
    for bucket in pending.values():
        for idx, item in bucket:
            db.add(
                ActionItem(
                    session_id=session.id,
                    organization_id=session.organization_id,
                    text=item["text"],
                    owner=item["owner"],
                    due_date=item["due_date"],
                    status="todo",
                    sort_order=idx,
                    source=item["source"],
                    raw_payload=item["raw_payload"],
                )
            )
            inserted += 1

    db.flush()
    logger.info(
        "action_items: merged session=%s kept=%d updated=%d removed=%d inserted=%d",
        session.id,
        kept,
        updated,
        removed,
        inserted,
    )
    return kept + updated + inserted
