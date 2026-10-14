"""Offer click event attribution contract (DISCOVERY-10B-3).

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-15

Evolves the discovery interaction events ledger (established in 0030) to support:
- ``offer_click`` event type for verified retailer outbound click attribution.
- ``product_offers`` and ``product_offer_sheet`` surfaces for shopping comparison surfaces.

Invariants:
- Identity Isolation: exactly one identity per row (authenticated user_id OR guest_session_id).
- Target Lineage: target_id records the historical identifier. product_id references
  products(id) ON DELETE SET NULL to preserve telemetry if a catalog product is deleted.
- Minimal Attribution: offer_id and retailer captured in metadata; zero IP address or
  user-agent collection.
- Clean backward compatibility and symmetric downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_OLD_EVENT_TYPES = (
    "'product_impression', 'product_click', 'product_save', 'product_unsave', 'look_select'"
)
_NEW_EVENT_TYPES = (
    "'product_impression', 'product_click', 'product_save', 'product_unsave', "
    "'look_select', 'offer_click'"
)

_OLD_SURFACES = (
    "'for_you_hero', 'for_you_grid', 'because_you_like', 'complete_looks'"
)
_NEW_SURFACES = (
    "'for_you_hero', 'for_you_grid', 'because_you_like', 'complete_looks', "
    "'product_offers', 'product_offer_sheet'"
)


def upgrade() -> None:
    # 1. Update event_type check constraint
    op.drop_constraint(
        "ck_discovery_events_event_type",
        "discovery_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_discovery_events_event_type",
        "discovery_events",
        f"event_type IN ({_NEW_EVENT_TYPES})",
    )

    # 2. Update surface check constraint
    op.drop_constraint(
        "ck_discovery_events_surface",
        "discovery_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_discovery_events_surface",
        "discovery_events",
        f"surface IN ({_NEW_SURFACES})",
    )


def downgrade() -> None:
    # 1. Revert surface check constraint
    op.drop_constraint(
        "ck_discovery_events_surface",
        "discovery_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_discovery_events_surface",
        "discovery_events",
        f"surface IN ({_OLD_SURFACES})",
    )

    # 2. Revert event_type check constraint
    op.drop_constraint(
        "ck_discovery_events_event_type",
        "discovery_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_discovery_events_event_type",
        "discovery_events",
        f"event_type IN ({_OLD_EVENT_TYPES})",
    )
