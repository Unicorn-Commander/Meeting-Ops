"""Personal Access Token management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.models import PersonalAccessToken, User
from auth.pat import create_pat, revoke_pat
from database.database import get_db

router = APIRouter(prefix="/api/auth/pats", tags=["personal-access-tokens"])


class CreatePATRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class PATCreateResponse(BaseModel):
    id: int
    name: str
    token_prefix: str
    plaintext: str
    created_at: datetime


class PATListItem(BaseModel):
    id: int
    name: str
    token_prefix: str
    last_used_at: Optional[datetime] = None
    created_at: datetime
    revoked_at: Optional[datetime] = None


def _to_item(row: PersonalAccessToken) -> PATListItem:
    return PATListItem(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


@router.post("", response_model=PATCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_personal_access_token(
    body: CreatePATRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row, plaintext = create_pat(db, user=current_user, name=body.name)
    return PATCreateResponse(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        plaintext=plaintext,
        created_at=row.created_at,
    )


@router.get("", response_model=list[PATListItem])
async def list_personal_access_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rows = (
        db.query(PersonalAccessToken)
        .filter(PersonalAccessToken.user_id == current_user.id)
        .order_by(PersonalAccessToken.created_at.desc(), PersonalAccessToken.id.desc())
        .all()
    )
    return [_to_item(row) for row in rows]


@router.delete("/{pat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_personal_access_token(
    pat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    revoke_pat(db, user=current_user, pat_id=pat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
