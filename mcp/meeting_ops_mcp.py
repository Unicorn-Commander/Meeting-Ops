#!/usr/bin/env python3
"""
Meeting-Ops MCP Server

Exposes Meeting-Ops meeting intelligence as tools for external AI agents
via the Model Context Protocol (MCP). Connects to the Meeting-Ops backend
REST API (default: http://localhost:9050).

Tools:
  - search_meetings: Semantic + keyword hybrid search across all meetings
  - ask_about_meetings: RAG query - ask questions about meeting content
  - list_meetings: List all recording sessions with filters
  - get_meeting_details: Get full details for a specific meeting
  - get_meeting_transcript: Get the transcript for a specific meeting
  - chat_with_meeting: Ask questions about a specific meeting
  - get_analytics: Get meeting analytics (speaker stats, trends)
  - get_meeting_insights: Get AI-generated insights for a meeting

Resources:
  - meetings://list - All meetings overview
  - meetings://{session_id} - Single meeting details

Usage:
  # stdio transport (for Claude Desktop, etc.)
  python3 mcp/meeting_ops_mcp.py

  # Or with custom backend URL
  MEETING_OPS_URL=http://192.168.10.30:9050 \
  MEETING_OPS_PAT=mops_pat_YOUR_TOKEN_HERE \
  python3 mcp/meeting_ops_mcp.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "meeting-ops": {
        "command": "python3",
        "args": ["/path/to/UC-Meeting-Ops/mcp/meeting_ops_mcp.py"],
        "env": {
          "MEETING_OPS_URL": "http://localhost:9050",
          "MEETING_OPS_PAT": "mops_pat_YOUR_TOKEN_HERE"
        }
      }
    }
  }

Mint a PAT in Meeting-Ops Settings -> Personal Access Tokens. The token is
shown once, then stored hashed-at-rest by the backend.
"""

import os
import json
import logging
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ── Configuration ───────────────────────────────────────────────────────
BACKEND_URL = os.getenv("MEETING_OPS_URL", "http://localhost:9050")
PERSONAL_ACCESS_TOKEN = os.getenv("MEETING_OPS_PAT", "").strip()

logger = logging.getLogger("meeting-ops-mcp")

# ── MCP Server ──────────────────────────────────────────────────────────
mcp = FastMCP(
    "Meeting-Ops",
    instructions=(
        "Meeting intelligence platform — search, query, and analyze "
        "recorded meetings via AI-powered RAG, semantic search, "
        "transcription, and analytics."
    ),
)

# ── HTTP Client Helpers ─────────────────────────────────────────────────


def _require_pat() -> str:
    if PERSONAL_ACCESS_TOKEN:
        return PERSONAL_ACCESS_TOKEN
    raise RuntimeError(
        "MEETING_OPS_PAT is required. Mint a token in Meeting-Ops Settings "
        "-> Personal Access Tokens, then set MEETING_OPS_PAT in your MCP "
        "client config."
    )


async def _api(method: str, path: str, **kwargs) -> Any:
    """Make an authenticated request to the Meeting-Ops backend API."""
    token = _require_pat()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await getattr(client, method)(
            f"{BACKEND_URL}{path}",
            headers=headers,
            **kwargs,
        )

        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()


def _fmt(data: Any) -> str:
    """Format API response data as readable text."""
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2, default=str)


async def _propose(action: str, payload: dict[str, Any]) -> str:
    data = await _api(
        "post",
        "/api/agent-actions/propose",
        json={"action": action, "payload": payload},
    )
    return _fmt(data)


