"""Seed garment run type into run_types reference table (M11).

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO run_types (code, label, sort_order) "
        "VALUES ('garment', 'Garment analysis', 3) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM run_types WHERE code = 'garment'"
    )
