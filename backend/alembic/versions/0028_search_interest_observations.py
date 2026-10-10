"""Search-interest observation history (D9B).

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-10

Append-only, concept-level search-interest evidence for FansiVibe Discovery.
Separate from ``product_observations`` on purpose: a search-interest observation
has no product, price or availability and must never be forced into the product
path. No trend detection, scoring, publication or provider integration is
implemented here.

Semantics:
- ``value`` is a provider-reported **relative** search-interest value and is
  present only when ``value_status = 'present'``; missing / suppressed / invalid
  stay NULL (never 0). ``is_relative`` is always true.
- ``period_start``/``period_end`` bound the observation period (timezone-aware);
  ``source_timestamp`` is provider time, ``observed_at`` is collection time
  (default ``now()``) — distinct, NULL when the provider supplies none.
- ``raw_source_record_id`` is unique and the natural key below is unique, so
  repeated collection never duplicates or inflates a series.
- ``synthetic`` marks fixture/test evidence — never real provider data.
- Provenance (``collection_run_id`` + ``raw_source_record_id``) uses SET NULL so
  history outlives operational cleanup. No raw records are deleted here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_interest_observations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
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
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("query_kind", sa.Text(), nullable=False),
        sa.Column("query_key", sa.Text(), nullable=False),
        sa.Column("query_display", sa.Text(), nullable=False),
        sa.Column("geo_scope", sa.Text(), nullable=False),
        sa.Column("geo_scope_type", sa.Text(), nullable=False),
        sa.Column("aggregation_interval", sa.Text(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=True),
        sa.Column("value_scale", sa.Text(), nullable=False),
        sa.Column("value_status", sa.Text(), nullable=False),
        sa.Column("is_relative", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("query_config_version", sa.Text(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "metric = 'search_interest'",
            name="ck_search_interest_observations_metric",
        ),
        sa.CheckConstraint(
            "query_kind IN ('search_term', 'topic')",
            name="ck_search_interest_observations_query_kind",
        ),
        sa.CheckConstraint(
            "geo_scope_type IN ('country', 'region', 'worldwide')",
            name="ck_search_interest_observations_geo_type",
        ),
        sa.CheckConstraint(
            "aggregation_interval IN ('daily', 'weekly', 'monthly', 'yearly')",
            name="ck_search_interest_observations_interval",
        ),
        sa.CheckConstraint(
            "value_status IN ('present', 'missing', 'suppressed', 'invalid')",
            name="ck_search_interest_observations_value_status",
        ),
        sa.CheckConstraint(
            "(value_status = 'present' AND value IS NOT NULL) "
            "OR (value_status <> 'present' AND value IS NULL)",
            name="ck_search_interest_observations_value_consistency",
        ),
        sa.CheckConstraint(
            "period_end > period_start",
            name="ck_search_interest_observations_period_order",
        ),
        sa.CheckConstraint(
            "is_relative",
            name="ck_search_interest_observations_is_relative",
        ),
        sa.CheckConstraint(
            "char_length(query_key) BETWEEN 1 AND 200",
            name="ck_search_interest_observations_query_key_len",
        ),
        sa.CheckConstraint(
            "char_length(query_display) BETWEEN 1 AND 300",
            name="ck_search_interest_observations_query_display_len",
        ),
        sa.CheckConstraint(
            "char_length(value_scale) BETWEEN 1 AND 120",
            name="ck_search_interest_observations_value_scale_len",
        ),
        sa.CheckConstraint(
            "char_length(payload_hash) BETWEEN 1 AND 128",
            name="ck_search_interest_observations_payload_hash_len",
        ),
        sa.UniqueConstraint(
            "source",
            "metric",
            "query_kind",
            "query_key",
            "geo_scope",
            "aggregation_interval",
            "period_start",
            "period_end",
            name="uq_search_interest_observations_natural_key",
        ),
    )
    op.create_index(
        "uq_search_interest_observations_raw_source_record",
        "search_interest_observations",
        ["raw_source_record_id"],
        unique=True,
    )
    op.create_index(
        "ix_search_interest_observations_query_geo_period",
        "search_interest_observations",
        ["query_key", "geo_scope", "period_start"],
    )
    op.create_index(
        "ix_search_interest_observations_source_observed_at",
        "search_interest_observations",
        ["source", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_search_interest_observations_source_observed_at",
        table_name="search_interest_observations",
    )
    op.drop_index(
        "ix_search_interest_observations_query_geo_period",
        table_name="search_interest_observations",
    )
    op.drop_index(
        "uq_search_interest_observations_raw_source_record",
        table_name="search_interest_observations",
    )
    op.drop_table("search_interest_observations")
