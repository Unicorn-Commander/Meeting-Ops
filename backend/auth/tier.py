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
        "live_diarization": False,
        "qwen36_summary": False,
        "speaker_library": False,
        "retention_controls": False,
        "brigade_byok": False,
        "hipaa": False,
        # Server-processing gates (v3.0.0). Free tier is browser-only: it
        # never uploads audio/text chunks, never triggers the canonical
        # server reprocess pipeline, never writes to Brigade, and has no
        # server-side cross-device sync. Everything stays in the browser
        # (on-device STT + LLM + IndexedDB, i.e. Privacy Mode by default).
        "canonical_reprocess": False,
        "brigade_integration": False,
        "cross_device_sync": False,
        "bulk_import": False,
        "agent_write_basic": True,
        "agent_write_reprocess": False,
        "agent_write_email_draft": False,
        "max_sessions_per_month": 50,
        "max_session_minutes": 60,
    },
    "pro": {
        "server_live": True,
        "diarization": True,
        # live_diarization (Sortformer streaming speaker labels during the
        # meeting) is intentionally OFF for pro. v3.20.1: per Aaron — the
        # value of live speaker labels is marginal vs the cost (always-on
        # GPU per concurrent stream), and the completion-time pyannote
        # pass already gives Pro full speaker-attributed transcripts at
        # session end. Restricted to enterprise + Founding 100.
        "live_diarization": False,
        "qwen36_summary": True,
        "speaker_library": True,
        "retention_controls": False,
        "brigade_byok": False,
        "hipaa": False,
        "canonical_reprocess": True,
        "brigade_integration": True,
        "cross_device_sync": True,
        "bulk_import": True,
        "agent_write_basic": True,
        "agent_write_reprocess": True,
        "agent_write_email_draft": True,
        "max_sessions_per_month": None,  # unlimited
        "max_session_minutes": None,
    },
    "enterprise": {
        "server_live": True,
        "diarization": True,
        "live_diarization": True,
        "qwen36_summary": True,
        "speaker_library": True,
        "retention_controls": True,
        "brigade_byok": True,
        "hipaa": True,
        "canonical_reprocess": True,
        "brigade_integration": True,
        "cross_device_sync": True,
        "bulk_import": True,
        "agent_write_basic": True,
        "agent_write_reprocess": True,
        "agent_write_email_draft": True,
        "max_sessions_per_month": None,
        "max_session_minutes": None,
    },
}


# v3.20.1: Founding 100 members inherit enterprise capabilities for the
# features listed here, regardless of their base tier. Aaron's intent:
# perks-only Founding cohort gets early-access compute features (live
# diarization) without paying enterprise pricing. Keep this list TIGHT —
# every flag here costs us on every Founding 100 customer at scale, so
# only add features that are genuinely a "first-look" benefit, not the
# full enterprise SKU. (Founding 100 is NOT a free upgrade to enterprise.)
_FOUNDING_MEMBER_OVERLAY: dict[str, Any] = {
    "live_diarization": True,
}


# All feature keys known across every tier — used to validate feature names
# at app boot in require_feature(). Recomputed once at import.
_KNOWN_FEATURES: frozenset[str] = frozenset().union(
    *(d.keys() for d in TIER_FEATURES.values())
)


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
    """Return the feature dict for a user's effective tier.

    Applies the Founding 100 overlay (`_FOUNDING_MEMBER_OVERLAY`) on top of
    the base tier features when ``user.is_founder`` is True. The base
    tier dict is copied, not mutated — TIER_FEATURES stays the immutable
    source of truth for what each plain tier gets.
    """
    base = TIER_FEATURES[get_user_tier(user)]
    if getattr(user, "is_founder", False):
        return {**base, **_FOUNDING_MEMBER_OVERLAY}
    return base


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


def require_feature(feature: str):
    """FastAPI dependency factory: 403s if the user's tier lacks `feature`.

    Like `require_tier` but keys off a named capability in TIER_FEATURES, so
    the gate tracks the feature matrix rather than a hardcoded minimum tier
    (a future plan that grants reprocess but not brigade just flips the
    matrix, no call-site change). Validates the feature name at app boot.

    Usage:
        @router.post("/finalize-audio")
        async def finalize_audio(
            user: User = Depends(require_feature("canonical_reprocess")),
        ):
            ...
    """
    if feature not in _KNOWN_FEATURES:
        raise ValueError(
            f"require_feature(feature={feature!r}): "
            f"unknown feature; known={sorted(_KNOWN_FEATURES)}"
        )

    async def checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not get_tier_features(current_user).get(feature):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This action needs a paid tier "
                    f"(missing capability: {feature})"
                ),
            )
        return current_user

    return checker


def get_org_tier(org: Any) -> str:
    """Return the effective tier for an Organization.

    Mirrors `get_user_tier` for cases where the caller is identified by
    org (e.g. satellite devices that authenticate via device secret and
    resolve to an owning org, not an individual user). The Organization
    model stores the tier in the `plan` column (free / pro / enterprise),
    not `tier`. Defaults to `free` when the column is missing or empty.
    """
    return ((getattr(org, "plan", None) or "free")).lower()


def gate_feature_for_caller(caller: Any, feature: str) -> None:
    """Inline tier gate for endpoints that resolve the caller themselves.

    Endpoints using `Depends(get_internal_or_user)` get back EITHER a real
    `User` OR an internal-service principal (loopback callers like
    room_recorder). Internal/service callers BYPASS tier gating — they are
    trusted infrastructure, not subject to user billing tiers. A real `User`
    whose effective tier lacks `feature` gets a 403.

    Call this right after the caller is resolved, before doing any work:
        gate_feature_for_caller(caller, "canonical_reprocess")
    """
    if feature not in _KNOWN_FEATURES:
        raise ValueError(
            f"gate_feature_for_caller(feature={feature!r}): "
            f"unknown feature; known={sorted(_KNOWN_FEATURES)}"
        )
    # Only real Users are tier-gated. Internal-service principals
    # (InternalServiceCaller, __slots__ = ("provenance",)) carry no `tier`
    # and bypass — they're trusted infra. We duck-type on the `tier`
    # attribute rather than isinstance(User): the test suite reloads
    # auth.models (conftest), which leaves multiple live User class
    # identities and makes isinstance miss. Every real User has `tier`.
    if not hasattr(caller, "tier"):
        return
    if not get_tier_features(caller).get(feature):
        raise HTTPException(
            status_code=403,
            detail=f"This action needs a paid tier (missing capability: {feature})",
        )
