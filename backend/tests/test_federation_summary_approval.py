from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import federation_summary_approval as approval


class _DB:
    def __init__(self):
        self.commits = 0
        self.refreshed = []

    def commit(self):
        self.commits += 1

    def refresh(self, session):
        self.refreshed.append(session)


def _session(final_summary=None, summary=None):
    return SimpleNamespace(
        final_summary=final_summary,
        summary=summary,
        federation_summary_approved_at=None,
        federation_summary_approved_by_user_id=None,
        federation_summary_approved_digest=None,
    )


@pytest.mark.asyncio
async def test_approve_requires_editor_permission(monkeypatch):
    session = _session({"executive": "Recap"})
    db = _DB()
    seen = {}

    def resolve(*_args, **kwargs):
        seen["min_level"] = kwargs.get("min_level")
        return session

    monkeypatch.setattr(approval, "_resolve_session", resolve)
    monkeypatch.setattr(approval, "_can_edit", lambda *_args: False)
    with pytest.raises(HTTPException) as exc:
        await approval.approve_summary(
            "10", db, SimpleNamespace(id=4), SimpleNamespace(organization=SimpleNamespace(id=1))
        )
    assert exc.value.status_code == 403
    assert seen["min_level"] == "edit"
    assert db.commits == 0

    viewer = await approval.get_summary_approval(
        "10", db, SimpleNamespace(id=4), SimpleNamespace(organization=SimpleNamespace(id=1))
    )
    assert viewer.status == "unapproved"
    assert viewer.can_manage is False


@pytest.mark.asyncio
async def test_approve_rejects_missing_summary(monkeypatch):
    session = _session()
    monkeypatch.setattr(approval, "_resolve_session", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(approval, "_can_edit", lambda *_args: True)
    with pytest.raises(HTTPException) as exc:
        await approval.approve_summary(
            "10", _DB(), SimpleNamespace(id=4), SimpleNamespace(organization=SimpleNamespace(id=1))
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approve_mutation_stales_and_revoke(monkeypatch):
    session = _session({"executive": "Original recap"})
    db = _DB()
    user = SimpleNamespace(id=9)
    active_org = SimpleNamespace(organization=SimpleNamespace(id=1))
    monkeypatch.setattr(approval, "_resolve_session", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(approval, "_can_edit", lambda *_args: True)

    approved = await approval.approve_summary("10", db, user, active_org)
    assert approved.status == "approved"
    assert approved.approved_by_user_id == 9
    assert approved.can_manage is True
    assert db.commits == 1

    session.final_summary = {"executive": "Changed recap"}
    stale = await approval.get_summary_approval("10", db, user, active_org)
    assert stale.status == "stale"
    assert stale.approved_at is None

    revoked = await approval.revoke_summary_approval("10", db, user, active_org)
    assert revoked.status == "unapproved"
    assert session.federation_summary_approved_digest is None
    assert db.commits == 2
