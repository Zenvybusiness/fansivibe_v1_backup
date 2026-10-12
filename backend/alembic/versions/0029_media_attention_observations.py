"""Media-attention observation and provenance history (D9B).

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-13

Append-only, concept-level media-attention observation evidence and article
provenance join table for FansiVibe Discovery. Separate from
``product_observations`` and ``search_interest_observations``: a media-attention
observation is derived from clustered, deduplicated media articles and represents
an editorial press signal, never consumer demand or search index.

Semantics:
- ``value`` represents the estimated deduplicated story count and is present
  only when ``value_status = 'present'`` and ``completeness_status = 'complete'``.
  Missing, suppressed, or invalid stay NULL (never 0).
- Exactly 4 approved status pairs:
  ('present', 'complete'), ('suppressed', 'truncated'),
  ('missing', 'unavailable'), ('invalid', 'unavailable').
- Count hierarchy:
  - zero: raw_article_count = 0 => outlets = 0, stories = 0, value = 0.0.
  - positive: raw_article_count >= 1 => 1 <= outlets <= raw, 1 <= stories <= raw, value == float(stories) >= 1.0.
- Rejection of NaN, Infinity, -Infinity via PostgreSQL CHECK constraints.
- Natural key includes ``query_config_version`` and ``clustering_version`` to guarantee
  coexistence across query definitions and clustering algorithms.
- Provenance join table ``media_attention_contributing_records`` cascades on deletion of
  raw records (180-day retention pruning) while preserving the parent observation intact.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_attention_observations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "collection_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collection_runs.id", ondelete="SET NULL"),
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
        sa.Column("completeness_status", sa.Text(), nullable=False),
        sa.Column("raw_article_count", sa.Integer(), nullable=True),
        sa.Column("distinct_outlet_count", sa.Integer(), nullable=True),
        sa.Column("estimated_deduplicated_story_count", sa.Integer(), nullable=True),
        sa.Column("query_config_version", sa.Text(), nullable=False),
        sa.Column("clustering_version", sa.Text(), nullable=False),
        sa.Column("contributing_raw_record_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("provenance_pruned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_relative", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "metric = 'media_attention'",
            name="ck_media_attention_observations_metric",
        ),
        sa.CheckConstraint(
            "query_kind IN ('concept', 'search_term', 'topic')",
            name="ck_media_attention_observations_query_kind",
        ),
        sa.CheckConstraint(
            "geo_scope_type IN ('country', 'region', 'worldwide')",
            name="ck_media_attention_observations_geo_type",
        ),
        sa.CheckConstraint(
            "aggregation_interval IN ('daily', 'weekly', 'monthly', 'rolling_7d')",
            name="ck_media_attention_observations_interval",
        ),
        sa.CheckConstraint(
            "value_status IS NOT NULL AND completeness_status IS NOT NULL AND ("
            "  (value_status = 'present' AND completeness_status = 'complete') OR "
            "  (value_status = 'suppressed' AND completeness_status = 'truncated') OR "
            "  (value_status = 'missing' AND completeness_status = 'unavailable') OR "
            "  (value_status = 'invalid' AND completeness_status = 'unavailable')"
            ")",
            name="ck_media_attention_observations_status_matrix",
        ),
        sa.CheckConstraint(
            "CASE "
            "  WHEN value_status = 'present' THEN ("
            "    value IS NOT NULL "
            "    AND value <> 'NaN'::numeric "
            "    AND value <> 'Infinity'::numeric "
            "    AND value <> '-Infinity'::numeric "
            "    AND raw_article_count IS NOT NULL "
            "    AND distinct_outlet_count IS NOT NULL "
            "    AND estimated_deduplicated_story_count IS NOT NULL "
            "    AND value = estimated_deduplicated_story_count "
            "    AND ("
            "      (raw_article_count = 0 "
            "       AND distinct_outlet_count = 0 "
            "       AND estimated_deduplicated_story_count = 0 "
            "       AND value = 0.0) "
            "      OR "
            "      (raw_article_count >= 1 "
            "       AND distinct_outlet_count >= 1 "
            "       AND distinct_outlet_count <= raw_article_count "
            "       AND estimated_deduplicated_story_count >= 1 "
            "       AND estimated_deduplicated_story_count <= raw_article_count "
            "       AND value >= 1.0) "
            "    )"
            "  ) "
            "  WHEN value_status IN ('suppressed', 'missing', 'invalid') THEN ("
            "    value IS NULL "
            "    AND raw_article_count IS NULL "
            "    AND distinct_outlet_count IS NULL "
            "    AND estimated_deduplicated_story_count IS NULL"
            "  ) "
            "  ELSE FALSE "
            "END",
            name="ck_media_attention_observations_value_counts_integrity",
        ),
        sa.CheckConstraint(
            "period_end > period_start",
            name="ck_media_attention_observations_period_order",
        ),
        sa.CheckConstraint(
            "char_length(query_key) BETWEEN 1 AND 200",
            name="ck_media_attention_observations_query_key_len",
        ),
        sa.CheckConstraint(
            "char_length(query_display) BETWEEN 1 AND 300",
            name="ck_media_attention_observations_query_display_len",
        ),
        sa.CheckConstraint(
            "char_length(value_scale) BETWEEN 1 AND 120",
            name="ck_media_attention_observations_value_scale_len",
        ),
        sa.CheckConstraint(
            "char_length(query_config_version) BETWEEN 1 AND 60",
            name="ck_media_attention_observations_query_config_ver_len",
        ),
        sa.CheckConstraint(
            "char_length(clustering_version) BETWEEN 1 AND 60",
            name="ck_media_attention_observations_clustering_ver_len",
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
            "query_config_version",
            "clustering_version",
            name="uq_media_attention_observations_natural_key",
        ),
    )
    op.create_index(
        "ix_media_attention_observations_query_geo_period",
        "media_attention_observations",
        ["query_key", "geo_scope", "period_start"],
    )
    op.create_index(
        "ix_media_attention_observations_source_observed_at",
        "media_attention_observations",
        ["source", "observed_at"],
    )
    op.create_index(
        "ix_media_attention_observations_run_id",
        "media_attention_observations",
        ["collection_run_id"],
    )

    op.create_table(
        "media_attention_contributing_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("media_attention_observations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_source_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_source_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity_cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("outlet_domain", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "observation_id",
            "raw_source_record_id",
            name="uq_media_attention_contrib_obs_raw",
        ),
        sa.CheckConstraint(
            "char_length(outlet_domain) BETWEEN 1 AND 255",
            name="ck_media_attention_contrib_outlet_domain_len",
        ),
    )
    op.create_index(
        "ix_media_attention_contrib_raw_id",
        "media_attention_contributing_records",
        ["raw_source_record_id"],
    )
    op.create_index(
        "ix_media_attention_contrib_cluster_id",
        "media_attention_contributing_records",
        ["similarity_cluster_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_attention_contrib_cluster_id",
        table_name="media_attention_contributing_records",
    )
    op.drop_index(
        "ix_media_attention_contrib_raw_id",
        table_name="media_attention_contributing_records",
    )
    op.drop_table("media_attention_contributing_records")

    op.drop_index(
        "ix_media_attention_observations_run_id",
        table_name="media_attention_observations",
    )
    op.drop_index(
        "ix_media_attention_observations_source_observed_at",
        table_name="media_attention_observations",
    )
    op.drop_index(
        "ix_media_attention_observations_query_geo_period",
        table_name="media_attention_observations",
    )
    op.drop_table("media_attention_observations")
