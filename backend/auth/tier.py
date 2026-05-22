"""Tier-based feature gating.

Source of truth for what each tier unlocks. TIER_FEATURES is the dict
every gate consumes; `get_user_tier()` resolves a User to a tier name
(with the is_superuser override to enterprise); `get_tier_features()`
returns the resolved feature dict; `require_tier()` is the FastAPI
dependency factory that 403s requests below a minimum tier.

Wire convention:
  - Backend route gates a feature with `Depends(require_tier("pro"))`
  - Frontend mirrors TIER_FEATURES.free as the default in `useTierFeatures()`
    so UI doesn't briefly render disabled while /api/auth/me is in-flight.
  - is_superuser users always resolve to enterprise. This makes support
    debugging feature flags simple (no need to manually flip tier columns
    on a user every time we want to repro something).

Quota numbers (max_sessions_per_month / max_session_minutes) are encoded
here for completeness but are not yet enforced by any code path. When
the quota service lands it should consume these same numbers via
`get_tier_features()` so there is one canonical source.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException

from auth.dependencies import get_current_active_user
from auth.models import User


TIER_FEATURES: dict[str, dict[str, Any]] = {
    "free": {
        "server_live": False,
        "diarization": False,
        "qwen36_summary": False,
        "speaker_library": False,
        "retention_controls": False,
        "brigade_byok": False,
        "hipaa": False,
        "max_sessions_per_month": 50,
        "max_session_minutes": 60,
    },
    "pro": {
        "server_live": True,
        "diarization": True,
        "qwen36_summary": True,
        "speaker_library": True,
        "retention_controls": False,
        "brigade_byok": False,
        "hipaa": False,
        "max_sessions_per_month": None,  # unlimited
        "max_session_minutes": None,
    },
    "enterprise": {
        "server_live": True,
        "diarization": True,
        "qwen36_summary": True,
        "speaker_library": True,
        "retention_controls": True,
        "brigade_byok": True,
        "hipaa": True,
        "max_sessions_per_month": None,
        "max_session_minutes": None,
    },
}


# Ordinal rank for tier comparisons. Higher number = more capabilities.
_TIER_RANK: dict[str, int] = {"free": 0, "pro": 1, "enterprise": 2}


def get_user_tier(user: User) -> str:
    """Return effective tier for a user.

    `is_superuser=True` overrides to `enterprise` regardless of the tier
    column. This way support/dev accounts always get full capability
    without us having to remember to update both flags.
    """
    if getattr(user, "is_superuser", False):
        return "enterprise"
    return getattr(user, "tier", None) or "free"


def get_tier_features(user: User) -> dict[str, Any]:
    """Return the feature dict for a user's effective tier."""
    return TIER_FEATURES[get_user_tier(user)]


def require_tier(min_tier: str):
    """FastAPI dependency factory: 403s if user tier is below min_tier.

    Usage:
        @router.post("/live")
        async def start_live(
            user: User = Depends(require_tier("pro")),
        ):
            ...

    Raises 500 at definition time (not request time) if min_tier is not
    one of the known tier names — catches typos at app boot rather than
    on a request from a paying customer.
    """
    if min_tier not in _TIER_RANK:
        raise ValueError(
            f"require_tier(min_tier={min_tier!r}): "
            f"min_tier must be one of {sorted(_TIER_RANK)}"
        )

    min_rank = _TIER_RANK[min_tier]

    async def checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        user_tier = get_user_tier(current_user)
        if _TIER_RANK[user_tier] < min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires {min_tier} tier or higher",
            )
        return current_user

    return checker
