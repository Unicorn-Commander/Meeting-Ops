#!/usr/bin/env python3
"""
Script to test login functionality
"""
import requests
import json
from sqlalchemy.orm import Session
from database.database import SessionLocal, init_database
from auth.models import User

def test_login_api():
    """Test the login API endpoint"""
    print("Testing login API endpoint...")
    
    # Test with form data (like OAuth2PasswordRequestForm expects)
    url = "http://localhost:9050/api/auth/login"
    
    credentials = [
        ("admin", "Changeme123!"),
        ("admin", "changeme123!"),
        ("admin", "Changeme123"),
    ]
    
    for username, password in credentials:
        print(f"\n🔍 Testing {username}:{password}")
        
        # Test with form data
        form_data = {
            'username': username,
            'password': password
        }
        
        try:
            response = requests.post(url, data=form_data)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Login successful!")
                print(f"   User: {data['user']['username']}")
                print(f"   Token: {data['access_token'][:20]}...")
                return True
            else:
                try:
                    error_data = response.json()
                    print(f"   ❌ Error: {error_data.get('detail', 'Unknown error')}")
                except:
                    print(f"   ❌ Error: {response.text}")
                    
        except requests.exceptions.ConnectionError:
            print("   ❌ Connection failed - is the server running?")
            return False
        except Exception as e:
            print(f"   ❌ Unexpected error: {e}")
    
    return False

def check_database():
    """Check database for admin user"""
    print("Checking database...")
    
    try:
        init_database()
        db: Session = SessionLocal()
        
        users = db.query(User).all()
        print(f"Found {len(users)} users in database:")
        
        for user in users:
            print(f"  👤 {user.username} ({user.email})")
            print(f"     Role: {user.role}")
            print(f"     Active: {user.is_active}")
            print(f"     Verified: {user.is_verified}")
            print(f"     Superuser: {user.is_superuser}")
            print(f"     Created: {user.created_at}")
            
            if user.username == "admin":
                # Try to verify password hash
                from auth.service import AuthService
                print(f"     Password hash starts with: {user.password_hash[:20]}...")
                
                # Test password verification
                test_passwords = ["Changeme123!", "changeme123!", "Changeme123"]
                for pwd in test_passwords:
                    if AuthService.verify_password(pwd, user.password_hash):
                        print(f"     ✅ Password '{pwd}' matches!")
                    else:
                        print(f"     ❌ Password '{pwd}' does not match")
            print()
            
    except Exception as e:
        print(f"❌ Database error: {e}")
    finally:
        try:
            db.close()
        except:
            pass

def test_health():
    """Test server health"""
    print("Testing server health...")
    
    try:
        response = requests.get("http://localhost:9050/api/status")
        if response.status_code == 200:
            data = response.json()
            print("✅ Server is responding")
            print(f"   Transcriber ready: {data.get('transcriber_ready', 'Unknown')}")
            print(f"   NPU available: {data.get('npu_available', 'Unknown')}")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Server is not responding - is it running on port 9050?")
        return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    return False

if __name__ == "__main__":
    print("🔧 Unicorn Commander Login Debug Tool")
    print("=" * 50)
    
    # Check database first
    check_database()
    
    print("\n" + "=" * 50)
    
    # Check server health
    if test_health():
        print("\n" + "=" * 50)
        
        # Test login
        if not test_login_api():
            print("\n💡 Troubleshooting tips:")
            print("1. Make sure the server is running: uvicorn main:app --host 0.0.0.0 --port 9050")
            print("2. Try creating/resetting admin: python reset_admin.py reset")
            print("3. Check the server logs for errors")
            print("4. The correct password is: Changeme123! (with capital C and exclamation)")
    else:
        print("\n💡 Start the server first:")
        print("   cd backend")
        print("   python -m uvicorn main:app --host 0.0.0.0 --port 9050 --reload")