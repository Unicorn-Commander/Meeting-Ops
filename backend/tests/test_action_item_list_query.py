"""The action-item list must not fetch large recording-session payloads."""

import re
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from api.action_items import list_action_items
from database.models import RecordingSession


@pytest.mark.asyncio
async def test_list_selects_only_response_session_columns(monkeypatch):
    statements = []

    def capture_all(query):
        statements.append(query.statement)
        return []

    monkeypatch.setattr(Query, "all", capture_all)
    with Session() as db:
        result = await list_action_items(
            status=None,
            session_id=None,
            limit=50,
            db=db,
            current_user=SimpleNamespace(id=1),
            active_org=SimpleNamespace(organization=SimpleNamespace(id=1)),
        )

    assert result == []
    assert len(statements) == 1
    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    select_clause = sql.partition("\nFROM ")[0]
    session_columns = set(
        re.findall(r"recording_sessions\.([a-z_]+)", select_clause)
    )
    assert session_columns == {
        "id",
        "session_id",
        "title",
        "name",
        "created_at",
    }
    assert "action_items.organization_id" in sql
    assert "recording_sessions.organization_id" in sql
    assert "ORDER BY recording_sessions.created_at DESC" in sql
    assert len(session_columns) < len(RecordingSession.__table__.columns)
