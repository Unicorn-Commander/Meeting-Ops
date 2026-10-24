from database.database import Base as AppBase
from auth.models import Base as AuthBase
from sqlalchemy import text

from database.database import engine

# A fresh database has no extensions; the models use CITEXT columns and the
# migrations rely on pgcrypto. Alembic creates these on an upgrade path, but the
# empty-volume path builds the schema straight from the models.
with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

print("Creating all tables...")
AuthBase.metadata.create_all(bind=engine)
AppBase.metadata.create_all(bind=engine)
print("All tables created successfully.")