# ── MCP Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def search_meetings(query: str, limit: int = 5) -> str:
    """Search across all recorded meetings using hybrid semantic + keyword search.

    Finds meetings by topic, speaker names, keywords, or any content
    mentioned in transcripts and summaries. Returns matching meetings
    ranked by relevance.

    Args:
        query: Natural language search query (e.g., "budget discussion",
               "meetings with John about Q4 planning")
        limit: Maximum number of results (1-20, default 5)
    """
    limit = max(1, min(20, limit))

    # Try semantic search first (Qdrant hybrid)
    try:
        data = await _api(
            "get",
            "/api/simple/recording-sessions/semantic-search",
            params={"q": query, "limit": limit},
        )
        if data and isinstance(data, list) and len(data) > 0:
            lines = [f"Found {len(data)} meetings matching '{query}':\n"]
            for i, item in enumerate(data, 1):
                title = item.get("title", "Untitled")
                score = item.get("score", 0)
                snippet = item.get("snippet", "")[:200]
                sid = item.get("session_id", "")
                created = item.get("created_at", "")[:10]
                lines.append(
                    f"{i}. **{title}** (score: {score:.3f})\n"
                    f"   Session ID: {sid}\n"
                    f"   Date: {created}\n"
                    f"   Snippet: {snippet}\n"
                )
            return "\n".join(lines)
    except Exception:
        pass

    # Fallback to full-text SQL search
    data = await _api(
        "get",
        "/api/simple/recording-sessions/search",
        params={"q": query, "limit": limit},
    )

    if not data:
        return f"No meetings found matching '{query}'."

    results = data if isinstance(data, list) else data.get("results", [])
    if not results:
        return f"No meetings found matching '{query}'."

    lines = [f"Found {len(results)} meetings matching '{query}':\n"]
    for i, item in enumerate(results, 1):
        title = item.get("title") or item.get("name", "Untitled")
        sid = item.get("session_id") or str(item.get("id", ""))
        created = str(item.get("created_at", ""))[:10]
        status = item.get("status", "")
        lines.append(
            f"{i}. **{title}** ({status})\n"
            f"   Session ID: {sid}\n"
            f"   Date: {created}\n"
        )
    return "\n".join(lines)


@mcp.tool()
async def ask_about_meetings(
    question: str,
    limit: int = 5,
) -> str:
    """Ask a question about your meetings using RAG (Retrieval-Augmented Generation).

    Searches meeting transcripts and summaries for relevant context, then
    uses an AI model to generate an answer citing specific meetings.
    Supports multi-turn conversation — follow-up questions automatically
    reference prior context.

    Args:
        question: Natural language question about meetings (e.g.,
                  "What decisions were made about the new product launch?",
                  "Summarize all meetings about the hiring process")
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


@mcp.tool()
async def list_meetings(
    status: str = "",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List all recording sessions, optionally filtered by status.

    Args:
        status: Filter by status (e.g., "completed", "recording", "error").
                Empty string returns all.
        limit: Maximum number of sessions to return (1-100, default 20)
        offset: Pagination offset (default 0)
    """
    limit = max(1, min(100, limit))
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status

    data = await _api("get", "/api/simple/recording-sessions", params=params)

    sessions = data if isinstance(data, list) else data.get("sessions", [])
    total = data.get("total", len(sessions)) if isinstance(data, dict) else len(sessions)

    if not sessions:
        return "No recording sessions found."

    lines = [f"Showing {len(sessions)} of {total} sessions:\n"]
    for s in sessions:
        title = s.get("title") or s.get("name", "Untitled")
        sid = s.get("session_id") or str(s.get("id", ""))
        status_val = s.get("status", "unknown")
        created = str(s.get("created_at", ""))[:16]
        duration = s.get("duration")
        dur_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration else "N/A"
        has_transcript = "Yes" if s.get("has_transcript") or s.get("transcript_simple") else "No"

        lines.append(
            f"- **{title}** [{status_val}]\n"
            f"  ID: {sid} | Date: {created} | Duration: {dur_str} | Transcript: {has_transcript}"
        )

    return "\n".join(lines)


@mcp.tool()
async def get_meeting_details(session_id: str) -> str:
    """Get full details for a specific meeting session.

    Returns metadata, summary, key points, action items, and decisions.

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
    """
    data = await _api("get", f"/api/simple/recording-sessions/{session_id}")

    title = data.get("title") or data.get("name", "Untitled")
    status = data.get("status", "unknown")
    created = str(data.get("created_at", ""))[:16]
    duration = data.get("duration")
    dur_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration else "N/A"

    lines = [
        f"# {title}",
        f"**Status:** {status}",
        f"**Date:** {created}",
        f"**Duration:** {dur_str}",
        f"**Session ID:** {session_id}",
    ]

    # Summary
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

    return "\n".join(lines)


@mcp.tool()
async def get_meeting_transcript(session_id: str, max_chars: int = 10000) -> str:
    """Get the transcript for a specific meeting.

    Returns the full transcript text (or truncated if very long).

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
        max_chars: Maximum characters to return (default 10000). Set higher
                   for full transcripts.
    """
    data = await _api("get", f"/api/simple/recording-sessions/{session_id}")

    title = data.get("title") or data.get("name", "Untitled")

    # Try transcript sources in priority order
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
        transcript = transcript[:max_chars] + f"\n\n... [Truncated at {max_chars} characters. Full transcript is {len(transcript)} characters.]"

    return f"# Transcript: {title}\n\n{transcript}"


