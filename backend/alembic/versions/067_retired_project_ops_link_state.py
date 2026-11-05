"""Allow local tombstones for retired Project-Ops proposals.

Revision ID: 067_retired_project_ops_link_state
Revises: 066_backfill_always_on_titles_timezone
Create Date: 2026-11-05
"""

from alembic import op


revision = "067_retired_project_ops_link_state"
down_revision = "066_backfill_always_on_titles_timezone"
branch_labels = None
depends_on = None


_STATES = (
    "local_only",
    "proposed",
    "approved_linked",
    "rejected",
    "sync_failed",
    "retired",
)
_PREVIOUS_STATES = _STATES[:-1]


def _constraint_sql(states: tuple[str, ...]) -> str:
    return "project_ops_link_state IN (" + ", ".join(
        f"'{state}'" for state in states
    ) + ")"


def upgrade() -> None:
    op.drop_constraint(
        "ck_action_items_project_ops_link_state",
        "action_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_items_project_ops_link_state",
        "action_items",
        _constraint_sql(_STATES),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_action_items_project_ops_link_state",
        "action_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_items_project_ops_link_state",
        "action_items",
        _constraint_sql(_PREVIOUS_STATES),
    )
