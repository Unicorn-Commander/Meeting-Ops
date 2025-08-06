#!/usr/bin/env python3
"""
Fix admin password for PostgreSQL database
"""
import os
import sys
import hashlib
import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Database URL
DATABASE_URL = "postgresql://meetingops:REMOVED@localhost:5432/meeting_sessions"

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def fix_admin_password():
    """Reset admin password in PostgreSQL"""
    print("🔧 Fixing admin password in PostgreSQL...")
    
    try:
        # Create engine
        engine = create_engine(DATABASE_URL)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✅ Connected to: {version}")
            
            # Check if admin user exists
            result = conn.execute(text("SELECT id, username FROM users WHERE username = 'admin';"))
            admin = result.fetchone()
            
            if admin:
                print(f"✅ Found admin user with ID: {admin[0]}")
                
                # Update password
                new_password = "changeme123!"
                hashed_password = hash_password(new_password)
                
                conn.execute(text("""
                    UPDATE users 
                    SET hashed_password = :password, 
                        is_active = true,
                        is_verified = true
                    WHERE username = 'admin';
                """), {"password": hashed_password})
                
                # Commit the transaction
                conn.commit()
                
                print("✅ Admin password updated successfully!")
                print(f"   Username: admin")
                print(f"   Password: {new_password}")
                print("   ⚠️ Please change this password after first login!")
                
            else:
                print("❌ Admin user not found. Creating new admin user...")
                
                # Create admin user
                hashed_password = hash_password("changeme123!")
                
                conn.execute(text("""
                    INSERT INTO users (username, email, hashed_password, full_name, is_active, is_verified)
                    VALUES ('admin', 'admin@meeting-ops.local', :password, 'System Administrator', true, true);
                """), {"password": hashed_password})
                
                conn.commit()
                
                print("✅ Admin user created successfully!")
                print("   Username: admin")
                print("   Password: changeme123!")
                print("   ⚠️ Please change this password after first login!")
                
    except OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        print("   Make sure PostgreSQL container is running:")
        print("   docker ps | grep postgres")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

def test_login():
    """Test the login with new credentials"""
    print("\n🧪 Testing login...")
    
    try:
        import requests
        
        response = requests.post(
            "http://localhost:9050/api/auth/login",
            json={"username": "admin", "password": "changeme123!"},
            timeout=5
        )
        
        if response.status_code == 200:
            print("✅ Login test successful!")
            data = response.json()
            print(f"   User: {data.get('user', {}).get('full_name', 'Unknown')}")
            print(f"   Role: {data.get('user', {}).get('role', 'Unknown')}")
        else:
            print(f"❌ Login test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"⚠️ Could not test login: {e}")
        print("   Backend might not be running on port 9050")

if __name__ == "__main__":
    print("Meeting-Ops Admin Password Fix")
    print("=" * 40)
    
    success = fix_admin_password()
    
    if success:
        test_login()
        
        print("\n🎯 Next steps:")
        print("1. Refresh the frontend page")  
        print("2. Login with: admin / changeme123!")
        print("3. Navigate to Recording Page to test audio")
    else:
        print("\n❌ Fix failed. Check the error messages above.")
        sys.exit(1)