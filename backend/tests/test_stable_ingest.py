from database.database import SessionLocal
from database.models import RecordingSession, Transcription


def _pat_headers(client):
    login = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    bearer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post(
        "/api/auth/pats",
        headers=bearer,
        json={"name": "Stable production bridge"},
    )
    assert created.status_code == 201, created.text
    return {
        "Authorization": f"Bearer {created.json()['plaintext']}",
        "X-MeetingOps-Org": "magic-unicorn",
        "Idempotency-Key": "stable-export-001",
    }


def _payload():
    return {
        "source": "unicorn-stable",
        "export_id": "stable-export-001",
        "exported_at": "2026-07-29T15:02:30Z",
        "room_id": "1b7da004-8c92-43ba-babb-ef77fe70385b",
        "room_name": "Executive Staff",
        "call_started_at": "2026-07-29T15:00:00Z",
        "call_ended_at": "2026-07-29T15:02:00Z",
        "label": "Stable call · Executive Staff",
        "line_count": 2,
        "lines": [
            {
                "participant_id": "aaron",
                "name": "Aaron",
                "text": "Ship the enterprise bridge.",
                "ts": 1785337205000,
                "is_final": True,
                "segment_id": "seg-a",
                "source": "local_mic",
            },
            {
                "participant_id": "shafen",
                "name": "Shafen",
                "text": "I will own verification.",
                "ts": 1785337210000,
                "is_final": True,
                "segment_id": "seg-b",
                "source": "agent",
            },
        ],
        "exporter": {"username": "aaron"},
        "metadata": {"stable_version": "51f3888"},
    }


def test_ingest_requires_auth(client):
    response = client.post("/api/v1/sessions/ingest", json=_payload())
    assert response.status_code == 401


def test_ingest_creates_speaker_owned_session_and_is_idempotent(client):
    headers = _pat_headers(client)
    first = client.post("/api/v1/sessions/ingest", headers=headers, json=_payload())
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["session_url"].endswith(
        f"/sessions/{first.json()['session_id']}"
    )

    second = client.post("/api/v1/sessions/ingest", headers=headers, json=_payload())
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False
    assert second.json()["session_id"] == first.json()["session_id"]

    db = SessionLocal()
    try:
        rows = (
            db.query(RecordingSession)
            .filter(RecordingSession.external_id == "stable-export-001")
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.external_source == "unicorn-stable"
        assert row.organization_id is not None
        assert row.status == "completed"
        assert row.transcript_diarized["speakers"] == ["Aaron", "Shafen"]
        assert [s["speaker"] for s in row.transcript_diarized["segments"]] == [
            "Aaron",
            "Shafen",
        ]
        assert [s["source"] for s in row.transcript_diarized["segments"]] == [
            "local_mic",
            "agent",
        ]
        assert row.participants == [
            {"id": "aaron", "name": "Aaron", "role": "participant", "kind": "human"},
            {"id": "shafen", "name": "Shafen", "role": "agent", "kind": "agent"},
        ]
        transcript_rows = (
            db.query(Transcription)
            .filter(Transcription.session_id == row.id)
            .order_by(Transcription.id)
            .all()
        )
        assert [item.speaker for item in transcript_rows] == ["Aaron", "Shafen"]
    finally:
        db.close()


def test_ingest_rejects_mismatched_idempotency_key(client):
    headers = _pat_headers(client)
    headers["Idempotency-Key"] = "different"
    response = client.post("/api/v1/sessions/ingest", headers=headers, json=_payload())
    assert response.status_code == 409


def test_ingest_rejects_same_export_id_with_changed_payload(client):
    headers = _pat_headers(client)
    first = client.post("/api/v1/sessions/ingest", headers=headers, json=_payload())
    assert first.status_code == 200, first.text

    changed = _payload()
    changed["lines"][0]["text"] = "Tampered replacement."
    second = client.post("/api/v1/sessions/ingest", headers=headers, json=changed)
    assert second.status_code == 409
