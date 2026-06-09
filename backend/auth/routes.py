import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from database.database import get_db
from auth.service import AuthService
from auth.dependencies import get_current_organization, get_current_user, require_admin, require_permission
from auth.email import send_password_reset_email, send_verification_email
from auth.models import Organization, PasswordResetToken, User, UserOrganization
from auth.config import auth_config
from auth.tier import get_tier_features, get_user_tier
from auth.utils import (
    generate_email_verification_token,
    get_password_hash,
    sanitize_email,
    validate_password,
    verify_email_verification_token,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Org/membership endpoints that read more naturally under /api/organizations
# than under the /api/auth prefix (the user's "home"/default workspace).
# Registered in main.py via _load_router(..., router_attr="organizations_router")
# so we don't proliferate a separate module — they live with the membership
# serialization helpers (_serialize_memberships) here.
organizations_router = APIRouter(prefix="/api/organizations", tags=["organizations"])

# Pydantic models for requests/responses
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    organization_id: Optional[int] = None
    role: str = "user"
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v: str):
        if not v.replace('_', '').isalnum():
            raise ValueError('Username must be alphanumeric')
        if len(v) < 3 or len(v) > 30:
            raise ValueError('Username must be between 3 and 30 characters')
        return v.lower()

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    is_superuser: bool = False
    created_at: datetime
    role: Optional[str] = None  # Will be populated from organization role or superuser status
    organizations: list[dict] = []
    active_organization: Optional[dict] = None
    # Tier-based feature gating. `tier` is the resolved effective tier
    # (is_superuser overrides to 'enterprise'); `tier_features` is the
    # full capability dict from TIER_FEATURES so the frontend can render
    # without a follow-up round trip. See backend/auth/tier.py.
    tier: str = "free"
    tier_features: dict[str, Any] = {}
    # Stripe billing surface — populated so the frontend can render the
    # "Founding 100" badge + the right Pricing-page CTA on the very first
    # render after login. `founding_cohort` is the cohort label (e.g.
    # "meeting_ops_v1") or None when the user is not a founding member.
    is_founding_member: bool = False
    founding_cohort: Optional[str] = None
    has_stripe_customer: bool = False

    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class LoginRequest(BaseModel):
    username: str  # Can be username or email
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str


class OrganizationMembershipResponse(BaseModel):
    id: int
    name: str
    slug: str
    role: str
    is_active: bool


class SetDefaultOrganizationRequest(BaseModel):
    organization_id: int


def _serialize_memberships(user: User) -> list[dict]:
    memberships: list[dict] = []
    for membership in user.organizations:
        organization = membership.organization
        if not organization:
            continue
        memberships.append(
            OrganizationMembershipResponse(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                role=membership.role,
                is_active=organization.is_active,
            ).model_dump()
        )

    memberships.sort(key=lambda item: item["name"].lower())
    return memberships


def _build_user_response(
    user: User,
    *,
    active_org: Optional[Organization] = None,
    active_role: Optional[str] = None,
) -> UserResponse:
    organizations = _serialize_memberships(user)
    role = "superuser" if user.is_superuser else active_role
    if not role and organizations:
        role = organizations[0]["role"]
    if not role:
        role = "user"

    active_organization = None
    if active_org:
        for org in organizations:
            if org["id"] == active_org.id:
                active_organization = org
                break
        if active_organization is None:
            active_organization = {
                "id": active_org.id,
                "name": active_org.name,
                "slug": active_org.slug,
                "role": active_role or ("superuser" if user.is_superuser else "viewer"),
                "is_active": active_org.is_active,
            }

    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        role=role,
        organizations=organizations,
        active_organization=active_organization,
        tier=get_user_tier(user),
        tier_features=get_tier_features(user),
        is_founding_member=bool(getattr(user, "is_founding_member", False)),
        founding_cohort=getattr(user, "founding_cohort", None),
        has_stripe_customer=bool(getattr(user, "stripe_customer_id", None)),
    )

# Routes
from auth.dependencies import get_current_user_optional


