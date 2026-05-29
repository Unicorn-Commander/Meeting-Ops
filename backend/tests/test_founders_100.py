"""Founders 100 mechanic tests.

The locked design (Aaron, 2026-05-29):
  - Founders pay the SAME $12/mo as everyone else. NOT a discount tier.
  - They get an `is_founder=True` flag that controls early-access +
    ecosystem bundle eligibility (Project-Ops / Accounting-Ops).
  - Cap at 100 active founders.
  - Flag is set at signup completion when FOUNDERS_100_ACTIVE=true and
    the count of existing founders is < FOUNDERS_100_LIMIT.

These tests exercise the helper `_maybe_grant_founder` directly so we
can deterministically check the cap behavior without spinning up 100
signups.
"""

from __future__ import annotations

import uuid

import pytest

def _models():
    from auth.models import User
    from database.database import SessionLocal
    return User, SessionLocal


def _make_user(*, is_founder: bool = False):
    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        uname = "fnd" + uuid.uuid4().hex[:8]
        user = User(
            email=f"{uname}@example.com",
            username=uname,
            hashed_password="x",
            is_active=True,
            is_verified=True,
            tier="free",
            is_founder=is_founder,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _founder_count() -> int:
    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        return db.query(User).filter(User.is_founder.is_(True)).count()
    finally:
        db.close()


def _refresh(user):
    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user.id).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_founder_flag_set_when_active_and_under_limit(app, monkeypatch):
    from api.stripe_webhook import _maybe_grant_founder

    monkeypatch.setenv("FOUNDERS_100_ACTIVE", "true")
    monkeypatch.setenv("FOUNDERS_100_LIMIT", "100")
    user = _make_user()
    assert _refresh(user).is_founder is False

    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        live_user = db.query(User).filter(User.id == user.id).first()
        _maybe_grant_founder(db, live_user)
    finally:
        db.close()

    assert _refresh(user).is_founder is True


def test_founder_flag_not_set_when_active_false(app, monkeypatch):
    from api.stripe_webhook import _maybe_grant_founder

    monkeypatch.setenv("FOUNDERS_100_ACTIVE", "false")
    user = _make_user()

    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        live_user = db.query(User).filter(User.id == user.id).first()
        _maybe_grant_founder(db, live_user)
    finally:
        db.close()

    assert _refresh(user).is_founder is False


def test_founder_flag_not_set_when_at_limit(app, monkeypatch):
    """If the existing count is >= FOUNDERS_100_LIMIT, new user does NOT
    get the flag. Aaron's locked behavior.
    """
    from api.stripe_webhook import _maybe_grant_founder

    monkeypatch.setenv("FOUNDERS_100_ACTIVE", "true")
    # Set the limit to the current founder count + 0 (i.e. already at limit).
    limit_at = _founder_count()
    monkeypatch.setenv("FOUNDERS_100_LIMIT", str(limit_at))
    user = _make_user()

    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        live_user = db.query(User).filter(User.id == user.id).first()
        _maybe_grant_founder(db, live_user)
    finally:
        db.close()

    assert _refresh(user).is_founder is False


def test_founder_grant_is_idempotent(app, monkeypatch):
    """Re-calling _maybe_grant_founder on an already-flagged user is a no-op
    (no extra commit, count unchanged).
    """
    from api.stripe_webhook import _maybe_grant_founder

    monkeypatch.setenv("FOUNDERS_100_ACTIVE", "true")
    monkeypatch.setenv("FOUNDERS_100_LIMIT", "1000")
    user = _make_user(is_founder=True)
    before = _founder_count()

    User, SessionLocal = _models()
    db = SessionLocal()
    try:
        live_user = db.query(User).filter(User.id == user.id).first()
        _maybe_grant_founder(db, live_user)
        _maybe_grant_founder(db, live_user)
    finally:
        db.close()

    after = _founder_count()
    assert before == after
    assert _refresh(user).is_founder is True
