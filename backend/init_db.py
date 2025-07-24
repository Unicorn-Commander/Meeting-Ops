#!/usr/bin/env python3
"""Initialize missing database tables"""

from database.database import init_database

if __name__ == "__main__":
    print("Initializing database tables...")
    init_database()
    print("✅ Database initialization complete!")