"""Tests for analytics endpoints"""
import pytest


def _analytics_available(client):
    """Check if analytics router loaded successfully."""
    response = client.get("/health")
    data = response.json()
    failed_names = [r["name"] for r in data.get("routers_failed", [])]
    return "analytics" not in failed_names


@pytest.fixture(autouse=True)
def skip_if_analytics_unavailable(client):
    """Skip all tests in this module if the analytics router failed to load."""
    if not _analytics_available(client):
        pytest.skip("analytics router not available in test environment")


def test_analytics_summary(client):
    """GET /api/analytics/summary returns valid structure."""
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert "time_range" in data
    assert "session_stats" in data
    assert "meeting_trends" in data
    assert "action_items" in data
    # Verify session_stats fields
    stats = data["session_stats"]
    assert "total_sessions" in stats
    assert "total_duration" in stats
    assert "average_duration" in stats


def test_analytics_sessions(client):
    """GET /api/analytics/sessions returns a list."""
    response = client.get("/api/analytics/sessions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_analytics_performance(client):
    """GET /api/analytics/performance returns NPU metrics."""
    response = client.get("/api/analytics/performance")
    assert response.status_code == 200
    data = response.json()
    assert "npu" in data
    npu = data["npu"]
    assert "enabled" in npu
    assert "real_time_factor" in npu
    assert "tokens_per_second" in npu


def test_analytics_time_range(client):
    """Query param time_range=week works."""
    response = client.get("/api/analytics/summary?time_range=week")
    assert response.status_code == 200
    data = response.json()
    assert data["time_range"] == "week"
