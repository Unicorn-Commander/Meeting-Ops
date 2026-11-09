"""Non-token usage reporting for org-routed Meeting-Ops work."""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

from .org_route import (
    MEETING_OPS_APP,
    OPS_CENTER_INTERNAL_URL_ENV,
    OPS_CENTER_SERVICE_TOKEN_ENV,
)

logger = logging.getLogger(__name__)


class UsageReporter(Protocol):
    """Report one idempotent non-token usage event."""

    def report(
        self,
        *,
        organization_id: int,
        metric: str,
        quantity: float,
        work_id: str,
        feature: str,
    ) -> None:
        """Report a quantity for one unit of work."""


class NoopUsageReporter:
    """Safe default for local development and deployments without the meter."""

    def report(
        self,
        *,
        organization_id: int,
        metric: str,
        quantity: float,
        work_id: str,
        feature: str,
    ) -> None:
        return None


class OpsCenterUsageReporter:
    """Send usage events to Ops-Center's existing metered endpoint.

    Reporting is best effort.  The model result is not discarded when the
    accounting rail is unavailable, and the work ID is sent as the endpoint's
    idempotency key so a retry cannot charge the same work twice.
    """

    def __init__(self, base_url: str, service_token: str):
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token

    def report(
        self,
        *,
        organization_id: int,
        metric: str,
        quantity: float,
        work_id: str,
        feature: str,
    ) -> None:
        if quantity <= 0:
            return
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    f"{self._base_url}/api/v1/metered/report",
                    headers={
                        "Authorization": f"Bearer {self._service_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "org_id": organization_id,
                        "metric": metric,
                        "quantity": float(quantity),
                        "idempotency_key": work_id,
                        "app": MEETING_OPS_APP,
                        "feature": feature,
                    },
                )
            if response.status_code >= 400:
                logger.warning(
                    "Usage report rejected metric=%s org_id=%s status=%s",
                    metric,
                    organization_id,
                    response.status_code,
                )
        except httpx.HTTPError:
            logger.warning(
                "Usage report could not reach Ops-Center metric=%s org_id=%s",
                metric,
                organization_id,
            )


_reporter_cache: tuple[str, bool, UsageReporter] | None = None


def get_usage_reporter() -> UsageReporter:
    """Build a reporter from the existing Ops-Center settings.

    When either setting is absent, the typed no-op keeps unit tests and local
    development offline. Production enables the HTTP reporter by providing the
    same internal base URL and service credential used for key lookup.
    """
    global _reporter_cache
    base_url = os.getenv(OPS_CENTER_INTERNAL_URL_ENV, "").strip().rstrip("/")
    service_token = os.getenv(OPS_CENTER_SERVICE_TOKEN_ENV, "").strip()
    cache_key = (base_url, bool(service_token))
    if _reporter_cache and _reporter_cache[:2] == cache_key:
        return _reporter_cache[2]
    reporter: UsageReporter
    if base_url and service_token:
        reporter = OpsCenterUsageReporter(base_url, service_token)
    else:
        reporter = NoopUsageReporter()
    _reporter_cache = (base_url, bool(service_token), reporter)
    return reporter


def audio_work_id(audio_path: str) -> str:
    """Return a stable fallback ID for a transcription work item."""
    import hashlib

    return f"stt:{hashlib.sha256(audio_path.encode('utf-8')).hexdigest()}"


def text_work_id(text: str) -> str:
    """Return a stable fallback ID for a TTS text item."""
    import hashlib

    return f"tts:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
