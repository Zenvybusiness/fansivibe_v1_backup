"""Add unique constraint for tryon_jobs idempotency key per user (Phase 5D).

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-23

Ensures strict database-level double-submit protection by converting the
non-unique index ix_tryon_jobs_user_idempotency into the unique constraint
uq_tryon_jobs_user_idempotency on (user_id, idempotency_key).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_tryon_jobs_user_idempotency", table_name="tryon_jobs")
    op.create_unique_constraint(
        "uq_tryon_jobs_user_idempotency",
        "tryon_jobs",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tryon_jobs_user_idempotency",
        "tryon_jobs",
        type_="unique",
    )
    op.create_index(
        "ix_tryon_jobs_user_idempotency",
        "tryon_jobs",
        ["user_id", "idempotency_key"],
    )

