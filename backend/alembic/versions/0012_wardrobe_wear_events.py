"""Create wardrobe_wear_events table (wear-event foundation).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-11

STEP 15.3 — persisted foundation for future Wardrobe Wear/Frequency
Intelligence (approved design, STEP 15.2). One row per wardrobe item per
wear; `wear_group_id` correlates the rows of one logging action
(single-item wear = group of one).

Conventions followed (see 0006/0001):
- `id` UUID PK via `gen_random_uuid()`; all timestamps TIMESTAMPTZ with
  `now()` defaults; `user_id → users.id ON DELETE CASCADE` so account
  erasure removes wear history (composition rule).
- `wardrobe_item_id` is a plain UUID with NO FK by design
  (No-FK-to-trigger rule, RELATIONSHIP_CONSTRAINTS §3.4): wear rows are
  history and must survive wardrobe-item deletion; stale UUIDs are ignored
  at read time (same precedent as saved-look coverage).
- `UNIQUE(user_id, idempotency_key)` mirrors `uq_saved_looks_idempotency`
  for the contract's Idempotency-Key replay (C-12/API-33).
- Indexes are user_id-leading btrees (no GIN; JSONB unused here).

No backfill: no valid historical wear source exists (STEP 15.1 FAIL).
No endpoint, use case, or intelligence in this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wardrobe_wear_events",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "wardrobe_item_id",
            sa.Uuid(),
            nullable=False,
            comment="intentionally NO FK to wardrobe_items (No-FK-to-trigger rule): wear history survives item deletion; stale UUIDs ignored at read time",
        ),
        sa.Column("worn_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("wear_group_id", sa.Uuid(), nullable=False),
        sa.Column(
            "idempotency_key",
            sa.Text(),
            nullable=False,
            comment="contract Idempotency-Key replay per logging action (C-12/API-33)",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_wardrobe_wear_events_idempotency"),
    )
    op.create_index(
        "ix_wardrobe_wear_events_user_id_wardrobe_item_id_worn_at",
        "wardrobe_wear_events",
        ["user_id", "wardrobe_item_id", "worn_at"],
    )
    op.create_index(
        "ix_wardrobe_wear_events_user_id_worn_at",
        "wardrobe_wear_events",
        ["user_id", "worn_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wardrobe_wear_events_user_id_worn_at", table_name="wardrobe_wear_events")
    op.drop_index("ix_wardrobe_wear_events_user_id_wardrobe_item_id_worn_at", table_name="wardrobe_wear_events")
    op.drop_table("wardrobe_wear_events")
