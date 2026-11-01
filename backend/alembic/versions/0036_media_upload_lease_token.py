"""Media upload processing lease token and fencing (Stage 2 P0-4 Phase 3.2).

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-01

Additive migration adding fencing lease token tracking to `media_upload_authorizations`:
- `processing_lease_token`: Unique UUID generated for each successful lease claim.
  Enforces fencing-token concurrency semantics: state transitions (renewal,
  release, publication, failure) require matching ownership token.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_upload_authorizations",
        sa.Column(
            "processing_lease_token",
            sa.Uuid(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("media_upload_authorizations", "processing_lease_token")
