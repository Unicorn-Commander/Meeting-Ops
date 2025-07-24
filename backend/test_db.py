#!/usr/bin/env python3

import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from database.database import init_database, get_db, SessionLocal
    from auth.models import User
    from auth.service import AuthService
    
    logger.info("Testing database initialization...")
    
    # Initialize database
    init_database()
    logger.info("✅ Database initialized successfully")
    
    # Test creating a session
    db = SessionLocal()
    try:
        # Check if admin user exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if admin_user:
            logger.info(f"✅ Admin user found: {admin_user.email}")
        else:
            logger.info("Creating admin user...")
            admin_user = AuthService.create_user(
                db,
                email="admin@unicorn-commander.local",
                username="admin",
                password="Changeme123!",
                full_name="System Administrator",
                role="admin"
            )
            admin_user.is_superuser = True
            admin_user.is_verified = True
            db.commit()
            logger.info("✅ Admin user created successfully")
            
        logger.info("✅ Database test completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        sys.exit(1)
    finally:
        db.close()
        
except Exception as e:
    logger.error(f"❌ Import or initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)