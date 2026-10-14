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
- ``collection_runs``              (discovery ingestion audit, D2)
- ``raw_source_records``          (verbatim source payload history, D2)
- ``products``                     (canonical normalized products, D2)
- ``product_source_map``           (product <-> source identity, D2)
- ``product_observations``         (append-only observation history, D5)

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
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
        UniqueConstraint("user_id", "idempotency_key", name="uq_analysis_runs_idempotency"),
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
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    # STEP 2.9 (C-02-F Option B, owner-locked): vision-observed garment fit
    # (free-form observed string, NULL when absent) + its analyzer confidence
    # (0-1 float, NULL when unavailable). No CHECK: bounds live at the API
    # schema and the scoring gate; historical NULLs never fail.
    fit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fit_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
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


class CollectionRun(Base):
    """One ingestion attempt against one authorized source (D2).

    Operational audit row: the counters record what the adapter batch did
    (fetched/inserted/updated/skipped/failed) and `error_summary` carries a
    sanitized failure note only — never credentials or raw payloads.
    `status` is running -> completed|failed; `finished_at` is stamped on
    completion. INSERT / update-on-finish only.
    """

    __tablename__ = "collection_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_collection_runs_status",
        ),
        CheckConstraint(
            "fetched_count >= 0 AND inserted_count >= 0 AND updated_count >= 0 "
            "AND skipped_count >= 0 AND failed_count >= 0",
            name="ck_collection_runs_counts_nonnegative",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_collection_runs_finished_after_start",
        ),
        CheckConstraint(
            "error_summary IS NULL OR char_length(error_summary) <= 2000",
            name="ck_collection_runs_error_summary_len",
        ),
        Index("ix_collection_runs_source_started_at", "source", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'running'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    inserted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RawSourceRecord(Base):
    """The verbatim provider payload for one source record (D2).

    Provenance is immutable: `payload` is the original structured provider
    payload and `payload_hash` is its deterministic digest. Normalized
    values are written to ``products`` — they never overwrite this row.
    ``(source, payload_hash)`` is unique so re-fetching an identical
    payload never duplicates storage. ``collection_run_id`` is CASCADE:
    a raw record has no meaning without its run. `error` text is sanitized
    and bounded. No image binaries are ever stored.
    """

    __tablename__ = "raw_source_records"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending', 'processed', 'failed', 'skipped')",
            name="ck_raw_source_records_status",
        ),
        CheckConstraint(
            "char_length(payload_hash) BETWEEN 1 AND 128",
            name="ck_raw_source_records_payload_hash_len",
        ),
        CheckConstraint(
            "processing_error IS NULL OR char_length(processing_error) <= 2000",
            name="ck_raw_source_records_processing_error_len",
        ),
        UniqueConstraint(
            "source",
            "payload_hash",
            name="uq_raw_source_records_source_payload_hash",
        ),
        Index(
            "ix_raw_source_records_source_record_id",
            "source",
            "source_record_id",
        ),
        Index("ix_raw_source_records_processing_status", "processing_status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    collection_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("collection_runs.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Product(Base):
    """One canonical, normalized product (D2).

    Normalized values only; the source payload and historical raw rows stay
    in ``raw_source_records``. ``image_urls`` holds provider CDN URLs (never
    binaries). Price is exact ``NUMERIC(12,2)`` (None = unprovided, never
    fabricated). ``first_seen_at``/``last_verified_at`` split discovery from
    verification time.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 300", name="ck_products_title_len"),
        CheckConstraint(
            "brand IS NULL OR char_length(brand) BETWEEN 1 AND 150",
            name="ck_products_brand_len",
        ),
        CheckConstraint(
            "category IS NULL OR char_length(category) BETWEEN 1 AND 100",
            name="ck_products_category_len",
        ),
        CheckConstraint(
            "subcategory IS NULL OR char_length(subcategory) BETWEEN 1 AND 100",
            name="ck_products_subcategory_len",
        ),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_products_price_nonnegative"),
        CheckConstraint(
            "currency IS NULL OR char_length(currency) BETWEEN 1 AND 10",
            name="ck_products_currency_len",
        ),
        Index("ix_products_category", "category"),
        Index("ix_products_brand", "brand"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    availability: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    product_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_urls: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductSourceMap(Base):
    """One source identity mapped to one canonical product (D2).

    ``(source, source_product_id)`` is unique, so a given source product
    always resolves to exactly one canonical product while many source rows
    may point at the same product. ``raw_source_record_id`` preserves the
    lineage back to the verbatim payload (SET NULL keeps the mapping if a
    historical raw record is removed).
    """

    __tablename__ = "product_source_map"
    __table_args__ = (
        CheckConstraint(
            "char_length(source_product_id) BETWEEN 1 AND 200",
            name="ck_product_source_map_source_product_id_len",
        ),
        UniqueConstraint(
            "source",
            "source_product_id",
            name="uq_product_source_map_source_product",
        ),
        Index("ix_product_source_map_product_id", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_product_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_source_record_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("raw_source_records.id", ondelete="SET NULL"), nullable=True
    )
    observed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductObservation(Base):
    """One append-only observation of a source listing (D5).

    Every successfully normalized listing is recorded once, capturing the
    metrics the pipeline actually has (price/currency/availability — NULL when
    unprovided, never zero). ``observed_at`` is collection time;
    ``source_timestamp`` is the source's own publication/update time (NULL if
    not supplied). ``raw_source_record_id`` is unique so re-processing a raw
    record cannot duplicate its observation; repeated identical collection
    runs are already deduped at the raw layer and therefore add no false
    trend evidence. Provenance (``collection_run_id`` +
    ``raw_source_record_id``) uses SET NULL so history outlives operational
    cleanup. No cleanup/deletion is implemented here.
    """

    __tablename__ = "product_observations"
    __table_args__ = (
        CheckConstraint(
            "char_length(source_product_id) BETWEEN 1 AND 200",
            name="ck_product_observations_source_product_id_len",
        ),
        CheckConstraint(
            "char_length(payload_hash) BETWEEN 1 AND 128",
            name="ck_product_observations_payload_hash_len",
        ),
        CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_product_observations_price_nonnegative",
        ),
        CheckConstraint(
            "currency IS NULL OR char_length(currency) BETWEEN 1 AND 10",
            name="ck_product_observations_currency_len",
        ),
        Index(
            "uq_product_observations_raw_source_record",
            "raw_source_record_id",
            unique=True,
        ),
        Index(
            "ix_product_observations_product_observed_at",
            "product_id",
            "observed_at",
        ),
        Index(
            "ix_product_observations_source_observed_at",
            "source",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_product_id: Mapped[str] = mapped_column(Text, nullable=False)
    collection_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True
    )
    raw_source_record_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("raw_source_records.id", ondelete="SET NULL"), nullable=True
    )
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    availability: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SearchInterestObservation(Base):
    """One append-only concept-level search-interest observation (D9B).

    A **relative** search-interest signal for a query/topic in a geography and
    an aggregation period — not a product listing. Kept in its own table so it
    can never be confused with ``products``/``product_observations``: there is
    no product id and no price/availability here.

    Semantics:
    - ``value`` is present only when ``value_status='present'``; missing /
      suppressed / invalid stay NULL (never 0).
    - ``period_start``/``period_end`` bound the observation period (aware UTC);
      ``source_timestamp`` is provider time and ``observed_at`` is collection
      time — distinct, and NULL when the provider supplies none.
    - ``raw_source_record_id`` is unique, and ``(source, metric, query_kind,
      query_key, geo_scope, aggregation_interval, period_start, period_end)`` is
      unique, so repeated collection never duplicates or inflates a series.
    - ``synthetic`` marks fixture/test evidence — never real provider data.
    """

    __tablename__ = "search_interest_observations"
    __table_args__ = (
        CheckConstraint(
            "metric = 'search_interest'",
            name="ck_search_interest_observations_metric",
        ),
        CheckConstraint(
            "query_kind IN ('search_term', 'topic')",
            name="ck_search_interest_observations_query_kind",
        ),
        CheckConstraint(
            "geo_scope_type IN ('country', 'region', 'worldwide')",
            name="ck_search_interest_observations_geo_type",
        ),
        CheckConstraint(
            "aggregation_interval IN ('daily', 'weekly', 'monthly', 'yearly')",
            name="ck_search_interest_observations_interval",
        ),
        CheckConstraint(
            "value_status IN ('present', 'missing', 'suppressed', 'invalid')",
            name="ck_search_interest_observations_value_status",
        ),
        CheckConstraint(
            "(value_status = 'present' AND value IS NOT NULL) "
            "OR (value_status <> 'present' AND value IS NULL)",
            name="ck_search_interest_observations_value_consistency",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_search_interest_observations_period_order",
        ),
        CheckConstraint(
            "is_relative",
            name="ck_search_interest_observations_is_relative",
        ),
        CheckConstraint(
            "char_length(query_key) BETWEEN 1 AND 200",
            name="ck_search_interest_observations_query_key_len",
        ),
        CheckConstraint(
            "char_length(query_display) BETWEEN 1 AND 300",
            name="ck_search_interest_observations_query_display_len",
        ),
        CheckConstraint(
            "char_length(value_scale) BETWEEN 1 AND 120",
            name="ck_search_interest_observations_value_scale_len",
        ),
        CheckConstraint(
            "char_length(payload_hash) BETWEEN 1 AND 128",
            name="ck_search_interest_observations_payload_hash_len",
        ),
        UniqueConstraint(
            "source",
            "metric",
            "query_kind",
            "query_key",
            "geo_scope",
            "aggregation_interval",
            "period_start",
            "period_end",
            name="uq_search_interest_observations_natural_key",
        ),
        Index(
            "uq_search_interest_observations_raw_source_record",
            "raw_source_record_id",
            unique=True,
        ),
        Index(
            "ix_search_interest_observations_query_geo_period",
            "query_key",
            "geo_scope",
            "period_start",
        ),
        Index(
            "ix_search_interest_observations_source_observed_at",
            "source",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    collection_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True
    )
    raw_source_record_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("raw_source_records.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    query_kind: Mapped[str] = mapped_column(Text, nullable=False)
    query_key: Mapped[str] = mapped_column(Text, nullable=False)
    query_display: Mapped[str] = mapped_column(Text, nullable=False)
    geo_scope: Mapped[str] = mapped_column(Text, nullable=False)
    geo_scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregation_interval: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    value: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    value_scale: Mapped[str] = mapped_column(Text, nullable=False)
    value_status: Mapped[str] = mapped_column(Text, nullable=False)
    is_relative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    query_config_version: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MediaAttentionObservation(Base):
    """One append-only concept-level media-attention observation (D9B).

    Represents an aggregated editorial press signal over a geography and period,
    derived from clustered, deduplicated media articles. Kept in its own table so
    it can never be confused with ``products``/``product_observations`` or
    ``search_interest_observations``.

    Semantics:
    - ``value`` represents the estimated deduplicated story count and is present
      only when ``value_status = 'present'`` and ``completeness_status = 'complete'``.
      Missing, suppressed, or invalid stay NULL (never 0).
    - Status matrix is strictly closed: exactly 4 valid pairs:
      ('present', 'complete'), ('suppressed', 'truncated'),
      ('missing', 'unavailable'), ('invalid', 'unavailable').
    - Count hierarchy:
      - empirical zero: raw_article_count = 0 => outlets = 0, stories = 0, value = 0.0.
      - positive branch: raw_article_count >= 1 => 1 <= outlets <= raw, 1 <= stories <= raw, value == float(stories) >= 1.0.
    - PostgreSQL numeric checks: value <> NaN, value <> Infinity, value <> -Infinity.
    - ``period_start``/``period_end`` bound the observation period (aware UTC).
    - Natural key includes ``query_config_version`` and ``clustering_version``
      to guarantee coexistence of different configurations and clustering algorithms
      without overwriting historical observations.
    - Idempotent repeated collection preserves the original observation.
    """

    __tablename__ = "media_attention_observations"
    __table_args__ = (
        CheckConstraint(
            "metric = 'media_attention'",
            name="ck_media_attention_observations_metric",
        ),
        CheckConstraint(
            "query_kind IN ('concept', 'search_term', 'topic')",
            name="ck_media_attention_observations_query_kind",
        ),
        CheckConstraint(
            "geo_scope_type IN ('country', 'region', 'worldwide')",
            name="ck_media_attention_observations_geo_type",
        ),
        CheckConstraint(
            "aggregation_interval IN ('daily', 'weekly', 'monthly', 'rolling_7d')",
            name="ck_media_attention_observations_interval",
        ),
        CheckConstraint(
            "value_status IS NOT NULL AND completeness_status IS NOT NULL AND ("
            "  (value_status = 'present' AND completeness_status = 'complete') OR "
            "  (value_status = 'suppressed' AND completeness_status = 'truncated') OR "
            "  (value_status = 'missing' AND completeness_status = 'unavailable') OR "
            "  (value_status = 'invalid' AND completeness_status = 'unavailable')"
            ")",
            name="ck_media_attention_observations_status_matrix",
        ),
        CheckConstraint(
            "CASE "
            "  WHEN value_status = 'present' THEN ("
            "    value IS NOT NULL "
            "    AND value <> 'NaN'::numeric "
            "    AND value <> 'Infinity'::numeric "
            "    AND value <> '-Infinity'::numeric "
            "    AND raw_article_count IS NOT NULL "
            "    AND distinct_outlet_count IS NOT NULL "
            "    AND estimated_deduplicated_story_count IS NOT NULL "
            "    AND value = estimated_deduplicated_story_count "
            "    AND ("
            "      (raw_article_count = 0 "
            "       AND distinct_outlet_count = 0 "
            "       AND estimated_deduplicated_story_count = 0 "
            "       AND value = 0.0) "
            "      OR "
            "      (raw_article_count >= 1 "
            "       AND distinct_outlet_count >= 1 "
            "       AND distinct_outlet_count <= raw_article_count "
            "       AND estimated_deduplicated_story_count >= 1 "
            "       AND estimated_deduplicated_story_count <= raw_article_count "
            "       AND value >= 1.0) "
            "    )"
            "  ) "
            "  WHEN value_status IN ('suppressed', 'missing', 'invalid') THEN ("
            "    value IS NULL "
            "    AND raw_article_count IS NULL "
            "    AND distinct_outlet_count IS NULL "
            "    AND estimated_deduplicated_story_count IS NULL"
            "  ) "
            "  ELSE FALSE "
            "END",
            name="ck_media_attention_observations_value_counts_integrity",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_media_attention_observations_period_order",
        ),
        CheckConstraint(
            "char_length(query_key) BETWEEN 1 AND 200",
            name="ck_media_attention_observations_query_key_len",
        ),
        CheckConstraint(
            "char_length(query_display) BETWEEN 1 AND 300",
            name="ck_media_attention_observations_query_display_len",
        ),
        CheckConstraint(
            "char_length(value_scale) BETWEEN 1 AND 120",
            name="ck_media_attention_observations_value_scale_len",
        ),
        CheckConstraint(
            "char_length(query_config_version) BETWEEN 1 AND 60",
            name="ck_media_attention_observations_query_config_ver_len",
        ),
        CheckConstraint(
            "char_length(clustering_version) BETWEEN 1 AND 60",
            name="ck_media_attention_observations_clustering_ver_len",
        ),
        UniqueConstraint(
            "source",
            "metric",
            "query_kind",
            "query_key",
            "geo_scope",
            "aggregation_interval",
            "period_start",
            "period_end",
            "query_config_version",
            "clustering_version",
            name="uq_media_attention_observations_natural_key",
        ),
        Index(
            "ix_media_attention_observations_query_geo_period",
            "query_key",
            "geo_scope",
            "period_start",
        ),
        Index(
            "ix_media_attention_observations_source_observed_at",
            "source",
            "observed_at",
        ),
        Index(
            "ix_media_attention_observations_run_id",
            "collection_run_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    collection_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    query_kind: Mapped[str] = mapped_column(Text, nullable=False)
    query_key: Mapped[str] = mapped_column(Text, nullable=False)
    query_display: Mapped[str] = mapped_column(Text, nullable=False)
    geo_scope: Mapped[str] = mapped_column(Text, nullable=False)
    geo_scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregation_interval: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    value: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    value_scale: Mapped[str] = mapped_column(Text, nullable=False)
    value_status: Mapped[str] = mapped_column(Text, nullable=False)
    completeness_status: Mapped[str] = mapped_column(Text, nullable=False)
    raw_article_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    distinct_outlet_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    estimated_deduplicated_story_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    query_config_version: Mapped[str] = mapped_column(Text, nullable=False)
    clustering_version: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_raw_record_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    provenance_pruned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_relative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MediaAttentionContributingRecord(Base):
    """Linkage between a media-attention observation and a raw source record (D9B).

    Provides durable, bidirectionally indexable provenance from an aggregated story
    observation back to each contributing raw article payload.
    - Foreign key to ``media_attention_observations.id`` uses ON DELETE CASCADE.
    - Foreign key to ``raw_source_records.id`` uses ON DELETE CASCADE.
    - Deleting raw records during retention pruning (e.g. 180-day hot storage cleanup)
      safely cascades and removes the join row, leaving the parent observation intact.
    """

    __tablename__ = "media_attention_contributing_records"
    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "raw_source_record_id",
            name="uq_media_attention_contrib_obs_raw",
        ),
        Index(
            "ix_media_attention_contrib_raw_id",
            "raw_source_record_id",
        ),
        Index(
            "ix_media_attention_contrib_cluster_id",
            "similarity_cluster_id",
        ),
        CheckConstraint(
            "char_length(outlet_domain) BETWEEN 1 AND 255",
            name="ck_media_attention_contrib_outlet_domain_len",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    observation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("media_attention_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_source_record_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_source_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    similarity_cluster_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False
    )
    is_canonical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    outlet_domain: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DiscoveryEvent(Base):
    """Discovery interaction events ledger for telemetry and behavioral analytics (DISCOVERY-10A)."""

    __tablename__ = "discovery_events"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND guest_session_id IS NULL) OR "
            "(user_id IS NULL AND guest_session_id IS NOT NULL)",
            name="ck_discovery_events_identity",
        ),
        CheckConstraint(
            "event_type IN ('product_impression', 'product_click', 'product_save', 'product_unsave', 'look_select')",
            name="ck_discovery_events_event_type",
        ),
        CheckConstraint(
            "target_type IN ('product', 'complete_look')",
            name="ck_discovery_events_target_type",
        ),
        CheckConstraint(
            "(target_type = 'complete_look' AND product_id IS NULL) OR (target_type = 'product')",
            name="ck_discovery_events_target_consistency",
        ),
        CheckConstraint(
            "surface IN ('for_you_hero', 'for_you_grid', 'because_you_like', 'complete_looks')",
            name="ck_discovery_events_surface",
        ),
        CheckConstraint(
            "position IS NULL OR (position >= 0 AND position <= 1000)",
            name="ck_discovery_events_position",
        ),
        Index(
            "uq_discovery_events_user_event",
            "user_id",
            "client_event_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_discovery_events_guest_event",
            "guest_session_id",
            "client_event_id",
            unique=True,
            postgresql_where=text("guest_session_id IS NOT NULL"),
        ),
        Index(
            "ix_discovery_events_user_type_received",
            "user_id",
            "event_type",
            text("received_at DESC"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "ix_discovery_events_product_type_received",
            "product_id",
            "event_type",
            text("received_at DESC"),
            postgresql_where=text("product_id IS NOT NULL"),
        ),
        Index(
            "ix_discovery_events_received_at",
            "received_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    guest_session_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, nullable=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    product_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    client_event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    client_occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


