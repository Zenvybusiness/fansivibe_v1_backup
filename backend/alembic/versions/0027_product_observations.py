"""Discovery product observation history (D5).

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-10

Append-only observation history for FansiVibe Discovery: each successfully
normalized source listing is stored once with the metrics the pipeline
actually has, so Trend Intelligence can later reason over evidence rather
than only the latest product state. No trend detection or scoring is
implemented here.

Semantics:
- ``observed_at`` is when the collector observed the listing (collection
  time); ``source_timestamp`` is the source-supplied publication/update time
  and is NULL when the source does not provide one. They are distinct.
- Optional metrics (``price``/``currency``/``availability``) are NULL when
  unprovided — never zero — so missing values are not read as real data.
- ``raw_source_record_id`` is unique, so a re-processed raw record cannot
  duplicate its observation; the raw layer already dedups repeated payloads,
  so repeated identical collection runs add no false observations.
- Provenance is kept via ``collection_run_id`` + ``raw_source_record_id``
  (both SET NULL so history outlives operational cleanup). No raw records are
  deleted here; no image binaries are ever stored.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_observations",
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
            "collection_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collection_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "raw_source_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_source_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("availability", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "char_length(source_product_id) BETWEEN 1 AND 200",
            name="ck_product_observations_source_product_id_len",
        ),
        sa.CheckConstraint(
            "char_length(payload_hash) BETWEEN 1 AND 128",
            name="ck_product_observations_payload_hash_len",
        ),
        sa.CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_product_observations_price_nonnegative",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR char_length(currency) BETWEEN 1 AND 10",
            name="ck_product_observations_currency_len",
        ),
    )
    # One observation per raw record: reprocessing cannot duplicate it. A
    # unique index (not constraint) still permits many NULLs if a historical
    # raw record is removed (SET NULL), keeping the observation.
    op.create_index(
        "uq_product_observations_raw_source_record",
        "product_observations",
        ["raw_source_record_id"],
        unique=True,
    )
    # Time-window query paths for Trend Intelligence.
    op.create_index(
        "ix_product_observations_product_observed_at",
        "product_observations",
        ["product_id", "observed_at"],
    )
    op.create_index(
        "ix_product_observations_source_observed_at",
        "product_observations",
        ["source", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_observations_source_observed_at", table_name="product_observations")
    op.drop_index("ix_product_observations_product_observed_at", table_name="product_observations")
    op.drop_index("uq_product_observations_raw_source_record", table_name="product_observations")
    op.drop_table("product_observations")
