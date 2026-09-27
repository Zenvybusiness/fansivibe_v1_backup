"""Add nullable idempotency_key and unique constraint to analysis_runs.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-27

C-10: Analysis Idempotency Implementation (Option B).
- Adds nullable Text column `idempotency_key` to `analysis_runs`.
- Adds UniqueConstraint("user_id", "idempotency_key", name="uq_analysis_runs_idempotency").
- Clean downgrade drops constraint then drops column.
- Existing rows with NULL idempotency_key remain valid.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("idempotency_key", sa.Text(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_analysis_runs_idempotency",
        "analysis_runs",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_analysis_runs_idempotency",
        "analysis_runs",
        type_="unique",
    )
    op.drop_column("analysis_runs", "idempotency_key")
