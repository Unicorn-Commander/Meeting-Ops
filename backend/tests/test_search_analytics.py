"""Tests for Workstream 3: Search, Analytics, and AI Insights endpoints."""
import json


# ---------------------------------------------------------------------------
# Helper to create a session with transcript content
# ---------------------------------------------------------------------------
def _create_session_with_transcript(client, name="Test Meeting", transcript_text=""):
    """Create a session and then manually set transcript fields via the DB."""
    resp = client.post(
        "/api/simple/recording-sessions",
        json={"name": name, "description": "automated test"},
    )
    assert resp.status_code == 200
    session_id = resp.json()["id"]
    return session_id


# ---------------------------------------------------------------------------
# 3A: Full-text search
# ---------------------------------------------------------------------------
class TestSearch:
    def test_search_returns_empty_for_no_match(self, client):
        resp = client.get(
            "/api/simple/recording-sessions/search",
            params={"q": "xyznonexistent12345"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_requires_query(self, client):
        resp = client.get("/api/simple/recording-sessions/search")
        # FastAPI returns 422 when required query param is missing
        assert resp.status_code == 422

    def test_search_finds_by_name(self, client):
        # Create a session whose name contains a known phrase
        session_id = _create_session_with_transcript(
            client, name="Budget Review Q1"
        )
        resp = client.get(
            "/api/simple/recording-sessions/search",
            params={"q": "Budget"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any(r["id"] == session_id for r in data)
        # Ensure snippet and match_field are present
        matched = [r for r in data if r["id"] == session_id][0]
        assert matched["match_field"] == "name"
        assert matched["snippet"] is not None

        # Cleanup
        client.delete(f"/api/simple/recording-sessions/{session_id}")

    def test_search_is_case_insensitive(self, client):
        session_id = _create_session_with_transcript(
            client, name="Security Audit Weekly"
        )
        for q in ["security", "SECURITY", "Security"]:
            resp = client.get(
                "/api/simple/recording-sessions/search",
                params={"q": q},
            )
            assert resp.status_code == 200
            assert any(r["id"] == session_id for r in resp.json()), f"Failed for query: {q}"

        client.delete(f"/api/simple/recording-sessions/{session_id}")


# ---------------------------------------------------------------------------
# 3B: Analytics endpoints
# ---------------------------------------------------------------------------
class TestAnalytics:
    def test_analytics_summary(self, client):
        resp = client.get("/api/analytics/summary", params={"time_range": "month"})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_stats" in data
        assert "speaking_time" in data
        assert "meeting_trends" in data
        assert "action_items" in data
        assert "total_speakers" in data["session_stats"]

    def test_analytics_summary_time_ranges(self, client):
        for tr in ["week", "month", "quarter", "year"]:
            resp = client.get("/api/analytics/summary", params={"time_range": tr})
            assert resp.status_code == 200
            assert resp.json()["time_range"] == tr

    def test_analytics_sessions(self, client):
        resp = client.get("/api/analytics/sessions", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_analytics_speakers(self, client):
        resp = client.get("/api/analytics/speakers", params={"time_range": "month"})
        assert resp.status_code == 200
        data = resp.json()
        assert "speakers" in data
        assert "total_speakers" in data

    def test_analytics_duration_trends_day(self, client):
        resp = client.get(
            "/api/analytics/duration-trends",
            params={"time_range": "month", "group_by": "day"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "trends" in data
        assert data["group_by"] == "day"

    def test_analytics_duration_trends_week(self, client):
        resp = client.get(
            "/api/analytics/duration-trends",
            params={"time_range": "quarter", "group_by": "week"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["group_by"] == "week"

    def test_analytics_performance(self, client):
        resp = client.get("/api/analytics/performance")
        assert resp.status_code == 200
        data = resp.json()
        assert "npu" in data
        assert data["npu"]["enabled"] is True


# ---------------------------------------------------------------------------
# 3C: AI Insights
# ---------------------------------------------------------------------------
class TestAIInsights:
    def test_insights_returns_defaults_for_no_transcription(self, client):
        session_id = _create_session_with_transcript(client, name="Empty Session")
        resp = client.get(f"/api/simple/recording-sessions/{session_id}/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "keywords" in data
        assert "speaker_insights" in data
        assert "sentiment" in data
        assert data["keywords"] == []
        assert data["speaker_insights"] == []

        client.delete(f"/api/simple/recording-sessions/{session_id}")

    def test_insights_404_for_missing_session(self, client):
        resp = client.get(
            "/api/simple/recording-sessions/nonexistent-uuid-12345/insights"
        )
        assert resp.status_code == 404

    def test_insights_response_schema(self, client):
        session_id = _create_session_with_transcript(client, name="Schema Test")
        resp = client.get(f"/api/simple/recording-sessions/{session_id}/insights")
        assert resp.status_code == 200
        data = resp.json()
        # Check all expected top-level fields
        expected_keys = {
            "summary", "keywords", "action_items", "speaker_insights",
            "sentiment", "duration", "topics", "key_decisions", "follow_ups",
        }
        assert expected_keys.issubset(set(data.keys()))
        # sentiment should have the three keys
        assert "positive" in data["sentiment"]
        assert "neutral" in data["sentiment"]
        assert "negative" in data["sentiment"]

        client.delete(f"/api/simple/recording-sessions/{session_id}")

    def test_regenerate_insights(self, client):
        session_id = _create_session_with_transcript(client, name="Regen Test")
        resp = client.post(
            f"/api/simple/recording-sessions/{session_id}/insights/regenerate"
        )
        assert resp.status_code == 200

        client.delete(f"/api/simple/recording-sessions/{session_id}")
