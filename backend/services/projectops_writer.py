"""Best-effort task writer: Meeting-Ops action items -> Project-Ops tasks.

Public surface:

  await write_action_items_to_projectops(
      db=db, session_pk=session_pk, completion_mode="reprocess"
  )

Called from two paths (mirroring ``services.brigade_writer``):

  * ``api.recording._run_session_reprocess`` (completion_mode="reprocess")
    after the Brigade graph write block.
  * the live/browser-only finalize background task in ``api.recording``
    (completion_mode="live").

What this IS: a one-way write from Meeting-Ops -> Project-Ops on meeting
completion. When a meeting's ``action_items`` are (re)written, we create a
matching Project-Ops task per item on a per-org target project.

What this ISN'T: bidirectional sync. We don't poll PO. We don't roll PO
tasks back on meeting delete (PO owns its own delete UX). Source of truth
for the *meeting side* is ``action_items``; for the *task side* it's PO.

Idempotency: the link is stamped onto ``action_items.raw_payload`` (an
existing nullable JSONB column — no migration). A row that already carries
``raw_payload.po_task_id`` is never re-created; the writer only (best-effort)
nudges the PO task's status if the local item has since been marked done.

Failure posture: the writer NEVER raises into the recording pipeline.
Every exception is logged + swallowed (top-level catch). When
``PROJECTOPS_API_KEY`` is unset the client is log-only and the writer
returns ``ok=True, mode="no-op"`` without any HTTP calls — a deployment
without Project-Ops wiring completes the meeting pipeline cleanly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


# raw_payload stamp keys (the idempotency marker + provenance).
STAMP_TASK_ID = "po_task_id"
STAMP_PROJECT_NUMBER = "po_project_number"
STAMP_SYNCED_AT = "po_synced_at"

# Org-scoped setting key, stored inside Organization.settings (JSONB).
ORG_DEFAULT_SETTING_KEY = "projectops_default_project_number"

# Per-meeting override key inside RecordingSession.processing_metadata.
SESSION_OVERRIDE_KEY = "po_project_override"

# Project-app marker that means session.project_id is a Project-Ops UUID.
PROJECT_APP_PROJECTOPS = "project-ops"

# Defaults for created tasks (per spec).
DEFAULT_TASK_PRIORITY = "MEDIUM"
DEFAULT_TASK_TYPE = "OTHER"

# Meeting-Ops action-item status -> Project-Ops TaskStatus, for the
# marked-done propagation path. Only statuses with a sensible PO analog
# are mapped; anything else leaves the PO task untouched.
_LOCAL_TO_PO_STATUS = {
    "done": "COMPLETED",
    "cancelled": "CANCELLED",
    "doing": "IN_PROGRESS",
    "todo": "PENDING",
}


@dataclass(frozen=True)
class ProjectOpsWriteResult:
    """Lightweight return value for the writer's call sites.

    ``ok`` is True for real writes AND the no-op / no-target paths (the
    meeting completed; that's the user-facing contract). ``mode`` lets
    callers + tests distinguish: "live" (real), "no-op" (PO unconfigured),
    "no-target" (no project resolved), "error".
    """

    ok: bool
    mode: str  # "live" | "no-op" | "no-target" | "error"
    created: int = 0
    skipped: int = 0
    detail: Optional[str] = None


def _utcnow_iso() -> str:
    """ISO-8601 UTC with a trailing Z (matches the stamp shape in the
    integration spec, e.g. ``2026-05-28T16:30:00Z``)."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def get_org_default_project_number(
    db: Session, organization_id: int
) -> Optional[str]:
    """Read ``projectops_default_project_number`` from Organization.settings.

    Stored on the existing ``Organization.settings`` JSONB column (org-scoped,
    no migration). Returns None when unset / org missing.
    """
    from auth.models import Organization

    org = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )
    if org is None:
        return None
    settings = org.settings or {}
    value = settings.get(ORG_DEFAULT_SETTING_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def set_org_default_project_number(
    db: Session, organization_id: int, project_number: Optional[str]
) -> bool:
    """Set (or clear, with None) the org default target project.

    Reassigns ``Organization.settings`` (rather than mutating in place) so
    SQLAlchemy reliably detects the JSONB change. Commits. Returns True on
    success, False if the org doesn't exist. The v1 wiring path — call from
    the backfill script's ``--set-default-project`` flag or a shell.
    """
    from auth.models import Organization

    org = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )
    if org is None:
        return False
    settings = dict(org.settings or {})
    if project_number:
        settings[ORG_DEFAULT_SETTING_KEY] = project_number.strip()
    else:
        settings.pop(ORG_DEFAULT_SETTING_KEY, None)
    org.settings = settings
    db.commit()
    return True


