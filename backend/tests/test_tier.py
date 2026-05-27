"""Tests for tier-based feature gating (backend/auth/tier.py).

Covers:
  - TIER_FEATURES dict shape (all tiers have the same keys)
  - get_user_tier resolves the column value
  - is_superuser overrides to 'enterprise'
  - get_tier_features returns per-tier dicts
  - require_tier raises 403 below min, passes through at or above min
  - require_tier rejects unknown min_tier at definition time
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi import HTTPException

from auth.tier import (
    TIER_FEATURES,
    get_tier_features,
    get_user_tier,
    require_tier,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeUser:
    """Stand-in for `auth.models.User` so we don't need a DB session."""

    tier: Optional[str] = "free"
    is_superuser: bool = False


# ---------------------------------------------------------------------------
# TIER_FEATURES shape
# ---------------------------------------------------------------------------


def test_tier_features_has_all_three_tiers():
    """The three tier names must be present and only those three."""
    assert set(TIER_FEATURES.keys()) == {"free", "pro", "enterprise"}


def test_tier_features_have_consistent_keys():
    """Every tier dict has the same capability keys, so frontend code
    that iterates capabilities never crashes on missing keys."""
    expected_keys = {
        "server_live",
        "diarization",
        "qwen36_summary",
        "speaker_library",
        "retention_controls",
        "brigade_byok",
        "hipaa",
        "canonical_reprocess",
        "brigade_integration",
        "cross_device_sync",
        "bulk_import",
        "max_sessions_per_month",
        "max_session_minutes",
    }
    for tier_name, features in TIER_FEATURES.items():
        assert set(features.keys()) == expected_keys, (
            f"tier {tier_name!r} has wrong keys: {set(features.keys()) ^ expected_keys}"
        )


def test_tier_features_capabilities_escalate():
    """free should have fewer enabled booleans than pro,
    and pro should have fewer than enterprise."""
    bool_keys = [
        "server_live",
        "diarization",
        "qwen36_summary",
        "speaker_library",
        "retention_controls",
        "brigade_byok",
        "hipaa",
    ]
    free_enabled = sum(1 for k in bool_keys if TIER_FEATURES["free"][k])
    pro_enabled = sum(1 for k in bool_keys if TIER_FEATURES["pro"][k])
    ent_enabled = sum(1 for k in bool_keys if TIER_FEATURES["enterprise"][k])

    assert free_enabled < pro_enabled < ent_enabled


def test_tier_features_quotas_unlimited_above_free():
    """pro + enterprise should have None (unlimited) quotas, free has real numbers."""
    assert TIER_FEATURES["free"]["max_sessions_per_month"] == 50
    assert TIER_FEATURES["free"]["max_session_minutes"] == 60
    assert TIER_FEATURES["pro"]["max_sessions_per_month"] is None
    assert TIER_FEATURES["pro"]["max_session_minutes"] is None
    assert TIER_FEATURES["enterprise"]["max_sessions_per_month"] is None
    assert TIER_FEATURES["enterprise"]["max_session_minutes"] is None


# ---------------------------------------------------------------------------
# get_user_tier
# ---------------------------------------------------------------------------


def test_get_user_tier_returns_column_value():
    """Non-superuser falls through to the tier column."""
    assert get_user_tier(FakeUser(tier="free", is_superuser=False)) == "free"
    assert get_user_tier(FakeUser(tier="pro", is_superuser=False)) == "pro"
    assert get_user_tier(FakeUser(tier="enterprise", is_superuser=False)) == "enterprise"


def test_get_user_tier_superuser_overrides_to_enterprise():
    """is_superuser=True forces enterprise regardless of tier column."""
    assert get_user_tier(FakeUser(tier="free", is_superuser=True)) == "enterprise"
    assert get_user_tier(FakeUser(tier="pro", is_superuser=True)) == "enterprise"


def test_get_user_tier_defaults_to_free_when_missing():
    """A user object without tier set (or with None) defaults to 'free'."""
    assert get_user_tier(FakeUser(tier=None, is_superuser=False)) == "free"


# ---------------------------------------------------------------------------
# get_tier_features
# ---------------------------------------------------------------------------


def test_get_tier_features_returns_dict_for_tier():
    free_features = get_tier_features(FakeUser(tier="free", is_superuser=False))
    assert free_features["server_live"] is False
    assert free_features["diarization"] is False

    pro_features = get_tier_features(FakeUser(tier="pro", is_superuser=False))
    assert pro_features["server_live"] is True
    assert pro_features["hipaa"] is False

    ent_features = get_tier_features(FakeUser(tier="enterprise", is_superuser=False))
    assert ent_features["hipaa"] is True
    assert ent_features["brigade_byok"] is True


def test_get_tier_features_superuser_gets_enterprise_dict():
    """is_superuser=True returns the enterprise feature dict even on a
    user with tier='free' in the column."""
    features = get_tier_features(FakeUser(tier="free", is_superuser=True))
    assert features["hipaa"] is True
    assert features["brigade_byok"] is True


# ---------------------------------------------------------------------------
# require_tier dependency
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine to completion for tests."""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_require_tier_passes_at_or_above_min():
    """A pro user must pass require_tier('pro') and require_tier('free')."""
    checker_pro = require_tier("pro")
    checker_free = require_tier("free")

    user = FakeUser(tier="pro", is_superuser=False)

    # Direct call to inner function (FastAPI would call this via Depends).
    assert _run(checker_pro(current_user=user)) is user
    assert _run(checker_free(current_user=user)) is user


def test_require_tier_403s_below_min():
    """A free user hitting a pro-gated endpoint gets a 403."""
    checker_pro = require_tier("pro")
    free_user = FakeUser(tier="free", is_superuser=False)

    with pytest.raises(HTTPException) as exc_info:
        _run(checker_pro(current_user=free_user))

    assert exc_info.value.status_code == 403
    assert "pro" in exc_info.value.detail


def test_require_tier_superuser_passes_everything():
    """A free-tier user with is_superuser=True passes enterprise gate."""
    checker_ent = require_tier("enterprise")
    superuser = FakeUser(tier="free", is_superuser=True)

    assert _run(checker_ent(current_user=superuser)) is superuser


def test_require_tier_unknown_min_tier_raises_at_definition_time():
    """Typos in the tier name fail at app boot, not on a paying customer."""
    with pytest.raises(ValueError) as exc_info:
        require_tier("ultra")
    assert "min_tier must be one of" in str(exc_info.value)
