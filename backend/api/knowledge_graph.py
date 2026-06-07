"""Knowledge Graph — cross-meeting, person-centric subgraph.

Surfaces a Speaker's Brigade (FalkorDB) neighborhood as an in-app graph,
reusing the per-session shaper (`_shape_brigade_graph`) and the 3D viewer's
``{nodes, links, focus}`` wire contract.

Tenancy / isolation model (mirrors the moat rules):
  * The ``SpeakerProfile`` is resolved ORG-SCOPED *before* any Brigade call —
    a cross-org or missing speaker is a 404 with no existence leak.
  * Brigade is never trusted to scope. In ``shared`` tenancy mode Brigade
    returns the raw neighborhood, so we filter the shaped nodes to the
    caller's ``org_id`` as defense-in-depth; in ``per_org_graph`` mode the
    graph itself is org-isolated so the filter is a no-op safety net.
  * ``org_id`` / graph-routing props are stripped from every node on the wire.
  * A hard server-side node cap (``KNOWLEDGE_GRAPH_NODE_CAP``, default 250)
    keeps the WebGL viewer comfortable and bounds the response.

This is a pure render of pre-computed graph data — no LLM call — so it costs
$0 marginal compute and keeps the browser-first economics intact.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.dependencies import get_current_organization, get_current_user
from auth.models import User
from auth.organization import ActiveOrganization
from auth.tier import require_feature
from database.database import get_db
from database.models import SpeakerProfile
from services.brigade_client import BrigadeClient
from services.brigade_writer import TENANCY_SHARED, _resolve_tenancy, _speaker_node_name

# Reuse the per-session shaper: same Brigade payload -> {nodes, links, focus}.
from api.recording import _shape_brigade_graph

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-graph"])

# Server-side node cap — the real OOM/perf guarantee for the 3D viewer.
_NODE_CAP = int(os.getenv("KNOWLEDGE_GRAPH_NODE_CAP", "250"))

# Person-view ships 1..2 hops (Brigade itself clamps to 1..5).
_MAX_HOPS = 2

# Props never sent to the client (tenancy / graph-routing internals).
_STRIPPED_NODE_PROPS = {"org_id", "graph", "graph_name", "tenancy_mode", "completion_mode"}


def _person_graph_url(speaker_node: str, organization_id: int) -> Optional[str]:
    """Deep-link to Brigade's knowledge UI focused on this speaker.

    NOTE: Brigade's UI does not yet honor ``?graph=``/``?focus=`` (it degrades
    to the default graph view) until the pending Brigade PR ships.
    """
    base = os.getenv("BRIGADE_PUBLIC_URL", "https://brigade.magicunicorn.dev").rstrip("/")
    try:
        graph_name = _resolve_tenancy(organization_id).graph_name
    except Exception:  # pragma: no cover - URL is best-effort
        return None
    return f"{base}/knowledge?graph={graph_name}&focus={speaker_node}"


def _enforce_org_and_cap(
    shaped: dict[str, Any],
    *,
    organization_id: int,
    shared_mode: bool,
) -> dict[str, Any]:
    """Filter shaped nodes to the caller's org (shared-mode safety), cap node
    count, strip tenancy/routing props, and drop now-dangling links.

    The focus node (the org-verified speaker) is always kept. In shared mode a
    neighbor stamped with a *different* ``org_id`` is dropped; a neighbor with
    no ``org_id`` is kept (all Meeting-Ops-written nodes carry one, and
    per_org_graph is the recommended customer posture where this can't arise).
    """
    org_str = str(organization_id)
    nodes = shaped.get("nodes") or []
    links = shaped.get("links") or []

    kept: list[dict[str, Any]] = []
    truncated = False
    for node in nodes:
        props = node.get("properties") or {}
        if shared_mode and not node.get("is_focus"):
            node_org = props.get("org_id")
            if node_org is not None and str(node_org) != org_str:
                continue
        if len(kept) >= _NODE_CAP:
            truncated = True
            continue
        node["properties"] = {k: v for k, v in props.items() if k not in _STRIPPED_NODE_PROPS}
        kept.append(node)

    kept_ids = {n.get("id") for n in kept}
    kept_links = [
        link
        for link in links
        if link.get("source") in kept_ids and link.get("target") in kept_ids
    ]
    return {
        "nodes": kept,
        "links": kept_links,
        "focus": shaped.get("focus"),
        "truncated": truncated,
    }


@router.get("/api/knowledge-graph/person/{speaker_id}")
async def get_person_graph(
    speaker_id: int,
    hops: int = 2,
    current_user: User = Depends(require_feature("brigade_integration")),
    active_org: ActiveOrganization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """A speaker's cross-meeting subgraph from Brigade, org-scoped + capped.

    Response: ``{speaker_id, speaker_name, nodes, links, focus, graph_url,
    node_cap, truncated, reason}`` where ``reason`` is one of
    ``not_synced_yet`` / ``single_meeting`` / ``live_failed`` / ``None``.
    """
    org_id = active_org.organization.id

    # --- Tenancy boundary: resolve the speaker ORG-SCOPED first. Cross-org or
    #     missing -> 404, no existence leak (mirrors the per-session endpoint). ---
    speaker = (
        db.query(SpeakerProfile)
        .filter(
            SpeakerProfile.id == speaker_id,
            SpeakerProfile.organization_id == org_id,
        )
        .first()
    )
    if not speaker:
        raise HTTPException(status_code=404, detail="Speaker not found")

    hops = max(1, min(int(hops), _MAX_HOPS))
    speaker_node = _speaker_node_name(speaker.id)

    try:
        shared_mode = _resolve_tenancy(org_id).mode == TENANCY_SHARED
    except Exception:  # pragma: no cover - safest default is to filter
        shared_mode = True

    envelope = {
        "speaker_id": speaker.id,
        "speaker_name": speaker.display_name,
        "graph_url": _person_graph_url(speaker_node, org_id),
        "focus": speaker_node,
        "node_cap": _NODE_CAP,
    }

    client = BrigadeClient()
    client_is_live = client.is_live
    try:
        raw = await client.fetch_entity_context(
            entity_name=speaker_node,
            include_relationships=True,
            include_related=True,
            max_depth=hops,
        )
    finally:
        await client.aclose()

    if raw is None:
        # fetch_entity_context returns None for BOTH "Brigade unreachable" and
        # "no node for this speaker yet" — disambiguate via is_live.
        reason = "live_failed" if client_is_live else "not_synced_yet"
        return {**envelope, "nodes": [], "links": [], "truncated": False, "reason": reason}

    shaped = _shape_brigade_graph(raw, focus_node_id=speaker_node)
    result = _enforce_org_and_cap(shaped, organization_id=org_id, shared_mode=shared_mode)

    # Sparse states read better with explicit copy than an empty 3D canvas.
    meeting_count = sum(1 for n in result["nodes"] if n.get("label") == "Meeting")
    if len(result["nodes"]) <= 1:
        reason: Optional[str] = "not_synced_yet"
    elif meeting_count <= 1:
        reason = "single_meeting"
    else:
        reason = None

    return {**envelope, **result, "reason": reason}
