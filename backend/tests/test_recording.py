"""Tests for recording session CRUD endpoints"""
import uuid


def test_create_session(client):
    """POST /api/simple/recording-sessions creates a session and returns its id."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Test Session", "description": "Unit test session"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["name"] == "Test Session"
    assert data["status"] == "active"


def test_list_sessions(client):
    """GET /api/simple/recording-sessions returns a list."""
    # Create a session first
    client.post(
        "/api/simple/recording-sessions",
        json={"name": "List Test Session"},
    )
    response = client.get("/api/simple/recording-sessions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_session_detail(client):
    """GET /{id} returns full session data with expected fields."""
    create_response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Detail Test Session", "description": "details"},
    )
    session_id = create_response.json()["id"]

    response = client.get(f"/api/simple/recording-sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id
    assert data["name"] == "Detail Test Session"


def test_get_session_not_found(client):
    """GET with nonexistent id returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/simple/recording-sessions/{fake_id}")
    assert response.status_code == 404


def test_delete_session(client):
    """DELETE removes the session."""
    create_response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Delete Test Session"},
    )
    session_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/simple/recording-sessions/{session_id}")
    assert delete_response.status_code == 200

    # Verify it's gone
    get_response = client.get(f"/api/simple/recording-sessions/{session_id}")
    assert get_response.status_code == 404


def test_delete_session_not_found(client):
    """DELETE with nonexistent id returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.delete(f"/api/simple/recording-sessions/{fake_id}")
    assert response.status_code == 404


def test_create_session_without_name(client):
    """POST without the required 'name' field returns 422 validation error."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"description": "No name provided"},
    )
    assert response.status_code == 422


def test_session_fields(client):
    """Verify response has expected fields: id, name, status, created_at, duration."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Fields Test Session", "description": "Check fields"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "name" in data
    assert "status" in data
    assert "created_at" in data
    assert "duration" in data
