"""Authentication boundaries for formerly public status and system routes."""

import pytest


PROTECTED_STATUS_ROUTES = (
    "/api/system/capabilities",
    "/api/system/pipeline",
    "/api/system/audio-devices",
    "/api/audio-devices",
    "/api/founding/status?cohort=meeting_ops_v1",
    "/api/live-transcription/status",
)


@pytest.mark.parametrize("path", PROTECTED_STATUS_ROUTES)
def test_status_and_system_routes_require_auth(client, monkeypatch, path):
    # The test environment normally leaves this enabled; make the route
    # deterministic if another focused test imported the cloud feature flag.
    from api import rooms

    monkeypatch.setattr(rooms, "ROOM_MODE_ENABLED", True)

    response = client.get(path)

    assert response.status_code == 401, response.text
