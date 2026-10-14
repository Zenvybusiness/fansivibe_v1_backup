"""Discovery interaction events ledger for telemetry and behavioral analytics (DISCOVERY-10A).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-15

Append-only, identity-isolated interaction events ledger for FansiVibe Discovery.
Captures product impressions, clicks, saves, unsaves, and Complete Look candidate
selections.

Semantics & Invariants:
- Identity Isolation: exactly one identity per row (authenticated user_id OR guest_session_id).
- Uniqueness & Idempotency: scoped by identity + client_event_id (uq_discovery_events_user_event,
  uq_discovery_events_guest_event).
- Target Lineage: target_id records the historical identifier. For product targets,
  product_id references products(id) ON DELETE SET NULL to preserve telemetry if a catalog
  product is deleted.
- Cascade on Account Deletion: user_id foreign key cascades ON DELETE CASCADE.
- Event Type Allow-list: product_impression, product_click, product_save, product_unsave, look_select.
  (look_save and product_dismiss are deferred and rejected).
- Timestamps: client_occurred_at records client time; received_at independently records server ingestion.
- Retention: dedicated index on received_at supports bounded 90-day pruning queries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("guest_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("client_event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("client_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND guest_session_id IS NULL) OR "
            "(user_id IS NULL AND guest_session_id IS NOT NULL)",
            name="ck_discovery_events_identity",
        ),
        sa.CheckConstraint(
            "event_type IN ('product_impression', 'product_click', 'product_save', 'product_unsave', 'look_select')",
            name="ck_discovery_events_event_type",
        ),
        sa.CheckConstraint(
            "target_type IN ('product', 'complete_look')",
            name="ck_discovery_events_target_type",
        ),
        sa.CheckConstraint(
            "(target_type = 'complete_look' AND product_id IS NULL) OR (target_type = 'product')",
            name="ck_discovery_events_target_consistency",
        ),
        sa.CheckConstraint(
            "surface IN ('for_you_hero', 'for_you_grid', 'because_you_like', 'complete_looks')",
            name="ck_discovery_events_surface",
        ),
        sa.CheckConstraint(
            "position IS NULL OR (position >= 0 AND position <= 1000)",
            name="ck_discovery_events_position",
        ),
    )

    op.create_index(
        "uq_discovery_events_user_event",
        "discovery_events",
        ["user_id", "client_event_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.create_index(
        "uq_discovery_events_guest_event",
        "discovery_events",
        ["guest_session_id", "client_event_id"],
        unique=True,
        postgresql_where=sa.text("guest_session_id IS NOT NULL"),
    )

    op.create_index(
        "ix_discovery_events_user_type_received",
        "discovery_events",
        ["user_id", "event_type", sa.text("received_at DESC")],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.create_index(
        "ix_discovery_events_product_type_received",
        "discovery_events",
        ["product_id", "event_type", sa.text("received_at DESC")],
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )

    op.create_index(
        "ix_discovery_events_received_at",
        "discovery_events",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_table("discovery_events")
