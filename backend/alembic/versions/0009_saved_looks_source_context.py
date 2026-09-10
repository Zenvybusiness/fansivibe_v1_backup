"""Add backend-owned source_context discriminator to saved_looks.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-11

STEP 11.16 — the saved_looks row itself must answer whether a save is an
outfit, hairstyle, or grooming save. Adds a nullable ``source_context``
column guarded by a CHECK allow-list (``hairstyle``/``grooming``/``outfit``).

Legacy-row strategy: the column is NULLABLE and existing rows are left
untouched. A NULL ``source_context`` explicitly means "legacy row written
before the STEP 11.16 contract — domain unknown". No backfill is performed
because no truthful inference exists: ``look_id IS NULL`` is not an outfit
marker, titles are not inspected, and ``learning_signals.context`` carries
no join key to its saved row. All newly written rows carry a non-null
value (enforced by the application insert path); the CHECK passes NULLs
through so legacy rows remain valid. No database default is introduced —
new writes must supply the value explicitly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saved_looks",
        sa.Column("source_context", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_saved_looks_source_context",
        "saved_looks",
        "source_context IN ('hairstyle', 'grooming', 'outfit')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_saved_looks_source_context", "saved_looks", type_="check"
    )
    op.drop_column("saved_looks", "source_context")
