"""Tests for recording session CRUD endpoints"""
import uuid
from unittest.mock import AsyncMock, patch

from auth.utils import get_password_hash


def _auth_headers(client):
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_session(client):
    """POST /api/simple/recording-sessions creates a session and returns its id."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Test Session", "description": "Unit test session"},
        headers=_auth_headers(client),
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["name"] == "Test Session"
    assert data["status"] == "active"


def test_list_sessions(client):
    """GET /api/simple/recording-sessions returns a cursor page."""
    # Create a session first
    client.post(
        "/api/simple/recording-sessions",
        json={"name": "List Test Session"},
        headers=_auth_headers(client),
    )
    response = client.get("/api/simple/recording-sessions", headers=_auth_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1
    assert "transcription" not in data["items"][0]


def test_session_list_and_detail_include_organization_timezone(client):
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal

    slug = f"timezone-payload-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        org = Organization(
            name=slug,
            slug=slug,
            is_active=True,
            settings={"timezone": "America/Chicago"},
        )
        user = User(
            email=f"{slug}@meeting-ops.local",
            username=slug,
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_verified=True,
            tier="enterprise",
        )
        db.add_all([org, user])
        db.flush()
        db.add(UserOrganization(user_id=user.id, organization_id=org.id, role="admin"))
        db.commit()
    finally:
        db.close()

    login = client.post(
        "/api/auth/login",
        data={"username": slug, "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-MeetingOps-Org": slug,
    }
    created = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Timezone payload session"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]

    listing = client.get("/api/simple/recording-sessions", headers=headers)
    assert listing.status_code == 200, listing.text
    row = next(item for item in listing.json()["items"] if item["id"] == session_id)
    assert row["organization_timezone"] == "America/Chicago"

    detail = client.get(
        f"/api/simple/recording-sessions/{session_id}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["organization_timezone"] == "America/Chicago"


def test_list_sessions_cursor_has_no_duplicates(client):
    headers = _auth_headers(client)
    for index in range(3):
        client.post(
            "/api/simple/recording-sessions",
            json={"name": f"Cursor Session {index}"},
            headers=headers,
        )

    first = client.get("/api/simple/recording-sessions?limit=2", headers=headers).json()
    assert first["next_cursor"]
    second = client.get(
        f"/api/simple/recording-sessions?limit=2&cursor={first['next_cursor']}",
        headers=headers,
    ).json()
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)



def test_list_sessions_meeting_date_cursor_pages_in_meeting_order(client):
    """sort=meeting_date_desc pages with a keyset cursor (it used to 400 on
    any cursor), in meeting-date order, without duplicates."""
    headers = _auth_headers(client)
    mine = {}
    for index, day in enumerate(["2026-01-05", "2026-03-01", "2026-02-10"]):
        sid = client.post(
            "/api/simple/recording-sessions",
            json={"name": f"Meeting order {index}"},
            headers=headers,
        ).json()["id"]
        r = client.patch(f"/api/simple/recording-sessions/{sid}", json={"meeting_date": day}, headers=headers)
        assert r.status_code == 200, r.text
        mine[sid] = day

    order, cursor = [], None
    for _ in range(200):
        url = "/api/simple/recording-sessions?limit=1&sort=meeting_date_desc"
        if cursor:
            url += f"&cursor={cursor}"
        page = client.get(url, headers=headers)
        assert page.status_code == 200, page.text
        body = page.json()
        order.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(order) == len(set(order))
    assert [mine[i] for i in order if i in mine] == ["2026-03-01", "2026-02-10", "2026-01-05"]

    # a cursor minted for one sort is refused for another
    first = client.get("/api/simple/recording-sessions?limit=1&sort=meeting_date_desc", headers=headers).json()
    bad = client.get(
        f"/api/simple/recording-sessions?limit=1&sort=meeting_date_asc&cursor={first['next_cursor']}",
        headers=headers,
    )
    assert bad.status_code == 400

def test_get_session_detail(client):
    """GET /{id} returns full session data with expected fields."""
    create_response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Detail Test Session", "description": "details"},
        headers=_auth_headers(client),
    )
    session_id = create_response.json()["id"]
    assert create_response.json()["created_at"].endswith("+00:00")

    response = client.get(f"/api/simple/recording-sessions/{session_id}", headers=_auth_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id
    assert data["name"] == "Detail Test Session"
    assert data["created_at"].endswith("+00:00")


def test_get_session_not_found(client):
    """GET with nonexistent id returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/simple/recording-sessions/{fake_id}", headers=_auth_headers(client))
    assert response.status_code == 404


def test_delete_session(client):
    """DELETE removes the session."""
    create_response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Delete Test Session"},
        headers=_auth_headers(client),
    )
    session_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/simple/recording-sessions/{session_id}", headers=_auth_headers(client))
    assert delete_response.status_code == 200

    # Verify it's gone
    get_response = client.get(f"/api/simple/recording-sessions/{session_id}", headers=_auth_headers(client))
    assert get_response.status_code == 404


def test_delete_session_purges_brigade_subgraph(client):
    from database.database import SessionLocal
    from database.models import RecordingSession
    from services.brigade_client import BrigadeWriteResult

    headers = _auth_headers(client)
    created = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Brigade Delete Session"},
        headers=headers,
    ).json()
    db = SessionLocal()
    try:
        session = db.query(RecordingSession).filter(RecordingSession.session_id == created["id"]).first()
        session.brigade_graph_node_id = f"meeting_ops_meeting_{session.id}"
        org_id = session.organization_id
        node_id = session.brigade_graph_node_id
        db.commit()
    finally:
        db.close()

    delete_graph = AsyncMock(return_value=BrigadeWriteResult(ok=True, mode="live"))
    with patch("services.brigade_writer.delete_session_from_brigade", delete_graph):
        response = client.delete(
            f"/api/simple/recording-sessions/{created['id']}",
            headers=headers,
        )

    assert response.status_code == 200
    delete_graph.assert_awaited_once_with(org_id, node_id)


def test_delete_session_not_found(client):
    """DELETE with nonexistent id returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.delete(f"/api/simple/recording-sessions/{fake_id}", headers=_auth_headers(client))
    assert response.status_code == 404


def test_create_session_without_name(client):
    """POST without the required 'name' field returns 422 validation error."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"description": "No name provided"},
        headers=_auth_headers(client),
    )
    assert response.status_code == 422


def test_session_fields(client):
    """Verify response has expected fields: id, name, status, created_at, duration."""
    response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Fields Test Session", "description": "Check fields"},
        headers=_auth_headers(client),
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "name" in data
    assert "status" in data
    assert "created_at" in data
    assert "duration" in data
