"""Durable Virtual Try-On jobs table and indices (Phase 5C).

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-23

Durable tryon_jobs table for tracking VTON requests:
- Job ID (UUID primary key)
- Authenticated user ID (foreign key to users.id)
- Person image reference (JSONB)
- Selected wardrobe garment ID (foreign key to wardrobe_items.id)
- Garment IDs (JSONB)
- Outfit source (text)
- Provider identifier (string)
- Job status: queued, processing, completed, failed, cancelled
- Creation, update, start, completion timestamps
- Result media reference (JSONB)
- Safe error code and failure message
- Retry tracking (retry_count, retry_of_job_id)
- Consent version and confirmation timestamp
- Idempotency key and request fingerprint
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tryon_jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_tryon_jobs_user_id"),
            nullable=False,
        ),
        sa.Column("outfit_source", sa.Text(), nullable=False, server_default="wardrobe"),
        sa.Column(
            "garment_id",
            sa.Uuid(),
            sa.ForeignKey("wardrobe_items.id", ondelete="SET NULL", name="fk_tryon_jobs_garment_id"),
            nullable=True,
        ),
        sa.Column("garment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False, server_default="mock"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("person_media_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_media_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("consent_version", sa.String(64), nullable=False),
        sa.Column(
            "consent_accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "retry_of_job_id",
            sa.Uuid(),
            sa.ForeignKey("tryon_jobs.id", ondelete="SET NULL", name="fk_tryon_jobs_retry_of_job_id"),
            nullable=True,
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_tryon_jobs_user_created",
        "tryon_jobs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_tryon_jobs_status",
        "tryon_jobs",
        ["status"],
    )
    op.create_index(
        "ix_tryon_jobs_user_idempotency",
        "tryon_jobs",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_tryon_jobs_user_idempotency", table_name="tryon_jobs")
    op.drop_index("ix_tryon_jobs_status", table_name="tryon_jobs")
    op.drop_index("ix_tryon_jobs_user_created", table_name="tryon_jobs")
    op.drop_table("tryon_jobs")

