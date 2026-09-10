"""Declare the 8-look catalog homogeneous at version 1.1.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-11

STEP 12.5 — catalog/DB seed version parity correction (STEP 12.4 finding).
The 4 hairstyle `looks` rows still carry `content_version = '1.0'` while
their payloads are already content-identical to the current
`KNOWLEDGE_VERSION = "1.1"` catalog; the 4 grooming rows are already 1.1.

Updates ONLY the 4 hairstyle rows (scoped by exact stable codes) from
'1.0' to '1.1'. Payloads, titles, grooming rows, and everything else are
untouched. No tables/columns/indexes/constraints are added or altered.
Downgrade restores only those same 4 rows to '1.0'.
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_HAIRSTYLE_CODES = (
    "textured_quiff",
    "classic_pompadour",
    "side_part",
    "brushed_up_undercut",
)


def _codes() -> str:
    return "(" + ", ".join(f"'{code}'" for code in _HAIRSTYLE_CODES) + ")"


def upgrade() -> None:
    op.execute(
        "UPDATE looks SET content_version = '1.1' "
        f"WHERE code IN {_codes()} AND content_version = '1.0'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE looks SET content_version = '1.0' "
        f"WHERE code IN {_codes()} AND content_version = '1.1'"
    )
