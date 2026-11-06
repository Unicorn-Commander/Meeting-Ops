"""Optional bearer protection for the Prometheus mount."""

import secrets


def test_metrics_remain_available_when_token_is_unset(client, monkeypatch):
    monkeypatch.delenv("METRICS_TOKEN", raising=False)

    response = client.get("/metrics")

    assert response.status_code == 200


def test_metrics_require_bearer_token_when_configured(client, monkeypatch):
    token = secrets.token_urlsafe(24)
    monkeypatch.setenv("METRICS_TOKEN", token)

    missing = client.get("/metrics")
    wrong = client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {secrets.token_urlsafe(24)}"},
    )
    valid = client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert valid.status_code == 200
    assert token not in missing.text
    assert missing.headers["www-authenticate"] == "Bearer"
