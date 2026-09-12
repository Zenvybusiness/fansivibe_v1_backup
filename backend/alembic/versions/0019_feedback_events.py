"""Create M11 feedback_events table (UC-32, TABLE_DEFINITIONS P1).

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-12

M11 (UC-32 `SubmitRecommendationFeedback`): append-only user reaction
history (rating / why + optional look/saved-look target). One concept
shared by the wardrobe and general recommendation clusters.

- `feedback_events`: EVENT (historical, P1, feature-gated) — INSERT /
  SELECT only, whole-row raw user event. No unique constraint beyond
  the PK (repeats with fresh keys append); idempotent replay is
  enforced by the `uq_feedback_events_idempotency (user_id,
  idempotency_key)` guard (M7 `uq_saved_looks_idempotency` precedent).
- `rating text NOT NULL` — rating tag; the exact vocabulary is pending
  the feedback design (BC-38/39, PR-12), so deliberately NO CHECK here
  (a CHECK on an unsettled set is speculative).
- `reason text NULL` — optional free-text "why" (no numeric bound
  frozen; blank-if-provided is rejected at the API layer).
- Targets (at most one per reaction — enforced in the use case):
  `target_look_id text NULL FK -> looks(code) ON DELETE SET NULL`
  (BC-38); `target_saved_look_id uuid NULL FK -> saved_looks(id) ON
  DELETE SET NULL` (BC-39) — feedback history survives target removal.
- `user_id -> users CASCADE` (composition, BC-25, PR-10).
- Index `(user_id, occurred_at)` btree (per-user history for the
  deferred aggregation read; target-side grouping only on measured
  need).
- No backfill: reactions accrue prospectively from user submits.
- Linear single head (0018 -> 0019); fully reversible via downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TEXT

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_events",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_look_id", TEXT, nullable=True),
        sa.Column("target_saved_look_id", sa.Uuid(), nullable=True),
        sa.Column("rating", TEXT, nullable=False),
        sa.Column("reason", TEXT, nullable=True),
        sa.Column("idempotency_key", TEXT, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["target_look_id"], ["looks.code"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_saved_look_id"], ["saved_looks.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_feedback_events_idempotency"
        ),
    )
    op.create_index(
        "ix_feedback_events_user_id_occurred_at",
        "feedback_events",
        ["user_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feedback_events_user_id_occurred_at", table_name="feedback_events"
    )
    op.drop_table("feedback_events")
