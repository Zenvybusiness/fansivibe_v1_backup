"""Media upload authorization and durable idempotency ledger (Stage 2 P0-4 / M16).

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-01

Additive migration establishing the durable upload authorization ledger:
- `media_upload_authorizations`: Stores durable per-user upload authorizations,
  canonical request fingerprints, and staging keys for 24 hours.
- Atomic distributed rate limiting: Supports sliding 60-second window queries
  via composite index on `(user_id, created_at)`.
- Idempotency & Conflict Detection: Composite primary key on `(user_id, idempotency_key)`
  guarantees per-user uniqueness and enables cross-worker RFC 9440 HTTP 409 conflict detection.
- OW-1 Ownership Scoping: `user_id` references `users(id)` ON DELETE CASCADE ensuring
  clean GDPR account deletion cascades with zero orphaned rows.
- Expiration & Pruning: Dedicated index on `(expires_at)` supports efficient bounded
  retention sweeps.
- Zero mutation of existing tables: 100% additive; does not alter wardrobe_items,
  users, looks, or discovery tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_upload_authorizations",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_media_upload_authorizations_user_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("upload_id", UUID(as_uuid=True), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("staging_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "user_id", "idempotency_key", name="pk_media_upload_authorizations"
        ),
        sa.UniqueConstraint(
            "upload_id", name="uq_media_upload_authorizations_upload_id"
        ),
    )

    op.create_index(
        "ix_media_upload_authorizations_user_rate",
        "media_upload_authorizations",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_media_upload_authorizations_expires_at",
        "media_upload_authorizations",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_upload_authorizations_expires_at",
        table_name="media_upload_authorizations",
    )
    op.drop_index(
        "ix_media_upload_authorizations_user_rate",
        table_name="media_upload_authorizations",
    )
    op.drop_table("media_upload_authorizations")