@mcp.tool()
async def chat_with_meeting(session_id: str, message: str) -> str:
    """Ask a question about a specific meeting using AI chat.

    The AI has access to the meeting's full transcript and summary.
    Supports multi-turn conversation within the same meeting.

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
        message: Your question about the meeting (e.g., "What were the
                 action items?", "Who spoke the most?", "Summarize the
                 discussion about pricing")
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
    """Get meeting analytics including session counts, speaker statistics, and trends.

    Args:
        time_range: Time range for analytics — "week", "month", "quarter",
                    or "year" (default "month")
    """
    data = await _api(
        "get",
        "/api/analytics/summary",
        params={"time_range": time_range},
    )

    lines = [f"# Meeting Analytics ({time_range})\n"]

    total = data.get("total_sessions", 0)
    avg_duration = data.get("average_duration", 0)
    total_duration = data.get("total_duration", 0)

    lines.append(f"**Total sessions:** {total}")
    if avg_duration:
        lines.append(f"**Average duration:** {int(avg_duration // 60)}m {int(avg_duration % 60)}s")
    if total_duration:
        hours = total_duration / 3600
        lines.append(f"**Total recording time:** {hours:.1f} hours")

    # Speaker data
    speakers = data.get("speaking_time", [])
    if speakers:
        lines.append("\n## Top Speakers")
        for sp in speakers[:10]:
            name = sp.get("speaker", "Unknown")
            talk_time = sp.get("total_time", 0)
            seg_count = sp.get("segment_count", 0)
            mins = int(talk_time // 60)
            secs = int(talk_time % 60)
            lines.append(f"- **{name}**: {mins}m {secs}s ({seg_count} segments)")

    # Try duration trends
    try:
        trends = await _api("get", "/api/analytics/duration-trends")
        if trends:
            trend_data = trends if isinstance(trends, list) else trends.get("trends", [])
            if trend_data:
                lines.append("\n## Recent Duration Trends")
                for t in trend_data[-7:]:
                    date = str(t.get("date", ""))[:10]
                    count = t.get("count", 0)
                    avg = t.get("avg_duration", 0)
                    lines.append(f"- {date}: {count} sessions, avg {int(avg // 60)}m")
    except Exception:
        pass

    return "\n".join(lines)


@mcp.tool()
async def get_meeting_insights(session_id: str) -> str:
    """Get AI-generated insights for a specific meeting.

    Includes keywords, topics, sentiment analysis, and action items
    extracted by the AI from the meeting transcript.

    Args:
        session_id: The session ID (UUID or integer ID) of the meeting
    """
    data = await _api(
        "get",
        f"/api/simple/recording-sessions/{session_id}/insights",
    )

    lines = ["# Meeting Insights\n"]

    # Keywords
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

    # Topics
    topics = data.get("topics", [])
    if topics:
        lines.append("\n## Topics")
        for topic in topics:
            if isinstance(topic, dict):
                lines.append(f"- {topic.get('name', topic)}")
            else:
                lines.append(f"- {topic}")

    # Sentiment
    sentiment = data.get("sentiment")
    if sentiment:
        if isinstance(sentiment, dict):
            label = sentiment.get("label", "")
            score = sentiment.get("score", "")
            lines.append(f"\n## Sentiment\n{label} (confidence: {score})")
        else:
            lines.append(f"\n## Sentiment\n{sentiment}")

    # Action items
    actions = data.get("action_items", [])
    if actions:
        lines.append("\n## Action Items")
        for a in actions:
            if isinstance(a, dict):
                lines.append(f"- {a.get('task', a)}")
            else:
                lines.append(f"- {a}")

    # Decisions
    decisions = data.get("decisions", [])
    if decisions:
        lines.append("\n## Decisions")
        for d in decisions:
            lines.append(f"- {d}")

    if len(lines) <= 2:
        return f"No AI insights available for session {session_id}. The meeting may not have been processed yet."

    return "\n".join(lines)


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


# ── Prompts ─────────────────────────────────────────────────────────────


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


# ── Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not PERSONAL_ACCESS_TOKEN:
        sys.exit(
            "MEETING_OPS_PAT is required. Mint a token in Meeting-Ops "
            "Settings -> Personal Access Tokens, then set MEETING_OPS_PAT "
            "in your MCP client config."
        )
    mcp.run()
