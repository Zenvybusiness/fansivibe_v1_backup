"""Add nullable fit evidence columns to wardrobe_items (C-02-F Option B).

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-27

Stores vision-observed garment fit (`fit`, free-form observed string or NULL
when absent) and its analyzer confidence (`fit_confidence`, 0-1 float or NULL
when unavailable) as first-class nullable attributes on the existing
`wardrobe_items` row. Purely additive: existing rows read NULL (missing
evidence = neutral at scoring, never backfilled, never inferred). No CHECK
constraint — bounds are enforced at the API schema (0-1) and the scoring
gate (>= 0.6); historical NULLs must never fail.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wardrobe_items", sa.Column("fit", sa.Text(), nullable=True))
    op.add_column(
        "wardrobe_items", sa.Column("fit_confidence", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("wardrobe_items", "fit_confidence")
    op.drop_column("wardrobe_items", "fit")
