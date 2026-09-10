"""Add outfit_selected signal type to signal_types seed.

Revision ID: 0008
Revises: 0006
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO signal_types (code, label, sort_order) "
        "VALUES ('outfit_selected', 'Outfit selected', 2) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM signal_types WHERE code = 'outfit_selected'"
    )