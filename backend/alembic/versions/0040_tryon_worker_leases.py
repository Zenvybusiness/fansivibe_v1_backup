"""Add worker ownership, fencing lease token, and lease expiration to tryon_jobs.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-27

Enables worker-safe multi-process / multi-instance startup and stale-job
recovery without external queues:
- worker_id: unique process identity owning an active/queued job
- lease_token: UUID fencing token preventing late writes from superseded workers
- lease_expires_at: bounded DB-clock lease expiration for dead-worker recovery
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tryon_jobs",
        sa.Column("worker_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "tryon_jobs",
        sa.Column("lease_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "tryon_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_tryon_jobs_status_lease_expires",
        "tryon_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tryon_jobs_status_lease_expires", table_name="tryon_jobs")
    op.drop_column("tryon_jobs", "lease_expires_at")
    op.drop_column("tryon_jobs", "lease_token")
    op.drop_column("tryon_jobs", "worker_id")

