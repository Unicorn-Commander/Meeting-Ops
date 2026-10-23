"""Public native-OIDC production must not publish /metrics.

The handler stays mounted for an internal scrape. The unicorncommander
Traefik router is the public front door and does not include it, and the
app comment must not claim oauth2-proxy already gates that host.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _meet_prod_rule() -> str:
    text = (ROOT / "deploy/unicorncommander/docker-compose.unicorncommander.yml").read_text()
    rules = [
        line for line in text.splitlines()
        if "traefik.http.routers.meet-prod.rule=" in line
    ]
    assert len(rules) == 1
    return rules[0]


def test_public_traefik_router_does_not_publish_metrics():
    rule = _meet_prod_rule()
    assert "PathPrefix(`/metrics`)" not in rule
    assert "/metrics" not in rule
    for prefix in ("/api", "/ws", "/health", "/mcp"):
        assert f"PathPrefix(`{prefix}`)" in rule


def test_metrics_comment_matches_native_oidc_production():
    text = (ROOT / "backend/main.py").read_text()
    start = text.index("# === Phase B.5: Prometheus /metrics endpoint ===")
    end = text.index('app.mount("/metrics"', start)
    block = text[start:end]
    assert "meeting-ops.unicorncommander.ai does not" in block
    assert "route /metrics" in block
    assert "already gated" not in block
    assert "Tailscale" not in block
    assert 'app.mount("/metrics"' in text[end:end + 40]
