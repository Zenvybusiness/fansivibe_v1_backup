"""Media upload completion lifecycle and canonical metadata (Stage 2 P0-4 Phase 3).

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-01

Additive migration adding media completion lifecycle state and canonical publication metadata:
- `status`: Lifecycle state ('authorized', 'processing', 'published', 'failed', 'expired').
- `canonical_key`: User-scoped canonical R2 object key.
- `canonical_sha256`: Authoritative SHA-256 hex digest of the canonical WebP bytes.
- `canonical_size_bytes`: Verified size in bytes of the canonical WebP object.
- `canonical_width`: Verified width of canonical WebP in pixels.
- `canonical_height`: Verified height of canonical WebP in pixels.
- `completed_at`: Timezone-aware timestamp of publication completion.
- `failure_reason`: Safe classification code on non-retryable failure.
- `processing_attempts`: Counter for completion processing attempts.
- Index `ix_media_upload_authorizations_status` for efficient lifecycle filtering and retry sweeps.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_upload_authorizations",
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="authorized",
        ),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("canonical_key", sa.String(512), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("canonical_sha256", sa.String(64), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("canonical_size_bytes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("canonical_width", sa.Integer(), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("canonical_height", sa.Integer(), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column("failure_reason", sa.String(64), nullable=True),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column(
            "processing_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_index(
        "ix_media_upload_authorizations_status",
        "media_upload_authorizations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_upload_authorizations_status",
        table_name="media_upload_authorizations",
    )
    op.drop_column("media_upload_authorizations", "processing_attempts")
    op.drop_column("media_upload_authorizations", "failure_reason")
    op.drop_column("media_upload_authorizations", "completed_at")
    op.drop_column("media_upload_authorizations", "canonical_height")
    op.drop_column("media_upload_authorizations", "canonical_width")
    op.drop_column("media_upload_authorizations", "canonical_size_bytes")
    op.drop_column("media_upload_authorizations", "canonical_sha256")
    op.drop_column("media_upload_authorizations", "canonical_key")
    op.drop_column("media_upload_authorizations", "status")
