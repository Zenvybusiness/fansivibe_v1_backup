"""Create M8 Events foundation tables (event_types vocab + user_events).

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-12

M8-A (DEC-015/DEC-016): the user's event calendar foundation. No routes,
use cases, or intelligence in this migration.

- `event_types`: system-owned controlled vocabulary (K9.1, PR-3), exactly
  8 codes with `mockTypes` labels (`date` -> `Date Night`);
  `sort_order = 0` for all rows (0005 precedent verbatim — no invented
  ordering) with deterministic `(sort_order, code)` reads;
  `active = true`; `office` excluded (M5-only); seeded here (DBR:562).
- `user_events`: E3 `UserEvent` current state (dated, editable), user-owned
  rows. `event_date` stays `DATE`; `event_time` is optional wall-clock
  `TIME` only — never converted, never timezone-aware (DEC-016).
  `location`/`notes` nullable free text with `char_length` bounds
  (DEC-016: 200 / 2000, supplied-empty rejected at the API layer via
  `min_length=1`, enforced here as `BETWEEN 1 AND n` when non-null).
- Index `(user_id, event_date)` btree (A9 event list by date). No unique
  constraint beyond the PK — duplicates allowed (F-8). No archive
  columns (archive NOT supported).
- `user_id -> users CASCADE` (composition, PR-10);
  `event_type_id -> event_types RESTRICT` (R34, BC-32).
- No backfill: events accrue prospectively from user creates.
- Linear single head (0016 -> 0017); fully reversible via downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TEXT

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


# Frozen M8 vocabulary (DEC-015 Decision 9): exactly these 8 codes with
# `EventType.mockTypes` labels. `office` is an M5 knowledge occasion only
# and must never be seeded here.
EVENT_TYPES = [
    ("casual", "Casual"),
    ("formal", "Formal"),
    ("business", "Business"),
    ("date", "Date Night"),
    ("party", "Party"),
    ("travel", "Travel"),
    ("workout", "Workout"),
    ("other", "Other"),
]


def _seed_event_types() -> None:
    values = ", ".join(
        f"({code!r}, {label!r}, 0, true)" for code, label in EVENT_TYPES
    )
    op.execute(
        "INSERT INTO event_types (code, label, sort_order, active) "
        f"VALUES {values}"
    )


def upgrade() -> None:
    op.create_table(
        "event_types",
        sa.Column("code", TEXT(), primary_key=True),
        sa.Column("label", TEXT(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    _seed_event_types()

    op.create_table(
        "user_events",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("event_type_id", sa.Text(), sa.ForeignKey("event_types.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_user_events_title_len"),
        sa.CheckConstraint(
            "location IS NULL OR char_length(location) BETWEEN 1 AND 200",
            name="ck_user_events_location_len",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) BETWEEN 1 AND 2000",
            name="ck_user_events_notes_len",
        ),
    )
    op.create_index(
        "ix_user_events_user_id_event_date",
        "user_events",
        ["user_id", "event_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_events_user_id_event_date", table_name="user_events")
    op.drop_table("user_events")
    op.drop_table("event_types")
