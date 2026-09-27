"""Preserve legacy weekly digest subscribers in the per-user preference."""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "064_backfill_legacy_weekly_digest_email"
down_revision = "063_in_app_digests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("email", sa.String),
                     sa.column("email_weekly_digest", sa.Boolean))
    memberships = sa.table("user_organizations", sa.column("user_id", sa.Integer),
                           sa.column("organization_id", sa.Integer), sa.column("role", sa.String))
    organizations = sa.table("organizations", sa.column("id", sa.Integer),
                             sa.column("settings", sa.JSON))
    subscribed_ids: set[int] = set()
    for org_id, raw_settings in bind.execute(sa.select(organizations.c.id, organizations.c.settings)):
        settings = raw_settings
        if isinstance(settings, str):
            try:
                settings = json.loads(settings)
            except (TypeError, ValueError):
                settings = {}
        cfg = settings.get("weekly_digest") if isinstance(settings, dict) else None
        if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
            continue
        recipients = {str(email).strip().lower() for email in cfg.get("recipients", [])
                      if isinstance(email, str) and email.strip()}
        rows = bind.execute(sa.select(users.c.id, users.c.email, memberships.c.role)
            .select_from(users.join(memberships, memberships.c.user_id == users.c.id))
            .where(memberships.c.organization_id == org_id)).all()
        for user_id, email, role in rows:
            if (recipients and (email or "").strip().lower() in recipients) or (
                not recipients and role in ("admin", "manager")
            ):
                subscribed_ids.add(user_id)
    if subscribed_ids:
        bind.execute(users.update().where(users.c.id.in_(subscribed_ids)).values(email_weekly_digest=True))


def downgrade() -> None:
    # Do not turn off a user's explicit post-migration opt-in.
    pass