def _resolve_target_project(
    db: Session, session: Any
) -> tuple[Optional[str], str]:
    """Resolve the Project-Ops target for this session's action items.

    Resolution order (most-specific first):
      0. The existing session->PO link: ``session.project_app ==
         'project-ops'`` + ``session.project_id`` (a PO project UUID).
         This is the canonical link the rest of Meeting-Ops already uses;
         honoring it means a session explicitly tied to a PO project just
         works, and we skip number->UUID resolution entirely.
      1. Per-meeting override: ``session.processing_metadata[po_project_override]``
         (a project number or UUID). Backend-only in v1; UI deferred.
      2. Org default: ``Organization.settings[projectops_default_project_number]``.
      3. None -> caller skips (mode="no-target").

    Returns ``(project_ref, source)`` where project_ref is a number
    ("P-00055") or a UUID, or ``(None, "none")``.
    """
    # 0. Existing canonical session -> PO project link.
    if (
        getattr(session, "project_app", None) == PROJECT_APP_PROJECTOPS
        and getattr(session, "project_id", None)
    ):
        return str(session.project_id).strip(), "session_link"

    # 1. Per-meeting override.
    meta = session.processing_metadata or {}
    if isinstance(meta, dict):
        override = meta.get(SESSION_OVERRIDE_KEY)
        if isinstance(override, str) and override.strip():
            return override.strip(), "override"

    # 2. Org default.
    org_default = get_org_default_project_number(db, session.organization_id)
    if org_default:
        return org_default, "org_default"

    # 3. Nothing.
    return None, "none"


def _meeting_label(session: Any) -> str:
    return (
        session.title
        or session.name
        or f"Meeting {session.id}"
    )


def _meeting_date(session: Any) -> str:
    """Best-effort human date for the task description."""
    for attr in ("meeting_date", "started_at", "created_at"):
        value = getattr(session, attr, None)
        if value is not None:
            try:
                return value.date().isoformat()
            except AttributeError:
                # ``meeting_date`` is already a date.
                return str(value)
    return "unknown date"


def _build_description(session: Any, item: Any) -> str:
    owner = (item.owner or "").strip() or "unassigned"
    return (
        f"From meeting: {_meeting_label(session)}, "
        f"{_meeting_date(session)}, owner: {owner}"
    )


def _stamp_item(item: Any, *, task_id: str, project_number: Optional[str]) -> None:
    """Write the PO link onto the action item's raw_payload. Reassigns the
    dict (not in-place mutation) so SQLAlchemy flags the JSONB column dirty
    without needing flag_modified."""
    payload = dict(item.raw_payload or {})
    payload[STAMP_TASK_ID] = task_id
    if project_number:
        payload[STAMP_PROJECT_NUMBER] = project_number
    payload[STAMP_SYNCED_AT] = _utcnow_iso()
    item.raw_payload = payload


