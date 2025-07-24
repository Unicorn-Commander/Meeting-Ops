#!/usr/bin/env python3
"""
Simple script to check admin user and test password
"""
from sqlalchemy.orm import Session
from database.database import SessionLocal, init_database
from auth.service import AuthService
from auth.models import User
from auth.utils import verify_password

def check_admin_simple():
    print("🔍 Checking admin user...")
    
    init_database()
    db: Session = SessionLocal()
    
    try:
        # Find admin user
        admin = db.query(User).filter_by(username="admin").first()
        
        if not admin:
            print("❌ Admin user does not exist!")
            print("Creating admin user...")
            
            admin_user = AuthService.create_user(
                db,
                email="admin@unicorn-commander.local",
                username="admin",
                password="Changeme123!",
                full_name="System Administrator"
            )
            admin_user.is_superuser = True
            admin_user.is_verified = True
            db.commit()
            
            print("✅ Admin user created!")
            admin = admin_user
        
        print(f"✅ Admin user found:")
        print(f"   Username: {admin.username}")
        print(f"   Email: {admin.email}")
        print(f"   Active: {admin.is_active}")
        print(f"   Verified: {admin.is_verified}")
        print(f"   Superuser: {admin.is_superuser}")
        
        # Test password
        print(f"\n🔐 Testing passwords:")
        test_passwords = ["Changeme123!", "changeme123!", "Changeme123", "admin", "password"]
        
        for pwd in test_passwords:
            if verify_password(pwd, admin.hashed_password):
                print(f"   ✅ '{pwd}' - CORRECT PASSWORD!")
            else:
                print(f"   ❌ '{pwd}' - incorrect")
        
        # Test authentication (like the API does)
        print(f"\n🔑 Testing authentication method:")
        auth_result = AuthService.authenticate_user(db, "admin", "Changeme123!")
        if auth_result:
            print("   ✅ Authentication successful!")
        else:
            print("   ❌ Authentication failed!")
            
        # Show password hash info
        print(f"\nPassword hash: {admin.hashed_password[:50]}...")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_admin_simple()