async def _optional_caller_for_register(
    caller: Optional[User] = Depends(get_current_user_optional),
) -> Optional[User]:
    """Self-serve signup dependency.

    `register()` accepts either an authenticated admin (legacy invite-only
    path) OR an anonymous caller (self-serve when ALLOW_REGISTRATION=true).
    The actual access check happens inside `register()` against
    `auth_config.ALLOW_REGISTRATION`.

    Replaces the v3.2.0 inline ternary `Depends(require_admin) if not
    auth_config.ALLOW_REGISTRATION else None` which FastAPI/Pydantic
    rejected at module import when ALLOW_REGISTRATION=true (the `None`
    branch left `current_user: Optional[User]` with no Depends and
    Pydantic tried to treat User as a response field).
    """
    return caller


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_optional_caller_for_register),
):
    """Register a new user"""
    # Check if registration is allowed
    if not auth_config.ALLOW_REGISTRATION and not current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Contact an administrator."
        )
    
    # Self-serve = no admin caller. Self-serve consumers get a private
    # personal org (not the shared default) and an email-verification link;
    # admin-created users keep the legacy behavior.
    is_self_serve = current_user is None
    try:
        user = AuthService.create_user(
            db,
            email=user_data.email,
            username=user_data.username,
            password=user_data.password,
            full_name=user_data.full_name,
            organization_id=user_data.organization_id,
            role=user_data.role,
            created_by_id=current_user.id if current_user else None,
            personal_org=is_self_serve and user_data.organization_id is None,
        )
        if is_self_serve and not user.is_verified:
            # Best-effort: a mail failure must not fail signup (the user can
            # resend). send_verification_email logs + returns False if SMTP
            # is unconfigured.
            token = generate_email_verification_token(user.email)
            send_verification_email(
                user.email,
                f"{auth_config.APP_BASE_URL}/api/auth/verify-email?token={token}",
            )
        # Founding 100 grant happens at Stripe-checkout-completion time
        # (annual-upfront subscriptions only), not at signup. The grant
        # is wired in api/stripe_webhook.py._maybe_grant_founding_member;
        # it intentionally does NOT fire here so free-tier signups don't
        # consume a cohort seat.
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

class ResendVerificationRequest(BaseModel):
    email: EmailStr


