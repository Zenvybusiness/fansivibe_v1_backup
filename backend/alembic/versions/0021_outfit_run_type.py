"""Seed outfit run type into run_types reference table.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO run_types (code, label, sort_order) "
        "VALUES ('outfit', 'Outfit analysis', 2) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM run_types WHERE code = 'outfit'"
    )
