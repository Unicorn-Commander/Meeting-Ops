"""HTTP client for Project-Ops — task write surface.

Used by ``services.projectops_writer`` to push Meeting-Ops action items
into Project-Ops as tasks on a per-org project. One-way write only
(Meeting-Ops -> Project-Ops); no read-back / sync.

Project-Ops API surface used here (verified live against
``http://project-ops-backend:3201`` on bigboy — a NestJS app, global
prefix ``/api/v1``):

  GET  /api/v1/projects?page=&limit=
    paginated list ``{data: [{id, projectNumber, ...}], meta: {...}}``.
    Used to resolve a human project number ("P-00055") -> the UUID the
    task-create endpoint actually wants. There is NO project-by-number
    route, so we page + match client-side (cached per client instance).

  POST /api/v1/tasks
    body: {projectId(UUID), title, description?, type?, status?,
           priority?, dueDate?(ISO), assignedToId?}
    201 -> the created task incl. ``id`` + ``project.projectNumber``.
    Guarded by JwtAuthGuard + RolesGuard (ADMIN | MANAGER | STAFF).

  PATCH /api/v1/tasks/{id}/status
    body: {status}  (PENDING|IN_PROGRESS|WAITING_FOR_CLIENT|COMPLETED|CANCELLED)
    200 -> the updated task. Used by the marked-done propagation path.

Auth: ``Authorization: Bearer <token>``. Project-Ops authenticates every
write with a Keycloak-issued JWT (Passport) — it does NOT accept an
``X-API-Key`` service header the way Brigade does. ``PROJECTOPS_API_KEY``
therefore holds a *bearer service token* (a Keycloak service-account JWT
for an ADMIN/MANAGER identity), not an API key. When it is unset every
method short-circuits to a log-only no-op and ``is_live`` is False, so a
deployment without the token still completes the meeting pipeline
cleanly — identical posture to ``brigade_client`` without BRIGADE_API_KEY.

Contract note (differs from brigade_client on purpose): the write methods
RAISE ``ProjectOpsClientError`` on terminal HTTP / network failure. The
writer (``projectops_writer``) is the swallow boundary — it catches and
returns ``ok=False`` so the recording pipeline never sees an exception.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


# Internal default keeps the client working inside the bigboy stack with
# no env wiring. meet-backend and project-ops-backend share the
# ``unicorn-network`` docker network, so the service name resolves.
# NOTE: 3201 (NestJS) + the ``/api/v1`` global prefix — NOT 8000.
DEFAULT_BASE_URL = "http://project-ops-backend:3201/api/v1"

# Task creation is a single Prisma insert; >8s means a real problem and
# the writer is fire-and-forget anyway. Slightly higher than brigade's
# 5s because we may also page the projects list to resolve a number.
DEFAULT_TIMEOUT_SECONDS = 8.0

DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF_SECONDS = 0.25
DEFAULT_BACKOFF_MULTIPLIER = 2.0

# Bound on how far we page the projects list when resolving a project
# number -> UUID. 100/page * 50 pages = 5000 projects; far beyond any
# real org and a hard stop against an accidental full-table walk.
_RESOLVE_PAGE_SIZE = 100
_RESOLVE_MAX_PAGES = 50

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class ProjectOpsClientError(Exception):
    """Terminal failure talking to Project-Ops. Raised by the write
    methods; caught + swallowed by ``projectops_writer``."""


def _api_key() -> Optional[str]:
    """Resolve the Project-Ops bearer service token from env.

    Returns None when unset — that flips the client into log-only mode
    (``is_live`` False), the writer's no-op path.
    """
    return os.getenv("PROJECTOPS_API_KEY") or None


def _base_url() -> str:
    return os.getenv("PROJECTOPS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


def _normalize_due_date(due_date: Any) -> Optional[str]:
    """Project-Ops' dueDate is validated by class-validator's IsDateString,
    which accepts any ISO-8601 string. Accept a ``datetime`` (the
    ActionItem.due_date column type) or an already-formatted string."""
    if due_date is None:
        return None
    if isinstance(due_date, datetime):
        return due_date.isoformat()
    text = str(due_date).strip()
    return text or None


class ProjectOpsClient:
    """Thin httpx wrapper for Project-Ops' task write endpoints.

    Intended to be short-lived per write batch (the writer creates one
    per session). A per-instance cache memoizes project-number -> UUID
    resolution so a batch of N action items on the same project only
    pages the projects list once.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        _client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = (base_url or _base_url()).rstrip("/")
        # Resolved at __init__ (not per-call) so tests can monkeypatch env
        # once and reuse the client across the batch. None => log-only.
        self._resolved_api_key = (
            api_key if api_key is not None else _api_key()
        )
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff_seconds
        self._backoff_multiplier = backoff_multiplier
        self._injected_client = _client
        self._owned_client: Optional[httpx.AsyncClient] = None
        # project_number (or raw uuid) -> resolved project UUID.
        self._project_id_cache: dict[str, str] = {}

    @property
    def is_live(self) -> bool:
        """True when a bearer token was resolved. False puts the client in
        log-only mode (write methods become no-ops); the writer checks
        this and reports mode='no-op' without making HTTP calls."""
        return self._resolved_api_key is not None

    async def aclose(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def __aenter__(self) -> "ProjectOpsClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Public surface (writer-facing)
    # ------------------------------------------------------------------

    async def create_task(
        self,
        *,
        project_number: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "MEDIUM",
        due_date: Any = None,
        type: str = "OTHER",
    ) -> dict[str, Any]:
        """Create one Project-Ops task. ``project_number`` may be a human
        number ("P-00055") — resolved to a UUID via the projects list — or
        a raw project UUID, used directly.

        Returns ``{"id": <task uuid>, "project_number": <projectNumber>}``.
        Raises ``ProjectOpsClientError`` on terminal failure. Callers are
        expected to gate on ``is_live`` first; if not live this raises
        rather than silently dropping the write.
        """
        if not self.is_live:
            raise ProjectOpsClientError(
                "create_task called while not configured (PROJECTOPS_API_KEY unset)"
            )

        project_id = await self._resolve_project_id(project_number)
        body: dict[str, Any] = {
            "projectId": project_id,
            "title": title,
            "type": type,
            "priority": priority,
        }
        if description:
            body["description"] = description
        normalized_due = _normalize_due_date(due_date)
        if normalized_due:
            body["dueDate"] = normalized_due

        data = await self._request_with_retries(
            "POST", "/tasks", json=body
        )
        if not isinstance(data, dict) or "id" not in data:
            raise ProjectOpsClientError(
                f"create_task: unexpected response shape: {str(data)[:200]}"
            )
        project_number_out = None
        project_block = data.get("project")
        if isinstance(project_block, dict):
            project_number_out = project_block.get("projectNumber")
        return {"id": data["id"], "project_number": project_number_out}

    async def update_task_status(
        self, *, task_id: str, status: str
    ) -> dict[str, Any]:
        """Patch a task's status (e.g. -> COMPLETED when the user marks
        the action item done in Meeting-Ops). Returns the updated task
        dict; raises ``ProjectOpsClientError`` on terminal failure."""
        if not self.is_live:
            raise ProjectOpsClientError(
                "update_task_status called while not configured"
            )
        data = await self._request_with_retries(
            "PATCH", f"/tasks/{task_id}/status", json={"status": status}
        )
        return data if isinstance(data, dict) else {}

    async def resolve_project_id(self, project_number: str) -> str:
        """Public passthrough to the number->UUID resolver (handy for
        scripts / diagnostics)."""
        return await self._resolve_project_id(project_number)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _resolve_project_id(self, project_ref: str) -> str:
        """Resolve a project number ("P-00055") to its UUID. If
        ``project_ref`` already looks like a UUID it is returned as-is
        (the session->PO link stores the UUID directly). Result is cached
        per client instance.

        Project-Ops exposes no by-number route, so we page the list
        endpoint and match ``projectNumber`` client-side. Raises
        ``ProjectOpsClientError`` if not found within the page bound.
        """
        ref = (project_ref or "").strip()
        if not ref:
            raise ProjectOpsClientError("empty project reference")
        if _looks_like_uuid(ref):
            return ref
        if ref in self._project_id_cache:
            return self._project_id_cache[ref]

        for page in range(1, _RESOLVE_MAX_PAGES + 1):
            data = await self._request_with_retries(
                "GET",
                "/projects",
                params={"page": page, "limit": _RESOLVE_PAGE_SIZE},
            )
            rows = data.get("data") if isinstance(data, dict) else data
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if row.get("projectNumber") == ref and row.get("id"):
                    self._project_id_cache[ref] = row["id"]
                    return row["id"]
            # Stop once we've walked the last page the API reports.
            meta = data.get("meta") if isinstance(data, dict) else None
            if isinstance(meta, dict):
                total_pages = meta.get("totalPages")
                if isinstance(total_pages, int) and page >= total_pages:
                    break
            if len(rows) < _RESOLVE_PAGE_SIZE:
                break

        raise ProjectOpsClientError(
            f"project number {ref!r} not found in Project-Ops "
            f"(searched up to {_RESOLVE_MAX_PAGES} pages)"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._resolved_api_key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _client_ctx(self) -> "_AsyncClientCtx":
        if self._injected_client is not None:
            return _AsyncClientCtx(self._injected_client, owns=False)
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=self._timeout)
        return _AsyncClientCtx(self._owned_client, owns=False)

    async def _request_with_retries(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Issue an HTTP request with bounded retries. Retries on
        connect/timeout/5xx; 4xx is terminal (the payload won't get
        better). Returns parsed JSON on 2xx; raises ProjectOpsClientError
        on terminal failure or after exhausting retries."""
        url = f"{self._base_url}{path}"
        backoff = self._initial_backoff
        last_detail: Optional[str] = None
        for attempt in range(self._max_retries):
            try:
                async with self._client_ctx() as client:
                    resp = await client.request(
                        method,
                        url,
                        json=json,
                        params=params,
                        headers=self._headers(),
                    )
                if resp.status_code < 400:
                    if not resp.content:
                        return {}
                    try:
                        return resp.json()
                    except Exception as exc:  # noqa: BLE001
                        raise ProjectOpsClientError(
                            f"{method} {path}: non-JSON 2xx body: {exc}"
                        )
                if 400 <= resp.status_code < 500:
                    body = resp.text[:300]
                    logger.warning(
                        "projectops_client 4xx %s %s %s body=%s",
                        resp.status_code,
                        method,
                        path,
                        body,
                    )
                    raise ProjectOpsClientError(
                        f"HTTP {resp.status_code}: {body}"
                    )
                last_detail = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except ProjectOpsClientError:
                raise
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.RemoteProtocolError,
            ) as exc:
                last_detail = f"{type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BLE001
                last_detail = f"{type(exc).__name__}: {exc}"
                logger.debug(
                    "projectops_client unexpected exc on attempt %d: %s",
                    attempt,
                    exc,
                )
            if attempt < self._max_retries - 1:
                await asyncio.sleep(backoff)
                backoff *= self._backoff_multiplier
        logger.warning(
            "projectops_client request failed after %d attempts %s %s detail=%s",
            self._max_retries,
            method,
            path,
            last_detail,
        )
        raise ProjectOpsClientError(last_detail or "request failed")


class _AsyncClientCtx:
    """Tiny shim so ``async with`` works for both owned and injected
    httpx clients without closing the injected one."""

    def __init__(self, client: httpx.AsyncClient, *, owns: bool) -> None:
        self._client = client
        self._owns = owns

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns:
            await self._client.aclose()


__all__ = [
    "ProjectOpsClient",
    "ProjectOpsClientError",
    "DEFAULT_BASE_URL",
]
