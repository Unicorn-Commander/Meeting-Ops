from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from database.database import get_db
from auth.service import AuthService
from auth.dependencies import get_current_organization, get_current_user, require_admin, require_permission
from auth.models import Organization, User, UserOrganization
from auth.config import auth_config
from auth.tier import get_tier_features, get_user_tier

router = APIRouter(prefix="/api/auth", tags=["authentication"])

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
    )

# Routes
@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin) if not auth_config.ALLOW_REGISTRATION else None
):
    """Register a new user"""
    # Check if registration is allowed
    if not auth_config.ALLOW_REGISTRATION and not current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Contact an administrator."
        )
    
    try:
        user = AuthService.create_user(
            db,
            email=user_data.email,
            username=user_data.username,
            password=user_data.password,
            full_name=user_data.full_name,
            organization_id=user_data.organization_id,
            role=user_data.role,
            created_by_id=current_user.id if current_user else None
        )
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

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
