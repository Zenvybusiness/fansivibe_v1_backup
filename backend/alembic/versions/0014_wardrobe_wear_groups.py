"""Create wardrobe_wear_groups idempotency ledger (durable wear action).

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-11

STEP 15.4B — implements the 15.4A audit verdict (NEEDS_CHANGE): one wear
POST is one logical idempotent action, but 0012/0013 persist one row per
item, so no single row can arbitrate whole-request idempotency under
concurrent same-key reuse (disjoint item sets fuse silently under one key).
This ledger gives the logical action a durable home:
`UNIQUE(user_id, idempotency_key)` serializes same-key writers; the loser
re-reads the committed group and replays (same payload) or 409s.

- `item_ids` JSONB holds ONLY the canonical request payload (sorted unique
  UUID strings) for replay comparison — never a query axis (same rule as
  `saved_looks.snapshot`); all wear aggregation reads flat
  `wardrobe_wear_events` rows.
- The ledger row `id` IS the `wear_group_id` shared by the action's event
  rows: no extra group-ID column, no header/line schema.
- No backfill: the endpoints are unreleased, so no production rows exist;
  history is never manufactured.
- Migration 0013 stays intact (per-row uniqueness remains defense-in-depth).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wardrobe_wear_groups",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "idempotency_key",
            sa.Text(),
            nullable=False,
            comment="contract Idempotency-Key per logical wear action (C-12/API-33): one user + one key = one group",
        ),
        sa.Column(
            "item_ids",
            JSONB(),
            nullable=False,
            comment="canonical request payload (sorted unique UUID strings) for replay comparison only; never a query axis",
        ),
        sa.Column("worn_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_wardrobe_wear_groups_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("wardrobe_wear_groups")
