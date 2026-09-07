"""Combined meetings: a summary-only session linked to its ordered parts.

Additive and reversible. ``recording_sessions.is_combined`` flags the
summary-only row; ``session_group_members`` links it to its parts in time
order. Both FKs cascade so deleting either side only removes the link row
(docs/COMBINED-MEETINGS-CONTRACT.md).

Revision ID: 060_combined_meetings
Revises: 059_integration_pat_scope
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa

revision = "060_combined_meetings"
down_revision = "059_integration_pat_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recording_sessions",
        sa.Column(
            "is_combined",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "session_group_members",
        sa.Column("combined_session_id", sa.Integer(), nullable=False),
        sa.Column("member_session_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["combined_session_id"],
            ["recording_sessions.id"],
            name="fk_session_group_members_combined",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["member_session_id"],
            ["recording_sessions.id"],
            name="fk_session_group_members_member",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "combined_session_id",
            "member_session_id",
            name="pk_session_group_members",
        ),
    )
    op.create_index(
        "ix_session_group_members_member",
        "session_group_members",
        ["member_session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_group_members_member",
        table_name="session_group_members",
    )
    op.drop_table("session_group_members")
    op.drop_column("recording_sessions", "is_combined")
