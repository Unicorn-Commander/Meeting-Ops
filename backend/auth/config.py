import os
from datetime import timedelta
from typing import Optional
from pydantic import BaseModel

class AuthConfig(BaseModel):
    # JWT settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Password policy
    MIN_PASSWORD_LENGTH: int = 8
    REQUIRE_UPPERCASE: bool = True
    REQUIRE_LOWERCASE: bool = True
    REQUIRE_NUMBERS: bool = True
    REQUIRE_SPECIAL_CHARS: bool = False
    
    # Security settings
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    
    # Email settings (for password reset, etc.)
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@unicorn-commander.local")
    
    # Registration
    ALLOW_REGISTRATION: bool = os.getenv("ALLOW_REGISTRATION", "false").lower() == "true"
    DEFAULT_USER_ROLE: str = "user"
    # Public base URL of the app, used to build links in transactional emails
    # (email verification, password reset). Must be the user-facing origin.
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://meetingops.magicunicorn.dev").rstrip("/")

    # OAuth2 (optional)
    ENABLE_OAUTH: bool = os.getenv("ENABLE_OAUTH", "false").lower() == "true"
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")

auth_config = AuthConfig()

# Role hierarchy for permission checking
ROLE_HIERARCHY = {
    "superuser": ["superuser", "admin", "manager", "user", "viewer"],
    "admin": ["admin", "manager", "user", "viewer"],
    "manager": ["manager", "user", "viewer"],
    "user": ["user", "viewer"],
    "viewer": ["viewer"]
}

# Permission definitions
PERMISSIONS = {
    # Session permissions
    "session.create": ["admin", "manager", "user"],
    "session.read": ["admin", "manager", "user", "viewer"],
    "session.update": ["admin", "manager", "user"],  # Users can only update their own
    "session.delete": ["admin", "manager"],  # Users can delete their own
    
    # File permissions
    "file.upload": ["admin", "manager", "user"],
    "file.download": ["admin", "manager", "user", "viewer"],
    "file.delete": ["admin", "manager"],
    
    # User management
    "user.create": ["admin"],
    "user.read": ["admin", "manager"],  # Users can read their own profile
    "user.update": ["admin"],  # Users can update their own profile
    "user.delete": ["admin"],
    
    # Organization management
    "org.update": ["admin"],
    "org.invite": ["admin", "manager"],
    "org.remove_user": ["admin"],
    
    # Settings
    "settings.read": ["admin", "manager", "user", "viewer"],
    "settings.update": ["admin"],
    
    # Analytics
    "analytics.view": ["admin", "manager"],
    
    # AI/ML permissions
    "ai.read": ["admin", "manager", "user", "viewer"],
    "ai.write": ["admin", "manager"],
    "ai.delete": ["admin"],
    "ai.model.read": ["admin", "manager", "user", "viewer"],
    "ai.model.write": ["admin", "manager"],
    "ai.model.delete": ["admin"],
    "ai.model.test": ["admin", "manager", "user"],
    "ai.transcription.read": ["admin", "manager", "user", "viewer"],
    "ai.transcription.write": ["admin", "manager", "user"],
}