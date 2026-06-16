"""Phase-1 beta invite-code endpoints.

Three routes (contract fixed with the frontend stream):

  POST /api/admin/invite-codes        (admin only)
      Mint `count` single-use codes. Body
      {for_user_id?: int, count: int=5 (1..50), note?: str}. The codes are
      attributed to `for_user_id` (so a seed user's /mine lists them) or, if
      absent, to the calling admin. Returns the minted codes.

  GET  /api/invite-codes/mine         (authed)
      The caller's own codes (created_by_user_id == me), newest first, in the
      contract shape:
      [{code, is_active, redeemed, redeemed_by_email, redeemed_at, created_at}].

  GET  /api/invite-codes/config       (anonymous OK)
      {"require_invite_code": auth_config.REQUIRE_INVITE_CODE} so the signup
      page knows whether to show the invite-code field.

Minting/redemption/comp live in auth/invite_codes.py and are shared with the
self-serve register hook.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.config import auth_config
from auth.dependencies import get_current_user
from auth.invite_codes import generate_code
from auth.models import BetaInviteCode, User
from auth.service import AuthService
from database.database import get_db

logger = logging.getLogger(__name__)

# Admin mint endpoint reads naturally under /api/admin; the caller-facing
# read endpoints live under /api/invite-codes. Both are mounted from this
# module (see main.py: router + admin_router).
router = APIRouter(prefix="/api/invite-codes", tags=["invite-codes"])
admin_router = APIRouter(prefix="/api/admin/invite-codes", tags=["invite-codes"])

_MAX_MINT_PER_CALL = 50


class MintInviteCodesRequest(BaseModel):
    for_user_id: Optional[int] = None
    count: int = Field(default=5, ge=1, le=_MAX_MINT_PER_CALL)
    note: Optional[str] = None


class InviteCodeMinted(BaseModel):
    code: str
    is_active: bool
    max_redemptions: int
    created_at: Optional[datetime] = None


class InviteCodeMineItem(BaseModel):
    code: str
    is_active: bool
    redeemed: bool
    redeemed_by_email: Optional[str] = None
    redeemed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class InviteConfigResponse(BaseModel):
    require_invite_code: bool


@admin_router.post("", response_model=list[InviteCodeMinted])
async def mint_invite_codes(
    payload: MintInviteCodesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InviteCodeMinted]:
    """Mint `count` single-use invite codes. PLATFORM-SUPERUSER ONLY.

    Phase-1 deliberately restricts minting to a true platform superuser (not an
    org admin): the whole point of the invite gate is controlled scarcity, so
    Aaron mints codes FOR seed users (`for_user_id`) and those users only SHARE
    them (via /mine) — they don't mint their own. NOTE: `require_admin` resolves
    "admin" from the caller's ACTIVE org, and every self-serve user is admin of
    their own {username}-personal org, so require_admin here would let ANY
    signed-in user mint — hence the explicit is_superuser gate. (Phase 2 will
    add a scoped grant that lets invitees mint their own.)

    Attributed to `for_user_id` when supplied (so a seed user's /mine lists
    them), else to the calling superuser. `count` is bounded 1..50 by the schema.
    A `for_user_id` that doesn't resolve to a real user is rejected (400) so
    codes aren't minted into the void."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a platform admin can mint invite codes",
        )
    owner_id = payload.for_user_id or current_user.id
    if payload.for_user_id is not None:
        target = db.query(User).filter(User.id == payload.for_user_id).first()
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="for_user_id does not match any user",
            )

    note = (payload.note or "").strip() or None
    minted: list[BetaInviteCode] = []
    # Generate distinct codes; the unique index is the real guard but we
    # pre-dedupe within the batch + retry on the astronomically rare
    # collision so a single dup can't fail the whole mint.
    seen: set[str] = set()
    attempts = 0
    while len(minted) < payload.count and attempts < payload.count * 10:
        attempts += 1
        code = generate_code()
        if code in seen:
            continue
        seen.add(code)
        row = BetaInviteCode(
            code=code,
            created_by_user_id=owner_id,
            max_redemptions=1,
            redemption_count=0,
            is_active=True,
            note=note,
        )
        db.add(row)
        minted.append(row)
    db.commit()

    AuthService.log_action(
        db,
        current_user.id,
        "invite_codes_minted",
        details={
            "count": len(minted),
            "for_user_id": owner_id,
        },
    )

    return [
        InviteCodeMinted(
            code=row.code,
            is_active=row.is_active,
            max_redemptions=row.max_redemptions,
            created_at=row.created_at,
        )
        for row in minted
    ]


@router.get("/mine", response_model=list[InviteCodeMineItem])
async def my_invite_codes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InviteCodeMineItem]:
    """The caller's own invite codes (created_by_user_id == me), newest
    first. `redeemed` reflects whether the code has been consumed at all;
    `redeemed_by_email` is resolved from the redeemer for the seed user's
    hand-out tracking."""
    rows = (
        db.query(BetaInviteCode)
        .filter(BetaInviteCode.created_by_user_id == current_user.id)
        .order_by(BetaInviteCode.created_at.desc(), BetaInviteCode.id.desc())
        .all()
    )

    # Batch-resolve redeemer emails (avoid N+1).
    redeemer_ids = {r.redeemed_by_user_id for r in rows if r.redeemed_by_user_id}
    emails: dict[int, str] = {}
    if redeemer_ids:
        for u in db.query(User).filter(User.id.in_(redeemer_ids)).all():
            emails[u.id] = u.email

    return [
        InviteCodeMineItem(
            code=row.code,
            is_active=row.is_active,
            redeemed=row.redemption_count > 0,
            redeemed_by_email=emails.get(row.redeemed_by_user_id),
            redeemed_at=row.redeemed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/config", response_model=InviteConfigResponse)
async def invite_codes_config() -> InviteConfigResponse:
    """Anonymous: tells the signup page whether an invite code is required."""
    return InviteConfigResponse(
        require_invite_code=auth_config.REQUIRE_INVITE_CODE
    )
