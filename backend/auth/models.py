from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database.database import Base
import os

# Use JSONB for PostgreSQL, JSON for others
def get_json_type():
    if "postgresql" in os.getenv("DATABASE_URL", ""):
        return JSONB
    return JSON

class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)  # URL-friendly name
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Plan and limits. NULL on max_file_bytes / max_concurrent_uploads means
    # "use the tier default from services.quotas.TIER_DEFAULTS". Use the
    # helpers in services/quotas.py rather than reading these columns
    # directly so per-org overrides and tier defaults compose correctly.
    plan = Column(String, default="free")  # free, pro, enterprise
    storage_quota_gb = Column(Integer, default=10)
    storage_used_gb = Column(Float, default=0.0)
    max_users = Column(Integer, default=5)
    # max_monthly_hours / max_file_bytes / max_concurrent_uploads are NULL by
    # default so services.quotas falls through to tier defaults. Existing
    # orgs that were created with the old default of 100 keep their value
    # (the migration does not retroactively NULL it).
    max_monthly_hours = Column(Integer, nullable=True)
    max_file_bytes = Column(BigInteger, nullable=True)
    max_concurrent_uploads = Column(Integer, nullable=True)
    
    # Settings
    settings = Column(get_json_type(), default={})
    is_active = Column(Boolean, default=True)

    # Per-org integration toggles + credentials (v3.19.0).
    # Shape (each key optional; absent = use env-var default + disabled):
    #   {
    #     "brigade":        {"enabled": bool, "api_base_url": str, "api_key_encrypted": str,
    #                        "tenancy_mode": "shared"|"per_org_graph"|"per_org_instance",
    #                        "shared_agent_id": str},
    #     "project_ops":    {"enabled": bool, "api_base_url": str, "api_key_encrypted": str,
    #                        "default_project_number": str},
    #     "contact_ops":    {"enabled": bool, "api_base_url": str, "api_key_encrypted": str},
    #     "accounting_ops": {"enabled": bool, "api_base_url": str, "api_key_encrypted": str},
    #     "stable":         {"enabled": bool, "api_base_url": str, "api_key_encrypted": str},
    #   }
    # api_key_encrypted is Fernet ciphertext (services.providers.crypto).
    # NEVER return the cleartext value from any HTTP response. Always mask
    # via api.integrations_org._mask_integration before serializing.
    integrations = Column(get_json_type(), nullable=False, default=dict, server_default="{}")
    
    # Relationships
    users = relationship("UserOrganization", back_populates="organization")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Profile
    full_name = Column(String)
    avatar_url = Column(String)
    phone = Column(String)
    department = Column(String)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)

    # Tier-based feature gating. One of 'free' / 'pro' / 'enterprise'.
    # Source of truth for what each tier unlocks lives in
    # backend/auth/tier.py (TIER_FEATURES dict). Backfilled by alembic
    # 028 to set Aaron + Shafen to enterprise. New users default to
    # 'free' until billing flips them.
    tier = Column(String(32), nullable=False, default="free")

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime)
    
    # Security
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    
    # API access
    api_key = Column(String, unique=True, nullable=True)
    api_key_created_at = Column(DateTime, nullable=True)
    
    # Relationships
    organizations = relationship("UserOrganization", back_populates="user", foreign_keys="UserOrganization.user_id")
    audit_logs = relationship("AuditLog", back_populates="user")
    personal_access_tokens = relationship(
        "PersonalAccessToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class PersonalAccessToken(Base):
    __tablename__ = "personal_access_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_personal_access_tokens_token_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    token_hash = Column(String(64), nullable=False, index=True)
    token_prefix = Column(String(12), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="personal_access_tokens")

class UserOrganization(Base):
    __tablename__ = "user_organizations"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_organizations_user_org"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Role in organization
    role = Column(String, nullable=False)  # admin, manager, user, viewer
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Permissions override (optional)
    custom_permissions = Column(get_json_type(), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="organizations", foreign_keys=[user_id])
    organization = relationship("Organization", back_populates="users")
    invited_by_user = relationship("User", foreign_keys=[invited_by])

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    
    # Action details
    action = Column(String, nullable=False)  # login, logout, create_session, delete_file, etc.
    resource_type = Column(String, nullable=True)  # session, file, user, etc.
    resource_id = Column(String, nullable=True)
    
    # Additional data
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    details = Column(get_json_type(), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")

# Note: Session organization support will be added later
