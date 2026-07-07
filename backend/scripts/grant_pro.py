#!/usr/bin/env python3
"""Grant (or revoke) a TIME-LIMITED Pro/paid comp for a Meeting-Ops user.

The comp is bounded: it sets ``User.tier`` + ``User.tier_expires_at = now + N
days``. The session-watchdog cron
(``services.session_watchdog.revert_expired_comps``) reverts the user to
'free' once the expiry passes, so a "free month" comp for an invited cohort
needs no Stripe/card and can't silently become permanent. A real subscription
later clears ``tier_expires_at`` (``api.stripe_webhook``), so a comped user who
then pays keeps Pro.

Usage (inside meet-backend, or from backend/ with DATABASE_URL set):
    python -m scripts.grant_pro alice@example.com --days 30
    python -m scripts.grant_pro alice@example.com --days 30 --tier pro \
        --founding --cohort meeting_ops_v1
    python -m scripts.grant_pro alice@example.com --revoke

Idempotent: re-running a grant refreshes the expiry window; --revoke on an
already-free user is a no-op. Prints a before/after JSON snapshot.

Note: this is a deliberate MANUAL admin grant. Unlike the Stripe path it does
NOT enforce the Founding 100 cap when --founding is passed — the operator owns
that decision.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tiers a comp may grant. Mirrors the paid names in auth.tier._TIER_RANK;
# 'free' is only reachable via --revoke.
_GRANTABLE_TIERS = ("basic", "pro", "suite", "enterprise")


def _snapshot(user) -> dict:
    """Serializable view of the comp-relevant columns for before/after output."""
    expires = getattr(user, "tier_expires_at", None)
    return {
        "email": user.email,
        "tier": user.tier,
        "tier_expires_at": expires.isoformat() if expires else None,
        "is_founding_member": bool(getattr(user, "is_founding_member", False)),
        "founding_cohort": getattr(user, "founding_cohort", None),
    }


def apply_comp(
    db,
    user,
    *,
    revoke: bool,
    tier: str = "pro",
    days: int = 30,
    founding: bool = False,
    cohort: str = "meeting_ops_v1",
):
    """Mutate ``user`` in place per the flags and commit.

    Returns ``(before, after)`` snapshot dicts. Factored out of ``main()`` so
    it is unit-testable without argv. On ``revoke`` it sets tier='free' and
    clears the expiry (leaving founding flags alone, mirroring the auto-revert
    watchdog's surgical scope). On grant it sets tier + a fresh
    ``now + days`` expiry, and optionally the founding flag/cohort.
    """
    before = _snapshot(user)
    if revoke:
        user.tier = "free"
        user.tier_expires_at = None
    else:
        user.tier = tier
        user.tier_expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        if founding:
            user.is_founding_member = True
            if cohort:
                user.founding_cohort = cohort
    db.add(user)
    db.commit()
    db.refresh(user)
    return before, _snapshot(user)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Grant/revoke a time-limited Pro comp for a Meeting-Ops user",
    )
    ap.add_argument("email", help="email of the user to comp")
    ap.add_argument("--days", type=int, default=30,
                    help="comp length in days (default 30)")
    ap.add_argument("--tier", default="pro", choices=_GRANTABLE_TIERS,
                    help="tier to grant (default pro)")
    ap.add_argument("--founding", action="store_true",
                    help="also set is_founding_member (perks overlay)")
    ap.add_argument("--cohort", default="meeting_ops_v1",
                    help="founding_cohort label when --founding (default meeting_ops_v1)")
    ap.add_argument("--revoke", action="store_true",
                    help="revert to free + clear expiry (ignores --days/--tier)")
    args = ap.parse_args()

    if not args.revoke and args.days < 1:
        print("ERROR: --days must be >= 1 (use --revoke to remove a comp)",
              file=sys.stderr)
        return 2

    from sqlalchemy import func

    from auth.models import User
    from database.database import SessionLocal

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        # Case-insensitive lookup: emails are stored lowercased on the Stripe
        # path but a manually-created user could differ.
        user = (
            db.query(User)
            .filter(func.lower(User.email) == email)
            .first()
        )
        if user is None:
            print(f"ERROR: no user with email={email!r}", file=sys.stderr)
            return 1
        before, after = apply_comp(
            db,
            user,
            revoke=args.revoke,
            tier=args.tier,
            days=args.days,
            founding=args.founding,
            cohort=args.cohort,
        )
        print(json.dumps(
            {
                "action": "revoke" if args.revoke else "grant",
                "before": before,
                "after": after,
            },
            indent=2,
        ))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
