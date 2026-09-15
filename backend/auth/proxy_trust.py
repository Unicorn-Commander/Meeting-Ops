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

The trust gate is **FAIL-CLOSED by default**:

  * **No secret configured → headers IGNORED.** If ``PROXY_AUTH_SHARED_SECRET``
    is unset/empty, the forward-auth identity headers are never honoured. This
    is correct (and safe) for deployments that don't use oauth2-proxy
    forward-auth at all — e.g. the native-OIDC prod path, which authenticates
    via the ``mo_uc_session`` cookie. A forged ``X-Auth-Request-*`` on such a
    deploy can no longer authenticate anyone.
  * **Secret configured → headers honoured only with a matching X-Proxy-Auth.**
    A request whose ``X-Proxy-Auth`` is missing or non-matching has its
    forward-auth headers ignored entirely. The caller then falls through to
    JWT / UC-SSO cookie / PAT / API-key auth — all cryptographically
    authenticated and unaffected by this gate — so a legitimately logged-in
    user is never locked out.

Trusted ⟺ (secret configured) AND (request carries a matching ``X-Proxy-Auth``).
An oauth2-proxy / forward-auth deployment therefore MUST set the secret AND wire
the Traefik ``X-Proxy-Auth`` injection (``customRequestHeaders``, which also
overwrites any client-supplied copy, so a forger cannot smuggle the header
through the proxy). As defence-in-depth the edge should also strip inbound
``X-Auth-Request-*`` headers. The secret is compared in constant time
(``secrets.compare_digest``), mirroring ``auth/internal.py``.

``forward_auth_trusted`` accepts any case-insensitive header mapping, so it
works for both Starlette ``Request.headers`` and ``WebSocket.headers``.

The secret itself may be supplied either as ``PROXY_AUTH_SHARED_SECRET`` (env)
or, preferred, as ``PROXY_AUTH_SHARED_SECRET_FILE`` pointing at a mounted file
-- the latter keeps the value out of ``docker inspect``. See the constants
below for the precedence and the deliberate fallback behaviour.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Mapping

logger = logging.getLogger(__name__)

# Secret-carrying header the fronting proxy (Traefik) injects on trusted routes.
PROXY_AUTH_HEADER = "X-Proxy-Auth"

# Two ways to supply the shared secret, checked in this order:
#
#   1. ``PROXY_AUTH_SHARED_SECRET_FILE`` -- path to a file whose entire content
#      (whitespace-stripped) is the secret. PREFERRED: the value never appears
#      in ``docker inspect`` / the container's environment, so it is not
#      readable by anything with the docker socket.
#   2. ``PROXY_AUTH_SHARED_SECRET`` -- the value inline in the environment.
#      Still supported, so a deploy can adopt (1) without a flag-day cutover.
#
# The file source falls back to the env var when the path is unset, missing,
# unreadable or empty, and says so in the log. That fallback is deliberate: this
# gate being unconfigured means every SSO forward-auth session stops being
# honoured, which logs real users out of a working deploy. A typo in a mount
# path must not do that while a valid env var is still present. The gate is
# still fail-closed in the way that matters -- if NEITHER source yields a value,
# the forward-auth identity headers are ignored entirely.
PROXY_AUTH_SECRET_ENV = "PROXY_AUTH_SHARED_SECRET"
PROXY_AUTH_SECRET_FILE_ENV = "PROXY_AUTH_SHARED_SECRET_FILE"

# path -> ((mtime_ns, size), value). Re-read only when the file changes, so the
# secret can be rotated without restarting the process, at the cost of one
# stat() per call.
_FILE_CACHE: dict = {}

# Rate-limit file problems to one log line per (path, reason) per process.
_FILE_WARNED: set = set()


def _warn_file(path: str, reason: str) -> None:
    key = (path, reason)
    if key in _FILE_WARNED:
        return
    _FILE_WARNED.add(key)
    logger.error(
        "%s=%r could not be used (%s); falling back to the %s environment "
        "variable. Fix the mount -- if neither source yields a secret, SSO "
        "forward-auth identity headers are ignored (fail-closed) and "
        "forward-auth logins stop working.",
        PROXY_AUTH_SECRET_FILE_ENV, path, reason, PROXY_AUTH_SECRET_ENV,
    )


def _secret_from_file() -> str:
    path = (os.environ.get(PROXY_AUTH_SECRET_FILE_ENV, "") or "").strip()
    if not path:
        return ""
    try:
        st = os.stat(path)
    except OSError as exc:
        _warn_file(path, f"stat failed: {exc.__class__.__name__}")
        return ""
    stamp = (st.st_mtime_ns, st.st_size)
    cached = _FILE_CACHE.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = fh.read().strip()
    except OSError as exc:
        _warn_file(path, f"read failed: {exc.__class__.__name__}")
        return ""
    _FILE_CACHE[path] = (stamp, value)
    if not value:
        _warn_file(path, "file is empty")
    return value


def configured_secret_source() -> str:
    """Which source supplied the secret: ``"file"``, ``"env"`` or ``"none"``.

    Observability only -- never returns or logs the value. Lets a deploy check
    that a ``_FILE`` mount is actually in use before the env var is removed.
    """
    if _secret_from_file():
        return "file"
    if (os.environ.get(PROXY_AUTH_SECRET_ENV, "") or ""):
        return "env"
    return "none"


def _configured_secret() -> str:
    return _secret_from_file() or os.environ.get(PROXY_AUTH_SECRET_ENV, "") or ""


def proxy_trust_enforced() -> bool:
    """True when a shared secret is configured.

    The trust gate is fail-closed regardless of this value; it reports whether
    the ``X-Proxy-Auth`` handshake is provisioned (i.e. whether this deploy can
    honour forward-auth identity headers at all). False => forward-auth is
    effectively disabled and all auth flows through tokens / cookies.
    """
    return bool(_configured_secret())


def _warn_no_secret() -> None:
    # Log once per process so an unconfigured forward-auth deploy is visible in
    # ops dashboards without flooding them. For native-OIDC / cookie deploys
    # (e.g. prod) this is expected and benign.
    if not getattr(_warn_no_secret, "_warned", False):
        logger.warning(
            "PROXY_AUTH_SHARED_SECRET is unset; SSO forward-auth identity "
            "headers (X-Auth-Request-*) are IGNORED (fail-closed). This is "
            "correct for deployments that don't use oauth2-proxy forward-auth "
            "(e.g. native-OIDC). If this deployment DOES use forward-auth, set "
            "the env var AND the matching Traefik %s injection.",
            PROXY_AUTH_HEADER,
        )
        _warn_no_secret._warned = True  # type: ignore[attr-defined]


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
        _warn_no_secret()
        return False  # fail-closed: no secret => forward-auth headers ignored

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


__all__ = [
    "PROXY_AUTH_HEADER",
    "PROXY_AUTH_SECRET_ENV",
    "PROXY_AUTH_SECRET_FILE_ENV",
    "configured_secret_source",
    "forward_auth_trusted",
    "proxy_trust_enforced",
]
