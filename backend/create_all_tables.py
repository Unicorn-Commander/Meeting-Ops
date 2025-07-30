#!/usr/bin/env python3
"""Create all database tables"""

import sys
sys.path.insert(0, '.')

from database.database import engine
from database.models import Base
from auth.models import User
from sqlalchemy import inspect

# Check current tables
inspector = inspect(engine)
tables_before = inspector.get_table_names()
print(f"Tables before: {tables_before}")

# Create all tables
print("\nCreating all tables...")
Base.metadata.create_all(bind=engine)

# Verify creation
inspector = inspect(engine)
tables_after = inspector.get_table_names()
print(f"\nTables after: {tables_after}")

# Show new tables
new_tables = set(tables_after) - set(tables_before)
if new_tables:
    print(f"\n✅ Created {len(new_tables)} new tables:")
    for table in sorted(new_tables):
        print(f"  - {table}")
else:
    print("\n✅ All tables already exist")