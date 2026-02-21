import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch


@pytest.fixture(scope="session")
def app():
    db_fd, db_path = tempfile.mkstemp(prefix="meeting_ops_test_", suffix=".db")
    os.close(db_fd)

    mp = MonkeyPatch()
    mp.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from database.database import init_database, SessionLocal
    init_database()

    # Seed admin user for auth tests
    from auth.models import User
    from auth.utils import get_password_hash

    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        user = User(
            email="admin@meeting-ops.local",
            username="admin",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
        db.add(user)
        db.commit()
    db.close()

    from main import app as fastapi_app

    yield fastapi_app

    mp.undo()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
