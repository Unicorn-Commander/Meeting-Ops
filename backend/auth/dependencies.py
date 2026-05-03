from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from sqlalchemy.orm import Session
from jose import JWTError

from database.database import get_db
from auth.models import User
from auth.service import AuthService
from auth.utils import decode_token, check_permission
from auth.config import auth_config

# OAuth2 scheme for JWT tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from SSO header, JWT token, or API key (optional).

    Order of trust:
      1. oauth2-proxy forward-auth headers (X-Auth-Request-Email)
      2. JWT bearer token
      3. X-API-Key header
    SSO is checked first so Keycloak-authed users are auto-provisioned.
    """
    user = None

    # Try SSO forward-auth headers first (oauth2-proxy / Keycloak).
    # Keycloak doesn't always emit a discrete email claim; preferred_username
    # often holds it, so we fall through several headers and accept the first
    # value that looks like an email.
    def _first_email(*candidates):
        for v in candidates:
            if v and "@" in v:
                return v.strip()
        return None
    sso_email = _first_email(
        request.headers.get("X-Auth-Request-Email"),
        request.headers.get("X-Forwarded-Email"),
        request.headers.get("X-Auth-Request-Preferred-Username"),
        request.headers.get("X-Forwarded-Preferred-Username"),
        request.headers.get("X-Auth-Request-User"),
        request.headers.get("X-Forwarded-User"),
    )
    if sso_email:
        sso_username = (
            request.headers.get("X-Auth-Request-Preferred-Username")
            or request.headers.get("X-Auth-Request-User")
            or request.headers.get("X-Forwarded-User")
        )
        sso_groups_h = (
            request.headers.get("X-Auth-Request-Groups")
            or request.headers.get("X-Forwarded-Groups")
            or ""
        )
        sso_groups = [g.strip() for g in sso_groups_h.split(",") if g.strip()]
        # Keycloak emits roles with a 'role:' prefix when included in groups claim.
        # Strip it for matching, and keep the long names for app-specific admin roles.
        normalized = {g.removeprefix("role:").lower() for g in sso_groups}
        admin_aliases = {
            "admin",
            "meeting-ops-admins",
            "meetingops-admin",
            "uc-admins",
            "app:meeting-ops-admin",
            "app:meetingops-admin",
            "app:meetingops:admin",
            "app:meeting-ops:admin",
        }
        is_admin = bool(normalized & admin_aliases)
        try:
            user = AuthService.get_or_create_sso_user(
                db,
                email=sso_email,
                username=sso_username,
                full_name=sso_username,
                is_superuser=is_admin,
            )
        except Exception:
            user = None

    # Try JWT token
    if not user and token:
        try:
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                user_id = payload.get("sub")
                if user_id:
                    user = AuthService.get_user_by_id(db, int(user_id))
        except (JWTError, ValueError):
            pass

    # Try API key if no valid JWT
    if not user and api_key:
        user = AuthService.get_user_by_api_key(db, api_key)

    # Check if user is active
    if user and not user.is_active:
        return None

    return user

async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Get current user (required)"""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user

def require_permission(permission: str):
    """Dependency to require a specific permission"""
    async def permission_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
        request: Request = None
    ):
        # Get organization ID from request or token
        org_id = None
        if request:
            # Try to get org_id from query params or path
            org_id = request.query_params.get("org_id") or request.path_params.get("organization_id")
        
        # Get user's role in the organization
        role = "viewer"  # Default role
        if current_user.is_superuser:
            role = "superuser"
        elif org_id:
            user_role = AuthService.get_user_role(db, current_user.id, int(org_id))
            if user_role:
                role = user_role
        elif current_user.organizations:
            # Use first organization's role as fallback
            role = current_user.organizations[0].role
        
        # Check permission
        if not check_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}"
            )
        
        return current_user
    
    return permission_checker

def require_role(required_role: str):
    """Dependency to require a specific role or higher"""
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        # Get user's highest role
        role = "viewer"
        if current_user.is_superuser:
            role = "superuser"
        elif current_user.organizations:
            # Get highest role across all organizations
            roles = [uo.role for uo in current_user.organizations]
            role_priority = {"superuser": 0, "admin": 1, "manager": 2, "user": 3, "viewer": 4}
            roles.sort(key=lambda r: role_priority.get(r, 5))
            if roles:
                role = roles[0]
        
        # Check role hierarchy
        from auth.config import ROLE_HIERARCHY
        allowed_roles = ROLE_HIERARCHY.get(required_role, [required_role])
        
        if role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY[role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {required_role}, Current: {role}"
            )
        
        return current_user
    
    return role_checker

# Convenience dependencies for common roles
require_admin = require_role("admin")
require_manager = require_role("manager")
require_user = require_role("user")

# Audit logging dependency
async def log_request(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Log API requests for audit trail"""
    if current_user:
        # Get IP address
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # Log the request
        AuthService.log_action(
            db,
            current_user.id,
            f"api_request:{request.method}:{request.url.path}",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params)
            }
        )