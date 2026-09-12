"""Widen the saved_looks source_context CHECK with the daily value.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-12

M9 save batch (DEC-018 §1, U-SOURCE-CONTEXT): the M9 `POST
/v1/looks/today/save` persists the derived `TodayLook` through the
existing M7 `SaveRecommendation` with `sourceContext = "daily"`
(REC_API §3.1 type code + §4.8 "sourceContext is the type code" + DAILY
§5.3). The `0009` CHECK predates any daily save path, so it is widened
additively — a superset admits every existing row/NULL untouched, and
all existing values stay valid. No backfill, no default, no other
change.

Outfit-scoped readers are untouched: `get_outfit_coverage`,
`resolve_preferred_item_ids`, and the W-7 follow-up keep
`== "outfit"`, so daily rows are ignored exactly like
hairstyle/grooming (frozen insight/preference numbers preserved).
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_CHECK = "ck_saved_looks_source_context"
_TABLE = "saved_looks"
_WIDE = "source_context IN ('hairstyle', 'grooming', 'outfit', 'daily')"
_NARROW = "source_context IN ('hairstyle', 'grooming', 'outfit')"


def upgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, _WIDE)


def downgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, _NARROW)