@router.get("/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
    """Confirm an email-verification link, then redirect to the app login
    with a status flag. Idempotent: re-clicking a still-valid link lands on
    success again. Invalid/expired tokens redirect to an error state rather
    than exposing whether the email exists."""
    redirect_ok = f"{auth_config.APP_BASE_URL}/#/login?verify=success"
    redirect_bad = f"{auth_config.APP_BASE_URL}/#/login?verify=invalid"
    email = verify_email_verification_token(token)
    if not email:
        return RedirectResponse(redirect_bad, status_code=303)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return RedirectResponse(redirect_bad, status_code=303)
    if not user.is_verified:
        user.is_verified = True
        db.commit()
        AuthService.log_action(db, user.id, "email_verified", "user", str(user.id))
    return RedirectResponse(redirect_ok, status_code=303)


@router.post("/resend-verification")
async def resend_verification(
    payload: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    """Re-send a verification email. Always returns the same 200 message so
    it can't be used to enumerate which addresses have accounts."""
    try:
        email = sanitize_email(payload.email)
    except ValueError:
        email = None
    if email:
        user = db.query(User).filter(User.email == email).first()
        if user and not user.is_verified:
            token = generate_email_verification_token(user.email)
            send_verification_email(
                user.email,
                f"{auth_config.APP_BASE_URL}/api/auth/verify-email?token={token}",
            )
    return {
        "message": "If an unverified account exists for that address, a verification link has been sent."
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login with username/email and password"""
    user = AuthService.authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        # Log failed login attempt
        AuthService.log_action(
            db, None, "login_failed",
            ip_address=request.client.host if request.client else None,
            details={"username": form_data.username}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create tokens
    tokens = AuthService.create_tokens(user)
    
    default_org = None
    default_role = None
    if user.organizations:
        default_org = user.organizations[0].organization
        default_role = user.organizations[0].role
    
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user=_build_user_response(
            user,
            active_org=default_org,
            active_role=default_role,
        )
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    from auth.utils import decode_token

    # Decode refresh token
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Get user
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user = AuthService.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    tokens = AuthService.create_tokens(user, payload.get("org_id"))
    
    default_org = None
    default_role = None
    if user.organizations:
        default_org = user.organizations[0].organization
        default_role = user.organizations[0].role
    
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user=_build_user_response(
            user,
            active_org=default_org,
            active_role=default_role,
        )
    )

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    active_org=Depends(get_current_organization),
):
    """Get current user profile"""
    return _build_user_response(
        current_user,
        active_org=active_org.organization,
        active_role=active_org.role,
    )

@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    active_org=Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """Update current user profile"""
    updated_user = AuthService.update_user(
        db,
        current_user.id,
        full_name=user_update.full_name,
        department=user_update.department,
        phone=user_update.phone,
        avatar_url=user_update.avatar_url
    )
    return _build_user_response(
        updated_user,
        active_org=active_org.organization,
        active_role=active_org.role,
    )

@router.post("/me/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change current user password"""
    success = AuthService.change_password(
        db,
        current_user.id,
        password_data.old_password,
        password_data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password"
        )
    
    return {"message": "Password changed successfully"}

@router.post("/me/api-key")
async def generate_api_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a new API key for current user"""
    api_key = AuthService.generate_user_api_key(db, current_user.id)
    return {
        "api_key": api_key,
        "message": "API key generated successfully. Store it securely as it won't be shown again."
    }


@router.get("/orgs", response_model=list[OrganizationMembershipResponse])
async def list_current_user_orgs(
    current_user: User = Depends(get_current_user),
):
    """List the authenticated user's organizations."""
    return [
        OrganizationMembershipResponse(**membership)
        for membership in _serialize_memberships(current_user)
    ]


@router.delete("/me")
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Self-serve account deletion (App Review 5.1.1(v)).

    *** DRAFT — destructive + runs on a LIVE prod backend. Review + test on
    staging before deploy, and deploy to BOTH nodes (dogfood + customer). ***

    The iOS app calls this on the cloud Delete-Account path. The admin
    `DELETE /users/{id}` refuses self-deletion, so this is the self-serve path.

    Cleanup (verified against database/models.py):
      - `recording_sessions.user_id` is a plain Integer (NO FK) -> find + delete
        the caller's sessions explicitly.
      - `transcriptions.session_id` is a plain Integer (NO FK) -> delete manually
        by session id.
      - `action_items` + `session_collaborators` FK -> recording_sessions.id with
        ondelete=CASCADE, so they go automatically when the sessions are deleted.
      - `db.delete(user)` cascades personal_access_tokens (all, delete-orphan)
        + the UserOrganization memberships.

    NOT YET DONE (decide in review before deploy):
      - Qdrant vectors for the deleted sessions (collection `meet_transcripts`).
      - The Keycloak user itself (no admin-delete helper exists yet; a user could
        otherwise re-auth into a fresh empty account). Full-delete vs disable?
      - Speaker profiles owned solely by this user (audit before mass-deleting
        anything shared at the org level).
    """
    from database.models import RecordingSession, Transcription

    uid = current_user.id
    AuthService.log_action(
        db, uid, "account_self_deleted",
        details={"username": current_user.username},
    )

    session_ids = [
        row[0]
        for row in db.query(RecordingSession.id)
        .filter(RecordingSession.user_id == uid)
        .all()
    ]
    if session_ids:
        # No FK cascade on transcriptions -> delete by session id first.
        db.query(Transcription).filter(
            Transcription.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        # Deleting the sessions cascades action_items + session_collaborators.
        db.query(RecordingSession).filter(
            RecordingSession.user_id == uid
        ).delete(synchronize_session=False)
        # TODO(review): delete Qdrant points for these session_ids.

    # TODO(review): delete the Keycloak user via a new admin helper (or disable).
    # TODO(review): delete speaker profiles owned solely by this user.

    db.delete(current_user)  # cascades PATs + org memberships
    db.commit()

    return {"message": "Account deleted"}


@organizations_router.put("/default", response_model=UserResponse)
async def set_default_organization(
    payload: SetDefaultOrganizationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the caller's "home"/default workspace (Organization).

    The default org is the top preference that
    `auth.organization.resolve_active_organization` falls back to when a
    request carries no `X-MeetingOps-Org` header / `?org=` selector — so a
    user's chosen workspace persists server-side across devices + on any
    node. The caller MUST be a member of the target org (or a superuser);
    we never let a user pin a workspace they can't access.
    """
    organization = (
        db.query(Organization)
        .filter(Organization.id == payload.organization_id)
        .first()
    )
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == current_user.id,
            UserOrganization.organization_id == organization.id,
        )
        .first()
    )
    if not membership and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization",
        )

    current_user.default_organization_id = organization.id
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return _build_user_response(
        current_user,
        active_org=organization,
        active_role=(membership.role if membership else None),
    )

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Logout current user"""
    # Log logout action
    AuthService.log_action(db, current_user.id, "logout", "user", str(current_user.id))
    
    # In a stateless JWT system, logout is handled client-side
    # We just log the action and return success
    return {"message": "Logged out successfully"}

# Admin routes
@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    organization_id: Optional[int] = None,
    current_user: User = Depends(require_permission("user.read")),
    active_org=Depends(get_current_organization),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    if organization_id and organization_id != active_org.organization.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to that organization",
        )

    target_org_id = organization_id or active_org.organization.id
    query = (
        db.query(User)
        .join(User.organizations)
        .filter(UserOrganization.organization_id == target_org_id)
    )
    users = query.offset(skip).limit(limit).all()
    target_org = db.query(Organization).filter(Organization.id == target_org_id).first()
    return [
        _build_user_response(
            user,
            active_org=target_org,
            active_role=AuthService.get_user_role(db, user.id, target_org_id),
        )
        for user in users
    ]

@router.put("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Activate a user account"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = True
    user.is_verified = True
    db.commit()
    
    return {"message": "User activated successfully"}

@router.put("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Deactivate a user account"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    user.is_active = False
    db.commit()
    
    return {"message": "User deactivated successfully"}

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role_data: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a user's role"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    new_role = role_data.get("role")
    if new_role not in ["user", "manager", "admin", "superuser", "viewer"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role"
        )
    
    # Update role by setting superuser status
    if new_role == "superuser":
        user.is_superuser = True
    else:
        user.is_superuser = False
    
    db.commit()
    
    # Log the action
    AuthService.log_action(
        db, current_user.id, "role_update", 
        details={"user_id": user_id, "new_role": new_role}
    )
    
    return {"message": f"User role updated to {new_role}"}

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a user account"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Log the action before deletion
    AuthService.log_action(
        db, current_user.id, "user_deleted", 
        details={"deleted_user_id": user_id, "deleted_username": user.username}
    )
    
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}


# ---------------------------------------------------------------------------
# Password reset (v3.21.0)
# ---------------------------------------------------------------------------

_password_reset_logger = logging.getLogger(__name__ + ".password_reset")

# Rate limit: max 3 forgot-password requests per email per hour.
_PASSWORD_RESET_RATE_LIMIT_MAX = 3
_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 60 * 60
_PASSWORD_RESET_TOKEN_TTL_HOURS = 1
_PASSWORD_RESET_RL_INPROC: dict[str, list[float]] = {}


def _hash_reset_token(plaintext: str) -> str:
    """sha256 hex of the plaintext token. Used both at issue time
    (what we persist) and at validation time (what we look up by)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _public_url() -> str:
    """Base URL the password-reset link points at. Mirrors billing._app_base_url:
    APP_BASE_URL > FRONTEND_BASE_URL > localhost fallback."""
    raw = (
        os.getenv("APP_BASE_URL")
        or os.getenv("FRONTEND_BASE_URL")
        or "http://localhost:7777"
    ).rstrip("/")
    return raw


