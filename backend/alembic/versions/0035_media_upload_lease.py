"""Media upload durable processing lease and crash recovery timestamps (Stage 2 P0-4 Phase 3.1).

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-01

Additive migration adding durable processing lease tracking to `media_upload_authorizations`:
- `processing_started_at`: Timezone-aware timestamp when active processing began.
- `processing_lease_expires_at`: Timezone-aware timestamp when processing lease expires.
- Index `ix_media_upload_authorizations_lease` on `(status, processing_lease_expires_at)`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_upload_authorizations",
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "media_upload_authorizations",
        sa.Column(
            "processing_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_media_upload_authorizations_lease",
        "media_upload_authorizations",
        ["status", "processing_lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_upload_authorizations_lease",
        table_name="media_upload_authorizations",
    )
    op.drop_column("media_upload_authorizations", "processing_lease_expires_at")
    op.drop_column("media_upload_authorizations", "processing_started_at")
