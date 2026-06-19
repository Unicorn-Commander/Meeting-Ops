"""Proxy-trust boundary for SSO forward-auth identity headers.

oauth2-proxy authenticates the user against Keycloak and Traefik forwards the
resolved identity to this backend as plaintext request headers
(``X-Auth-Request-Email`` / ``-Groups`` / ``-Preferred-Username`` / ...). On a
shared Docker network those headers are trivially forgeable: any *other*
container can open a socket straight to this backend (bypassing Traefik) and
set them itself. Because ``X-Auth-Request-Groups`` drives ``is_superuser`` at
auto-provision time, an unguarded trust of these headers is a full auth bypass
*and* a privilege escalation to global admin.

This module gates that trust on a per-deploy shared secret that ONLY the
fronting proxy knows and injects (``X-Proxy-Auth``). The backend honours the
forward-auth identity headers only when the request also carries the matching
secret.

Rollout is designed so login can never break at any step:

  * **FAIL-OPEN until configured.** If ``PROXY_AUTH_SHARED_SECRET`` is
    unset/empty, the identity headers are trusted exactly as before, with a
    loud one-time warning. Ship the code first (no behaviour change), wire the
    Traefik ``X-Proxy-Auth`` injection second, THEN set the secret to switch to
    fail-closed. No flag-day.
  * **FAIL-CLOSED once the secret is set.** A request whose ``X-Proxy-Auth``
    is missing or non-matching has its forward-auth headers ignored entirely.
    The caller then falls through to JWT / UC-SSO cookie / PAT / API-key auth —
    all cryptographically authenticated and unaffected by this gate — so a
    legitimately logged-in user is never locked out.

The secret is compared in constant time (``secrets.compare_digest``), mirroring
``auth/internal.py``. The Traefik middleware that injects ``X-Proxy-Auth`` must
also *overwrite* any client-supplied copy (``customRequestHeaders`` does this),
so a forger cannot smuggle the header through the proxy.

``forward_auth_trusted`` accepts any case-insensitive header mapping, so it
works for both Starlette ``Request.headers`` and ``WebSocket.headers``.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Mapping

logger = logging.getLogger(__name__)

# Secret-carrying header the fronting proxy (Traefik) injects on trusted routes.
PROXY_AUTH_HEADER = "X-Proxy-Auth"


def _configured_secret() -> str:
    return os.environ.get("PROXY_AUTH_SHARED_SECRET", "") or ""


def proxy_trust_enforced() -> bool:
    """True when a secret is configured (fail-closed mode is active)."""
    return bool(_configured_secret())


def _warn_fail_open() -> None:
    # Log once per process so the insecure-but-intentional staging window is
    # visible in ops dashboards without flooding them.
    if not getattr(_warn_fail_open, "_warned", False):
        logger.warning(
            "PROXY_AUTH_SHARED_SECRET is unset; SSO forward-auth identity "
            "headers (X-Auth-Request-*) are trusted WITHOUT a proxy-trust "
            "boundary. This is FAIL-OPEN for staged rollout only. Set the env "
            "var (and the matching Traefik %s injection) to enforce.",
            PROXY_AUTH_HEADER,
        )
        _warn_fail_open._warned = True  # type: ignore[attr-defined]


def _warn_rejected() -> None:
    # Rate-limited to once per process so a hammering forger can't flood logs.
    if not getattr(_warn_rejected, "_warned", False):
        logger.warning(
            "Ignoring SSO forward-auth identity headers on a request lacking a "
            "valid %s secret (likely a forged or direct-to-container call). The "
            "caller falls through to token auth.",
            PROXY_AUTH_HEADER,
        )
        _warn_rejected._warned = True  # type: ignore[attr-defined]


def forward_auth_trusted(headers: Mapping[str, str]) -> bool:
    """Whether the SSO forward-auth identity headers on this request are trusted.

    ``headers`` is any case-insensitive mapping (Starlette ``Request.headers``
    or ``WebSocket.headers``). Returns True when the headers may be honoured,
    False when they must be ignored.
    """
    configured = _configured_secret()
    if not configured:
        _warn_fail_open()
        return True  # fail-open until the secret is provisioned

    presented = headers.get(PROXY_AUTH_HEADER)
    if not presented:
        _warn_rejected()
        return False
    # compare_digest short-circuits on unequal length; encode both sides so a
    # non-string presented value can't perturb the timing profile.
    try:
        ok = secrets.compare_digest(
            presented.encode("utf-8"), configured.encode("utf-8")
        )
    except (AttributeError, TypeError):
        ok = False
    if not ok:
        _warn_rejected()
    return ok


__all__ = ["PROXY_AUTH_HEADER", "forward_auth_trusted", "proxy_trust_enforced"]
