"""App-level OIDC SSO for Unicorn Commander (uchub Keycloak).

Lets any uchub-authenticated user sign into Meeting-Ops directly, without an
oauth2-proxy in front:

    GET /api/auth/sso/uc/start    -> redirect to Keycloak authorize
    GET /api/auth/sso/uc/callback -> exchange code, auto-provision via
                                     AuthService.get_or_create_sso_user, mint
                                     the app's own JWT, drop it in an HttpOnly
                                     cookie the auth dependency reads, then
                                     redirect into the app.

The public landing page and the email/password consumer accounts are left
untouched — this only adds a direct "Sign in with Unicorn Commander" path that
reuses the existing SSO auto-provisioning (personal org, free tier). The
Unicorn Commander dashboard app-card links straight to /start for zero-click
SSO (the user already holds a uchub session, so Keycloak completes silently).
"""
import logging
import os
import secrets
import urllib.parse
from datetime import timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.orm import Session

from auth.organization import is_global_admin, parse_group_list
from auth.service import AuthService
from auth.utils import create_access_token
from database.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso/uc", tags=["sso"])

# Reuse the backend's existing Keycloak config (set in the prod compose).
_KC_BASE = os.getenv("KEYCLOAK_URL", "https://auth.unicorncommander.ai").rstrip("/")
_KC_REALM = os.getenv("KEYCLOAK_REALM", "uchub")
KC_ISSUER = f"{_KC_BASE}/realms/{_KC_REALM}"
KC_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "meeting-ops-prod")
KC_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "https://meeting-ops.unicorncommander.ai").rstrip("/")
REDIRECT_URI = f"{APP_PUBLIC_URL}/api/auth/sso/uc/callback"

# Cookie the auth dependency reads (see auth/dependencies.py).
SESSION_COOKIE_NAME = os.getenv("UC_SSO_COOKIE_NAME", "mo_uc_session")
SESSION_DAYS = int(os.getenv("UC_SSO_SESSION_DAYS", "7"))

_STATE_COOKIE = "mo_uc_oidc_state"
_RT_COOKIE = "mo_uc_oidc_rt"
_TRANSIENT_PATH = "/api/auth/sso/uc"


def _safe_return_to(rt: Optional[str]) -> str:
    """Open-redirect guard: only local single-slash paths."""
    if rt and rt.startswith("/") and not rt.startswith("//"):
        return rt
    return "/"


def _login_error(reason: str) -> RedirectResponse:
    return RedirectResponse(
        f"{APP_PUBLIC_URL}/#/login?sso_error={urllib.parse.quote(reason)}",
        status_code=302,
    )


@router.get("/start")
async def uc_sso_start(returnTo: Optional[str] = None):
    """Kick off the Keycloak authorization-code flow."""
    if not KC_CLIENT_SECRET:
        logger.error("UC SSO start invoked but KEYCLOAK_CLIENT_SECRET is unset")
        return _login_error("sso_not_configured")

    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": KC_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "state": state,
    }
    authorize_url = f"{KC_ISSUER}/protocol/openid-connect/auth?" + urllib.parse.urlencode(params)
    resp = RedirectResponse(authorize_url, status_code=302)
    cookie_kw = dict(httponly=True, secure=True, samesite="lax", max_age=600, path=_TRANSIENT_PATH)
    resp.set_cookie(_STATE_COOKIE, state, **cookie_kw)
    resp.set_cookie(_RT_COOKIE, _safe_return_to(returnTo), **cookie_kw)
    return resp


@router.get("/callback")
async def uc_sso_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Complete the flow: exchange code, provision, set the session cookie."""
    if error:
        logger.warning("UC SSO callback returned error from Keycloak: %s", error)
        return _login_error(error)

    expected_state = request.cookies.get(_STATE_COOKIE)
    return_to = _safe_return_to(request.cookies.get(_RT_COOKIE))
    if not code or not state or not expected_state or state != expected_state:
        logger.warning(
            "UC SSO callback state check failed (code=%s, state_match=%s)",
            bool(code), state == expected_state,
        )
        return _login_error("state_mismatch")

    token_url = f"{KC_ISSUER}/protocol/openid-connect/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": KC_CLIENT_ID,
        "client_secret": KC_CLIENT_SECRET,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            tr = await client.post(
                token_url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if tr.status_code != 200:
            logger.error("UC SSO token exchange failed: %s %s", tr.status_code, tr.text[:300])
            return _login_error("token_exchange_failed")
        claims = jwt.get_unverified_claims(tr.json().get("id_token") or "")
    except Exception:
        logger.exception("UC SSO token exchange / claim parse failed")
        return _login_error("token_exchange_failed")

    email = claims.get("email") or claims.get("preferred_username")
    if not email or "@" not in str(email):
        logger.warning("UC SSO: no usable email claim; claim keys=%s", list(claims.keys()))
        return _login_error("no_email")

    groups = parse_group_list(claims.get("groups") or [])
    try:
        user = AuthService.get_or_create_sso_user(
            db,
            email=email,
            username=claims.get("preferred_username"),
            full_name=claims.get("name") or claims.get("preferred_username"),
            is_superuser=is_global_admin(groups),
            groups=groups,
        )
    except Exception:
        logger.exception("UC SSO auto-provision failed for %s", email)
        return _login_error("provision_failed")

    # Mint a session-lifetime app access token (same shape the bearer path
    # decodes: sub=user id, type=access) and hand it back as an HttpOnly
    # cookie. probeSso() in the SPA reads /api/auth/me, which the auth
    # dependency now satisfies from this cookie.
    org_id = user.organizations[0].organization_id if user.organizations else None
    session_token = create_access_token(
        {"sub": str(user.id), "username": user.username, "email": user.email, "org_id": org_id},
        expires_delta=timedelta(days=SESSION_DAYS),
    )
    resp = RedirectResponse(f"{APP_PUBLIC_URL}{return_to}", status_code=302)
    resp.set_cookie(
        SESSION_COOKIE_NAME, session_token,
        httponly=True, secure=True, samesite="lax",
        max_age=SESSION_DAYS * 86400, path="/",
    )
    resp.delete_cookie(_STATE_COOKIE, path=_TRANSIENT_PATH)
    resp.delete_cookie(_RT_COOKIE, path=_TRANSIENT_PATH)
    logger.info("UC SSO sign-in complete for %s (user_id=%s)", email, user.id)
    return resp
