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
# The caller stamps head next. Alembic would create alembic_version as
# VARCHAR(32); revision ids here run longer (039_widen_alembic_ver widens it on
# the upgrade path), so create it at the widened size first.
with engine.begin() as conn:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        "version_num VARCHAR(255) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    ))
print("All tables created successfully.")
