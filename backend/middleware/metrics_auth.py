"""Optional bearer authentication for the Prometheus ASGI mount."""

from __future__ import annotations

import hmac
import os

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def _configured_metrics_token() -> str:
    """Return the opt-in metrics token without ever logging or exposing it."""
    return os.getenv("METRICS_TOKEN", "").strip()


def _authorization_header(scope: Scope) -> str:
    """Extract the Authorization header from an ASGI HTTP scope."""
    for name, value in scope.get("headers", ()):
        if name.lower() != b"authorization":
            continue
        try:
            return value.decode("latin-1").strip()
        except UnicodeDecodeError:
            return ""
    return ""


def _has_valid_bearer(scope: Scope, expected: str) -> bool:
    """Check an exact bearer token using a constant-time comparison."""
    parts = _authorization_header(scope).split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    return hmac.compare_digest(parts[1], expected)


class MetricsTokenAuth:
    """ASGI wrapper that gates Prometheus only when ``METRICS_TOKEN`` is set."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        expected = _configured_metrics_token()
        if expected and not _has_valid_bearer(scope, expected):
            response = JSONResponse(
                {"detail": "Not authenticated"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
