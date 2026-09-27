"""Seed the item_added signal type.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-27

Seeds the one `signal_types` row required by C-07 (Option A): wardrobe
item creation emits `item_added` via the existing learning-signal writer.
Without this row the `learning_signals.signal_type` FK (`RESTRICT`)
rejects the write. Follows the 0008 (`outfit_selected`) and 0015
(assistant cards) precedents verbatim. No existing rows affected.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO signal_types (code, label, sort_order) "
        "VALUES ('item_added', 'Wardrobe item added', 5) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM signal_types WHERE code = 'item_added'"
    )
