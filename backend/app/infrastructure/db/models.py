"""SQLAlchemy ORM models — the minimal STEP-4 table subset for the first
vertical slice.

Tables (from `docs/database/TABLE_DEFINITIONS.md`):
- ``users``, ``user_state``        (current state, P0)
- ``looks``, ``run_types``, ``signal_types``  (system knowledge, K9.1)
- ``analysis_runs``                (append-only history, P2)
- ``saved_looks``                  (current state, immutable rows, P0)
- ``learning_signals``             (append-only history, P0)
- ``wardrobe_categories``          (P0 vocabulary reference, K9.1)
- ``colors``                       (P0 vocabulary reference, K9.1)
- ``materials``                    (P0 vocabulary reference, K9.1)

History tables are append-only at the role-grant level (PR-5); the only
permitted mutation of ``analysis_runs`` is the guarded completion write
(TRX-5), exposed via the ``complete_analysis_run`` SQL function.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.session import Base


class Users(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 100", name="ck_users_display_name_len"),
        UniqueConstraint("auth_provider", "auth_subject", name="uq_users_auth_pair"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    auth_provider: Mapped[str] = mapped_column(Text, nullable=False)
    auth_subject: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserState(Base):
    __tablename__ = "user_state"
    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_user_state_version"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    style_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Looks(Base):
    __tablename__ = "looks"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_looks_title_len"),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    image_ref: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    content_version: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RunTypes(Base):
    __tablename__ = "run_types"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_run_types_label_len"),
        CheckConstraint("sort_order >= 0", name="ck_run_types_sort_order"),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SignalTypes(Base):
    __tablename__ = "signal_types"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_signal_types_label_len"),
        CheckConstraint("sort_order >= 0", name="ck_signal_types_sort_order"),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AnalysisRuns(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_analysis_runs_status",
        ),
        Index("ix_analysis_runs_user_id_created_at", "user_id", "created_at"),
        Index(
            "ix_analysis_runs_user_id_run_type_created_at",
            "user_id",
            "run_type",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(
        Text, ForeignKey("run_types.code", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    # STEP 12.3 — combined knowledge provenance (`<catalog>+<OI>`, e.g.
    # "1.1+1.0"). Nullable: legacy rows predate the contract (NULL = unknown).
    # Independent from engine_version (rules-code revision).
    knowledge_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_media: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedLooks(Base):
    __tablename__ = "saved_looks"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_saved_looks_title_len"),
        CheckConstraint(
            "source_context IN ('hairstyle', 'grooming', 'outfit')",
            name="ck_saved_looks_source_context",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_saved_looks_idempotency"),
        Index("ix_saved_looks_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    look_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("looks.code", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # STEP 11.16 — backend-owned domain discriminator (hairstyle/grooming/
    # outfit). Nullable only for legacy rows written before this contract
    # (NULL = unknown); all new writes supply a non-null value.
    source_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LearningSignals(Base):
    __tablename__ = "learning_signals"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 200", name="ck_learning_signals_label_len"),
        Index("ix_learning_signals_user_id_occurred_at", "user_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(
        Text, ForeignKey("signal_types.code", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WardrobeCategories(Base):
    __tablename__ = "wardrobe_categories"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_wardrobe_categories_label_len"),
    )

    code: Mapped[str] = mapped_column(
        Text, primary_key=True, nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Colors(Base):
    __tablename__ = "colors"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_colors_label_len"),
    )

    code: Mapped[str] = mapped_column(
        Text, primary_key=True, nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Materials(Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_materials_label_len"),
    )

    code: Mapped[str] = mapped_column(
        Text, primary_key=True, nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WardrobeItems(Base):
    __tablename__ = "wardrobe_items"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("wardrobe_categories.code", ondelete="RESTRICT"),
        nullable=False,
    )
    color_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("colors.code", ondelete="RESTRICT"),
        nullable=False,
    )
    material_id: Mapped[Optional[str]] = mapped_column(
        Text,
        ForeignKey("materials.code", ondelete="RESTRICT"),
        nullable=True,
    )
    is_favorite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    image_ref: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
