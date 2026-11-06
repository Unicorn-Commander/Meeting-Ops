"""The API documentation surface is opt-in for public deployments."""

import pytest


DOC_PATHS = ("/openapi.json", "/docs", "/redoc")


@pytest.mark.parametrize("path", DOC_PATHS)
def test_public_docs_are_not_enumerable_when_disabled(client, monkeypatch, path):
    monkeypatch.delenv("MEETING_OPS_PUBLIC_DOCS", raising=False)

    response = client.get(path)

    assert response.status_code == 404


@pytest.mark.parametrize("path", DOC_PATHS)
def test_public_docs_are_available_when_explicitly_enabled(client, monkeypatch, path):
    monkeypatch.setenv("MEETING_OPS_PUBLIC_DOCS", "1")

    response = client.get(path)

    assert response.status_code == 200, response.text
    if path == "/openapi.json":
        assert response.headers["content-type"].startswith("application/json")
    else:
        assert response.headers["content-type"].startswith("text/html")


def test_root_does_not_advertise_disabled_docs(client, monkeypatch):
    monkeypatch.delenv("MEETING_OPS_PUBLIC_DOCS", raising=False)
    assert "docs" not in client.get("/").json()

    monkeypatch.setenv("MEETING_OPS_PUBLIC_DOCS", "1")
    assert client.get("/").json()["docs"] == "/docs"
