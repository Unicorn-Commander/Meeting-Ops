"""Hosted Meeting-Ops MCP endpoint over streamable HTTP.

Mounts the shared FastMCP server (defined in
``backend.services.mcp_app``) at ``/mcp`` on the main FastAPI app, so
external AI clients (Claude Desktop, Cursor, Cline, Continue, Zed,
ChatGPT Desktop, etc.) can connect without cloning the repo.

Auth: every request must carry ``Authorization: Bearer <credential>``.
User-scoped ``mops_pat_<...>`` PATs and verified uchub Keycloak access tokens
are accepted. The resolved local user and bearer credential are pinned to
contextvars for the duration of the request so the shared tool code can
forward it to the backend REST API and inherit per-user RBAC for free.

The hosted transport is gated by ``MCP_HOSTED_ENABLED`` (default true).
When false, ``mount_mcp_app`` is a no-op and ``/mcp`` 404s.

Health check: :func:`mcp_health_status` returns ``"ok"``, ``"disabled"``,
or ``"error: <reason>"`` so the top-level ``/health`` endpoint can
surface MCP availability at a glance.
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response


logger = logging.getLogger(__name__)


# Mirrors the FastMCP default; we mount at "/mcp" and let FastMCP own
# the trailing path internals.
_MOUNT_PATH = "/mcp"

# Browser clients known to use the hosted MCP endpoint. The app's configured
# origins are added below; ``MCP_ALLOWED_ORIGINS=*`` is the explicit opt-in for
# the pre-existing echo-any-origin behavior.
_ALLOWED_ORIGIN_HINTS = (
    "https://claude.ai",
    "https://claude.com",
    "https://cursor.sh",
    "https://chatgpt.com",
)

_PRM_ROOT_PATH = "/.well-known/oauth-protected-resource"
_PRM_MCP_PATH = f"{_PRM_ROOT_PATH}{_MOUNT_PATH}"
_MCP_RESOURCE_DOCUMENTATION = (
    "https://unicorncommander.ai/platform/bring-your-own-ai"
)


# Track readiness for /health.
_state: dict[str, str] = {"status": "disabled"}

# Holder for the currently-active inner FastMCP ASGI app. Recomputed
# every time the lifespan starts so the test harness (which spins
# lifespans up + down within one process) and uvicorn --reload always
# see a fresh, run-once session manager. Production hits this exactly
# once on startup.
_active_inner: dict[str, object] = {"app": None}


def _enabled() -> bool:
    raw = os.getenv("MCP_HOSTED_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def mcp_health_status() -> str:
    """Return the current MCP hosted-endpoint health status."""
    return _state.get("status", "disabled")


def _normalize_origin(value: str | None) -> str | None:
    """Return an origin without path/query/userinfo, or None if invalid."""
    raw = (value or "").strip()
    if not raw or raw == "*":
        return raw or None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _configured_mcp_origins() -> set[str]:
    """Build the MCP browser-origin allow-list from deployment config."""
    configured = os.getenv("MCP_ALLOWED_ORIGINS", "")
    configured_values = {
        origin
        for value in configured.split(",")
        if (origin := _normalize_origin(value))
    }
    if "*" in configured_values:
        return {"*"}

    allowed = set(_ALLOWED_ORIGIN_HINTS)
    for env_name in ("PUBLIC_BASE_URL", "APP_PUBLIC_URL", "CORS_ORIGINS"):
        for value in os.getenv(env_name, "").split(","):
            origin = _normalize_origin(value)
            if origin and origin != "*":
                allowed.add(origin)
    allowed.update(configured_values)
    return allowed


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    normalized = _normalize_origin(origin)
    if not normalized:
        return False
    allowed = _configured_mcp_origins()
    return "*" in allowed or normalized in allowed


def _public_base_url(scope: dict | None = None) -> str:
    """Resolve the externally visible app origin without hard-coding a host."""
    for env_name in ("PUBLIC_BASE_URL", "APP_PUBLIC_URL"):
        configured = os.getenv(env_name, "").strip().rstrip("/")
        if configured:
            parsed = urlsplit(configured)
            if parsed.scheme in {"http", "https"} and parsed.netloc and not (
                parsed.username or parsed.password
            ) and parsed.path in ("", "/") and not parsed.query and not parsed.fragment:
                return f"{parsed.scheme.lower()}://{parsed.netloc}".rstrip("/")

    scope = scope or {}
    raw_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    forwarded_host = raw_headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    host = forwarded_host or raw_headers.get("host", "").strip()
    if not host:
        server = scope.get("server") or ("localhost", 80)
        host = str(server[0])
        if server[1] not in (80, 443):
            host = f"{host}:{server[1]}"
    proto = (
        raw_headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
        or str(scope.get("scheme", "http")).lower()
    )
    if proto not in {"http", "https"}:
        proto = "https"
    return f"{proto}://{host}".rstrip("/")


def _keycloak_issuer() -> str:
    """Derive the PRM authorization server from the existing KC env names."""
    explicit = os.getenv("KEYCLOAK_ISSUER", "").strip().rstrip("/")
    if explicit:
        return explicit
    base = os.getenv("KEYCLOAK_URL", "https://auth.unicorncommander.ai").rstrip("/")
    realm = os.getenv("KEYCLOAK_REALM", "uchub").strip("/") or "uchub"
    return f"{base}/realms/{realm}"


def _protected_resource_document(scope: dict | None = None) -> dict:
    base_url = _public_base_url(scope)
    return {
        "resource": f"{base_url}{_MOUNT_PATH}",
        "authorization_servers": [_keycloak_issuer()],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "profile", "email", "offline_access", "mcp"],
        "resource_name": "Meeting-Ops MCP",
        "resource_documentation": _MCP_RESOURCE_DOCUMENTATION,
    }


# ── ASGI middleware: PAT auth + ContextVar pinning ─────────────────────


class _PATAuthMiddleware:
    """ASGI middleware that gates the mounted FastMCP app on bearer auth.

    Wraps the streamable-HTTP ASGI sub-app produced by FastMCP. On every
    HTTP request:

    1. Resolve a user-scoped PAT or a verified uchub Keycloak access token
       through the same auth helpers used by REST.
    2. Pin the bearer and resolved local user onto contextvars, and force the
       backend URL to localhost (the MCP tools call the same FastAPI app).
    3. Reset every contextvar after the inner app finishes, even on error.

    Preflight (CORS ``OPTIONS``) requests are answered directly without
    auth so browser-installed MCP clients can probe the endpoint. A browser
    Origin outside the configured allow-list is rejected before auth.
    """

    def __init__(self, inner_app):
        self._inner = inner_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._inner(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }

        method = scope.get("method", "GET").upper()
        origin = headers.get("origin")

        if not _origin_allowed(origin):
            await self._send_cors_forbidden(send)
            return

        # Preflight: respond before any auth.
        if method == "OPTIONS":
            await self._send_cors_preflight(send, origin)
            return

        # Extract bearer
        auth = headers.get("authorization", "")
        token = ""
        bearer_present = auth.lower().startswith("bearer ")
        if bearer_present:
            token = auth[7:].strip()

        # Import lazily so the api/mcp_http import doesn't pull in database
        # modules during conftest's reload dance.
        from auth.pat import TOKEN_PREFIX as PAT_PREFIX, resolve_pat
        from database.database import SessionLocal

        if not token:
            await self._send_401(
                send,
                origin,
                "Missing or malformed Authorization header.",
                token_presented=bearer_present,
                scope=scope,
            )
            return

        user = None
        if token.startswith(PAT_PREFIX):
            db = SessionLocal()
            try:
                try:
                    user = resolve_pat(db, plaintext=token)
                except Exception:
                    logger.exception("PAT resolution failed")
                    user = None
            finally:
                db.close()
        elif token.count(".") == 2:
            # Keycloak verification performs blocking JWKS I/O on a cache miss;
            # keep that work off the event loop. The helper returns only
            # verified claims and the REST-identical local user mapping.
            try:
                from auth.dependencies import resolve_keycloak_user
                from auth.oidc_sso import verify_kc_bearer_token

                claims = await asyncio.to_thread(verify_kc_bearer_token, token)
                if claims:
                    db = SessionLocal()
                    try:
                        user = resolve_keycloak_user(db, claims)
                    finally:
                        db.close()
            except Exception:
                logger.exception("Keycloak bearer resolution failed")
                user = None

        if not user:
            await self._send_401(
                send,
                origin,
                "Invalid, expired, or unrecognized bearer token.",
                token_presented=True,
                scope=scope,
            )
            return

        # Pin the bearer, local user, and backend URL onto contextvars for the
        # duration of this request, then dispatch to FastMCP. Tools read
        # those contextvars to forward calls back into the same backend
        # API (over localhost) on behalf of the authenticated user.
        from services.mcp_app import (
            set_backend_url,
            set_pat,
            reset_backend_url,
            reset_pat,
            set_mcp_user,
            reset_mcp_user,
        )

        pat_token = set_pat(token)
        user_token = set_mcp_user(user)
        backend_url = os.getenv("MCP_BACKEND_URL", "http://localhost:9050")
        backend_token = set_backend_url(backend_url)

        # Wrap `send` so we can stamp CORS headers onto the FastMCP
        # response without touching the FastMCP internals.
        async def send_with_cors(message):
            if message.get("type") == "http.response.start":
                message = _augment_headers_with_cors(message, origin)
            await send(message)

        try:
            await self._inner(scope, receive, send_with_cors)
        finally:
            reset_pat(pat_token)
            reset_backend_url(backend_token)
            reset_mcp_user(user_token)

    async def _send_cors_preflight(self, send, origin: str | None) -> None:
        headers = _cors_headers(origin) + [
            (b"content-length", b"0"),
        ]
        await send({
            "type": "http.response.start",
            "status": 204,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": b""})

    async def _send_cors_forbidden(self, send) -> None:
        import json as _json

        body = _json.dumps({
            "error": "forbidden",
            "detail": "Origin is not allowed for the MCP endpoint.",
        }).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"vary", b"Origin"),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def _send_401(
        self,
        send,
        origin: str | None,
        detail: str,
        *,
        token_presented: bool,
        scope: dict,
    ) -> None:
        import json as _json

        body = _json.dumps({"error": "unauthorized", "detail": detail}).encode("utf-8")
        resource_metadata = (
            f"{_public_base_url(scope)}{_PRM_MCP_PATH}"
        )
        challenge = (
            'Bearer realm="meeting-ops-mcp", '
            f'resource_metadata="{resource_metadata}"'
        )
        if token_presented:
            challenge += ', error="invalid_token"'
        headers = _cors_headers(origin) + [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"www-authenticate", challenge.encode("latin-1")),
        ]
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})


def _cors_headers(origin: str | None) -> list[tuple[bytes, bytes]]:
    """Build CORS headers after the caller has passed the origin allow-list."""

    allow_origin = "*"
    if origin:
        # Keep the exact browser Origin in the response; normalization is only
        # for comparison, and browsers require the echoed value to match.
        allow_origin = origin
    headers = [
        (b"access-control-allow-origin", allow_origin.encode("latin-1")),
        (b"access-control-allow-methods", b"GET, POST, OPTIONS, DELETE"),
        (
            b"access-control-allow-headers",
            b"Authorization, Content-Type, Accept, Mcp-Session-Id, "
            b"Mcp-Protocol-Version, Last-Event-ID",
        ),
        (
            b"access-control-expose-headers",
            b"Mcp-Session-Id",
        ),
        (b"access-control-max-age", b"600"),
        (b"vary", b"Origin"),
    ]
    return headers


def _augment_headers_with_cors(start_message: dict, origin: str | None) -> dict:
    existing = list(start_message.get("headers", []))
    cors = _cors_headers(origin)
    # Drop any pre-existing CORS headers from the inner app so ours win.
    cors_keys = {h[0] for h in cors}
    filtered = [h for h in existing if h[0].lower() not in cors_keys]
    start_message = dict(start_message)
    start_message["headers"] = filtered + cors
    return start_message


def _prm_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Accept, Content-Type, Authorization",
        "Cache-Control": "public, max-age=3600",
    }


async def _protected_resource_metadata(request: Request) -> JSONResponse:
    """RFC 9728 document; deliberately unauthenticated."""
    return JSONResponse(
        _protected_resource_document(request.scope),
        headers=_prm_headers(),
    )


async def _protected_resource_options() -> Response:
    return Response(status_code=204, headers=_prm_headers())


async def _mcp_trailing_slash_redirect() -> RedirectResponse:
    return RedirectResponse(url=_MOUNT_PATH, status_code=308)


def _register_mcp_oauth_routes(app: FastAPI) -> None:
    """Register public discovery routes and the canonical MCP redirect."""
    # Register the slash redirect before the exact canonical route.
    app.add_api_route(
        f"{_MOUNT_PATH}/",
        _mcp_trailing_slash_redirect,
        methods=["GET", "POST", "DELETE"],
        include_in_schema=False,
    )
    for path in (_PRM_ROOT_PATH, _PRM_MCP_PATH):
        app.add_api_route(
            path,
            _protected_resource_metadata,
            methods=["GET"],
            include_in_schema=False,
        )
        app.add_api_route(
            path,
            _protected_resource_options,
            methods=["OPTIONS"],
            include_in_schema=False,
        )


# ── Mount entry point ──────────────────────────────────────────────────


def mount_mcp_app(app: FastAPI) -> None:
    """Mount the hosted MCP streamable-HTTP transport onto the FastAPI app.

    Idempotent and gated on ``MCP_HOSTED_ENABLED``. Logs a one-line
    summary on either path so deploy logs make the activation state
    obvious.
    """

    if not _enabled():
        _state["status"] = "disabled"
        logger.info(
            "Hosted MCP endpoint disabled (MCP_HOSTED_ENABLED=false); "
            "%s will 404.",
            _MOUNT_PATH,
        )
        return

    try:
        # We don't build the inner FastMCP ASGI app here. Instead, mount
        # a proxy that resolves the current inner app at request time,
        # so the lifespan can rebuild it on each start (the underlying
        # session manager is single-use). See open_mcp_lifespan().
        wrapped = _PATAuthMiddleware(_LazyInnerApp())
        _register_mcp_oauth_routes(app)
        # FastMCP's streamable_http_app owns the literal path "/mcp"
        # internally. Use an exact ASGI route rather than Starlette's Mount:
        # Mount would redirect the bare canonical /mcp to /mcp/, while the
        # public contract and PRM document use /mcp without a trailing slash.
        app.add_route(
            _MOUNT_PATH,
            _MountedAtRoot(wrapped),
            methods=["GET", "POST", "DELETE"],
            include_in_schema=False,
        )

        _state["status"] = "ok"
        logger.info(
            "Hosted MCP endpoint mounted at %s (transport=streamable_http)",
            _MOUNT_PATH,
        )
    except Exception as exc:  # pragma: no cover - import-time failure
        _state["status"] = f"error: {exc}"
        logger.exception("Failed to mount hosted MCP endpoint: %s", exc)


class _LazyInnerApp:
    """Dispatches to the FastMCP ASGI app currently registered in
    ``_active_inner``. Lets the parent FastAPI app mount a stable
    handler that the lifespan can swap out on each start.
    """

    async def __call__(self, scope, receive, send):
        inner = _active_inner.get("app")
        if inner is None:
            # Lifespan hasn't run yet — return 503 so the failure mode
            # is obvious to a probing client.
            if scope.get("type") == "http":
                import json as _json
                body = _json.dumps({
                    "error": "service_unavailable",
                    "detail": "Hosted MCP session manager not started.",
                }).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
            return
        await inner(scope, receive, send)


class _MountedAtRoot:
    """Make FastMCP's ``/mcp`` route reachable through a FastAPI mount.

    Mount semantics (Starlette ``Mount``) extend ``root_path`` to include
    the mount prefix, so the sub-app's ``get_route_path()`` returns the
    request URL minus the prefix. FastMCP's streamable-HTTP app routes
    its handler at the literal path ``/mcp`` (its server-internal mount
    expects to live at the URL root). When we mount it under our own
    ``/mcp``, the sub-app sees ``route_path = "/"`` (or ``""``) and 404s.

    Fix: drop the mount prefix from ``root_path`` before handing the
    scope to the sub-app, AND force ``path`` to ``/mcp`` so the inner
    Starlette routes match exactly. This makes the sub-app behave as if
    it were the URL root receiving ``/mcp`` directly — which is what
    FastMCP's ``streamable_http_app()`` was designed for.
    """

    def __init__(self, inner):
        self._inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            scope = dict(scope)
            # Remove our mount prefix from root_path so the inner app
            # resolves /mcp at its own route table root.
            root_path = scope.get("root_path", "") or ""
            if root_path.endswith(_MOUNT_PATH):
                scope["root_path"] = root_path[: -len(_MOUNT_PATH)]
            # Force the canonical path to /mcp. The parent app redirects the
            # public /mcp/ spelling before this adapter is reached.
            scope["path"] = "/mcp"
            scope["raw_path"] = b"/mcp"
        await self._inner(scope, receive, send)


class McpCorsBypassMiddleware:
    """ASGI middleware that owns CORS for /mcp paths only.

    The main app's :class:`fastapi.middleware.cors.CORSMiddleware` is
    configured for the SPA's known origins (LAN, claude.ai, cursor.sh).
    The MCP endpoint is browser-installable from hosted AI clients, so it
    needs its own configured Origin policy without loosening the rest of the
    app. This middleware:

    * Returns CORS preflight (OPTIONS) for /mcp synchronously, before
      any downstream router runs.
    * Stamps CORS headers onto every non-preflight /mcp response so the
      browser-installed clients can read the body.
    * Rejects a disallowed browser Origin with 403 before bearer auth, so the
      response cannot become a token-probing path.
    * Passes through any non-/mcp request untouched.

    Added to the FastAPI app AFTER the main CORSMiddleware so it runs
    FIRST on each request (Starlette middleware is LIFO). The net effect:
    /mcp gets the configured policy below; everything else continues to
    use the strict app-wide CORS policy.
    """

    def __init__(self, app):
        self._inner = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self._inner(scope, receive, send)
            return

        path = scope.get("path", "")
        if not (path == _MOUNT_PATH or path.startswith(_MOUNT_PATH + "/")):
            await self._inner(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        origin = headers.get("origin")
        method = scope.get("method", "GET").upper()

        if not _origin_allowed(origin):
            body = (
                b'{"error":"forbidden","detail":"Origin is not allowed '
                b'for the MCP endpoint."}'
            )
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"vary", b"Origin"),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        if method == "OPTIONS":
            preflight_headers = _cors_headers(origin) + [
                (b"content-length", b"0"),
            ]
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": preflight_headers,
            })
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message):
            if message.get("type") == "http.response.start":
                message = _augment_headers_with_cors(message, origin)
            await send(message)

        await self._inner(scope, receive, send_with_cors)


# ── Lifespan plumbing ──────────────────────────────────────────────────


async def open_mcp_lifespan():
    """Start FastMCP's StreamableHTTP session manager.

    FastMCP backs the streamable transport with a long-lived task group.
    When the hosted MCP app is mounted under FastAPI (instead of being
    Starlette's own root app), its inner lifespan does NOT fire — so the
    session manager never runs and every request returns 404.

    We call this from the parent FastAPI app's lifespan to drive the
    session manager ourselves. Returns an opaque handle the caller MUST
    pass to :func:`close_mcp_lifespan` on shutdown.

    No-op if hosted MCP is disabled.
    """
    if not _enabled():
        return None
    try:
        from services.mcp_app import mcp as fastmcp_instance
        # The session manager is single-use: ``.run()`` can only be called
        # once per instance. Reset the cached one so a fresh manager is
        # built — this matters for the test harness, which spins the
        # FastAPI lifespan up + down many times per session, and for
        # uvicorn --reload during dev.
        fastmcp_instance._session_manager = None
        inner_app = fastmcp_instance.streamable_http_app()
        # Publish the freshly-built ASGI sub-app so _LazyInnerApp picks
        # it up on subsequent requests.
        _active_inner["app"] = inner_app
        cm = fastmcp_instance.session_manager.run()
        await cm.__aenter__()
        logger.info("Hosted MCP session manager started.")
        return cm
    except Exception as exc:
        logger.exception("Failed to start hosted MCP session manager: %s", exc)
        _state["status"] = f"error: {exc}"
        _active_inner["app"] = None
        return None


async def close_mcp_lifespan(cm) -> None:
    if cm is None:
        return
    try:
        await cm.__aexit__(None, None, None)
        logger.info("Hosted MCP session manager stopped.")
    except Exception as exc:  # pragma: no cover
        logger.warning("Hosted MCP session manager shutdown error: %s", exc)
    finally:
        _active_inner["app"] = None


__all__ = [
    "mount_mcp_app",
    "mcp_health_status",
    "McpCorsBypassMiddleware",
    "open_mcp_lifespan",
    "close_mcp_lifespan",
]
