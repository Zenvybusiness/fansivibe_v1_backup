"""Create activity_days streak history (M10-A foundation).

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-12

M10-A (DEC-019/DEC-020/DEC-021): one row per styled user-day backing the
derived current streak (`activity_days`, E9, P1). Shape follows
`docs/database/TABLE_DEFINITIONS.md` §4 (`activity_days`) with the
STEP 19.14 required variance: `styled` defaults to `true` (every row is
written by the per-signal upsert as styled; the column default only
covers direct inserts). `summary` stays NULL in M10 v1 (no aggregate
content defined — honesty over fabrication).

- `UNIQUE (user_id, day)` (BC-4): at most one row per user per day, so a
  repeated same-day upsert can never double-count the streak. The unique
  backing btree IS the `(user_id, day)` streak-scan index (A8,
  `INDEX_STRATEGY.md` §4.7) — no separate index is created.
- `user_id → users CASCADE`: account deletion erases activity history
  with the account (TRX-8, PR-10); no orphaned rows.
- Append-only history (`INSERT`/`SELECT` only, PR-5): no UPDATE/DELETE
  grant beyond the upsert's own conflict path.
- No backfill: streak accrues prospectively from M10-A deploy (DEC-020
  §F); history is never manufactured.
- Linear single head (0015 → 0016); fully reversible via downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_days",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("styled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "day", name="uq_activity_days_user_day"),
    )


def downgrade() -> None:
    op.drop_table("activity_days")
