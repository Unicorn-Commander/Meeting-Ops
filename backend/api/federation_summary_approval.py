"""Human approval gate for the Customer-Ops meeting-summary projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.federation_meetings import (
    approved_summary_payload,
    summary_approval_digest,
)
from api.sessions_participants import _can_edit, _resolve_session
from auth.dependencies import get_current_organization, get_current_user
from auth.models import User
from auth.organization import ActiveOrganization
from database.database import get_db


router = APIRouter(
    prefix="/api/simple/recording-sessions/{session_id}/federation-summary-approval",
    tags=["federation-summary-approval"],
)


class SummaryApprovalOut(BaseModel):
    status: str
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[int] = None


def _out(session) -> SummaryApprovalOut:
    status, _payload = approved_summary_payload(session)
    return SummaryApprovalOut(
        status=status,
        approved_at=(
            session.federation_summary_approved_at
            if status == "approved"
            else None
        ),
        approved_by_user_id=(
            session.federation_summary_approved_by_user_id
            if status == "approved"
            else None
        ),
    )


@router.get("", response_model=SummaryApprovalOut)
async def get_summary_approval(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(
        db,
        active_org.organization.id,
        session_id,
        current_user,
    )
    return _out(session)


@router.put("", response_model=SummaryApprovalOut)
async def approve_summary(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(
        db,
        active_org.organization.id,
        session_id,
        current_user,
        min_level="edit",
    )
    if not _can_edit(session, current_user, active_org):
        raise HTTPException(
            status_code=403,
            detail="Not permitted to approve this summary",
        )
    digest = summary_approval_digest(session)
    if digest is None:
        raise HTTPException(
            status_code=409,
            detail="No summary is available to approve",
        )
    session.federation_summary_approved_digest = digest
    session.federation_summary_approved_at = datetime.now(timezone.utc)
    session.federation_summary_approved_by_user_id = current_user.id
    db.commit()
    db.refresh(session)
    return _out(session)


@router.delete("", response_model=SummaryApprovalOut)
async def revoke_summary_approval(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    session = _resolve_session(
        db,
        active_org.organization.id,
        session_id,
        current_user,
        min_level="edit",
    )
    if not _can_edit(session, current_user, active_org):
        raise HTTPException(
            status_code=403,
            detail="Not permitted to revoke this summary approval",
        )
    session.federation_summary_approved_digest = None
    session.federation_summary_approved_at = None
    session.federation_summary_approved_by_user_id = None
    db.commit()
    db.refresh(session)
    return _out(session)
