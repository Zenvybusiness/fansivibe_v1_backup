"""Discovery data foundation — collection runs, raw source records,
canonical products and their source-identity mapping (D2).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-10

Minimum storage foundation for authorized-source data ingestion. No real
external collection, trend detection, ranking or recommendation is
implemented here.

Provenance rules:
- ``raw_source_records`` preserve the verbatim provider payload (JSONB)
  plus a deterministic payload hash. Normalized values never overwrite
  the raw row.
- ``products`` hold normalized canonical values only.
- ``product_source_map`` links a canonical product to each source
  identity and (optionally) the raw record it was derived from, so one
  product may be backed by several sources without duplicate storage.

No image binaries are stored — only provider CDN URLs inside JSONB.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_collection_runs_status",
        ),
        sa.CheckConstraint(
            "fetched_count >= 0 AND inserted_count >= 0 AND updated_count >= 0 "
            "AND skipped_count >= 0 AND failed_count >= 0",
            name="ck_collection_runs_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_collection_runs_finished_after_start",
        ),
        sa.CheckConstraint(
            "error_summary IS NULL OR char_length(error_summary) <= 2000",
            name="ck_collection_runs_error_summary_len",
        ),
    )
    op.create_index(
        "ix_collection_runs_source_started_at",
        "collection_runs",
        ["source", "started_at"],
    )

    op.create_table(
        "raw_source_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "collection_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collection_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processing_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processed', 'failed', 'skipped')",
            name="ck_raw_source_records_status",
        ),
        sa.CheckConstraint(
            "char_length(payload_hash) BETWEEN 1 AND 128",
            name="ck_raw_source_records_payload_hash_len",
        ),
        sa.CheckConstraint(
            "processing_error IS NULL OR char_length(processing_error) <= 2000",
            name="ck_raw_source_records_processing_error_len",
        ),
        sa.UniqueConstraint(
            "source",
            "payload_hash",
            name="uq_raw_source_records_source_payload_hash",
        ),
    )
    op.create_index(
        "ix_raw_source_records_collection_run_id",
        "raw_source_records",
        ["collection_run_id"],
    )
    op.create_index(
        "ix_raw_source_records_source_record_id",
        "raw_source_records",
        ["source", "source_record_id"],
    )
    op.create_index(
        "ix_raw_source_records_processing_status",
        "raw_source_records",
        ["processing_status"],
    )

    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("attributes", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("availability", sa.Boolean(), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("image_urls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 300", name="ck_products_title_len"),
        sa.CheckConstraint(
            "brand IS NULL OR char_length(brand) BETWEEN 1 AND 150",
            name="ck_products_brand_len",
        ),
        sa.CheckConstraint(
            "category IS NULL OR char_length(category) BETWEEN 1 AND 100",
            name="ck_products_category_len",
        ),
        sa.CheckConstraint(
            "subcategory IS NULL OR char_length(subcategory) BETWEEN 1 AND 100",
            name="ck_products_subcategory_len",
        ),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_products_price_nonnegative"),
        sa.CheckConstraint(
            "currency IS NULL OR char_length(currency) BETWEEN 1 AND 10",
            name="ck_products_currency_len",
        ),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_brand", "products", ["brand"])

    op.create_table(
        "product_source_map",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_product_id", sa.Text(), nullable=False),
        sa.Column(
            "raw_source_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_source_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "char_length(source_product_id) BETWEEN 1 AND 200",
            name="ck_product_source_map_source_product_id_len",
        ),
        sa.UniqueConstraint(
            "source",
            "source_product_id",
            name="uq_product_source_map_source_product",
        ),
    )
    op.create_index(
        "ix_product_source_map_product_id",
        "product_source_map",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_source_map_product_id", table_name="product_source_map")
    op.drop_table("product_source_map")
    op.drop_index("ix_products_brand", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_raw_source_records_processing_status", table_name="raw_source_records")
    op.drop_index("ix_raw_source_records_source_record_id", table_name="raw_source_records")
    op.drop_index("ix_raw_source_records_collection_run_id", table_name="raw_source_records")
    op.drop_table("raw_source_records")
    op.drop_index("ix_collection_runs_source_started_at", table_name="collection_runs")
    op.drop_table("collection_runs")
