"""Create wardrobe_items table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wardrobe_items",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Text(), sa.ForeignKey("wardrobe_categories.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("color_id", sa.Text(), sa.ForeignKey("colors.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("material_id", sa.Text(), sa.ForeignKey("materials.code", ondelete="RESTRICT"), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("image_ref", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_wardrobe_items_user_id", "wardrobe_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_wardrobe_items_user_id", table_name="wardrobe_items")
    op.drop_table("wardrobe_items")