"""Add style_journey_weekly_snapshots table for SJ1 weekly progress history.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-28

Stores immutable, owner-scoped weekly Style Journey progress snapshots
with per-user unique week boundaries (`(user_id, week_start)`) and full
score breakdown + activity counts + timezone audit metadata.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "style_journey_weekly_snapshots",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("style_score", sa.Integer(), nullable=False),
        sa.Column("base_points", sa.Integer(), nullable=False),
        sa.Column("wardrobe_points", sa.Integer(), nullable=False),
        sa.Column("saved_points", sa.Integer(), nullable=False),
        sa.Column(
            "styled_days_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "signals_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "aggregation_policy",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'end_of_week_score_v1'"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id",
            "week_start",
            name="uq_style_journey_weekly_snapshots_user_week",
        ),
        sa.CheckConstraint(
            "week_end > week_start",
            name="ck_sj_weekly_snapshots_week_span",
        ),
        sa.CheckConstraint(
            "style_score BETWEEN 60 AND 100",
            name="ck_sj_weekly_snapshots_style_score",
        ),
        sa.CheckConstraint(
            "base_points = 60",
            name="ck_sj_weekly_snapshots_base_points",
        ),
        sa.CheckConstraint(
            "wardrobe_points BETWEEN 0 AND 20",
            name="ck_sj_weekly_snapshots_wardrobe_points",
        ),
        sa.CheckConstraint(
            "saved_points BETWEEN 0 AND 20",
            name="ck_sj_weekly_snapshots_saved_points",
        ),
        sa.CheckConstraint(
            "styled_days_count BETWEEN 0 AND 7",
            name="ck_sj_weekly_snapshots_styled_days",
        ),
        sa.CheckConstraint(
            "signals_count >= 0",
            name="ck_sj_weekly_snapshots_signals_count",
        ),
    )
    op.create_index(
        "ix_style_journey_weekly_snapshots_user_week",
        "style_journey_weekly_snapshots",
        ["user_id", "week_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_style_journey_weekly_snapshots_user_week",
        table_name="style_journey_weekly_snapshots",
    )
    op.drop_table("style_journey_weekly_snapshots")

