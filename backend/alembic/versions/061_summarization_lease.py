"""Cross-process lease so one meeting gets one summarization run.

The live-summary websocket is opened per viewer and asks the summarizer to
start on connect. Three people watching one meeting is three start calls, and
the only thing collapsing them into one background run is an in-process dict
inside each summarizer service. That is correct exactly while the backend is
one process — the moment there is a second uvicorn worker, a replica, or a
summarizer running in the arq worker containers (same image, already beside
the backend), each process keeps its own dict and the same transcript is
summarized, and billed, once per process.

This adds the shared state that dict cannot have. One row per meeting being
summarized, holder-stamped, with an expiry that a heartbeat pushes forward;
the row is deleted when the run stops, and a lapsed row may be taken over by
any process (the previous holder died without releasing).

Deliberately a new empty table: no existing row is read, rewritten or locked,
so this is safe to apply to the live database.

Revision ID: 061_summarization_lease
Revises: 060_meeting_identity
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa

revision = "061_summarization_lease"
down_revision = "060_meeting_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summarization_leases",
        # Not a FK: callers key the summarizers with both
        # recording_sessions.session_id (uuid text) and str(id) (integer PK as
        # text), so the key space is wider than either column.
        sa.Column("session_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("holder", sa.String(length=200), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_summarization_leases_expires_at",
        "summarization_leases",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_summarization_leases_expires_at",
        table_name="summarization_leases",
    )
    op.drop_table("summarization_leases")