async def write_action_items_to_projectops(
    *,
    db: Session,
    session_pk: int,
    completion_mode: str = "reprocess",
    client: Optional[Any] = None,
) -> ProjectOpsWriteResult:
    """Create Project-Ops tasks for this session's un-synced action items.

    Args:
        db: caller-provided SQLAlchemy session (we don't open our own so
            the call site owns transaction scope).
        session_pk: ``recording_sessions.id`` (integer PK).
        completion_mode: "reprocess" or "live" — logged for provenance.
        client: optional ProjectOpsClient (tests inject a stub). When None
            a default-config client is built + closed on exit.

    Returns ProjectOpsWriteResult. Never raises.
    """
    # Lazy imports keep projectops_client / models off the import path
    # until this is actually called.
    from services.projectops_client import ProjectOpsClient, ProjectOpsClientError

    try:
        from database.models import ActionItem, RecordingSession

        session = (
            db.query(RecordingSession)
            .filter(RecordingSession.id == session_pk)
            .first()
        )
        if session is None:
            logger.info(
                "projectops_writer skipped: session_pk=%s not found", session_pk
            )
            return ProjectOpsWriteResult(
                ok=False, mode="error", detail="session not found"
            )

        target_ref, source = _resolve_target_project(db, session)
        if not target_ref:
            logger.info(
                "projectops_writer no target project for session=%s "
                "(no session link, override, or org default) — skipping",
                session_pk,
            )
            return ProjectOpsWriteResult(ok=True, mode="no-target")

        owned_client = client is None
        active_client = client or ProjectOpsClient()
        try:
            if not active_client.is_live:
                logger.info(
                    "projectops_writer: PO unconfigured (PROJECTOPS_API_KEY "
                    "unset), skipping session=%s",
                    session_pk,
                )
                return ProjectOpsWriteResult(ok=True, mode="no-op")

            action_items = (
                db.query(ActionItem)
                .filter(ActionItem.session_id == session.id)
                .order_by(ActionItem.sort_order.asc(), ActionItem.id.asc())
                .all()
            )

            created = 0
            skipped = 0
            for item in action_items:
                existing = (item.raw_payload or {}).get(STAMP_TASK_ID)
                if existing:
                    # Already bridged. Don't duplicate; best-effort nudge
                    # the PO task status if the local item moved on.
                    skipped += 1
                    await _maybe_propagate_status(active_client, item, existing)
                    continue

                try:
                    result = await active_client.create_task(
                        project_number=target_ref,
                        title=item.text,
                        description=_build_description(session, item),
                        priority=DEFAULT_TASK_PRIORITY,
                        due_date=item.due_date,
                        type=DEFAULT_TASK_TYPE,
                    )
                except ProjectOpsClientError as exc:
                    # A live write failed. Stop hammering a degraded PO;
                    # leave un-synced rows for the backfill job. Rows
                    # touched so far stay committed (best-effort partial).
                    logger.warning(
                        "projectops_writer create_task failed session=%s "
                        "item=%s target=%s: %s",
                        session_pk,
                        item.id,
                        target_ref,
                        exc,
                    )
                    return ProjectOpsWriteResult(
                        ok=False,
                        mode="error",
                        created=created,
                        skipped=skipped,
                        detail=str(exc)[:200],
                    )

                _stamp_item(
                    item,
                    task_id=result["id"],
                    project_number=result.get("project_number") or _ref_as_number(target_ref),
                )
                db.commit()
                created += 1

            logger.info(
                "projectops_writer session=%s mode=%s target=%s(%s) "
                "created=%d skipped=%d",
                session_pk,
                completion_mode,
                target_ref,
                source,
                created,
                skipped,
            )
            return ProjectOpsWriteResult(
                ok=True,
                mode="live",
                created=created,
                skipped=skipped,
                detail=f"target={target_ref} source={source}",
            )
        finally:
            if owned_client:
                await active_client.aclose()
    except Exception as exc:  # noqa: BLE001
        # Top-level catch — the writer must never raise into the recording
        # pipeline. Logged with traceback for the operator.
        logger.exception(
            "projectops_writer swallowed error session_pk=%s: %s",
            session_pk,
            exc,
        )
        return ProjectOpsWriteResult(
            ok=False, mode="error", detail=str(exc)[:200]
        )


def _ref_as_number(project_ref: str) -> Optional[str]:
    """If the resolved target was a human project number (not a UUID),
    use it as the stamped project number when the create response didn't
    echo one back."""
    from services.projectops_client import _looks_like_uuid

    return None if _looks_like_uuid(project_ref) else project_ref


async def _maybe_propagate_status(
    client: Any, item: Any, task_id: str
) -> None:
    """Best-effort: if the local action item has a PO-mappable status,
    nudge the linked PO task. Swallows everything — this runs inside the
    skip path and must not break idempotent re-runs."""
    po_status = _LOCAL_TO_PO_STATUS.get((item.status or "").strip().lower())
    # Only propagate terminal/meaningful transitions on re-run; "todo" ->
    # PENDING is the PO default and not worth a round-trip.
    if not po_status or po_status == "PENDING":
        return
    try:
        await client.update_task_status(task_id=task_id, status=po_status)
        logger.info(
            "projectops_writer propagated status item=%s task=%s -> %s",
            item.id,
            task_id,
            po_status,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "projectops_writer status propagation swallowed item=%s: %s",
            item.id,
            exc,
        )


async def propagate_action_item_status(
    item: Any, *, client: Optional[Any] = None
) -> ProjectOpsWriteResult:
    """Best-effort entry point for the action-items PATCH endpoint. When a
    user marks an item done (etc.) in the Meeting-Ops UI and the row was
    bridged to PO (``raw_payload.po_task_id`` set), nudge the PO task's
    status. Never raises.
    """
    from services.projectops_client import ProjectOpsClient

    try:
        task_id = (item.raw_payload or {}).get(STAMP_TASK_ID)
        if not task_id:
            return ProjectOpsWriteResult(ok=True, mode="no-target")

        owned_client = client is None
        active_client = client or ProjectOpsClient()
        try:
            if not active_client.is_live:
                return ProjectOpsWriteResult(ok=True, mode="no-op")
            await _maybe_propagate_status(active_client, item, task_id)
            return ProjectOpsWriteResult(ok=True, mode="live")
        finally:
            if owned_client:
                await active_client.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "projectops_writer propagate_action_item_status swallowed "
            "item=%s: %s",
            getattr(item, "id", "?"),
            exc,
        )
        return ProjectOpsWriteResult(ok=False, mode="error", detail=str(exc)[:200])


__all__ = [
    "write_action_items_to_projectops",
    "propagate_action_item_status",
    "get_org_default_project_number",
    "set_org_default_project_number",
    "ProjectOpsWriteResult",
    "ORG_DEFAULT_SETTING_KEY",
    "SESSION_OVERRIDE_KEY",
]
