"""Seed assistant card-interaction signal types.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-12

Seeds the two `signal_types` rows required by endpoint #17
(`POST /v1/assistant/feedback`, UC-23, STEP B-A): `suggestion_opened` and
`assistant_navigation`. Without these rows the `learning_signals.signal_type`
FK (`RESTRICT`) rejects every card-feedback write.

Approved as an explicit exception to the B-A no-migration rule: the frozen
contract mandates exactly these two codes and the client must never name
signal types itself (PR-7), so the vocabulary must exist server-side.
Follows the 0008 (`outfit_selected`) precedent verbatim.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO signal_types (code, label, sort_order) "
        "VALUES ('suggestion_opened', 'Suggestion opened', 3), "
        "('assistant_navigation', 'Assistant navigation', 4) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM signal_types "
        "WHERE code IN ('suggestion_opened', 'assistant_navigation')"
    )
