"""Add nullable knowledge_version provenance to analysis_runs.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-11

STEP 12.3 — one provenance field on the analysis-run record:
``knowledge_version`` holds ``<catalog knowledge version>+<OI knowledge
version>`` (currently "1.1+1.0"), independent from ``engine_version``.
NULLABLE with no default and no backfill: legacy rows predate the contract
(NULL = unknown, explicitly). No existing column, constraint, or row is
touched; readers tolerate NULL.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("knowledge_version", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_runs", "knowledge_version")