async def _password_reset_under_rate_limit(email_key: str) -> bool:
    """3-per-hour per-email rate limit. Redis-first (SETEX counter), with
    an in-proc fallback that matches the landing-page pattern. The key
    space is namespaced so it doesn't collide with the landing limiter.
    """
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis.asyncio as redis  # local import
            client = await redis.from_url(redis_url, decode_responses=True)
            try:
                key = f"auth:pwreset:rl:{email_key}"
                count = await client.incr(key)
                if count == 1:
                    await client.expire(
                        key, _PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS
                    )
                return count <= _PASSWORD_RESET_RATE_LIMIT_MAX
            finally:
                await client.close()
        except Exception as exc:  # noqa: BLE001
            _password_reset_logger.warning(
                "password-reset rate-limit: redis unavailable (%s); falling back to in-proc",
                exc,
            )

    # In-proc fallback (per-pod, not cross-pod safe — same caveat as landing).
    import time as _time
    now = _time.time()
    bucket = [
        t for t in _PASSWORD_RESET_RL_INPROC.get(email_key, [])
        if now - t < _PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(bucket) >= _PASSWORD_RESET_RATE_LIMIT_MAX:
        _PASSWORD_RESET_RL_INPROC[email_key] = bucket
        return False
    bucket.append(now)
    _PASSWORD_RESET_RL_INPROC[email_key] = bucket
    return True


class PasswordResetForgotRequest(BaseModel):
    email: EmailStr


class PasswordResetSubmitRequest(BaseModel):
    token: str
    new_password: str


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
)
async def password_reset_forgot(
    payload: PasswordResetForgotRequest,
    db: Session = Depends(get_db),
):
    """Initiate a password reset.

    Always returns 202 with the same body regardless of whether the
    email matches a user — never leak account existence. When the email
    matches an active user, we generate a single-use token, persist its
    sha256, and email the plaintext link to the user. Rate limited to 3
    requests per email per hour (Redis SETEX with in-proc fallback).
    """
    response_body = {
        "message": (
            "If an account matches that email, a reset link is on the way."
        )
    }

    try:
        email = sanitize_email(payload.email)
    except ValueError:
        email = None
    if not email:
        return response_body

    # Rate-limit on the normalized email so attackers can't bypass by
    # case-perturbing the address.
    if not await _password_reset_under_rate_limit(email):
        _password_reset_logger.info(
            "password-reset: rate-limited email=%s", email
        )
        # Still return 202 — rate-limit existence is also a leak vector.
        return response_body

    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        return response_body

    # Cryptographically random 32-byte token, base64url encoded
    # (token_urlsafe(32) returns ~43 chars).
    plaintext = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(plaintext)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_PASSWORD_RESET_TOKEN_TTL_HOURS)

    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=now,
    )
    db.add(reset)
    db.commit()

    reset_url = f"{_public_url()}/reset-password?token={plaintext}"
    # send_password_reset_email is best-effort + non-raising.
    send_password_reset_email(user.email, reset_url)
    _password_reset_logger.info(
        "password-reset: token issued user_id=%s expires_at=%s",
        user.id, expires_at.isoformat(),
    )
    return response_body


