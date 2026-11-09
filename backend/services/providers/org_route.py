"""Meeting-Ops access to the per-organization model gateway.

The application never stores the virtual key.  The default key provider asks
Ops-Center for the key needed by this app and keeps it in memory only.  Tests
can inject a provider so no network access is needed.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

MEETING_OPS_APP = "meeting-ops"
ORG_ROUTE_ENV = "MEETING_OPS_USE_ORG_ROUTE"
ORG_GATEWAY_BASE_URL_ENV = "ORG_GATEWAY_BASE_URL"
OPS_CENTER_INTERNAL_URL_ENV = "OPS_CENTER_INTERNAL_URL"
OPS_CENTER_SERVICE_TOKEN_ENV = "OPS_CENTER_SERVICE_TOKEN"
ORG_ROUTE_CACHE_SECONDS = 10 * 60


class OrgRouteError(RuntimeError):
    """A required org gateway operation could not be completed."""


@dataclass(frozen=True)
class OrgGatewayKey:
    """The opaque key returned for one org and one calling application."""

    key: str
    expires_at: Optional[str] = None


class OrgGatewayKeyProvider(Protocol):
    """Resolve the gateway key for one organization."""

    def get_key(self, org_id: int) -> OrgGatewayKey:
        """Return an app-scoped key without exposing it to logs or storage."""


def org_route_enabled() -> bool:
    """Return whether Meeting-Ops should use the org gateway route."""
    return os.getenv(ORG_ROUTE_ENV, "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def gateway_base_url() -> str:
    """Return the configured OpenAI-compatible gateway base URL.

    The setting is intentionally required when the feature is enabled.  A
    missing gateway must fail visibly instead of reverting to an old host.
    """
    value = os.getenv(ORG_GATEWAY_BASE_URL_ENV, "").strip().rstrip("/")
    if not value:
        raise OrgRouteError(
            "Gateway route is enabled but ORG_GATEWAY_BASE_URL is not configured"
        )
    return value


def _key_from_payload(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    candidate = payload.get("key") or payload.get("gateway_key") or payload.get("gatewayKey")
    if candidate:
        return str(candidate)
    nested = payload.get("data")
    if isinstance(nested, dict):
        candidate = nested.get("key") or nested.get("gateway_key") or nested.get("gatewayKey")
        if candidate:
            return str(candidate)
    return None


def _expires_in_seconds(expires_at: Any) -> Optional[float]:
    """Convert common expiry representations into seconds from now."""
    if expires_at is None:
        return None
    try:
        if isinstance(expires_at, (int, float)):
            timestamp = float(expires_at)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            return timestamp - time.time()
        text = str(expires_at).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp() - time.time()
    except (TypeError, ValueError, OverflowError):
        return None


class OpsCenterOrgGatewayKeyProvider:
    """Fetch and briefly cache an app-scoped org gateway key."""

    def __init__(self, cache_seconds: int = ORG_ROUTE_CACHE_SECONDS):
        self._cache_seconds = min(int(cache_seconds), ORG_ROUTE_CACHE_SECONDS)
        self._cache: dict[int, tuple[float, OrgGatewayKey]] = {}
        self._lock = threading.Lock()

    def get_key(self, org_id: int) -> OrgGatewayKey:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(int(org_id))
            if cached and cached[0] > now:
                return cached[1]

        ops_center_url = os.getenv(OPS_CENTER_INTERNAL_URL_ENV, "").strip().rstrip("/")
        service_token = os.getenv(OPS_CENTER_SERVICE_TOKEN_ENV, "").strip()
        if not ops_center_url:
            raise OrgRouteError(
                "Gateway key fetch failed: OPS_CENTER_INTERNAL_URL is not configured"
            )
        if not service_token:
            raise OrgRouteError(
                "Gateway key fetch failed: OPS_CENTER_SERVICE_TOKEN is not configured"
            )

        url = f"{ops_center_url}/api/v1/internal/orgs/{int(org_id)}/gateway-key"
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {service_token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise OrgRouteError(
                "Gateway key fetch failed while contacting Ops-Center"
            ) from exc

        if response.status_code != 200:
            raise OrgRouteError(
                f"Gateway key fetch failed: Ops-Center returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OrgRouteError("Gateway key fetch failed: invalid Ops-Center response") from exc

        key = _key_from_payload(payload)
        if not key:
            raise OrgRouteError("Gateway key fetch failed: Ops-Center returned no key")

        expires_at = None
        if isinstance(payload, dict):
            expires_at = payload.get("expiresAt") or payload.get("expires_at")
        result = OrgGatewayKey(key=key, expires_at=str(expires_at) if expires_at else None)
        ttl = float(self._cache_seconds)
        remaining = _expires_in_seconds(expires_at)
        if remaining is not None:
            ttl = min(ttl, max(0.0, remaining))
        if ttl > 0:
            with self._lock:
                self._cache[int(org_id)] = (time.monotonic() + ttl, result)
        return result


_default_key_provider: Optional[OpsCenterOrgGatewayKeyProvider] = None
_default_key_provider_lock = threading.Lock()


def get_org_gateway_key_provider() -> OrgGatewayKeyProvider:
    """Return the process-local key provider singleton."""
    global _default_key_provider
    with _default_key_provider_lock:
        if _default_key_provider is None:
            _default_key_provider = OpsCenterOrgGatewayKeyProvider()
        return _default_key_provider
