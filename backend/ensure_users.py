#!/usr/bin/env python3
"""
Ensure both default users exist in the database
"""

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import User
from passlib.context import CryptContext

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions")

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

# Password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def ensure_user_exists(username, email, password, full_name, is_superuser=False):
    """Ensure a user exists with the given credentials"""
    user = db.query(User).filter(User.username == username).first()
    
    if user:
        # Update password
        user.hashed_password = pwd_context.hash(password)
        user.email = email
        user.full_name = full_name
        user.is_superuser = is_superuser
        user.is_active = True
        user.is_verified = True
        db.commit()
        print(f"✅ Updated {username} - password: {password}")
    else:
        # Create new user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=pwd_context.hash(password),
            is_active=True,
            is_verified=True,
            is_superuser=is_superuser
        )
        db.add(user)
        db.commit()
        print(f"✅ Created {username} - password: {password}")
    
    return user

# Ensure both default users exist
print("🔧 Ensuring default users exist in database...")

# Admin user
admin = ensure_user_exists(
    username="admin",
    email="admin@meeting-ops.local",
    password="admin123",
    full_name="System Administrator",
    is_superuser=True
)

# Regular user
user = ensure_user_exists(
    username="user",
    email="user@meeting-ops.local", 
    password="user123",
    full_name="Regular User",
    is_superuser=False
)

print("\n📋 Current users in database:")
all_users = db.query(User).all()
for u in all_users:
    role = "Admin" if u.is_superuser else "User"
    print(f"   - {u.username} ({role}): {u.email}")

db.close()

print("\n✅ Default accounts ready:")
print("   Admin: admin / admin123")
print("   User:  user / user123")