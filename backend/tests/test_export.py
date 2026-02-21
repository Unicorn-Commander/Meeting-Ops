"""Tests for export/download endpoints"""
import uuid


def _create_session(client, name="Export Test Session"):
    """Helper to create a session and return its id."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"name": name, "description": "Session for export tests"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_export_txt(client):
    """GET /download/transcript returns text content for an existing session."""
    session_id = _create_session(client)
    response = client.get(
        f"/api/simple/recording-sessions/{session_id}/download/transcript"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    # The transcript should contain the session name
    assert "Export Test Session" in response.text


def test_export_transcript_simple(client):
    """GET /download/transcript/simple returns simple text for an existing session."""
    session_id = _create_session(client, name="Simple Export Session")
    response = client.get(
        f"/api/simple/recording-sessions/{session_id}/download/transcript/simple"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "Simple Export Session" in response.text


def test_export_session_not_found(client):
    """GET /download/transcript returns 404 for a nonexistent session."""
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/api/simple/recording-sessions/{fake_id}/download/transcript"
    )
    assert response.status_code == 404
