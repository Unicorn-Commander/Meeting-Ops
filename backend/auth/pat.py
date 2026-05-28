"""Personal Access Token helpers.

PAT plaintext is shown once at creation time. Only a SHA-256 digest is stored.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.models import PersonalAccessToken, User


TOKEN_PREFIX = "mops_pat_"
TOKEN_RANDOM_CHARS = 32
TOKEN_PREFIX_DISPLAY_CHARS = 12
_BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_pat(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _generate_plaintext() -> str:
    random_part = "".join(secrets.choice(_BASE32_ALPHABET) for _ in range(TOKEN_RANDOM_CHARS))
    return f"{TOKEN_PREFIX}{random_part}"


def _clean_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Token name must not be empty")
    if len(cleaned) > 100:
        raise HTTPException(status_code=400, detail="Token name must be <= 100 characters")
    return cleaned


def create_pat(db: Session, *, user: User, name: str) -> tuple[PersonalAccessToken, str]:
    plaintext = _generate_plaintext()
    model = PersonalAccessToken(
        user_id=user.id,
        name=_clean_name(name),
        token_hash=hash_pat(plaintext),
        token_prefix=plaintext[:TOKEN_PREFIX_DISPLAY_CHARS],
        created_at=_now(),
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model, plaintext


def resolve_pat(db: Session, *, plaintext: str) -> Optional[User]:
    if not plaintext or not plaintext.startswith(TOKEN_PREFIX):
        return None

    token_hash = hash_pat(plaintext)
    row = (
        db.query(PersonalAccessToken)
        .filter(
            PersonalAccessToken.token_hash == token_hash,
            PersonalAccessToken.revoked_at.is_(None),
        )
        .first()
    )
    if not row:
        return None
    user = row.user
    if not user or not user.is_active:
        return None
    row.last_used_at = _now()
    db.commit()
    db.refresh(user)
    return user


def revoke_pat(db: Session, *, user: User, pat_id: int) -> bool:
    row = (
        db.query(PersonalAccessToken)
        .filter(
            PersonalAccessToken.id == pat_id,
            PersonalAccessToken.user_id == user.id,
            PersonalAccessToken.revoked_at.is_(None),
        )
        .first()
    )
    if not row:
        return False
    row.revoked_at = _now()
    db.commit()
    return True
