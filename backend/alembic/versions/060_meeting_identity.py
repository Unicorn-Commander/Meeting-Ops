"""Meeting identity, separate from export identity.

058 gave a session the identity of the *export* that created it
(organization_id, external_source, external_id). Unicorn Stable produces one
export per participant browser, and the payload each browser signs includes
its own wall clock, so one call yields as many external_ids as there were
people who hung up — and therefore as many sessions, and as many summaries.

This adds the identity of the *meeting*:

  meeting_key       one call = one value, whatever the export count
  external_room_id  the upstream room the call happened in (indexed; the
                    coalescing lookup is room + overlapping time window)

Both are NULL for every existing row and for every session that does not come
from an upstream call. NULLs are distinct under a Postgres unique constraint,
so the ~900 pre-existing rows do not collide with each other.

Revision ID: 060_meeting_identity
Revises: 059_integration_pat_scope
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa

revision = "060_meeting_identity"
down_revision = "059_integration_pat_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recording_sessions",
        sa.Column("meeting_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "recording_sessions",
        sa.Column("external_room_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_recording_sessions_external_room_id",
        "recording_sessions",
        ["external_room_id"],
    )
    op.create_unique_constraint(
        "uq_recording_sessions_org_meeting_key",
        "recording_sessions",
        ["organization_id", "meeting_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_recording_sessions_org_meeting_key",
        "recording_sessions",
        type_="unique",
    )
    op.drop_index(
        "ix_recording_sessions_external_room_id",
        table_name="recording_sessions",
    )
    op.drop_column("recording_sessions", "external_room_id")
    op.drop_column("recording_sessions", "meeting_key")
