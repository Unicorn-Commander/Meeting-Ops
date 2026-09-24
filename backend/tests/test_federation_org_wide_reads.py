"""Org-wide federation reads (Legal-Ops, 2026-09-24).

Same guarantees as the contact tools: tenant-bound, minimized participants,
and a summary (with its decisions) leaves only when a human approved it.
Plus: an org that limits meetings to participants refuses org-wide reads.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from api import federation_meetings as fm


def _ctx(org_id: int, scopes=("meetings:read",)) -> fm.FederationContext:
    return fm.FederationContext(
        org_id=org_id, workspace_id="ws-legal", sub="legal-ops-perry", scopes=set(scopes)
    )


@pytest.fixture
def seeded(canonical_db_schema):
    from auth.models import Organization
    from database.database import SessionLocal
    from database.models import ActionItem, RecordingSession

    db = SessionLocal()
    org_id = canonical_db_schema
    suffix = uuid.uuid4().hex[:8]
    other = Organization(name=f"Other Tenant {suffix}", slug=f"other-{suffix}", is_active=True)
    db.add(other)
    db.commit()
    db.refresh(other)
    tag = uuid.uuid4().hex[:8]

    def make(org, title, **extra):
        s = RecordingSession(
            session_id=str(uuid.uuid4()), name=title, title=title, meeting_type="adhoc",
            mode="upload", status=extra.pop("status", "completed"), duration=90.0,
            organization_id=org, source_type="upload",
            participants=[{"name": "Shafen Khan", "email": "s@example.com", "contact_id": "c-1",
                           "speaker_embedding": [0.1]}],
            **extra,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    approved = make(
        org_id, f"GFL NDA review {tag}",
        final_summary={"executive": "We agreed the NDA scope.", "key_points": ["mutual NDA"],
                       "decisions": [{"text": "Sign the mutual NDA"}]},
        transcript_simple=f"secret-phrase-{tag} was said",
    )
    approved.federation_summary_approved_digest = fm.summary_approval_digest(approved)
    approved.federation_summary_approved_at = datetime.now(timezone.utc)
    unapproved = make(
        org_id, f"Budget sync {tag}",
        final_summary={"executive": "Unreviewed text", "decisions": [{"text": "Hidden decision"}]},
    )
    foreign = make(other.id, f"GFL NDA review {tag} (other tenant)")
    db.add(ActionItem(session_id=approved.id, organization_id=org_id, text="Send redline",
                      status="todo", sort_order=0))
    db.commit()
    yield {"db": db, "org": org_id, "other": other, "tag": tag,
           "approved": approved, "unapproved": unapproved, "foreign": foreign}
    db.close()


def _call(db, ctx, name, args):
    return asyncio.run(fm._dispatch_tool(db, ctx, name, args))


def test_search_is_tenant_bound_and_minimized(seeded):
    out = _call(seeded["db"], _ctx(seeded["org"]), "search_meetings", {"query": f"NDA review {seeded['tag']}"})
    ids = {m["id"] for m in out["meetings"]}
    assert seeded["approved"].id in ids
    assert seeded["foreign"].id not in ids
    m = out["meetings"][0]
    assert m["participants"] == [{"contact_id": "c-1", "display_name": "Shafen Khan"}]
    assert "email" not in str(m["participants"])


def test_transcript_is_searched_only_with_the_transcript_scope(seeded):
    q = {"query": f"secret-phrase-{seeded['tag']}"}
    assert _call(seeded["db"], _ctx(seeded["org"]), "search_meetings", q)["count"] == 0
    wide = _ctx(seeded["org"], ("meetings:read", fm.TRANSCRIPT_SCOPE))
    assert _call(seeded["db"], wide, "search_meetings", q)["count"] == 1


def test_search_treats_wildcards_literally(seeded):
    assert _call(seeded["db"], _ctx(seeded["org"]), "search_meetings", {"query": "%"})["count"] == 0


def test_details_release_summary_and_decisions_only_when_approved(seeded):
    db, ctx = seeded["db"], _ctx(seeded["org"])
    ok = _call(db, ctx, "get_meeting_details", {"session_id": str(seeded["approved"].id)})
    assert ok["summary_status"] == "approved"
    assert ok["summary"]["body"] == "We agreed the NDA scope."
    assert ok["decisions"] == [{"text": "Sign the mutual NDA"}]
    assert [a["text"] for a in ok["action_items"]] == ["Send redline"]
    hidden = _call(db, ctx, "get_meeting_details", {"session_id": seeded["unapproved"].session_id})
    assert hidden["summary"] is None and hidden["decisions"] == []
    assert "Unreviewed" not in str(hidden) and "Hidden decision" not in str(hidden)
    assert "transcript" not in str(ok).lower().replace("summary_status", "")


def test_another_tenants_meeting_is_not_found(seeded):
    with pytest.raises(HTTPException) as exc:
        _call(seeded["db"], _ctx(seeded["org"]), "get_meeting_details", {"session_id": str(seeded["foreign"].id)})
    assert exc.value.status_code == 404


def test_list_meetings_and_action_items(seeded):
    db, ctx = seeded["db"], _ctx(seeded["org"])
    listed = _call(db, ctx, "list_meetings", {"limit": 100})
    assert seeded["foreign"].id not in {m["id"] for m in listed["meetings"]}
    items = _call(db, ctx, "list_action_items", {"session_id": str(seeded["approved"].id)})
    assert items["action_items"][0]["status"] == "open"


def test_participants_only_org_refuses_org_wide_reads(seeded):
    from auth.models import Organization

    db = seeded["db"]
    org = db.query(Organization).get(seeded["org"])
    before = dict(org.settings or {})
    org.settings = {**before, "session_visibility": "participants"}
    db.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            _call(db, _ctx(seeded["org"]), "list_meetings", {})
        assert exc.value.status_code == 403
    finally:
        org.settings = before
        db.commit()


def test_tools_are_listed():
    names = {t["name"] for t in fm._TOOL_SCHEMAS}
    assert fm.ORG_WIDE_TOOLS <= names
