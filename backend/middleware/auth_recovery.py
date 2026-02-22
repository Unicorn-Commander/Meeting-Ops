"""
Authentication Recovery Middleware
Handles JWT token refresh and session recovery
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import jwt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

class AuthRecoveryMiddleware(BaseHTTPMiddleware):
    """Middleware to handle authentication failures gracefully"""
    
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
        
    async def dispatch(self, request: Request, call_next):
        try:
            # Check if this is an auth-required endpoint
            if self._requires_auth(request.url.path):
                # Extract token
                token = self._extract_token(request)
                
                if token:
                    try:
                        # Verify token
                        payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
                        
                        # Check if token is about to expire
                        exp = datetime.fromtimestamp(payload['exp'])
                        if exp - datetime.now(timezone.utc) < timedelta(minutes=5):
                            # Token expires soon, add refresh header
                            response = await call_next(request)
                            response.headers["X-Token-Expires-Soon"] = "true"
                            return response
                            
                    except jwt.ExpiredSignatureError:
                        # Token expired - return special error code
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Token expired",
                                "code": "TOKEN_EXPIRED",
                                "refresh_required": True
                            }
                        )
                    except jwt.InvalidTokenError:
                        # Invalid token
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Invalid token",
                                "code": "INVALID_TOKEN"
                            }
                        )
                        
            # Process request normally
            response = await call_next(request)
            
            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            
            return response
            
        except Exception as e:
            logger.error(f"Auth recovery middleware error: {e}")
            # Don't expose internal errors
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
            
    def _requires_auth(self, path: str) -> bool:
        """Check if path requires authentication"""
        # Public endpoints that don't require auth
        public_paths = [
            "/api/auth/login",
            "/api/auth/refresh",
            "/api/auth/register",
            "/api/health",
            "/api/status",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/",
            "/static",
            "/favicon.ico"
        ]
        
        # Also allow OPTIONS requests without auth (for CORS)
        return not any(path.startswith(p) for p in public_paths)
        
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract token from request"""
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
            
        # Check cookie
        return request.cookies.get("access_token")


class SessionRecoveryMiddleware(BaseHTTPMiddleware):
    """Middleware to handle session recovery after failures"""
    
    def __init__(self, app):
        super().__init__(app)
        self.failed_sessions = {}
        
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            
            # Track failed recording sessions
            if request.url.path.startswith("/api/recording-sessions/") and response.status_code >= 500:
                session_id = self._extract_session_id(request.url.path)
                if session_id:
                    self.failed_sessions[session_id] = {
                        'time': datetime.now(timezone.utc),
                        'error_count': self.failed_sessions.get(session_id, {}).get('error_count', 0) + 1
                    }
                    
                    # Add recovery header
                    response.headers["X-Session-Recovery-Available"] = "true"
                    
            # Clean old failed sessions
            self._cleanup_old_sessions()
            
            return response
            
        except Exception as e:
            logger.error(f"Session recovery middleware error: {e}")
            return await call_next(request)
            
    def _extract_session_id(self, path: str) -> Optional[str]:
        """Extract session ID from path"""
        parts = path.split("/")
        if len(parts) >= 4 and parts[2] == "recording-sessions":
            return parts[3]
        return None
        
    def _cleanup_old_sessions(self):
        """Remove old failed session records"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self.failed_sessions = {
            sid: info for sid, info in self.failed_sessions.items()
            if info['time'] > cutoff
        }