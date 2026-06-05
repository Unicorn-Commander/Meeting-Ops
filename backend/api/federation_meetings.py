"""Inbound federation read surface — Customer-Ops cockpit signal.

Customer-Ops (the relationship/funnel cockpit) renders "this customer's
meetings, summaries, and action items" in its customer-360, federated
from Meeting-Ops at read time. Meeting-Ops stays the system-of-record;
Customer-Ops stores nothing.

The reads are CONTACT-CENTRIC — keyed on a Contact-Ops ``contact_id``
(the canonical Contact-Ops person id). A meeting "belongs to" a contact
when that contact_id appears in the meeting's participant list
(``recording_sessions.participants[].contact_id``; GIN-indexed for the
``@>`` containment lookup — see alembic 041).

Auth (machine-to-machine, NOT the per-user PAT MCP at /mcp):
  * Bearer is a Brigade-minted RS256/EdDSA token (aud=meeting-ops),
    verified by services.brigade_jwt_verifier (JWKS, iss, exp, ...).
  * Tenant is bound from the verified ``workspace_id`` claim ->
    Organization.workspace_id -> org_id. NEVER from a header.
  * The data reads additionally require the ``meetings:read`` scope.

Transports (same handlers underneath; the Customer-Ops client points at
whichever it speaks):
  * REST:  GET /api/federation/v1/contacts/{contact_id}/{meetings|summaries|action-items}
  * MCP :  POST /api/federation/mcp   (JSON-RPC: initialize / tools/list / tools/call)

This surface is read-only; no writes back into Meeting-Ops.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth.models import Organization
from database.database import get_db
from database.models import ActionItem, RecordingSession
from services.brigade_jwt_verifier import (
    extract_scopes,
    verify_brigade_jwt_with_reason,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/federation", tags=["federation"])

# The read scope a Brigade token must carry to read meeting signal. The
# Customer-Ops KC client is granted this; Brigade propagates it.
READ_SCOPE = os.getenv("FEDERATION_MEETINGS_READ_SCOPE", "meetings:read")

# Default page size for the meeting list; the contract caps to keep the
# cockpit responsive.
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


# ── Tenant binding ─────────────────────────────────────────────────────


def org_for_workspace_id(db: Session, workspace_id: str) -> Optional[Organization]:
    """Resolve a uc-registry workspace UUID to a Meeting-Ops org.

    Meeting-Ops tenancy is an integer ``organization_id``; the suite
    identity is the ``workspace_id`` UUID. ``Organization.workspace_id``
    (alembic 041) is the join. Returns None when the workspace is not
    provisioned here — the caller fails closed (403)."""
    if not workspace_id:
        return None
    return (
        db.query(Organization)
        .filter(Organization.workspace_id == workspace_id)
        .first()
    )


@dataclass
class FederationContext:
    org_id: int
    workspace_id: str
    sub: str
    scopes: set = field(default_factory=set)
    claims: dict = field(default_factory=dict)


def require_brigade_token(
    request: Request, db: Session = Depends(get_db)
) -> FederationContext:
    """Verify the Brigade federation bearer and bind the tenant.

    401 on a missing/invalid token; 403 when the asserted workspace is
    not provisioned in Meeting-Ops. Does NOT enforce the read scope —
    that is asserted per data-read so initialize/tools-list stay open to
    any valid meeting-ops token."""
    auth = request.headers.get("authorization", "")
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="missing or malformed bearer token")

    result = verify_brigade_jwt_with_reason(parts[1].strip())
    if not result.valid or not result.claims:
        raise HTTPException(
            status_code=401, detail=f"invalid federation token ({result.reason})"
        )

    claims = result.claims
    workspace_id = str(claims.get("workspace_id") or claims.get("org_id") or "")
    org = org_for_workspace_id(db, workspace_id)
    if org is None:
        logger.warning(
            "federation: workspace not provisioned workspace_id=%s sub=%s",
            workspace_id,
            claims.get("sub"),
        )
        raise HTTPException(
            status_code=403, detail="workspace not provisioned in meeting-ops"
        )

    return FederationContext(
        org_id=org.id,
        workspace_id=workspace_id,
        sub=str(claims.get("sub") or ""),
        scopes=extract_scopes(claims),
        claims=claims,
    )


def _require_read_scope(ctx: FederationContext) -> None:
    if READ_SCOPE not in ctx.scopes:
        raise HTTPException(
            status_code=403, detail=f"missing required scope: {READ_SCOPE}"
        )


# ── Serialization helpers ──────────────────────────────────────────────


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else None


def _clamp_limit(limit: Optional[int]) -> int:
    if not limit or limit < 1:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_LIMIT)


def _participants_public(session: RecordingSession) -> list[dict]:
    """Project the JSONB participant list to the federation shape.

    Each participant -> {contact_id, display_name, email}. contact_id may
    be null for participants not yet resolved to a Contact-Ops person."""
    raw = session.participants if isinstance(session.participants, list) else []
    out: list[dict] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        out.append(
            {
                "contact_id": p.get("contact_id") or None,
                "display_name": p.get("name") or None,
                "email": p.get("email") or None,
            }
        )
    return out


def _contact_filter(contact_id: str):
    """JSONB containment predicate: participants @> [{"contact_id": X}].

    Backed by the GIN index on recording_sessions.participants (alembic
    041) so the lookup is index-assisted, not a full scan."""
    return RecordingSession.participants.contains([{"contact_id": contact_id}])


def _action_item_counts(db: Session, org_id: int, session_ids: list[int]) -> dict:
    if not session_ids:
        return {}
    from sqlalchemy import func

    rows = (
        db.query(ActionItem.session_id, func.count(ActionItem.id))
        .filter(
            ActionItem.organization_id == org_id,
            ActionItem.session_id.in_(session_ids),
        )
        .group_by(ActionItem.session_id)
        .all()
    )
    return {sid: int(n) for sid, n in rows}


# ── The three contact-keyed reads ──────────────────────────────────────


def list_meetings_for_contact(
    db: Session,
    org_id: int,
    contact_id: str,
    *,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> dict:
    """Meetings where ``contact_id`` was a participant (newest first).

    Keyset pagination on session id (descending); ``cursor`` is the last
    id of the prior page."""
    n = _clamp_limit(limit)
    q = db.query(RecordingSession).filter(
        RecordingSession.organization_id == org_id,
        _contact_filter(contact_id),
    )
    if cursor:
        try:
            q = q.filter(RecordingSession.id < int(cursor))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="invalid cursor")
    rows = q.order_by(RecordingSession.id.desc()).limit(n + 1).all()

    has_more = len(rows) > n
    page = rows[:n]
    counts = _action_item_counts(db, org_id, [s.id for s in page])

    items = []
    for s in page:
        items.append(
            {
                "id": s.id,
                "title": s.title or s.name or None,
                "started_at": _iso(s.started_at),
                "ended_at": _iso(s.ended_at),
                "duration_seconds": int(round(s.duration or 0)),
                "status": s.status,
                "has_summary": bool(s.summary) or bool(s.final_summary),
                "action_item_count": counts.get(s.id, 0),
                "participants": _participants_public(s),
            }
        )
    return {
        "items": items,
        "count": len(items),
        "next_cursor": str(page[-1].id) if (has_more and page) else None,
    }


def list_summaries_for_contact(
    db: Session, org_id: int, contact_id: str, *, limit: Optional[int] = None
) -> list[dict]:
    """Summaries of meetings where ``contact_id`` was a participant."""
    n = _clamp_limit(limit)
    rows = (
        db.query(RecordingSession)
        .filter(
            RecordingSession.organization_id == org_id,
            _contact_filter(contact_id),
            or_(
                RecordingSession.summary.isnot(None),
                RecordingSession.final_summary.isnot(None),
            ),
        )
        .order_by(RecordingSession.id.desc())
        .limit(n)
        .all()
    )
    out: list[dict] = []
    for s in rows:
        fs = s.final_summary if isinstance(s.final_summary, dict) else {}
        key_points = fs.get("key_points") or fs.get("bullets") or []
        if not isinstance(key_points, list):
            key_points = []
        body = s.summary or fs.get("summary") or fs.get("overview") or ""
        out.append(
            {
                "id": f"summary-{s.id}",
                "meeting_id": s.id,
                "headline": s.title or s.name or fs.get("headline") or None,
                "body": body,
                "key_points": key_points,
                "created_at": _iso(s.updated_at or s.created_at),
            }
        )
    return out


def list_action_items_for_contact(
    db: Session, org_id: int, contact_id: str, *, limit: Optional[int] = None
) -> list[dict]:
    """Action items from meetings where ``contact_id`` was a participant.

    ``project_ops_task_id`` is whatever the Project-Ops bridge stamped on
    the item (raw_payload.po_task_id); null when the item was never
    bridged."""
    n = _clamp_limit(limit)
    session_ids = [
        r.id
        for r in db.query(RecordingSession.id)
        .filter(
            RecordingSession.organization_id == org_id,
            _contact_filter(contact_id),
        )
        .all()
    ]
    if not session_ids:
        return []
    rows = (
        db.query(ActionItem)
        .filter(
            ActionItem.organization_id == org_id,
            ActionItem.session_id.in_(session_ids),
        )
        .order_by(ActionItem.created_at.desc(), ActionItem.id.desc())
        .limit(n)
        .all()
    )
    out: list[dict] = []
    for it in rows:
        payload = it.raw_payload if isinstance(it.raw_payload, dict) else {}
        out.append(
            {
                "id": it.id,
                "meeting_id": it.session_id,
                "text": it.text,
                "status": it.status,
                # owner is free-text today; we do not resolve owner ->
                # contact_id yet, so this is null until that lands.
                "assignee_contact_id": None,
                "due_at": _iso(it.due_date),
                "project_ops_task_id": payload.get("po_task_id"),
                "created_at": _iso(it.created_at),
            }
        )
    return out


# ── REST transport ─────────────────────────────────────────────────────


@router.get("/v1/contacts/{contact_id}/meetings")
async def rest_meetings(
    contact_id: str,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
    ctx: FederationContext = Depends(require_brigade_token),
    db: Session = Depends(get_db),
):
    _require_read_scope(ctx)
    return list_meetings_for_contact(
        db, ctx.org_id, contact_id, limit=limit, cursor=cursor
    )


@router.get("/v1/contacts/{contact_id}/summaries")
async def rest_summaries(
    contact_id: str,
    limit: Optional[int] = None,
    ctx: FederationContext = Depends(require_brigade_token),
    db: Session = Depends(get_db),
):
    _require_read_scope(ctx)
    return list_summaries_for_contact(db, ctx.org_id, contact_id, limit=limit)


@router.get("/v1/contacts/{contact_id}/action-items")
async def rest_action_items(
    contact_id: str,
    limit: Optional[int] = None,
    ctx: FederationContext = Depends(require_brigade_token),
    db: Session = Depends(get_db),
):
    _require_read_scope(ctx)
    return list_action_items_for_contact(db, ctx.org_id, contact_id, limit=limit)


# ── MCP JSON-RPC transport ─────────────────────────────────────────────

_TOOL_SCHEMAS = [
    {
        "name": "list_meetings_for_contact",
        "description": (
            "Meetings where a Contact-Ops contact was a participant "
            "(newest first, keyset-paginated)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
            },
            "required": ["contact_id"],
        },
    },
    {
        "name": "list_summaries_for_contact",
        "description": "Summaries of meetings where a contact was a participant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["contact_id"],
        },
    },
    {
        "name": "list_action_items_for_contact",
        "description": "Action items from meetings where a contact was a participant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["contact_id"],
        },
    },
]


def _rpc_ok(rpc_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _rpc_err(rpc_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _dispatch_tool(
    db: Session, ctx: FederationContext, name: str, args: dict
) -> Any:
    contact_id = str(args.get("contact_id") or "").strip()
    if not contact_id:
        raise HTTPException(status_code=400, detail="contact_id is required")
    limit = args.get("limit")
    if name == "list_meetings_for_contact":
        return list_meetings_for_contact(
            db, ctx.org_id, contact_id, limit=limit, cursor=args.get("cursor")
        )
    if name == "list_summaries_for_contact":
        return list_summaries_for_contact(db, ctx.org_id, contact_id, limit=limit)
    if name == "list_action_items_for_contact":
        return list_action_items_for_contact(db, ctx.org_id, contact_id, limit=limit)
    raise KeyError(name)


@router.post("/mcp")
async def federation_mcp(
    request: Request,
    ctx: FederationContext = Depends(require_brigade_token),
    db: Session = Depends(get_db),
):
    """Minimal MCP JSON-RPC: initialize / tools/list / tools/call.

    The bearer is verified + tenant-bound by ``require_brigade_token``;
    ``tools/call`` additionally enforces the read scope."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid JSON-RPC envelope")

    method = body.get("method")
    rpc_id = body.get("id")

    if method == "initialize":
        return _rpc_ok(
            rpc_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "meeting-ops-federation",
                    "version": "1.0.0",
                },
            },
        )
    if method in ("notifications/initialized", "initialized"):
        return _rpc_ok(rpc_id, {})
    if method == "tools/list":
        return _rpc_ok(rpc_id, {"tools": _TOOL_SCHEMAS})
    if method == "tools/call":
        _require_read_scope(ctx)
        params = body.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            data = _dispatch_tool(db, ctx, str(name), args if isinstance(args, dict) else {})
        except KeyError:
            return _rpc_err(rpc_id, -32601, f"unknown tool: {name}")
        except HTTPException as exc:
            return _rpc_err(rpc_id, -32602, str(exc.detail))
        return _rpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": json.dumps(data, default=str)}]},
        )

    return _rpc_err(rpc_id, -32601, f"unknown method: {method}")