def _lookup_reset_token(db: Session, token: str) -> Optional[PasswordResetToken]:
    """Resolve a plaintext token to its persisted row by sha256 hash.
    Returns None when the token doesn't exist."""
    if not token:
        return None
    token_hash = _hash_reset_token(token)
    return (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )


def _reset_token_state(record: Optional[PasswordResetToken]) -> str:
    """Return one of 'missing' / 'used' / 'expired' / 'valid'."""
    if record is None:
        return "missing"
    if record.used_at is not None:
        return "used"
    expires_at = record.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        # SQLite returns naive datetimes; treat as UTC.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and expires_at < datetime.now(timezone.utc):
        return "expired"
    return "valid"


@router.get("/password/reset/validate")
async def password_reset_validate(
    token: str,
    db: Session = Depends(get_db),
):
    """Lightweight check that a reset token is still good before showing
    the new-password form. 200 on valid; 410 on expired/used; 400 on
    unknown/malformed."""
    record = _lookup_reset_token(db, token)
    state = _reset_token_state(record)
    if state == "valid":
        return {"valid": True}
    if state in ("expired", "used"):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This password-reset link has expired.",
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This password-reset link is not valid.",
    )


@router.post("/password/reset")
async def password_reset_submit(
    payload: PasswordResetSubmitRequest,
    db: Session = Depends(get_db),
):
    """Complete a password reset.

    Validates the token (lookup by sha256 hash, not used, not expired),
    enforces the existing password policy, updates the user's
    hashed_password, and marks the token used. Returns 200 on success,
    400 on invalid/malformed token or weak password, 410 on expired/used
    token."""
    record = _lookup_reset_token(db, payload.token)
    state = _reset_token_state(record)
    if state in ("expired", "used"):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This password-reset link has expired.",
        )
    if state != "valid" or record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password-reset link is not valid.",
        )

    ok, errors = validate_password(payload.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=" ".join(errors) or "Password does not meet policy.",
        )

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None or not user.is_active:
        # Same response shape as expired — don't leak whether the user
        # was deleted between issue + submit.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This password-reset link is no longer valid.",
        )

    user.hashed_password = get_password_hash(payload.new_password)
    record.used_at = datetime.now(timezone.utc)
    db.add(user)
    db.add(record)
    db.commit()
    AuthService.log_action(
        db, user.id, "password_reset_completed",
        resource_type="user", resource_id=str(user.id),
    )
    _password_reset_logger.info(
        "password-reset: completed user_id=%s", user.id
    )
    return {"message": "Password updated. You can sign in with the new password."}
