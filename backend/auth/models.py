from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Float
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
    
    # Plan and limits
    plan = Column(String, default="free")  # free, pro, enterprise
    storage_quota_gb = Column(Integer, default=10)
    storage_used_gb = Column(Float, default=0.0)
    max_users = Column(Integer, default=5)
    max_monthly_hours = Column(Integer, default=100)
    
    # Settings
    settings = Column(get_json_type(), default={})
    is_active = Column(Boolean, default=True)
    
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

class UserOrganization(Base):
    __tablename__ = "user_organizations"
    
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