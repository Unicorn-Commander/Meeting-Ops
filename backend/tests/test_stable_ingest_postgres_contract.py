"""PostgreSQL schema contract for the Stable transcript import mode."""

import os

import pytest
from sqlalchemy import create_engine, text

from api.stable_ingest import STABLE_INGEST_SESSION_MODE


def test_stable_ingest_mode_is_accepted_by_postgres_schema():
    """Fail when application semantics drift from the live CHECK constraint.

    The regular API suite intentionally runs on SQLite. Release/CI lanes with
    PostgreSQL set MEETING_OPS_POSTGRES_CONTRACT_URL so this test queries the
    actual constraint rather than silently losing CHECK coverage.
    """

    url = os.getenv("MEETING_OPS_POSTGRES_CONTRACT_URL")
    if not url:
        pytest.skip("MEETING_OPS_POSTGRES_CONTRACT_URL is required for this contract")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            definition = connection.execute(
                text(
                    """
                    SELECT pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conname = 'ck_recording_sessions_mode'
                    """
                )
            ).scalar_one()
    finally:
        engine.dispose()

    assert f"'{STABLE_INGEST_SESSION_MODE}'" in definition
