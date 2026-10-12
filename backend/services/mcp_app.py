"""Shared MCP server app for Meeting-Ops.

This module owns the single FastMCP instance and every tool / resource /
prompt definition. Both the stdio entry point (``mcp/meeting_ops_mcp.py``)
and the hosted streamable-HTTP transport (``backend/api/mcp_http.py``)
import the same instance from here.

The tools forward every backend call as ``Authorization: Bearer
mops_pat_...`` so the existing PAT auth + per-user RBAC in
``backend/api/`` does all the scoping. The PAT itself is read from a
:class:`contextvars.ContextVar` so the same code path works for both
transports:

* stdio sets the ContextVar once from ``MEETING_OPS_PAT`` at startup.
* hosted HTTP sets it per-request from the inbound ``Authorization``
  header, then resets it after the response is sent.

Most MCP tools talk to the same backend REST API that the SPA + external
integrations talk to.  ``import_recording`` is the deliberate exception: the
hosted MCP process is already inside the backend, so it resolves the PAT and
calls the shared upload service directly instead of making a loopback HTTP
request.  Both paths retain the same server-side RBAC, tier, quota, and
organization scoping rules.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from services.mcp_cross_app import (
    build_cross_app_references,
    empty_cross_app_references,
    render_cross_app_section,
)


logger = logging.getLogger("meeting-ops-mcp")


# ── Per-request context ────────────────────────────────────────────────
#
# The PAT context var is the trust boundary: every tool call below pulls
# its PAT out of this var, never from a global. The transport layer
# (stdio entry point OR HTTP middleware) is responsible for populating
# it before any tool runs, and clearing it after.
#
# A separate backend URL context var lets the HTTP transport short-circuit
# to localhost (the backend lives in the same container) while stdio
# uses whatever the user configured.

_pat_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "meeting_ops_mcp_pat", default=None
)
_backend_url_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "meeting_ops_mcp_backend_url", default=None
)


def set_pat(token: str | None) -> contextvars.Token:
    """Set the PAT for the current async context.

    Returns a token the caller MUST reset to restore the previous value
    (typical pattern: ``tok = set_pat(...); try: ...; finally: reset_pat(tok)``).
    """
    return _pat_var.set(token)


def reset_pat(token: contextvars.Token) -> None:
    _pat_var.reset(token)


def set_backend_url(url: str | None) -> contextvars.Token:
    return _backend_url_var.set(url)


def reset_backend_url(token: contextvars.Token) -> None:
    _backend_url_var.reset(token)


def _default_backend_url() -> str:
    return os.getenv("MEETING_OPS_URL", "http://localhost:9050").rstrip("/")


# ── HTTP Client Helpers ─────────────────────────────────────────────────


def _require_pat() -> str:
    pat = _pat_var.get()
    if pat:
        return pat
    raise RuntimeError(
        "Meeting-Ops MCP: no Personal Access Token bound to this call. "
        "For stdio, set MEETING_OPS_PAT. For hosted MCP, include "
        "Authorization: Bearer mops_pat_... on the request."
    )


def _backend_url() -> str:
    return (_backend_url_var.get() or _default_backend_url()).rstrip("/")


def _resolve_mcp_active_organization(db, user, organization_id=None):
    """Resolve the same member-scoped default workspace used by the API.

    MCP has no browser request headers, so a PAT-bound organization is the
    explicit preference when present; otherwise use the user's persisted home
    organization and then their first membership.  The returned object is the
    same ``ActiveOrganization`` shape consumed by upload tier gates.
    """
    from auth.models import Organization, UserOrganization
    from auth.organization import ActiveOrganization, ensure_default_organization

    membership = None
    organization = None
    if organization_id is not None:
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if organization is None:
            raise HTTPException(status_code=403, detail="MCP token organization is unavailable.")
        membership = (
            db.query(UserOrganization)
            .filter(
                UserOrganization.user_id == user.id,
                UserOrganization.organization_id == organization.id,
            )
            .first()
        )
        if membership is None and not user.is_superuser:
            raise HTTPException(status_code=403, detail="MCP caller is not a member of this organization.")
    else:
        memberships = (
            db.query(UserOrganization)
            .filter(UserOrganization.user_id == user.id)
            .order_by(UserOrganization.id.asc())
            .all()
        )
        preferred_id = getattr(user, "default_organization_id", None)
        membership = next(
            (item for item in memberships if item.organization_id == preferred_id),
            None,
        )
        if membership is None and memberships:
            membership = memberships[0]
        if membership is not None:
            organization = (
                db.query(Organization)
                .filter(Organization.id == membership.organization_id)
                .first()
            )
        elif user.is_superuser:
            organization = ensure_default_organization(db)
        else:
            raise HTTPException(status_code=403, detail="MCP caller has no active organization.")

    role = "superuser" if user.is_superuser else (membership.role if membership else "viewer")
    return ActiveOrganization(organization=organization, membership=membership, role=role)


async def _api(method: str, path: str, **kwargs) -> Any:
    """Make an authenticated request to the Meeting-Ops backend API."""
    token = _require_pat()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await getattr(client, method)(
            f"{_backend_url()}{path}",
            headers=headers,
            **kwargs,
        )
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()


def _fmt(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2, default=str)


def _unwrap_list_payload(data: Any) -> tuple[list[dict[str, Any]], bool]:
    """Normalize a backend list payload into ``(rows, has_more)``.

    The REST endpoints these tools call do NOT agree on an envelope, and
    the shapes have drifted underneath us before:

    * ``GET /api/simple/recording-sessions`` returns the cursor-paginated
      envelope ``{"items": [...], "next_cursor": ..., "has_more": bool}``
      (it returned a bare JSON list until the pagination work in 3214f92).
    * ``GET /api/simple/recording-sessions/semantic-search`` returns
      ``{"query": ..., "results": [...], "count": n}``.
    * ``GET /api/simple/recording-sessions/search`` returns a bare list.
    * ``GET /api/analytics/duration-trends`` returns ``{"trends": [...]}``.

    Guessing a single key here is how ``list_meetings`` silently reported
    "no sessions" for every caller while the backend was returning a full
    page (see issue #9). Accept every shape we know about, and degrade to
    an empty page rather than raising when we meet one we don't.
    """
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)], False
    if isinstance(data, dict):
        for key in ("items", "results", "sessions", "trends"):
            value = data.get(key)
            if isinstance(value, list):
                rows = [row for row in value if isinstance(row, dict)]
                return rows, bool(data.get("has_more"))
    return [], False


async def _propose(action: str, payload: dict[str, Any]) -> str:
    data = await _api(
        "post",
        "/api/agent-actions/propose",
        json={"action": action, "payload": payload},
    )
    return _fmt(data)


# ── MCP Server ──────────────────────────────────────────────────────────


mcp = FastMCP(
    "Meeting-Ops",
    instructions=(
        "Meeting intelligence platform — search, query, and analyze "
        "recorded meetings via AI-powered RAG, semantic search, "
        "transcription, and analytics."
    ),
    # Disable FastMCP's built-in DNS-rebinding Host/Origin gate. We mount
    # this behind FastAPI, oauth2-proxy, and Traefik in production — all
    # three already enforce strict Host policy. In dev / tests the
    # endpoint is bound to localhost and gated by PAT. Reproducing the
    # FastMCP default (localhost-only Host allowlist) would 421-block
    # production traffic at ``meeting-ops.unicorncommander.ai`` and
    # break the TestClient harness.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ── MCP Tools (read-only) ──────────────────────────────────────────────


@mcp.tool()
async def search_meetings(query: str, limit: int = 5) -> str:
    """Search across all recorded meetings using hybrid semantic + keyword search.

    Finds meetings by topic, speaker names, keywords, or any content
    mentioned in transcripts and summaries. Returns matching meetings
    ranked by relevance. To resolve mentioned contacts/projects/cases
    against sibling Unicorn Commander apps (Contact-Ops, Project-Ops,
    Crisis-Ops), call ``get_cross_app_hints(session_id)`` per result.

    Args:
        query: Natural language search query (e.g., "budget discussion",
               "meetings with John about Q4 planning")
        limit: Maximum number of results (1-20, default 5)
    """
    limit = max(1, min(20, limit))

    try:
        data = await _api(
            "get",
            "/api/simple/recording-sessions/semantic-search",
            params={"q": query, "limit": limit},
        )
        # The endpoint answers with {"query", "results", "count"} — never a
        # bare list — so the old `isinstance(data, list)` guard was always
        # False and this tool silently degraded to keyword-only search for
        # every caller. Unwrap properly; an empty result set still falls
        # through to the keyword path below, which is the intended safety net
        # when Qdrant has nothing indexed or the tier gate refuses.
        hits, _ = _unwrap_list_payload(data)
        if hits:
            lines = [f"Found {len(hits)} meetings matching '{query}':\n"]
            for i, item in enumerate(hits, 1):
                # A JSON null in any of these is not a missing key, so the
                # "default" argument never fires: .get(k, d) returns None and
                # the format below raises (None:.3f) or slices None. The whole
                # block sits inside `except Exception: pass`, so the failure is
                # invisible -- semantic results are silently discarded and the
                # tool degrades to keyword-only search that still looks healthy.
                title = item.get("title") or "Untitled"
                try:
                    score = float(item.get("score") or 0)
                except (TypeError, ValueError):
                    score = 0.0
                snippet = (item.get("snippet") or "")[:200]
                sid = item.get("session_id") or ""
                created = _meeting_when(item, 10)
                lines.append(
                    f"{i}. **{title}** (score: {score:.3f})\n"
                    f"   Session ID: {sid}\n"
                    f"   Date: {created}\n"
                    f"   Snippet: {snippet}\n"
                )
            return "\n".join(lines)
    except Exception:
        pass

    data = await _api(
        "get",
        "/api/simple/recording-sessions/search",
        params={"q": query, "limit": limit},
    )

    results, _ = _unwrap_list_payload(data)
    if not results:
        return f"No meetings found matching '{query}'."

    lines = [f"Found {len(results)} meetings matching '{query}':\n"]
    for i, item in enumerate(results, 1):
        title = item.get("title") or item.get("name", "Untitled")
        sid = item.get("session_id") or str(item.get("id", ""))
        created = _meeting_when(item, 10)
        status = item.get("status", "")
        lines.append(
            f"{i}. **{title}** ({status})\n"
            f"   Session ID: {sid}\n"
            f"   Date: {created}\n"
        )
    return "\n".join(lines)


@mcp.tool()
async def ask_about_meetings(question: str, limit: int = 5) -> str:
    """Ask a question about your meetings using RAG (Retrieval-Augmented Generation).

    Searches meeting transcripts and summaries for relevant context, then
    uses an AI model to generate an answer citing specific meetings.

    Args:
        question: Natural language question about meetings
        limit: Number of meeting chunks to retrieve for context (1-20, default 5)
    """
    limit = max(1, min(20, limit))

    data = await _api(
        "post",
        "/api/ai-chat/rag/query",
        json={"message": question, "limit": limit},
    )

    answer = data.get("answer", "No answer generated.")
    sources = data.get("sources", [])
    metadata = data.get("metadata", {})

    lines = [answer, ""]

    if sources:
        lines.append("**Sources:**")
        for src in sources:
            title = src.get("title", "Untitled")
            sid = src.get("session_id", "")
            score = src.get("score", 0)
            lines.append(f"  - {title} (session: {sid}, relevance: {score:.3f})")

    rewritten = metadata.get("rewritten_query")
    if rewritten:
        lines.append(f"\n_Query interpreted as: \"{rewritten}\"_")

    return "\n".join(lines)


def _meeting_when(item: dict, width: int = 16) -> str:
    """When the meeting happened: meeting_date + meeting_time (the org's wall
    clock, what the Sessions page shows). Falls back to the upload time
    (created_at) for sessions that have no meeting date. Before this, every
    tool reported created_at, so a call uploaded a week late read as a week late."""
    d = item.get("meeting_date")
    if d:
        t = str(item.get("meeting_time") or "")[:5]
        return f"{d} {t}".strip() if width > 10 else str(d)[:10]
    return str(item.get("created_at", ""))[:width]


@mcp.tool()
async def list_meetings(status: str = "", limit: int = 20, offset: int = 0) -> str:
    """List all recording sessions, optionally filtered by status.

    Args:
        status: Filter by status (e.g., "completed", "recording"). Empty = all.
        limit: Maximum sessions to return (1-100, default 20)
        offset: Pagination offset (default 0)
    """
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    # Headless/MCP callers carry no X-MeetingOps-Org selector (only the web
    # workspace-switcher sends that header), so the backend would otherwise
    # scope to a single fallback active org — often the magic-unicorn platform
    # default — and return nothing for users whose sessions live in their own
    # orgs. Request the caller's full membership set instead: a member-scoped,
    # privacy-safe path already supported by list_sessions. See issue #9.
    #
    # ``status`` and ``offset`` are applied HERE, not on the wire: the list
    # endpoint takes neither (it is cursor-paginated and has no status
    # filter), so sending them was a silent no-op that made both documented
    # arguments lie to the caller. Over-fetch one page and slice locally.
    # The endpoint caps a page at 200 rows, so deep offsets are out of reach
    # without real cursor support — that's a follow-up, not a regression.
    fetch_limit = min(200, offset + limit)
    params: dict[str, Any] = {
        "limit": fetch_limit,
        "include_all_my_orgs": True,
        # Newest MEETING first (the date each row now shows), not newest upload.
        "sort": "meeting_date_desc",
    }

    data = await _api("get", "/api/simple/recording-sessions", params=params)

    sessions, has_more = _unwrap_list_payload(data)
    if status:
        wanted = status.strip().lower()
        sessions = [
            s for s in sessions if str(s.get("status", "")).strip().lower() == wanted
        ]
    if offset:
        has_more = has_more or len(sessions) > offset + limit
        sessions = sessions[offset:]
    if len(sessions) > limit:
        has_more = True
        sessions = sessions[:limit]

    if not sessions:
        return "No recording sessions found."

    more = " (more available)" if has_more else ""
    lines = [f"Showing {len(sessions)} sessions{more}:\n"]
    for s in sessions:
        title = s.get("title") or s.get("name", "Untitled")
        sid = s.get("session_id") or str(s.get("id", ""))
        status_val = s.get("status", "unknown")
        created = _meeting_when(s)
        duration = s.get("duration")
        dur_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration else "N/A"
        # The list payload defers every transcript column for speed, so the
        # old "Transcript: Yes/No" line read "No" on every row regardless of
        # reality. Show the workspace instead — it IS on the payload, and with
        # include_all_my_orgs a page now spans several of them.
        org = s.get("organization_name") or ""
        org_str = f" | Org: {org}" if org else ""
        lines.append(
            f"- **{title}** [{status_val}]\n"
            f"  ID: {sid} | Date: {created} | Duration: {dur_str}{org_str}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_meeting_details(session_id: str) -> str:
    """Get full details for a specific meeting session.

    Returns meeting details plus cross-app reference hints for related
    contacts/projects/cases in the UC ecosystem (Contact-Ops, Project-Ops,
    Crisis-Ops). AI clients can call those sibling MCP servers to resolve
    the handles into full records.

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
    """
    data = await _api("get", f"/api/simple/recording-sessions/{session_id}")

    title = data.get("title") or data.get("name", "Untitled")
    status = data.get("status", "unknown")
    created = _meeting_when(data)
    uploaded = str(data.get("created_at", ""))[:16]
    duration = data.get("duration")
    dur_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration else "N/A"

    lines = [
        f"# {title}",
        f"**Status:** {status}",
        f"**Date:** {created}",
        f"**Uploaded:** {uploaded}",
        f"**Duration:** {dur_str}",
        f"**Session ID:** {session_id}",
    ]

    summary = data.get("final_summary") or data.get("summary")
    if summary:
        if isinstance(summary, dict):
            if summary.get("executive"):
                lines.append(f"\n## Executive Summary\n{summary['executive']}")
            if summary.get("bullets"):
                lines.append("\n## Key Points")
                for b in summary["bullets"]:
                    lines.append(f"- {b}")
            if summary.get("decisions"):
                lines.append("\n## Decisions")
                for d in summary["decisions"]:
                    lines.append(f"- {d}")
            if summary.get("action_items"):
                lines.append("\n## Action Items")
                for a in summary["action_items"]:
                    lines.append(f"- {a}")
        elif isinstance(summary, str):
            try:
                parsed = json.loads(summary)
                lines.append(f"\n## Summary\n{_fmt(parsed)}")
            except (json.JSONDecodeError, TypeError):
                lines.append(f"\n## Summary\n{summary}")

    # Cross-app reference hints — best-effort. The sibling apps are not
    # contacted here; we just emit handles for the AI client to chase.
    try:
        refs = build_cross_app_references(data)
        section = render_cross_app_section(refs)
        if section:
            lines.append(section)
    except Exception:  # pragma: no cover - defensive
        logger.debug("cross-app reference build failed", exc_info=True)

    return "\n".join(lines)


@mcp.tool()
async def get_meeting_transcript(session_id: str, max_chars: int = 10000) -> str:
    """Get the transcript for a specific meeting.

    Returns the transcript plus cross-app reference hints (Contact-Ops /
    Project-Ops / Crisis-Ops) so AI clients can resolve mentioned people,
    projects, and cases against sibling MCP servers.

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
        max_chars: Maximum characters to return (default 10000)
    """
    data = await _api("get", f"/api/simple/recording-sessions/{session_id}")

    title = data.get("title") or data.get("name", "Untitled")

    transcript = data.get("transcript_simple", "")
    if not transcript:
        diarized = data.get("transcript_diarized")
        if diarized and isinstance(diarized, dict):
            segments = diarized.get("segments", [])
            lines = []
            for seg in segments:
                speaker = seg.get("speaker", "Speaker")
                text = seg.get("text", "")
                if text:
                    lines.append(f"{speaker}: {text}")
            transcript = "\n".join(lines)

    if not transcript:
        raw = data.get("transcript", "")
        if raw:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, dict) and "text" in parsed:
                    transcript = parsed["text"]
                elif isinstance(parsed, dict) and "segments" in parsed:
                    transcript = " ".join(
                        s.get("text", "") for s in parsed["segments"]
                    )
                else:
                    transcript = str(parsed)
            except (json.JSONDecodeError, TypeError):
                transcript = str(raw)

    if not transcript:
        return f"No transcript available for meeting '{title}' ({session_id})."

    max_chars = max(100, min(100000, max_chars))
    if len(transcript) > max_chars:
        transcript = (
            transcript[:max_chars]
            + f"\n\n... [Truncated at {max_chars} characters. "
            f"Full transcript is {len(transcript)} characters.]"
        )

    out = f"# Transcript: {title}\n\n{transcript}"

    try:
        refs = build_cross_app_references(data)
        section = render_cross_app_section(refs)
        if section:
            out = out + section
    except Exception:  # pragma: no cover - defensive
        logger.debug("cross-app reference build failed", exc_info=True)

    return out


@mcp.tool()
async def chat_with_meeting(session_id: str, message: str) -> str:
    """Ask a question about a specific meeting using AI chat.

    Args:
        session_id: The session ID of the meeting
        message: Your question about the meeting
    """
    data = await _api(
        "post",
        f"/api/ai-chat/sessions/{session_id}/messages",
        json={"message": message},
    )

    content = data.get("content", "No response generated.")
    sources = data.get("sources", [])
    metadata = data.get("metadata", {})

    lines = [content]

    if sources:
        src = sources[0]
        title = src.get("title", "")
        if title:
            lines.append(f"\n_Meeting: {title}_")

    response_ms = metadata.get("response_time_ms")
    if response_ms:
        lines.append(f"_Response time: {response_ms}ms_")

    return "\n".join(lines)


@mcp.tool()
async def get_analytics(time_range: str = "month") -> str:
    """Get meeting analytics including session counts, speaker stats, and trends.

    Args:
        time_range: "week" | "month" | "quarter" | "year" (default "month")
    """
    data = await _api(
        "get",
        "/api/analytics/summary",
        params={"time_range": time_range},
    )

    lines = [f"# Meeting Analytics ({time_range})\n"]

    # /api/analytics/summary nests the counters under "session_stats" and
    # keeps "speaking_time" at the top level. Reading them all as top-level
    # keys is why this tool printed "Total sessions: 0" next to a fully
    # populated Top Speakers list — the speakers are derived from the very
    # sessions the count claimed did not exist. Fall back to the flat keys so
    # an older backend still renders.
    stats = data.get("session_stats")
    if not isinstance(stats, dict):
        stats = {}

    total = stats.get("total_sessions", data.get("total_sessions", 0)) or 0
    avg_duration = stats.get("average_duration", data.get("average_duration", 0)) or 0
    total_duration = stats.get("total_duration", data.get("total_duration", 0)) or 0

    lines.append(f"**Total sessions:** {total}")
    if avg_duration:
        lines.append(f"**Average duration:** {int(avg_duration // 60)}m {int(avg_duration % 60)}s")
    if total_duration:
        hours = total_duration / 3600
        lines.append(f"**Total recording time:** {hours:.1f} hours")

    speakers = data.get("speaking_time", [])
    if speakers:
        lines.append("\n## Top Speakers")
        for sp in speakers[:10]:
            name = sp.get("speaker", "Unknown")
            # Endpoint emits "duration" / "segments"; the older flat names are
            # kept as fallbacks. Without this every speaker rendered 0m 0s.
            talk_time = sp.get("duration", sp.get("total_time", 0)) or 0
            seg_count = sp.get("segments", sp.get("segment_count", 0)) or 0
            mins = int(talk_time // 60)
            secs = int(talk_time % 60)
            lines.append(f"- **{name}**: {mins}m {secs}s ({seg_count} segments)")

    try:
        trends = await _api(
            "get",
            "/api/analytics/duration-trends",
            params={"time_range": time_range},
        )
        trend_data, _ = _unwrap_list_payload(trends)
        if trend_data:
            lines.append("\n## Recent Duration Trends")
            for t in trend_data[-7:]:
                # Buckets are keyed "period"/"sessions", not "date"/"count",
                # so every bucket used to print as ": 0 sessions".
                bucket = str(t.get("period") or t.get("date") or "")[:10]
                count = t.get("sessions", t.get("count", 0)) or 0
                avg = t.get("avg_duration", 0) or 0
                lines.append(f"- {bucket}: {count} sessions, avg {int(avg // 60)}m")
    except Exception:
        pass

    return "\n".join(lines)


@mcp.tool()
async def get_meeting_insights(session_id: str) -> str:
    """Get AI-generated insights for a specific meeting.

    Args:
        session_id: The session ID of the meeting
    """
    data = await _api(
        "get",
        f"/api/simple/recording-sessions/{session_id}/insights",
    )

    lines = ["# Meeting Insights\n"]

    keywords = data.get("keywords", [])
    if keywords:
        lines.append("## Keywords")
        kw_strs = []
        for kw in keywords[:20]:
            if isinstance(kw, dict):
                kw_strs.append(kw.get("word") or kw.get("keyword") or kw.get("name") or str(kw))
            else:
                kw_strs.append(str(kw))
        lines.append(", ".join(kw_strs))

    topics = data.get("topics", [])
    if topics:
        lines.append("\n## Topics")
        for topic in topics:
            if isinstance(topic, dict):
                lines.append(f"- {topic.get('name', topic)}")
            else:
                lines.append(f"- {topic}")

    sentiment = data.get("sentiment")
    if sentiment:
        if isinstance(sentiment, dict):
            label = sentiment.get("label", "")
            score = sentiment.get("score", "")
            lines.append(f"\n## Sentiment\n{label} (confidence: {score})")
        else:
            lines.append(f"\n## Sentiment\n{sentiment}")

    actions = data.get("action_items", [])
    if actions:
        lines.append("\n## Action Items")
        for a in actions:
            if isinstance(a, dict):
                lines.append(f"- {a.get('task', a)}")
            else:
                lines.append(f"- {a}")

    decisions = data.get("decisions", [])
    if decisions:
        lines.append("\n## Decisions")
        for d in decisions:
            lines.append(f"- {d}")

    if len(lines) <= 2:
        return f"No AI insights available for session {session_id}. The meeting may not have been processed yet."

    return "\n".join(lines)


@mcp.tool()
async def get_cross_app_hints(session_id: str) -> str:
    """Get cross-app reference hints for a meeting.

    Returns just the ``cross_app_references`` block (mentioned contacts,
    projects, cases) without the full meeting payload. Use this when the
    AI client already has the meeting context loaded and only wants the
    handles to query sibling Unicorn Commander MCP servers (Contact-Ops,
    Project-Ops, Crisis-Ops). The hints are best-effort — Meeting-Ops
    never contacts the sibling apps server-side, the AI client does.

    Schema:
        {
          "session_id": "...",
          "cross_app_references": {
            "mentioned_contacts": [{"name", "email", "confidence",
                                    "contact_ops_hint": {"app", "url", "query"}}],
            "mentioned_projects": [{"name", "confidence",
                                    "project_ops_hint": {"app", "url", "query"}}],
            "mentioned_cases":    [{"name", "confidence",
                                    "crisis_ops_hint": {"app", "url", "query"}}]
          }
        }

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
    """
    try:
        data = await _api("get", f"/api/simple/recording-sessions/{session_id}")
    except Exception:
        # Never break the AI's workflow on a missing/forbidden session —
        # emit the empty shape so the schema is still stable.
        return _fmt({
            "session_id": session_id,
            "cross_app_references": empty_cross_app_references(),
        })

    refs = build_cross_app_references(data)
    return _fmt({
        "session_id": session_id,
        "cross_app_references": refs,
    })


# ── MCP Tools (server-side media import) ───────────────────────────────


@mcp.tool()
async def import_recording(
    source_url: str | None = None,
    local_path: str | None = None,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Import one server-side audio/video source through the upload pipeline.

    Provide exactly one HTTPS ``source_url`` or one absolute ``local_path``
    under the server's ``MEETING_OPS_IMPORT_ROOTS`` allowlist.  The operation
    is immediately queued and returns a stable session id; it does not make a
    loopback HTTP request.  Repeating the call for the same caller and source
    bytes returns the original session.
    """
    from auth.pat import resolve_pat_record
    from database.database import SessionLocal
    from services.mcp_import import import_recording_for_caller

    token = _require_pat()
    db = SessionLocal()
    try:
        pat = resolve_pat_record(db, plaintext=token)
        if pat is None or pat.scope != "user":
            raise HTTPException(status_code=401, detail="A user-scoped MCP PAT is required.")
        active_org = _resolve_mcp_active_organization(db, pat.user, pat.organization_id)
        return await import_recording_for_caller(
            db=db,
            caller=pat.user,
            active_org=active_org,
            source_url=source_url,
            local_path=local_path,
            title=title,
            tags=tags,
        )
    finally:
        db.close()


# ── MCP Tools (propose → confirm; mutate-via-confirmation) ─────────────


@mcp.tool()
async def propose_create_session(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
) -> str:
    """Propose creating a session. Requires user confirmation before mutation."""
    payload: dict[str, Any] = {"title": title}
    if description:
        payload["description"] = description
    if tags:
        payload["tags"] = tags
    return await _propose("create_session", payload)


@mcp.tool()
async def propose_rename_session(session_id: str, title: str) -> str:
    """Propose renaming a session. Requires user confirmation before mutation."""
    return await _propose(
        "rename_session",
        {"session_id": session_id, "title": title},
    )


@mcp.tool()
async def propose_add_tag(session_id: str, tag: str) -> str:
    """Propose adding a tag to a session. Requires user confirmation before mutation."""
    return await _propose("add_tag", {"session_id": session_id, "tag": tag})


@mcp.tool()
async def propose_remove_tag(session_id: str, tag: str) -> str:
    """Propose removing a tag from a session. Requires user confirmation before mutation."""
    return await _propose("remove_tag", {"session_id": session_id, "tag": tag})


@mcp.tool()
async def propose_trigger_reprocess(session_id: str) -> str:
    """Propose triggering server reprocessing. Requires user confirmation."""
    return await _propose("trigger_reprocess", {"session_id": session_id})


@mcp.tool()
async def propose_draft_followup_email(
    session_id: str,
    recipient_name: str = "",
    notes: str = "",
) -> str:
    """Propose drafting a follow-up email. Requires confirmation before returning the draft."""
    payload: dict[str, Any] = {"session_id": session_id}
    if recipient_name:
        payload["recipient_name"] = recipient_name
    if notes:
        payload["notes"] = notes
    return await _propose("draft_followup_email", payload)


@mcp.tool()
async def confirm_action(token: str) -> str:
    """Confirm and apply a pending Meeting-Ops action proposal."""
    data = await _api(
        "post",
        "/api/agent-actions/confirm",
        json={"confirmation_token": token},
    )
    return _fmt(data)


@mcp.tool()
async def cancel_action(token: str) -> str:
    """Cancel a pending Meeting-Ops action proposal."""
    data = await _api(
        "post",
        "/api/agent-actions/cancel",
        json={"confirmation_token": token},
    )
    return _fmt(data)


# ── MCP Resources ──────────────────────────────────────────────────────


@mcp.resource("meetings://list")
async def meetings_list_resource() -> str:
    """Overview of all recorded meetings."""
    return await list_meetings(limit=50)


@mcp.resource("meetings://{session_id}")
async def meeting_resource(session_id: str) -> str:
    """Details for a specific meeting."""
    return await get_meeting_details(session_id)


# ── Prompts ────────────────────────────────────────────────────────────


@mcp.prompt()
def meeting_analysis(meeting_id: str) -> str:
    """Analyze a specific meeting in depth."""
    return (
        f"Please analyze meeting {meeting_id} by:\n"
        "1. Getting the meeting details\n"
        "2. Reading the transcript\n"
        "3. Getting the AI insights\n"
        "4. Providing a comprehensive analysis including key themes, "
        "decisions, action items, and any follow-up recommendations."
    )


@mcp.prompt()
def cross_meeting_research(topic: str) -> str:
    """Research a topic across all meetings."""
    return (
        f"Please research '{topic}' across all recorded meetings by:\n"
        "1. Searching for meetings related to this topic\n"
        "2. Asking the RAG system about this topic\n"
        "3. Synthesizing findings from multiple meetings\n"
        "4. Highlighting key decisions, action items, and evolving "
        "perspectives on this topic over time."
    )


# ── Public surface ─────────────────────────────────────────────────────


# Canonical set of read-only tool names. Tests assert that the shared
# instance still exposes every one of these so the stdio + hosted HTTP
# transports never silently diverge in capability.
READONLY_TOOL_NAMES: tuple[str, ...] = (
    "search_meetings",
    "ask_about_meetings",
    "list_meetings",
    "get_meeting_details",
    "get_meeting_transcript",
    "chat_with_meeting",
    "get_analytics",
    "get_meeting_insights",
    # v3.22 — cross-app reference resolver. Returns the lightweight
    # ``cross_app_references`` block standalone so AI clients can fetch
    # it without pulling the full meeting payload.
    "get_cross_app_hints",
)


__all__ = [
    "mcp",
    "set_pat",
    "reset_pat",
    "set_backend_url",
    "reset_backend_url",
    "READONLY_TOOL_NAMES",
    "import_recording",
]
