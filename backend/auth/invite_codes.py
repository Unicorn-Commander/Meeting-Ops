"""Phase-1 beta invite-code helpers.

Shared by the self-serve register hook (auth/routes.py) and the invite-code
router (api/invite_codes.py) so the validate / atomic-consume / personal-org
comp logic lives in exactly one place.

Flow (when auth_config.REQUIRE_INVITE_CODE is on):
  1. register() resolves + validates the code BEFORE create_user
     (validate_invite_code) -> 403 if missing / unknown / inactive /
     exhausted. No row is mutated here.
  2. create_user() runs. A failed create raises before step 3, so a failed
     signup never burns a code.
  3. register() consumes the code ATOMICALLY (consume_invite_code):
     UPDATE ... WHERE id=:id AND redemption_count < max_redemptions and
     checks rowcount, so two parallel registrations can't both claim the
     last seat. The loser gets rowcount=0 and is treated as exhausted.
  4. register() comps the new user's personal org to Pro
     (comp_personal_org_to_pro), mirroring
     api/stripe_webhook._apply_org_plan_from_sub exactly: plan='pro' +
     max_monthly_hours=None.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from auth.models import BetaInviteCode, Organization, User, UserOrganization

logger = logging.getLogger(__name__)

# Unambiguous code alphabet (no 0/O/1/I/l) so codes are easy to read aloud
# / type from a hand-off. 10 chars from a 31-char alphabet ≈ 49 bits.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 10


def generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def validate_invite_code(db: Session, raw_code: Optional[str]) -> BetaInviteCode:
    """Resolve + validate an invite code for redemption.

    Returns the row when the code exists, is active, and still has
    redemptions left. Raises ValueError otherwise (the caller maps that to a
    403). Intentionally does NOT mutate anything — consumption is a separate,
    atomic step that runs only after create_user succeeds.
    """
    code = (raw_code or "").strip()
    if not code:
        raise ValueError("A valid invite code is required.")
    row = (
        db.query(BetaInviteCode)
        .filter(BetaInviteCode.code == code)
        .first()
    )
    if row is None:
        raise ValueError("A valid invite code is required.")
    if not row.is_active:
        raise ValueError("A valid invite code is required.")
    if row.redemption_count >= row.max_redemptions:
        raise ValueError("A valid invite code is required.")
    return row


def consume_invite_code(db: Session, code_id: int, redeemed_by_user_id: int) -> bool:
    """Atomically claim one redemption of the code.

    Single UPDATE guarded by `redemption_count < max_redemptions` so a race
    can't double-redeem a single-use code: whichever transaction commits
    first wins, the other sees rowcount == 0. Stamps redeemed_by/redeemed_at
    and flips is_active False once the code is exhausted. Returns True iff
    this call claimed a seat.
    """
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(BetaInviteCode)
        .where(BetaInviteCode.id == code_id)
        .where(BetaInviteCode.redemption_count < BetaInviteCode.max_redemptions)
        .values(
            redemption_count=BetaInviteCode.redemption_count + 1,
            redeemed_by_user_id=redeemed_by_user_id,
            redeemed_at=now,
            # Exhausted once this redemption takes it to the cap. The +1 is the
            # value AFTER this update; compare against max_redemptions.
            is_active=(BetaInviteCode.redemption_count + 1 < BetaInviteCode.max_redemptions),
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return (result.rowcount or 0) > 0


def _resolve_personal_org(db: Session, user: User) -> Optional[Organization]:
    """Find the new user's personal org to comp.

    Prefers an admin membership (create_user(personal_org=True) makes the
    user admin of `{username}-personal`); falls back to the
    `{username}-personal` slug. Returns None if neither resolves (logged,
    non-fatal — the user is still created, just not comped)."""
    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == user.id,
            UserOrganization.role == "admin",
        )
        .first()
    )
    if membership is not None:
        org = (
            db.query(Organization)
            .filter(Organization.id == membership.organization_id)
            .first()
        )
        if org is not None:
            return org
    return (
        db.query(Organization)
        .filter(Organization.slug == f"{user.username}-personal")
        .first()
    )


def comp_personal_org_to_pro(db: Session, user: User) -> bool:
    """Comp the new user's personal org to the Pro plan.

    Mirrors api/stripe_webhook._apply_org_plan_from_sub EXACTLY for the Pro
    case: org.plan='pro' AND org.max_monthly_hours=None (clear any per-org
    override so services.quotas falls through to the Pro default). Best-effort:
    a missing org is logged, not fatal. Returns True iff an org was comped.
    """
    org = _resolve_personal_org(db, user)
    if org is None:
        logger.warning(
            "invite-comp: no personal org found for user_id=%s username=%s; "
            "org plan NOT comped to pro",
            user.id, user.username,
        )
        return False
    org.plan = "pro"
    org.max_monthly_hours = None
    db.add(org)
    db.commit()
    logger.info(
        "invite-comp: org_id=%s plan->pro (max_monthly_hours cleared) for user_id=%s",
        org.id, user.id,
    )
    return True
