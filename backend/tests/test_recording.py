
def test_recording_session_flow(client):
    create_response = client.post(
        "/api/simple/recording-sessions",
        json={"name": "Test Session", "description": "Test description"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    session_id = created["id"]

    list_response = client.get("/api/simple/recording-sessions")
    assert list_response.status_code == 200
    sessions = list_response.json()
    assert any(session["id"] == session_id for session in sessions)

    get_response = client.get(f"/api/simple/recording-sessions/{session_id}")
    assert get_response.status_code == 200
    session_data = get_response.json()
    assert session_data["id"] == session_id

    delete_response = client.delete(f"/api/simple/recording-sessions/{session_id}")
    assert delete_response.status_code == 200
