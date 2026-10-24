"""Multi-retailer product offers and price history foundation (DISCOVERY-10B-2).

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-15

Separates canonical product identity from merchant commerce.
Establishes:
- ``retailers``: verified merchant registry with affiliate configuration.
- ``product_variants``: optional variant layer (size/color/SKU/GTIN) under canonical products.
- ``retailer_offers``: independent merchant listings pointing to a canonical product,
  preserving retailer-specific price, availability, and direct URLs without cross-retailer
  overwrites.
- ``offer_price_history``: append-only price tracking and freshness ledger.

Invariants:
- Never overwrite retailer A's commercial offer with retailer B's data.
- Canonical ``products`` table remains the stable entity registry.
- Unique constraint on ``(retailer_id, source_product_id)`` guarantees idempotent ingestion.
- Synthetic fixtures have NO retailer offers.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Retailers Table
    op.create_table(
        "retailers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("affiliate_network", sa.Text(), nullable=True),
        sa.Column("affiliate_url_template", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_retailers_slug"),
        sa.CheckConstraint(
            "char_length(slug) BETWEEN 1 AND 100",
            name="ck_retailers_slug_len",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200",
            name="ck_retailers_name_len",
        ),
        sa.CheckConstraint(
            "char_length(domain) BETWEEN 1 AND 200",
            name="ck_retailers_domain_len",
        ),
    )

    # 2. Product Variants Table
    op.create_table(
        "product_variants",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("gtin", sa.Text(), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column(
            "attributes",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "sku IS NULL OR char_length(sku) BETWEEN 1 AND 100",
            name="ck_product_variants_sku_len",
        ),
        sa.CheckConstraint(
            "gtin IS NULL OR char_length(gtin) BETWEEN 8 AND 14",
            name="ck_product_variants_gtin_len",
        ),
        sa.CheckConstraint(
            "size IS NULL OR char_length(size) BETWEEN 1 AND 50",
            name="ck_product_variants_size_len",
        ),
        sa.CheckConstraint(
            "color IS NULL OR char_length(color) BETWEEN 1 AND 50",
            name="ck_product_variants_color_len",
        ),
    )
    op.create_index(
        "ix_product_variants_product_id",
        "product_variants",
        ["product_id"],
    )
    op.create_index(
        "ix_product_variants_gtin",
        "product_variants",
        ["gtin"],
        postgresql_where=sa.text("gtin IS NOT NULL"),
    )

    # 3. Retailer Offers Table
    op.create_table(
        "retailer_offers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retailer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("retailers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_product_id", sa.Text(), nullable=False),
        sa.Column(
            "raw_source_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_source_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("affiliate_url", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("original_price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "currency",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'INR'"),
        ),
        sa.Column(
            "availability",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "in_stock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "retailer_id",
            "source_product_id",
            name="uq_retailer_offers_retailer_source_product",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_retailer_offers_price_nonnegative",
        ),
        sa.CheckConstraint(
            "original_price IS NULL OR original_price >= 0",
            name="ck_retailer_offers_original_price_nonnegative",
        ),
        sa.CheckConstraint(
            "char_length(currency) BETWEEN 1 AND 10",
            name="ck_retailer_offers_currency_len",
        ),
        sa.CheckConstraint(
            "char_length(source_product_id) BETWEEN 1 AND 200",
            name="ck_retailer_offers_source_product_id_len",
        ),
        sa.CheckConstraint(
            "product_url IS NULL OR char_length(product_url) BETWEEN 1 AND 2048",
            name="ck_retailer_offers_product_url_len",
        ),
    )
    op.create_index(
        "ix_retailer_offers_product_id",
        "retailer_offers",
        ["product_id"],
    )
    op.create_index(
        "ix_retailer_offers_retailer_id",
        "retailer_offers",
        ["retailer_id"],
    )
    op.create_index(
        "ix_retailer_offers_last_checked_at",
        "retailer_offers",
        ["last_checked_at"],
    )

    # 4. Offer Price History Table
    op.create_table(
        "offer_price_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "offer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("retailer_offers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "currency",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'INR'"),
        ),
        sa.Column(
            "availability",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "raw_source_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_source_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_offer_price_history_price_nonnegative",
        ),
        sa.CheckConstraint(
            "char_length(currency) BETWEEN 1 AND 10",
            name="ck_offer_price_history_currency_len",
        ),
    )
    op.create_index(
        "ix_offer_price_history_offer_observed",
        "offer_price_history",
        ["offer_id", sa.text("observed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_offer_price_history_offer_observed", table_name="offer_price_history")
    op.drop_table("offer_price_history")
    op.drop_index("ix_retailer_offers_last_checked_at", table_name="retailer_offers")
    op.drop_index("ix_retailer_offers_retailer_id", table_name="retailer_offers")
    op.drop_index("ix_retailer_offers_product_id", table_name="retailer_offers")
    op.drop_table("retailer_offers")
    op.drop_index("ix_product_variants_gtin", table_name="product_variants")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_table("retailers")
