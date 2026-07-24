"""Opaque, one-time-visible secrets for per-meeting invitations.

Only SHA-256 digests are persisted.  The raw secret is returned to the caller
that creates or rotates it and must not be logged, serialized by list
endpoints, or written to the database.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import quote


INVITATION_TOKEN_VERSION = 2
LEGACY_INVITATION_TOKEN_VERSION = 1

# Legacy UUID links migrated by revision 053 remain usable only during this
# transition.  An environment value may shorten the window, but cannot extend
# it past this code-level ceiling.
LEGACY_INVITATION_MAX_CUTOFF = datetime(
    2026, 10, 31, 0, 0, 0, tzinfo=timezone.utc
)


def generate_invitation_secret() -> str:
    """Return a URL-safe secret with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_invitation_secret(secret: str) -> str:
    """Return the stable lookup digest for an invitation secret."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def invitation_resend_minimum_interval_seconds() -> int:
    """Return the bounded resend interval used by every invitation sender.

    Keeping this at the token-service boundary prevents the explicit share
    control and the email-a-copy workflow from drifting into different retry
    policies. Bad operational configuration fails to the safe default.
    """
    try:
        configured = int(
            os.getenv("MEETING_INVITE_RESEND_MIN_INTERVAL_SECONDS", "60")
        )
    except ValueError:
        configured = 60
    return max(30, min(configured, 3600))


def legacy_invitation_is_allowed(
    token_version: int | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Whether a migrated v1 UUID invitation is still in its bounded window."""
    if token_version != LEGACY_INVITATION_TOKEN_VERSION:
        return True

    cutoff = LEGACY_INVITATION_MAX_CUTOFF
    configured = os.getenv("MEETING_INVITE_LEGACY_TOKEN_CUTOFF", "").strip()
    if configured:
        try:
            parsed = datetime.fromisoformat(configured.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            cutoff = min(cutoff, parsed.astimezone(timezone.utc))
        except ValueError:
            # Fail closed for malformed operational configuration.
            return False

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc) < cutoff


def build_invitation_url(secret: str) -> str:
    """Build a link whose secret stays in the browser fragment.

    URL fragments are not sent in HTTP request lines, avoiding disclosure in
    reverse-proxy access logs.  The SPA posts the secret in a JSON body.
    """
    base = (
        os.getenv("MEETING_OPS_PUBLIC_URL", "").strip()
        or os.getenv("APP_PUBLIC_URL", "").strip()
        or ""
    ).rstrip("/")
    suffix = f"/invite-bootstrap.html#token={quote(secret, safe='')}"
    return f"{base}{suffix}" if base else suffix
