import os
import sys
import tempfile

# Create temp SQLite DB and set env BEFORE pytest collects anything else.
_db_fd, _db_path = tempfile.mkstemp(prefix="meeting_ops_test_", suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

# Ensure backend root is on sys.path
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest


def pytest_configure(config):
    """Ensure DATABASE_URL points to test SQLite before any imports."""
    os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"


@pytest.fixture(scope="session")
def app():
    """Create a test FastAPI app with an isolated SQLite database."""
    # Force reload database module to pick up SQLite URL
    import importlib

    # Reload database.models first (owns Base), then database.database (imports Base).
    # Any model modules that previously imported Base must be reloaded afterwards so
    # their tables are attached to the same metadata for this isolated SQLite DB.
    if "database.models" in sys.modules:
        importlib.reload(sys.modules["database.models"])
    if "database.database" in sys.modules:
        importlib.reload(sys.modules["database.database"])
    if "auth.models" in sys.modules:
        importlib.reload(sys.modules["auth.models"])
    from database.database import engine, SessionLocal
    from database.models import Base

    # Import the auth models needed by these API tests before create_all so
    # their tables register on the same metadata object as the core DB models.
    from auth.models import User, Organization, UserOrganization, AuditLog  # noqa: F401

    # Create all tables in the test SQLite DB
    Base.metadata.create_all(bind=engine)

    # Seed admin user for auth tests
    from auth.utils import get_password_hash

    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                email="admin@meeting-ops.local",
                username="admin",
                hashed_password=get_password_hash("admin123"),
                is_active=True,
                is_verified=True,
                is_superuser=True,
            )
            db.add(admin_user)
            db.commit()

        default_org = db.query(Organization).filter(Organization.slug == "magic-unicorn").first()
        if not default_org:
            default_org = Organization(
                name="Magic Unicorn",
                slug="magic-unicorn",
                is_active=True,
            )
            db.add(default_org)
            db.commit()

        if not db.query(UserOrganization).filter(
            UserOrganization.user_id == admin_user.id,
            UserOrganization.organization_id == default_org.id,
        ).first():
            db.add(UserOrganization(
                user_id=admin_user.id,
                organization_id=default_org.id,
                role="admin",
            ))
            db.commit()
    finally:
        db.close()

    from main import app as fastapi_app
    yield fastapi_app

    # Cleanup temp DB
    if os.path.exists(_db_path):
        os.remove(_db_path)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
