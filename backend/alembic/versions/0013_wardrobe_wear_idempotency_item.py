"""Scope the wear-event idempotency UNIQUE to (user, key, item).

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-11

STEP 15.4 finding (caught by the new API tests, not weakened): one logging
action writes one row PER ITEM sharing a single `idempotency_key`, so the
0012 `UNIQUE(user_id, idempotency_key)` rejects every multi-item group at
its second row. The correct arbitration unit is the row:
`UNIQUE(user_id, idempotency_key, wardrobe_item_id)`.

Replay/conflict semantics are unchanged — the use case still compares the
full canonical payload (item set + worn instant) on re-read; concurrent
identical submits still collide on the shared rows and resolve to replay,
concurrent differing submits still resolve to 409.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_wardrobe_wear_events_idempotency",
        "wardrobe_wear_events",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_wardrobe_wear_events_idempotency_item",
        "wardrobe_wear_events",
        ["user_id", "idempotency_key", "wardrobe_item_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_wardrobe_wear_events_idempotency_item",
        "wardrobe_wear_events",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_wardrobe_wear_events_idempotency",
        "wardrobe_wear_events",
        ["user_id", "idempotency_key"],
    )
