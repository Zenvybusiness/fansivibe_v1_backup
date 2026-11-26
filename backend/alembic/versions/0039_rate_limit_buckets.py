"""Add rate_limit_buckets table for multi-worker / multi-instance rate limiting.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-26

Provides atomic PostgreSQL-backed sliding/windowed rate limiting across
multiple Uvicorn workers and backend replicas without requiring Redis.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("bucket_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key", name="pk_rate_limit_buckets"),
    )
    op.create_index(
        "ix_rate_limit_buckets_window_start",
        "rate_limit_buckets",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_buckets_window_start", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")

