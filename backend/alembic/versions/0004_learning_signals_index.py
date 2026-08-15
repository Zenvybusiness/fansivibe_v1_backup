"""Add composite index on learning_signals for signal history queries.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-15
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_learning_signals_user_id_signal_type_occurred_at",
        "learning_signals",
        ["user_id", "signal_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_signals_user_id_signal_type_occurred_at",
        table_name="learning_signals",
    )