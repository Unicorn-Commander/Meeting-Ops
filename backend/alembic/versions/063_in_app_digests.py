"""In-app digest sources, account opt-ins, and per-recipient delivery claims."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "063_in_app_digests"
down_revision = "062_merge_combined_and_lease"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("email_daily_digest", "email_weekly_digest"):
        op.add_column("users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("meeting_digest", sa.Column("source_meeting_ids", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True))
    op.add_column("meeting_digest", sa.Column("generated_at", sa.DateTime(), nullable=True))
    op.create_table(
        "digest_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("digest_id", sa.Integer(), sa.ForeignKey("meeting_digest.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("organization_id", "period", "date", "user_id", name="uq_digest_delivery_recipient_window"),
    )


def downgrade():
    op.drop_table("digest_delivery")
    op.drop_column("meeting_digest", "generated_at")
    op.drop_column("meeting_digest", "source_meeting_ids")
    op.drop_column("users", "email_weekly_digest")
    op.drop_column("users", "email_daily_digest")
