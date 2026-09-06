"""P0 Wardrobe reference vocabulary tables.

Creates wardrobe_categories, colors, and materials reference tables
as defined in TABLE_DEFINITIONS.md §6.1 and DOMAIN_TABLE_MAPPING.md §3.3.

These are backend-owned, versioned content (K9.1) referenced by
wardrobe_items.category_id, color_id, material_id with FK RESTRICT.

Also see: DATABASE_DESIGN_RULES.md PR-3, PR-4, K9.1;
DATABASE_DESIGN_RULES.md §6.1 P0 reference tables.
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TEXT

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


# Canonical vocabulary values from the existing Wardrobe documentation/config.
# Conflict inspection (Step 3C): wardrobe_categories has conflicting counts
# across sources — WardrobeMockData.dart lists 6 (including 'all' UI grouping),
# AddItemConfig lists 4, and the actual wardrobe_items use 5 real categories
# (tops, bottoms, outerwear, footwear, accessories). This migration uses the 5
# codes that wardrobe_items actually reference: tops, bottoms, outerwear,
# footwear, accessories. The 'all' code is a UI construct, not an item category.
# Colors: 18 from AddItemConfig (consistent across docs).
# Textures/Materials: 16 from AddItemConfig (consistent across docs).

WARDROBE_CATEGORIES = [
    ("tops", "Tops"),
    ("bottoms", "Bottoms"),
    ("outerwear", "Outerwear"),
    ("footwear", "Footwear"),
    ("accessories", "Accessories"),
]

COLORS = [
    ("black", "Black"),
    ("white", "White"),
    ("navy", "Navy"),
    ("charcoal", "Charcoal"),
    ("grey", "Grey"),
    ("beige", "Beige"),
    ("burgundy", "Burgundy"),
    ("olive", "Olive"),
    ("khaki", "Khaki"),
    ("cream", "Cream"),
    ("light_blue", "Light Blue"),
    ("blush", "Blush"),
    ("tan", "Tan"),
    ("silver", "Silver"),
    ("gold", "Gold"),
    ("indigo", "Indigo"),
    ("stone", "Stone"),
]

MATERIALS = [
    ("cotton", "Cotton"),
    ("linen", "Linen"),
    ("wool", "Wool"),
    ("cashmere", "Cashmere"),
    ("silk", "Silk"),
    ("denim", "Denim"),
    ("leather", "Leather"),
    ("suede", "Suede"),
    ("canvas", "Canvas"),
    ("polyester", "Polyester"),
    ("velvet", "Velvet"),
    ("knit", "Knit"),
    ("jersey", "Jersey"),
    ("tweed", "Tweed"),
    ("corduroy", "Corduroy"),
    ("fleece", "Fleece"),
]


def _insert_categories() -> None:
    for code, label in WARDROBE_CATEGORIES:
        op.execute(
            f"INSERT INTO wardrobe_categories (code, label, sort_order, active) "
            f"VALUES ({code!r}, {label!r}, 0, true)"
        )


def _insert_colors() -> None:
    for code, label in COLORS:
        op.execute(
            f"INSERT INTO colors (code, label, sort_order, active) "
            f"VALUES ({code!r}, {label!r}, 0, true)"
        )


def _insert_materials() -> None:
    for code, label in MATERIALS:
        op.execute(
            f"INSERT INTO materials (code, label, sort_order, active) "
            f"VALUES ({code!r}, {label!r}, 0, true)"
        )


def upgrade() -> None:
    op.create_table(
        "wardrobe_categories",
        sa.Column("code", TEXT(), primary_key=True),
        sa.Column("label", TEXT(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    _insert_categories()

    op.create_table(
        "colors",
        sa.Column("code", TEXT(), primary_key=True),
        sa.Column("label", TEXT(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    _insert_colors()

    op.create_table(
        "materials",
        sa.Column("code", TEXT(), primary_key=True),
        sa.Column("label", TEXT(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    _insert_materials()


def downgrade() -> None:
    op.drop_table("materials")
    op.drop_table("colors")
    op.drop_table("wardrobe_categories")