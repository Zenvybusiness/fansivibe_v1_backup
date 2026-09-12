"""SQLAlchemy ORM models — the minimal STEP-4 table subset for the first
vertical slice.

Tables (from `docs/database/TABLE_DEFINITIONS.md`):
- ``users``, ``user_state``        (current state, P0)
- ``looks``, ``run_types``, ``signal_types``  (system knowledge, K9.1)
- ``analysis_runs``                (append-only history, P2)
- ``saved_looks``                  (current state, immutable rows, P0)
- ``learning_signals``             (append-only history, P0)
- ``activity_days``                (streak history, P1, M10-A)
- ``wardrobe_wear_events``         (append-only history, P0)
- ``wardrobe_wear_groups``         (durable wear-action ledger, P0)
- ``wardrobe_categories``          (P0 vocabulary reference, K9.1)
- ``colors``                       (P0 vocabulary reference, K9.1)
- ``materials``                    (P0 vocabulary reference, K9.1)
- ``event_types``                  (M8 vocabulary reference, K9.1)
- ``user_events``                  (event calendar current state, P1, M8-A)

History tables are append-only at the role-grant level (PR-5); the only
permitted mutation of ``analysis_runs`` is the guarded completion write
(TRX-5), exposed via the ``complete_analysis_run`` SQL function.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
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
    # D-AUTH-1 — local email/password provider credential. Bcrypt hash of
    # the password (never the password itself); NULL for legacy dev rows
    # and non-password identities. The (provider, subject) UNIQUE pair
    # remains the account identity (BC-1); email accounts use
    # provider "email" with the normalized email as subject, so email
    # uniqueness is enforced by the existing pair constraint.
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # D-AUTH-1 — `POST /v1/auth/register` replay key (C-12): a retried
    # register with the same key returns the same account, never a
    # duplicate (M7 replay/conflict semantics for account creation).
    register_idempotency_key: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserSession(Base):
    """One device/session row — the R51 session/token store (D-AUTH-1).

    One `POST /v1/auth/register` or `/v1/auth/login` mints one row and
    one JWT (`jti` = this row id). `POST /v1/auth/logout` stamps
    `revoked_at`; revoked/expired rows never authenticate again.
    The bearer token itself is never stored — `token_digest` is the
    SHA-256 of the JWT. Account erasure cascades (TRX-8): deleting the
    user deletes every session, so all tokens die with the account.
    INSERT / SELECT / revoke-only; rows are never edited otherwise.
    """

    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_user_sessions_token_digest"),
        Index("ix_user_sessions_user_id_expires_at", "user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


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
            "source_context IN ('hairstyle', 'grooming', 'outfit', 'daily')",
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
    # outfit, plus M9 "daily" via 0018). Nullable only for legacy rows
    # written before this contract (NULL = unknown); all new writes supply
    # a non-null value.
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


class FeedbackEvents(Base):
    """One append-only user reaction (M11, UC-32, P1 feature-gated).

    Raw reaction history (rating / why + optional look/saved-look
    target) feeding the deferred derived-preference aggregation via
    reads — never state, never a learning signal. INSERT / SELECT
    only; no unique constraint beyond the PK (repeats with fresh keys
    append; idempotent replay is guarded by
    `uq_feedback_events_idempotency`). `rating` carries deliberately no
    CHECK (vocabulary pending the feedback design, BC-38/39, PR-12).
    Targets are SET NULL so feedback history survives target removal
    (BC-38/39, DEC-013).
    """

    __tablename__ = "feedback_events"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_feedback_events_idempotency"),
        Index("ix_feedback_events_user_id_occurred_at", "user_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_look_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("looks.code", ondelete="SET NULL"), nullable=True
    )
    target_saved_look_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("saved_looks.id", ondelete="SET NULL"), nullable=True
    )
    rating: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ActivityDays(Base):
    """One styled-day row per user per day (E9, P1, M10-A).

    Streak history for `GET /v1/learning/summary` (endpoint #34, DEC-020
    §D): the current streak is recomputed from these rows at read time
    (PR-2); this table is the immutable per-day history. Rows are written
    only by the per-signal upsert riding the signal's own commit
    (`ActivityDayRepositorySQL.upsert_styled_day`); `summary` stays NULL
    in M10 v1 (no aggregate content defined).
    """

    __tablename__ = "activity_days"
    __table_args__ = (
        # BC-4: at most one row per user per day — the unique backing
        # btree doubles as the (user_id, day) streak-scan index (A8).
        UniqueConstraint("user_id", "day", name="uq_activity_days_user_day"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    styled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
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


class WardrobeWearEvents(Base):
    __tablename__ = "wardrobe_wear_events"
    __table_args__ = (
        # STEP 15.4 (migration 0013): scoped per row, not per group — one
        # logging action shares a key across its item rows.
        UniqueConstraint("user_id", "idempotency_key", "wardrobe_item_id", name="uq_wardrobe_wear_events_idempotency_item"),
        Index("ix_wardrobe_wear_events_user_id_wardrobe_item_id_worn_at", "user_id", "wardrobe_item_id", "worn_at"),
        Index("ix_wardrobe_wear_events_user_id_worn_at", "user_id", "worn_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # STEP 15.3 — intentionally NO FK to wardrobe_items (No-FK-to-trigger
    # rule, RELATIONSHIP_CONSTRAINTS §3.4): wear rows are history and must
    # survive item deletion; stale UUIDs are ignored at read time.
    wardrobe_item_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    worn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Correlates the rows of one logging action (single-item wear = a group
    # of one). Plain UUID, no parent table (STEP 15.2 granularity decision).
    wear_group_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WardrobeWearGroups(Base):
    __tablename__ = "wardrobe_wear_groups"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_wardrobe_wear_groups_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    # STEP 15.4B — canonical request payload (sorted unique UUID strings)
    # for replay comparison ONLY; never a query axis (same rule as
    # `saved_looks.snapshot`). The row `id` IS the `wear_group_id` shared
    # by the action's `wardrobe_wear_events` rows.
    item_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False
    )
    worn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventType(Base):
    """M8 event-type vocabulary row (E3 `event_types`, P1, K9.1).

    System-owned controlled vocabulary (PR-3 deprecate-not-delete):
    exactly the 8 frozen M8 codes, seeded by migration 0017. Separate
    from the M5 knowledge occasions; `office` lives there, never here.
    """

    __tablename__ = "event_types"
    __table_args__ = (
        CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="ck_event_types_label_len"),
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


class UserEvent(Base):
    """A user-created calendar event (E3 `user_events`, P1, M8-A).

    Current state (dated, editable): full-replace PUT, physical DELETE
    (no archive column). `event_date` is a `DATE` value object, never a
    timestamp; `event_time` is optional wall-clock `TIME` only — never
    converted, never timezone-aware (DEC-016). Duplicates allowed (no
    unique constraint beyond the PK, F-8). Feeds `preferred_occasions`
    (R36) and seeds outfit generation (R35) at the use-case layer —
    never from this model.
    """

    __tablename__ = "user_events"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_user_events_title_len"),
        CheckConstraint(
            "location IS NULL OR char_length(location) BETWEEN 1 AND 200",
            name="ck_user_events_location_len",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) BETWEEN 1 AND 2000",
            name="ck_user_events_notes_len",
        ),
        Index("ix_user_events_user_id_event_date", "user_id", "event_date"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    event_type_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("event_types.code", ondelete="RESTRICT"),
        nullable=False,
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
