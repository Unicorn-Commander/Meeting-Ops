"""Merge point: combined meetings (dogfood chain) + summarization lease (main chain).

Two branches diverged from 059_integration_pat_scope:
  main:     059 -> 060_meeting_identity -> 061_summarization_lease
  dogfood:  059 -> 060_combined_meetings
This empty revision joins them so `alembic upgrade head` has one head again.
Dogfood (at 060_combined_meetings) applies 060_meeting_identity + 061 then this;
prod (at 061_summarization_lease) applies 060_combined_meetings then this.

Revision ID: 062_merge_combined_and_lease
Revises: 061_summarization_lease, 060_combined_meetings
Create Date: 2026-09-07
"""
from typing import Sequence, Union

revision: str = "062_merge_combined_and_lease"
down_revision: Union[str, Sequence[str], None] = ("061_summarization_lease", "060_combined_meetings")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
