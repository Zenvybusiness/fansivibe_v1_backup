"""Initial Fansivibe schema — first vertical slice (hairstyle).

Tables (STEP-4 minimal subset):
- ``users``, ``user_state``
- ``looks``, ``run_types``, ``signal_types``
- ``analysis_runs``, ``saved_looks``, ``learning_signals``

Also creates the TRX-5 write-once completion function
``complete_analysis_run`` (the only permitted ``analysis_runs`` mutation).

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

LOOKS_SEED = [
    (
        "textured_quiff",
        "Textured Quiff",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A modern take on the classic quiff with added texture and "
                "movement. The volume on top complements oval face shapes by "
                "adding vertical dimension while the textured finish keeps it "
                "effortless and contemporary."
            ),
            "stylingTips": (
                "Apply a volumizing mousse to damp hair, blow-dry upward using a "
                "round brush, then finish with a light-hold matte clay. Use fingers "
                "to create separation and texture."
            ),
            "maintenance": "Medium \u2022 Trim every 4-5 weeks",
            "bestFor": "Oval, Heart, and Rectangle face shapes",
            "reasons": [
                "Oval face shapes benefit from volume on top, which the quiff provides naturally",
                "Textured finish softens the structured silhouette for a modern, approachable look",
                "Works exceptionally well with warm medium skin tones and adds contrast",
                "Aligns with your Modern Classic Style DNA for a cohesive appearance",
            ],
            "scoreSeed": 0.94,
        },
    ),
    (
        "classic_pompadour",
        "Classic Pompadour",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A timeless pompadour with swept-back volume and clean sides. "
                "Offers a more polished, formal alternative while maintaining "
                "the vertical emphasis that suits your face shape."
            ),
            "stylingTips": (
                "Use a strong-hold pomade on towel-dried hair, blow-dry back "
                "and up, then comb into place. Finish with a light hairspray "
                "for all-day hold."
            ),
            "maintenance": "High \u2022 Trim every 3-4 weeks",
            "bestFor": "Oval, Round, and Square face shapes",
            "reasons": [
                "Provides elegant volume that elongates and balances facial features",
                "Clean sides keep the silhouette sharp and intentional",
                "Pairs naturally with structured, tailored wardrobe pieces",
            ],
            "scoreSeed": 0.87,
        },
    ),
    (
        "side_part",
        "Side Part",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A refined side part with medium length on top and tapered "
                "sides. A versatile, professional option that works across "
                "settings while maintaining a clean, structured appearance."
            ),
            "stylingTips": (
                "Apply a styling cream to damp hair, create a deep side part, "
                "and blow-dry in place. Finish with a light-hold wax for "
                "natural movement."
            ),
            "maintenance": "Low \u2022 Trim every 5-6 weeks",
            "bestFor": "Oval, Square, and Diamond face shapes",
            "reasons": [
                "Creates asymmetry that adds visual interest to symmetrical face shapes",
                "Tapered sides prevent the silhouette from feeling too wide",
                "Easy to transition from professional to casual settings",
            ],
            "scoreSeed": 0.82,
        },
    ),
    (
        "brushed_up_undercut",
        "Brushed Up Undercut",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A contemporary undercut with brushed-up length on top. "
                "Provides maximum contrast between the longer top and faded "
                "sides for a bold, fashion-forward statement."
            ),
            "stylingTips": (
                "Apply a sea salt spray for texture, blow-dry forward and up, "
                "then use a matte paste to shape. Keep the sides faded every "
                "2-3 weeks."
            ),
            "maintenance": "Medium \u2022 Trim every 3-4 weeks",
            "bestFor": "Oval, Heart, and Diamond face shapes",
            "reasons": [
                "High contrast silhouette makes a strong style statement",
                "Undercut keeps the look clean and low-maintenance on the sides",
                "Brushed-up top adds height that complements oval face proportions",
            ],
            "scoreSeed": 0.78,
        },
    ),
]

RUN_TYPES_SEED = [("hairstyle", "Hairstyle analysis")]

SIGNAL_TYPES_SEED = [
    ("look_saved", "A look was saved"),
    ("analysis_updated", "Profile updated from an analysis"),
]


def _tables() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("auth_provider", sa.Text(), nullable=False),
        sa.Column("auth_subject", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(display_name) BETWEEN 1 AND 100", name="ck_users_display_name_len"),
        sa.UniqueConstraint("auth_provider", "auth_subject", name="uq_users_auth_pair"),
    )
    op.create_table(
        "user_state",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("style_profile", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("preferences", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("flags", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("version >= 0", name="ck_user_state_version"),
    )
    op.create_table(
        "looks",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("image_ref", JSONB(), nullable=True),
        sa.Column("content_version", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_looks_title_len"),
    )
    op.create_table(
        "run_types",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_run_types_label_len"),
        sa.CheckConstraint("sort_order >= 0", name="ck_run_types_sort_order"),
    )
    op.create_table(
        "signal_types",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_signal_types_label_len"),
        sa.CheckConstraint("sort_order >= 0", name="ck_signal_types_sort_order"),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_type", sa.Text(), sa.ForeignKey("run_types.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("input_media", JSONB(), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_analysis_runs_status",
        ),
    )
    op.create_index(
        "ix_analysis_runs_user_id_created_at",
        "analysis_runs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_runs_user_id_run_type_created_at",
        "analysis_runs",
        ["user_id", "run_type", "created_at"],
    )
    op.create_table(
        "saved_looks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("look_id", sa.Text(), sa.ForeignKey("looks.code", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column(
            "idempotency_key",
            sa.Text(),
            nullable=False,
            comment="slice-level extension for the contract's required Idempotency-Key replay (C-12/API-33)",
        ),
        sa.Column("source_run_id", UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_saved_looks_title_len"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_saved_looks_idempotency"),
    )
    op.create_index(
        "ix_saved_looks_user_id_created_at",
        "saved_looks",
        ["user_id", "created_at"],
    )
    op.create_table(
        "learning_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_type", sa.Text(), sa.ForeignKey("signal_types.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("context", JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(label) BETWEEN 1 AND 200", name="ck_learning_signals_label_len"),
    )
    op.create_index(
        "ix_learning_signals_user_id_occurred_at",
        "learning_signals",
        ["user_id", "occurred_at"],
    )


def _q(value: str) -> str:
    """Inline SQL literal for a trusted seed constant (never user input)."""
    return "'" + value.replace("'", "''") + "'"


def _seed() -> None:
    for code, title, version, payload in LOOKS_SEED:
        op.execute(
            f"INSERT INTO looks (code, title, content_version, payload, published_at) "
            f"VALUES ({_q(code)}, {_q(title)}, {_q(version)}, "
            f"CAST({_q(json.dumps(payload))} AS jsonb), now())"
        )
    for i, (code, label) in enumerate(RUN_TYPES_SEED):
        op.execute(
            f"INSERT INTO run_types (code, label, sort_order) "
            f"VALUES ({_q(code)}, {_q(label)}, {i})"
        )
    for i, (code, label) in enumerate(SIGNAL_TYPES_SEED):
        op.execute(
            f"INSERT INTO signal_types (code, label, sort_order) "
            f"VALUES ({_q(code)}, {_q(label)}, {i})"
        )


def _completion_function() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION complete_analysis_run(
                p_run_id uuid,
                p_user_id uuid,
                p_status text,
                p_result jsonb
            ) RETURNS boolean AS $$
            DECLARE
                updated_count integer;
            BEGIN
                UPDATE analysis_runs
                   SET status = p_status,
                       result = p_result,
                       completed_at = now()
                 WHERE id = p_run_id
                   AND user_id = p_user_id
                   AND status = 'pending';
                GET DIAGNOSTICS updated_count = ROW_COUNT;
                RETURN updated_count = 1;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )


def upgrade() -> None:
    _tables()
    _seed()
    _completion_function()


def downgrade() -> None:
    op.execute(sa.text("DROP FUNCTION IF EXISTS complete_analysis_run(uuid, uuid, text, jsonb)"))
    op.drop_index("ix_learning_signals_user_id_occurred_at", table_name="learning_signals")
    op.drop_table("learning_signals")
    op.drop_index("ix_saved_looks_user_id_created_at", table_name="saved_looks")
    op.drop_table("saved_looks")
    op.drop_index("ix_analysis_runs_user_id_run_type_created_at", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_user_id_created_at", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_table("signal_types")
    op.drop_table("run_types")
    op.drop_table("looks")
    op.drop_table("user_state")
    op.drop_table("users")
