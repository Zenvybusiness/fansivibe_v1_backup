"""SQLAlchemy repository implementations (Persistence adapters).

All reads are owner-scoped (`user_id`) — OW-1. `complete` uses the server-side
`complete_analysis_run` function (TRX-5 write-once guard).
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.ports.repositories import (
    AnalysisRunRecord,
    AnalysisRunSummary,
    AuthAccountRecord,
    AuthSessionRecord,
    CatalogProduct,
    CatalogProductRecord,
    FeedbackEventRecord,
    MediaAttentionRepository,
    ProductCandidateRepository,
    ProductFilterCriteria,
    SavedLookCoverage,
    SavedLookRecord,
    SearchInterestEvidence,
    UserEventRecord,
    UserProfileRecord,
    VocabularyRecord,
    WardrobeInsightSummary,
    WardrobeItemRecord,
    WearEventRecord,
    WearGroupRecord,
    WearSummary,
)
from app.domain.services.media_attention import (
    ContributingRecordAssignment,
    MediaAttentionEvidence,
    MediaAttentionObservation,
)
from app.domain.services.normalization import NormalizedProduct
from app.domain.services.product_identity import (
    MATCH_EXACT,
    MATCH_VERIFIED,
    IdentityCandidates,
    IdentityDecision,
    resolve_identity,
)
from app.domain.services.search_interest import SearchInterestObservation
from app.domain.services.trends import ObservationEvidence
from app.infrastructure.db.models import (
    ActivityDays,
    AnalysisRuns,
    CollectionRun,
    EventType,
    FeedbackEvents,
    LearningSignals,
    Looks,
    MediaAttentionContributingRecord as MediaAttentionContributingRecordModel,
    MediaAttentionObservation as MediaAttentionObservationModel,
    Product,
    ProductObservation,
    ProductSourceMap,
    RawSourceRecord,
    SavedLooks,
    SearchInterestObservation as SearchInterestObservationModel,
    UserEvent,
    UserSession,
    UserState,
    Users,
    WardrobeItems,
    WardrobeCategories,
    WardrobeWearEvents,
    WardrobeWearGroups,
    Colors,
    Materials,
    DiscoveryEvent,
)

_ENGINE_VERSION = "rules-v1"

# Reserved `products.attributes` key holding validated stable identifiers
# (e.g. ``{"gtin": "0004006381333931"}``). Fashion attributes live at the top
# level; this key is what the identity lookup queries.
_IDENTIFIERS_KEY = "identifiers"


def _canonical_uuid_string(value: object) -> Optional[str]:
    """Canonical lowercase UUID string, or None when unparseable.

    Saved-outfit `snapshot.selectedItemIds` entries are validated at save
    time, but legacy rows may hold anything — malformed entries are ignored
    by coverage, never fatal.
    """
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except (ValueError, TypeError):
        return None


def _worn_rank(instant: datetime | None, *, descending: bool) -> tuple[bool, float]:
    """Rank key for an optional last-worn instant (STEP 15.6).

    Ascending sort on the returned key orders instants oldest-first with
    never-worn (None) FIRST when `descending` is False (least-worn), and
    newest-first with never-worn LAST when True (most/recently-worn).
    Callers append the canonical item id string as the final tiebreak.
    """
    if instant is None:
        return (True, 0.0) if descending else (False, 0.0)
    stamp = instant.timestamp()
    return (False, -stamp) if descending else (True, stamp)


class AnalysisRunRepositorySQL:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        user_id: UUID,
        run_type: str,
        engine_version: str = _ENGINE_VERSION,
        input_media: Optional[dict] = None,
        knowledge_version: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> UUID:
        row = AnalysisRuns(
            user_id=user_id,
            run_type=run_type,
            status="pending",
            engine_version=engine_version,
            knowledge_version=knowledge_version,
            input_media=input_media,
            idempotency_key=idempotency_key,
        )
        try:
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
            return row.id
        except IntegrityError:
            self._session.rollback()
            raise

    def get_for_user(self, *, user_id: UUID, run_id: UUID) -> Optional[AnalysisRunRecord]:
        row = self._session.execute(
            select(AnalysisRuns).where(
                AnalysisRuns.id == run_id, AnalysisRuns.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return self._to_record(row)

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[AnalysisRunRecord]:
        row = self._session.execute(
            select(AnalysisRuns).where(
                AnalysisRuns.user_id == user_id,
                AnalysisRuns.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[AnalysisRunSummary], int]:
        base = select(AnalysisRuns).where(AnalysisRuns.user_id == user_id)
        total = self._session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        rows = self._session.execute(
            base.order_by(AnalysisRuns.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
        return [self._to_summary(r) for r in rows], total

    def complete(
        self, *, run_id: UUID, user_id: UUID, status: str, result: Optional[dict]
    ) -> bool:
        # STEP 11.13: `cast(..., JSONB)` so SQLAlchemy serializes the dict
        # client-side — psycopg3 cannot adapt a raw Python dict, which made
        # every live completion fail (TRX-5 write-once guard itself is
        # unchanged; the server function still receives jsonb).
        outcome = self._session.execute(
            select(
                func.complete_analysis_run(
                    run_id, user_id, status, cast(result, JSONB)
                )
            )
        ).scalar_one()
        self._session.commit()
        return bool(outcome)

    def fail(self, *, run_id: UUID, user_id: UUID, error: Optional[dict]) -> bool:
        """Mark a pending run `failed` with its frozen error body (TRX-5).

        Same STEP 11.13 JSONB cast as `complete` — the raw dict never reaches
        the driver unadapted.
        """
        outcome = self._session.execute(
            select(func.fail_analysis_run(run_id, user_id, cast(error, JSONB)))
        ).scalar_one()
        self._session.commit()
        return bool(outcome)

    @staticmethod
    def _to_record(row: AnalysisRuns) -> AnalysisRunRecord:
        return AnalysisRunRecord(
            id=row.id,
            run_type=row.run_type,
            status=row.status,
            engine_version=row.engine_version,
            created_at=row.created_at,
            completed_at=row.completed_at,
            input_media=row.input_media,
            result=row.result,
            error=row.error,
            knowledge_version=row.knowledge_version,
            idempotency_key=getattr(row, "idempotency_key", None),
        )

    @staticmethod
    def _to_summary(row: AnalysisRuns) -> AnalysisRunSummary:
        return AnalysisRunSummary(
            id=row.id,
            run_type=row.run_type,
            status=row.status,
            engine_version=row.engine_version,
            created_at=row.created_at,
            completed_at=row.completed_at,
            input_media=row.input_media,
            knowledge_version=getattr(row, "knowledge_version", None),
        )


class UserStateRepositorySQL:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_style_profile(self, *, user_id: UUID) -> Optional[dict]:
        row = self._session.execute(
            select(UserState.style_profile).where(UserState.user_id == user_id)
        ).scalar_one_or_none()
        return row or None

    def update_style_profile(
        self,
        *,
        user_id: UUID,
        face_shape: Optional[str] = None,
        skin_tone: Optional[str] = None,
        body_type: Optional[str] = None,
        style_type: Optional[str] = None,
        source_run_id: Optional[str] = None,
    ) -> None:
        """Merge non-empty image-derived appearance attributes into user_state.style_profile (C-09).

        Uses PostgreSQL `||` JSONB concatenation (`existing || patch`) so previously known
        attributes and any unrelated keys survive partial vision analysis runs.
        Only non-empty incoming strings replace existing values; empty strings, missing keys,
        or nulls do not erase existing data. `source_run_id` is updated to the latest successful run.
        """
        patch: dict[str, Any] = {}
        for key, val in (
            ("face_shape", face_shape),
            ("skin_tone", skin_tone),
            ("body_type", body_type),
            ("style_type", style_type),
        ):
            if val is not None and isinstance(val, str) and val.strip() != "":
                patch[key] = val
        if source_run_id is not None and str(source_run_id).strip() != "":
            patch["source_run_id"] = str(source_run_id)

        if not patch:
            return

        self._session.execute(
            update(UserState)
            .where(UserState.user_id == user_id)
            .values(
                style_profile=func.coalesce(
                    UserState.style_profile, cast({}, JSONB)
                ).op("||")(cast(patch, JSONB))
            )
        )
        self._session.commit()

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]:
        row = self._session.execute(
            select(Users, UserState)
            .join(UserState, UserState.user_id == Users.id)
            .where(UserState.user_id == user_id)
        ).one_or_none()
        if row is None:
            return None
        user, state = row
        return UserProfileRecord(
            user_id=user.id,
            display_name=user.display_name,
            style_profile=state.style_profile or {},
            preferences=state.preferences or {},
            settings={},
            flags=state.flags or {},
            version=state.version,
        )

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None:
        """Merge a JSONB patch into `user_state.preferences` (STEP 11.6).

        Uses PostgreSQL `||` concatenation (`existing || patch`) so sibling
        keys survive — the object is never wholesale replaced. The write is
        owner-scoped to the authenticated `user_id` row (OW-1); when no such
        row exists the statement matches nothing (callers surface 404 via
        `get_profile`). `style_profile` (TRX-6) is untouched.
        """
        self._session.execute(
            update(UserState)
            .where(UserState.user_id == user_id)
            .values(
                preferences=UserState.preferences.op("||")(
                    cast(preferences, JSONB)
                )
            )
        )
        self._session.commit()


class SavedLookRepositorySQL:
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def insert(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        source_context: str,
        snapshot: dict,
        idempotency_key: str,
        source_run_id: Optional[UUID],
    ) -> SavedLookRecord:
        row = SavedLooks(
            user_id=user_id,
            look_id=look_id,
            title=title,
            source_context=source_context,
            snapshot=snapshot,
            idempotency_key=idempotency_key,
            source_run_id=source_run_id,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_record(row)

    def get_for_user(self, *, user_id: UUID, saved_look_id: UUID) -> Optional[SavedLookRecord]:
        row = self._session.execute(
            select(SavedLooks).where(
                SavedLooks.id == saved_look_id, SavedLooks.user_id == user_id
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[SavedLookRecord]:
        row = self._session.execute(
            select(SavedLooks).where(
                SavedLooks.user_id == user_id,
                SavedLooks.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[SavedLookRecord], int]:
        base = select(SavedLooks).where(SavedLooks.user_id == user_id)
        total = self._session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        rows = self._session.execute(
            base.order_by(SavedLooks.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
        return [self._to_record(r) for r in rows], total

    def count_for_user(self, *, user_id: UUID) -> int:
        row = self._session.execute(
            select(func.count())
            .select_from(SavedLooks)
            .where(SavedLooks.user_id == user_id)
        ).scalar_one()
        return int(row) if row is not None else 0

    def get_outfit_coverage(self, *, user_id: UUID) -> SavedLookCoverage:

        """Deterministic saved-outfit coverage facts for one owner (W-7/UC-14).

        Read-only: selects only the `snapshot` column of the owner's
        `source_context == "outfit"` rows (id order, so iteration is
        stable), canonicalizes `snapshot.selectedItemIds` defensively, and
        resolves survivors against the owner's current `wardrobe_items` in
        one owner-scoped query. Hairstyle/grooming/legacy rows never
        contribute; malformed entries and stale (deleted) IDs are ignored,
        never fatal — so the insight endpoint cannot 500 on old data.
        """
        snapshots = self._session.execute(
            select(SavedLooks.snapshot)
            .where(
                SavedLooks.user_id == user_id,
                SavedLooks.source_context == "outfit",
            )
            .order_by(SavedLooks.id)
        ).scalars().all()
        referenced: set[str] = set()
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            raw_ids = snapshot.get("selectedItemIds")
            if not isinstance(raw_ids, list):
                continue
            for raw in raw_ids:
                canonical = _canonical_uuid_string(raw)
                if canonical is not None:
                    referenced.add(canonical)
        represented_ids: set[str] = set()
        represented_categories: dict[str, int] = {}
        if referenced:
            rows = self._session.execute(
                select(WardrobeItems.id, WardrobeItems.category_id).where(
                    WardrobeItems.user_id == user_id,
                    WardrobeItems.id.in_(
                        [UUID(value) for value in sorted(referenced)]
                    ),
                )
            ).all()
            for item_id, category_id in rows:
                represented_ids.add(str(item_id))
                represented_categories[category_id] = (
                    represented_categories.get(category_id, 0) + 1
                )
        return SavedLookCoverage(
            saved_outfit_count=len(snapshots),
            represented_item_ids=frozenset(sorted(represented_ids)),
            represented_categories=dict(sorted(represented_categories.items())),
        )

    def delete(
        self, *, user_id: UUID, saved_look_id: UUID
    ) -> None:
        row = self._session.execute(
            select(SavedLooks).where(
                SavedLooks.id == saved_look_id, SavedLooks.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    @staticmethod
    def _to_record(row: SavedLooks) -> SavedLookRecord:
        return SavedLookRecord(
            id=row.id,
            look_id=row.look_id,
            title=row.title,
            source_context=row.source_context,
            snapshot=row.snapshot,
            source_run_id=row.source_run_id,
            created_at=row.created_at,
        )


class LearningSignalRepositorySQL:
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def insert_look_saved(
        self,
        *,
        user_id: UUID,
        signal_type: str = "look_saved",
        label: str,
        context: Optional[dict],
    ) -> None:
        """Persist one learning-signal row with the requested type verbatim.

        Validity is enforced by the existing `signal_types` FK (`RESTRICT`):
        unknown codes raise on flush and store nothing — no new vocabulary
        source, no silent fallback. Owner scoping comes from the caller-supplied
        `user_id` (OW-1), matching every other repository here.
        """
        self._session.add(
            LearningSignals(
                user_id=user_id,
                signal_type=signal_type,
                label=label,
                context=context,
            )
        )
        self._session.flush()

    def list_recent_labels(self, *, user_id: UUID, limit: int) -> list[str]:
        """Newest-first owned signal labels (M10-B recents, DEC-020 §E).

        `occurred_at` desc with `id` desc as the deterministic tiebreak;
        at most `limit` rows, fewer when history is short, `[]` when
        empty. SELECT-only — label strings leave this method; type,
        context, and timestamps never do.
        """
        return list(
            self._session.execute(
                select(LearningSignals.label)
                .where(LearningSignals.user_id == user_id)
                .order_by(
                    LearningSignals.occurred_at.desc(),
                    LearningSignals.id.desc(),
                )
                .limit(limit)
            ).scalars()
        )


class ActivityDayRepositorySQL:
    """SQL streak-history adapter (E9, P1, M10-A).

    The upsert executes on the caller's session without committing: the
    owning use case's existing commit covers the signal INSERT and this
    upsert together (DEC-020 §F, same-commit rule). Owner scoping comes
    from the caller-supplied `user_id` (OW-1), matching every other
    repository here.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_styled_day(self, *, user_id: UUID, day: date) -> None:
        """Mark the user's calendar day styled (idempotent per day).

        `ON CONFLICT (user_id, day) DO UPDATE styled=true`: a repeated
        same-day write keeps exactly one row and can never double-count
        the streak (BC-4). `summary` is never touched — NULL in M10 v1.
        """
        stmt = (
            pg_insert(ActivityDays)
            .values(user_id=user_id, day=day, styled=True)
            .on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={"styled": True},
            )
        )
        self._session.execute(stmt)

    def list_styled_days(self, *, user_id: UUID) -> list[date]:
        """Return the user's styled days in ascending order (owner-scoped)."""
        return list(
            self._session.execute(
                select(ActivityDays.day)
                .where(
                    ActivityDays.user_id == user_id,
                    ActivityDays.styled.is_(True),
                )
                .order_by(ActivityDays.day.asc())
            ).scalars()
        )


class WardrobeItemRepositorySQL:
    """SQLAlchemy repository implementation for wardrobe items (OW-1 owner-scoping)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        category: Optional[str] = None,
        color: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
    ) -> tuple[list["WardrobeItemRecord"], int]:
        base = select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        if category is not None:
            base = base.where(WardrobeItems.category_id == category)
        if color is not None:
            base = base.where(WardrobeItems.color_id == color)
        total = self._session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        sort_columns = {
            "created_at": WardrobeItems.created_at,
            "updated_at": WardrobeItems.updated_at,
            "name": WardrobeItems.name,
        }
        primary = sort_columns.get(sort or "created_at", WardrobeItems.created_at)
        direction = primary.asc() if order == "asc" else primary.desc()
        # Secondary id ordering keeps pagination deterministic on ties.
        rows = self._session.execute(
            base.order_by(direction, WardrobeItems.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
        records = [self._to_record(r) for r in rows]
        return records, total

    def get_by_id(
        self, *, user_id: UUID, item_id: UUID
    ) -> Optional["WardrobeItemRecord"]:
        row = self._session.execute(
            select(WardrobeItems).where(
                WardrobeItems.id == item_id, WardrobeItems.user_id == user_id
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        category: str,
        color: str,
        material: Optional[str],
        isFavorite: bool,
        image_ref: Optional[dict[str, Any]] = None,
        fit: Optional[str] = None,
        fit_confidence: Optional[float] = None,
    ) -> "WardrobeItemRecord":
        row = WardrobeItems(
            user_id=user_id,
            name=name,
            category_id=category,
            color_id=color,
            material_id=material,
            is_favorite=isFavorite,
            image_ref=image_ref,
            fit=fit,
            fit_confidence=fit_confidence,
        )
        self._session.add(row)
        self._session.flush()
        self._session.refresh(row)
        return self._to_record(row)

    def update(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        name: Optional[str],
        category: Optional[str],
        color: Optional[str],
        material: Optional[str],
        material_set: bool = False,
        isFavorite: Optional[bool],
        image_ref: Optional[dict[str, Any]] = None,
        image_ref_set: bool = False,
        fit: Optional[str] = None,
        fit_set: bool = False,
        fit_confidence: Optional[float] = None,
        fit_confidence_set: bool = False,
    ) -> Optional["WardrobeItemRecord"]:
        row = self._session.execute(
            select(WardrobeItems).where(
                WardrobeItems.id == item_id, WardrobeItems.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if name is not None:
            row.name = name
        if category is not None:
            row.category_id = category
        if color is not None:
            row.color_id = color
        if material_set:
            # Explicit null clears the optional material; an omitted field
            # never reaches here (the use case passes material_set=False).
            row.material_id = material
        if isFavorite is not None:
            row.is_favorite = isFavorite
        if image_ref_set:
            # Explicit null clears the image reference; an omitted field
            # never reaches here (the use case passes image_ref_set=False).
            row.image_ref = image_ref
        if fit_set:
            # Explicit null clears the observed fit; an omitted field never
            # reaches here (the use case passes fit_set=False).
            row.fit = fit
        if fit_confidence_set:
            # Explicit null clears the fit confidence; an omitted field never
            # reaches here (the use case passes fit_confidence_set=False).
            row.fit_confidence = fit_confidence
        # W-4 contract: the server refreshes updatedAt on every update.
        row.updated_at = func.now()
        self._session.flush()
        self._session.refresh(row)
        return self._to_record(row)

    def delete(
        self, *, user_id: UUID, item_id: UUID
    ) -> None:
        row = self._session.execute(
            select(WardrobeItems).where(
                WardrobeItems.id == item_id, WardrobeItems.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def get_insight_summary(self, *, user_id: UUID) -> "WardrobeInsightSummary":
        """One aggregate query: per-category counts + favorites, owner-scoped.

        Read-only; no rows loaded. Inactive vocabulary codes are excluded so
        retired categories are never reported as gaps.
        """
        rows = self._session.execute(
            select(
                WardrobeCategories.code,
                func.count(WardrobeItems.id),
                func.count(WardrobeItems.id).filter(
                    WardrobeItems.is_favorite.is_(True)
                ),
            )
            .outerjoin(
                WardrobeItems,
                and_(
                    WardrobeItems.category_id == WardrobeCategories.code,
                    WardrobeItems.user_id == user_id,
                ),
            )
            .where(WardrobeCategories.active.is_(True))
            .group_by(WardrobeCategories.code)
            .order_by(WardrobeCategories.code)
        ).all()
        counts = {code: item_count for code, item_count, _ in rows}
        favorites = sum(fav_count for _, _, fav_count in rows)
        return WardrobeInsightSummary(
            total=sum(counts.values()),
            favorite_count=favorites,
            counts_by_category=counts,
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _to_record(row: WardrobeItems) -> "WardrobeItemRecord":
        return WardrobeItemRecord(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            category=row.category_id,
            color=row.color_id,
            material=row.material_id,
            is_favorite=row.is_favorite,
            fit=row.fit,
            fit_confidence=row.fit_confidence,
            image_ref=row.image_ref,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class WearEventRepositorySQL:
    """SQLAlchemy repository implementation for wear events (STEP 15.4).

    Owner-scoped (OW-1) like every other repository here. `wardrobe_item_id`
    is a plain UUID with no ORM relationship — the use case validates each
    ID against the owner's current wardrobe before logging, and reads never
    join items (stale UUIDs simply resolve to nothing downstream).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def log(
        self,
        *,
        user_id: UUID,
        wardrobe_item_id: UUID,
        worn_at,
        wear_group_id: UUID,
        idempotency_key: str,
    ) -> "WearEventRecord":
        row = WardrobeWearEvents(
            user_id=user_id,
            wardrobe_item_id=wardrobe_item_id,
            worn_at=worn_at,
            wear_group_id=wear_group_id,
            idempotency_key=idempotency_key,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_record(row)

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> list["WearEventRecord"]:
        rows = self._session.execute(
            select(WardrobeWearEvents)
            .where(
                WardrobeWearEvents.user_id == user_id,
                WardrobeWearEvents.idempotency_key == idempotency_key,
            )
            .order_by(WardrobeWearEvents.wardrobe_item_id)
        ).scalars().all()
        return [self._to_record(r) for r in rows]

    def list_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        item_id: Optional[UUID] = None,
    ) -> tuple[list["WearEventRecord"], int]:
        base = select(WardrobeWearEvents).where(
            WardrobeWearEvents.user_id == user_id
        )
        if item_id is not None:
            base = base.where(WardrobeWearEvents.wardrobe_item_id == item_id)
        total = self._session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        # worn_at desc, id asc tiebreak — deterministic pagination on ties
        # (a multi-item POST shares one worn_at across its rows).
        rows = self._session.execute(
            base.order_by(
                WardrobeWearEvents.worn_at.desc(), WardrobeWearEvents.id.asc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
        return [self._to_record(r) for r in rows], total

    def get_wear_summary(
        self, *, user_id: UUID, recent_since: datetime
    ) -> "WearSummary":
        """Read-only wear-intelligence facts for one owner (STEP 15.6).

        One aggregate query over the FLAT `wardrobe_wear_events` rows LEFT
        JOINed from the owner's current `wardrobe_items` — per-item COUNT
        and MAX(worn_at) computed in SQL, no event rows loaded. The join
        direction is the whole grounding story: unworn items appear with
        count 0 / last-worn None, while historical rows whose item no
        longer exists match nothing and are ignored (the ledger
        `wardrobe_wear_groups.item_ids` is never read). Both sides are
        owner-scoped. Grouping the per-item aggregates into rankings and
        category frequencies happens over at most one row per wardrobe
        item — never over the event history.
        """
        rows = self._session.execute(
            select(
                WardrobeItems.id,
                WardrobeItems.category_id,
                func.count(WardrobeWearEvents.id),
                func.max(WardrobeWearEvents.worn_at),
            )
            .select_from(WardrobeItems)
            .outerjoin(
                WardrobeWearEvents,
                and_(
                    WardrobeWearEvents.wardrobe_item_id == WardrobeItems.id,
                    WardrobeWearEvents.user_id == user_id,
                ),
            )
            .where(WardrobeItems.user_id == user_id)
            .group_by(WardrobeItems.id, WardrobeItems.category_id)
            .order_by(WardrobeItems.id)
        ).all()
        counts: dict[str, int] = {}
        last_worn: dict[str, Optional[datetime]] = {}
        categories: dict[str, int] = {}
        for item_id, category_id, count, max_worn in rows:
            key = str(item_id)
            instant = max_worn
            if instant is not None and instant.tzinfo is not None:
                instant = instant.astimezone(timezone.utc)
            counts[key] = count
            last_worn[key] = instant
            categories[category_id] = categories.get(category_id, 0) + count
        total = sum(counts.values())
        if counts:
            peak = max(counts.values())
            floor = min(counts.values())
        else:
            peak = floor = 0
        most = (
            []
            if total == 0
            else sorted(
                (key for key, count in counts.items() if count == peak),
                key=lambda key: (_worn_rank(last_worn[key], descending=True), key),
            )
        )
        least = sorted(
            (key for key, count in counts.items() if count == floor),
            key=lambda key: (_worn_rank(last_worn[key], descending=False), key),
        )
        unworn = sorted(key for key, count in counts.items() if count == 0)
        recent = sorted(
            (
                key
                for key, instant in last_worn.items()
                if instant is not None and instant >= recent_since
            ),
            key=lambda key: (_worn_rank(last_worn[key], descending=True), key),
        )
        return WearSummary(
            total_wears=total,
            wear_counts=counts,
            last_worn=last_worn,
            most_worn_item_ids=most,
            least_worn_item_ids=least,
            unworn_item_ids=unworn,
            recently_worn_item_ids=recent,
            wears_by_category=dict(sorted(categories.items())),
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _to_record(row: WardrobeWearEvents) -> "WearEventRecord":
        # Normalize to UTC: psycopg returns timestamptz in the connection's
        # TimeZone, so without this a fresh insert (UTC) and its idempotent
        # replay (DB zone) would render the same instant differently —
        # byte-identical replay requires one stable zone.
        worn_at = row.worn_at
        if worn_at is not None and worn_at.tzinfo is not None:
            worn_at = worn_at.astimezone(timezone.utc)
        created_at = row.created_at
        if created_at is not None and created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc)
        return WearEventRecord(
            id=row.id,
            user_id=row.user_id,
            wardrobe_item_id=row.wardrobe_item_id,
            worn_at=worn_at,
            wear_group_id=row.wear_group_id,
            idempotency_key=row.idempotency_key,
            created_at=created_at,
        )


class WearGroupRepositorySQL:
    """SQLAlchemy repository for the wear-action ledger (STEP 15.4B).

    Owner-scoped (OW-1). The `create_group` insert is the whole-request
    idempotency arbiter: `UNIQUE(user_id, idempotency_key)` makes
    concurrent same-key writers serialize on the index — the loser gets an
    `IntegrityError` only after the winner's transaction ends, so a
    rollback followed by `get_by_idempotency` always observes the durable
    outcome (replay vs 409). No generic idempotency framework.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_group(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        item_ids: list[str],
        worn_at,
    ) -> "WearGroupRecord":
        row = WardrobeWearGroups(
            user_id=user_id,
            idempotency_key=idempotency_key,
            item_ids=list(item_ids),
            worn_at=worn_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_record(row)

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional["WearGroupRecord"]:
        row = self._session.execute(
            select(WardrobeWearGroups).where(
                WardrobeWearGroups.user_id == user_id,
                WardrobeWearGroups.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _to_record(row: WardrobeWearGroups) -> "WearGroupRecord":
        # Same UTC normalization as wear rows: byte-identical replay needs
        # one stable zone regardless of the connection TimeZone.
        worn_at = row.worn_at
        if worn_at is not None and worn_at.tzinfo is not None:
            worn_at = worn_at.astimezone(timezone.utc)
        created_at = row.created_at
        if created_at is not None and created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc)
        return WearGroupRecord(
            id=row.id,
            user_id=row.user_id,
            idempotency_key=row.idempotency_key,
            item_ids=list(row.item_ids or []),
            worn_at=worn_at,
            created_at=created_at,
        )


class VocabularyRepositorySQL:
    """SQLAlchemy read of one system vocabulary table (M5 `#19`/`#20`).

    System-owned, never user-scoped (KN-2/KN-9): only `active` rows, in
    deterministic `(sort_order, code)` order. Read-only — no commit, no
    write, no user data. `model` is `WardrobeCategories` or `Colors`
    (identical vocab columns).
    """

    def __init__(self, session: Session, model) -> None:
        self._session = session
        self._model = model

    def list_active(self) -> list["VocabularyRecord"]:
        rows = self._session.execute(
            select(self._model)
            .where(self._model.active.is_(True))
            .order_by(self._model.sort_order.asc(), self._model.code.asc())
        ).scalars().all()
        return [
            VocabularyRecord(code=row.code, label=row.label, sort_order=row.sort_order)
            for row in rows
        ]


class UserEventRepositorySQL:
    """SQLAlchemy event-calendar adapter — OW-1 owner-scoping (M8-A).

    All row methods are owner-scoped (`user_id`) and commit-free: the
    owning use case commits (SavedLook precedent). `flush` exposes
    server-generated ids/timestamps without committing. No signal
    writes, no preference writes (R36 lives in the use case, DEC-015).

    List ordering is deterministic: `event_date` in the requested
    direction, `event_time` the same direction with NULLS LAST
    explicit, then `id` asc as the final tiebreak.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def create(
        self,
        *,
        user_id: UUID,
        title: str,
        event_type: str,
        event_date: date,
        event_time: Optional[time] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> UserEventRecord:
        row = UserEvent(
            user_id=user_id,
            title=title,
            event_type_id=event_type,
            event_date=event_date,
            event_time=event_time,
            location=location,
            notes=notes,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_record(row)

    def get_for_user(self, *, user_id: UUID, event_id: UUID) -> Optional[UserEventRecord]:
        row = self._session.execute(
            select(UserEvent).where(
                UserEvent.id == event_id, UserEvent.user_id == user_id
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def list_for_user(
        self,
        *,
        user_id: UUID,
        from_date: Optional[date] = None,
        order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserEventRecord], int]:
        base = select(UserEvent).where(UserEvent.user_id == user_id)
        if from_date is not None:
            base = base.where(UserEvent.event_date >= from_date)
        total = self._session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        date_col = UserEvent.event_date.asc() if order == "asc" else UserEvent.event_date.desc()
        time_col = UserEvent.event_time.asc().nullslast() if order == "asc" else UserEvent.event_time.desc().nullslast()
        rows = self._session.execute(
            base.order_by(date_col, time_col, UserEvent.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
        return [self._to_record(r) for r in rows], total

    def update(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        title: str,
        event_type: str,
        event_date: date,
        event_time: Optional[time] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[UserEventRecord]:
        row = self._session.execute(
            select(UserEvent).where(
                UserEvent.id == event_id, UserEvent.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.title = title
        row.event_type_id = event_type
        row.event_date = event_date
        row.event_time = event_time
        row.location = location
        row.notes = notes
        # M8-B contract: the server refreshes updatedAt on every update
        # (wardrobe W-4 precedent).
        row.updated_at = func.now()
        self._session.flush()
        self._session.refresh(row)
        return self._to_record(row)

    def delete(
        self, *, user_id: UUID, event_id: UUID
    ) -> None:
        row = self._session.execute(
            select(UserEvent).where(
                UserEvent.id == event_id, UserEvent.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    @staticmethod
    def _to_record(row: UserEvent) -> UserEventRecord:
        return UserEventRecord(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            event_type=row.event_type_id,
            event_date=row.event_date,
            event_time=row.event_time,
            location=row.location,
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class EventTypeRepositorySQL:
    """SQLAlchemy read of the M8 `event_types` vocabulary (M8-A).

    System-owned, never user-scoped (K9.1): only `active` rows, in
    deterministic `(sort_order, code)` order (DEC-015, Vocabulary
    precedent). Read-only — no commit, no write, no user data.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active(self) -> list["VocabularyRecord"]:
        rows = self._session.execute(
            select(EventType)
            .where(EventType.active.is_(True))
            .order_by(EventType.sort_order.asc(), EventType.code.asc())
        ).scalars().all()
        return [
            VocabularyRecord(code=row.code, label=row.label, sort_order=row.sort_order)
            for row in rows
        ]

    def get_by_code(self, *, code: str) -> Optional["VocabularyRecord"]:
        row = self._session.execute(
            select(EventType).where(
                EventType.code == code, EventType.active.is_(True)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return VocabularyRecord(code=row.code, label=row.label, sort_order=row.sort_order)


class FeedbackRepositorySQL:
    """SQLAlchemy append-only store for M11 reactions (UC-32).

    One INSERT per submit (tier 1); idempotent replay is keyed by
    `(user_id, idempotency_key)` (M7 precedent). No commit inside row
    methods — the owning use case commits.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_record(row: FeedbackEvents) -> FeedbackEventRecord:
        return FeedbackEventRecord(
            id=row.id,
            user_id=row.user_id,
            target_look_id=row.target_look_id,
            target_saved_look_id=row.target_saved_look_id,
            rating=row.rating,
            reason=row.reason,
            idempotency_key=row.idempotency_key,
            occurred_at=row.occurred_at,
        )

    def insert(
        self,
        *,
        user_id: UUID,
        target_look_id: Optional[str],
        target_saved_look_id: Optional[UUID],
        rating: str,
        reason: Optional[str],
        idempotency_key: str,
    ) -> FeedbackEventRecord:
        row = FeedbackEvents(
            user_id=user_id,
            target_look_id=target_look_id,
            target_saved_look_id=target_saved_look_id,
            rating=rating,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_record(row)

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[FeedbackEventRecord]:
        row = self._session.execute(
            select(FeedbackEvents).where(
                FeedbackEvents.user_id == user_id,
                FeedbackEvents.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    def list_for_user(
        self, *, user_id: UUID, limit: int = 100
    ) -> list[FeedbackEventRecord]:
        rows = (
            self._session.execute(
                select(FeedbackEvents)
                .where(FeedbackEvents.user_id == user_id)
                .order_by(FeedbackEvents.occurred_at.asc(), FeedbackEvents.id.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [self._to_record(row) for row in rows]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class LookRepositorySQL:
    """SQLAlchemy existence read for catalog looks (M11 target check).

    System-owned, never user-scoped (KN catalog): resolves a submitted
    `targetLookId` to its canonical code. Read-only — no commit, no
    write, no user data.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_code(self, *, code: str) -> Optional[str]:
        row = self._session.get(Looks, code)
        if row is None:
            return None
        return row.code


class AuthRepositorySQL:
    """Account + session persistence for the auth module (D-AUTH-1, M1).

    Identity is always the opaque (provider, subject) pair (BC-1); the
    bearer token itself is never persisted — sessions are keyed by its
    SHA-256 digest. Session revocation is revoke-only (a timestamp, no
    row edit otherwise); account deletion cascades to sessions at the
    FK (TRX-8), so no explicit session cleanup exists here.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_account(
        self, *, auth_provider: str, auth_subject: str
    ) -> Optional[AuthAccountRecord]:
        row = self._session.execute(
            select(Users).where(
                Users.auth_provider == auth_provider,
                Users.auth_subject == auth_subject,
            )
        ).scalar_one_or_none()
        return self._to_account(row) if row is not None else None

    def create_account(
        self,
        *,
        auth_provider: str,
        auth_subject: str,
        display_name: str,
        password_hash: Optional[str],
        idempotency_key: Optional[str],
    ) -> AuthAccountRecord:
        user = Users(
            auth_provider=auth_provider,
            auth_subject=auth_subject,
            display_name=display_name,
            password_hash=password_hash,
            register_idempotency_key=idempotency_key,
        )
        self._session.add(user)
        self._session.flush()
        self._session.add(UserState(user_id=user.id))
        self._session.flush()
        self._session.refresh(user)
        return self._to_account(user)

    def create_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        token_digest: str,
        expires_at: datetime,
    ) -> AuthSessionRecord:
        row = UserSession(
            id=session_id,
            user_id=user_id,
            token_digest=token_digest,
            expires_at=expires_at,
        )
        self._session.add(row)
        self._session.flush()
        self._session.refresh(row)
        return self._to_session(row)

    def find_session(
        self, *, token_digest: str
    ) -> Optional[AuthSessionRecord]:
        row = self._session.execute(
            select(UserSession).where(UserSession.token_digest == token_digest)
        ).scalar_one_or_none()
        return self._to_session(row) if row is not None else None

    def revoke_session(self, *, session_id: UUID) -> None:
        self._session.execute(
            update(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=func.now())
        )

    def delete_account(self, *, user_id: UUID) -> bool:
        """Delete one account; DB CASCADE removes all user-owned rows (TRX-8).

        Returns False when the account is already gone (caller maps to
        404 — idempotent erasure). Knowledge/vocabulary rows survive:
        they carry no user FK (RESTRICT/SET NULL guards hold).
        """
        row = self._session.execute(
            select(Users).where(Users.id == user_id)
        ).scalar_one_or_none()
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _to_account(row: Users) -> AuthAccountRecord:
        return AuthAccountRecord(
            user_id=row.id,
            auth_provider=row.auth_provider,
            auth_subject=row.auth_subject,
            display_name=row.display_name,
            password_hash=row.password_hash,
            register_idempotency_key=row.register_idempotency_key,
        )

    @staticmethod
    def _to_session(row: UserSession) -> AuthSessionRecord:
        return AuthSessionRecord(
            id=row.id,
            user_id=row.user_id,
            token_digest=row.token_digest,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )


class DiscoveryRepositorySQL:
    """Discovery collection persistence (D3).

    Each method is one committed unit of work, so a partially completed run
    keeps the records it already persisted and its counters stay truthful.
    ``upsert_product`` keys a canonical product by the unique
    ``product_source_map(source, source_product_id)`` identity — no
    name-based cross-source merging.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_run(self, *, source: str) -> UUID:
        run = CollectionRun(source=source)
        self._session.add(run)
        self._session.commit()
        return run.id

    def insert_raw_if_absent(
        self,
        *,
        run_id: UUID,
        source: str,
        source_record_id: Optional[str],
        payload: object,
        payload_hash: str,
        source_timestamp: Optional[datetime],
    ) -> tuple[UUID, bool]:
        row = RawSourceRecord(
            collection_run_id=run_id,
            source=source,
            source_record_id=source_record_id,
            payload=payload,
            payload_hash=payload_hash,
            source_timestamp=source_timestamp,
        )
        self._session.add(row)
        try:
            self._session.commit()
            return row.id, True
        except IntegrityError:
            # uq_raw_source_records_source_payload_hash — identical payload
            # already stored; return the existing row instead of duplicating.
            self._session.rollback()
            existing_id = self._session.execute(
                select(RawSourceRecord.id).where(
                    RawSourceRecord.source == source,
                    RawSourceRecord.payload_hash == payload_hash,
                )
            ).scalar_one()
            return existing_id, False

    def mark_raw(self, *, raw_id: UUID, status: str, error: Optional[str]) -> None:
        self._session.execute(
            update(RawSourceRecord)
            .where(RawSourceRecord.id == raw_id)
            .values(
                processing_status=status,
                processing_error=error,
                updated_at=func.now(),
            )
        )
        self._session.commit()

    @staticmethod
    def _db_attributes(product: NormalizedProduct) -> dict:
        """Fashion attributes plus the reserved validated-identifier sub-key."""
        identifiers: dict = {}
        if product.gtin:
            identifiers["gtin"] = product.gtin
        if product.manufacturer_id:
            identifiers["manufacturer_id"] = product.manufacturer_id
        if not identifiers:
            return dict(product.attributes)
        return {**product.attributes, _IDENTIFIERS_KEY: identifiers}

    def _update_product_fields(self, product_id: UUID, product: NormalizedProduct) -> None:
        """Refresh canonical fields from a newer observation of the same identity.

        Required fields (title) are always refreshed; optional fields are only
        overwritten when the new observation actually provides them, so a
        sparse payload never erases valid data. Attributes are merged key-wise.
        """
        row = self._session.get(Product, product_id)
        row.title = product.title
        for attr in ("brand", "category", "subcategory", "currency", "product_url"):
            value = getattr(product, attr)
            if value is not None:
                setattr(row, attr, value)
        if product.price is not None:
            row.price = product.price
        if product.availability is not None:
            row.availability = product.availability
        if product.image_urls:
            row.image_urls = list(product.image_urls)
        new_attributes = self._db_attributes(product)
        merged = dict(row.attributes or {})
        for key, value in new_attributes.items():
            if key == _IDENTIFIERS_KEY and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        if merged:
            row.attributes = merged
        row.last_verified_at = func.now()

    def _product_id_by_gtin(self, gtin: Optional[str]) -> Optional[UUID]:
        if not gtin:
            return None
        return self._session.execute(
            select(Product.id)
            .where(Product.attributes[_IDENTIFIERS_KEY]["gtin"].astext == gtin)
            .limit(1)
        ).scalar_one_or_none()

    def _possible_match_product_ids(self, product: NormalizedProduct) -> tuple[UUID, ...]:
        if not product.brand or not product.category:
            return ()
        rows = (
            self._session.execute(
                select(Product.id)
                .where(
                    func.lower(Product.brand) == product.brand.lower(),
                    func.lower(Product.category) == product.category.lower(),
                )
                .limit(5)
            )
            .scalars()
            .all()
        )
        return tuple(rows)

    def _record_observation(
        self,
        *,
        product_id: UUID,
        product: NormalizedProduct,
        run_id: UUID,
        source: str,
        source_product_id: str,
        raw_id: UUID,
        payload_hash: str,
    ) -> None:
        """Append one observation row in the current (uncommitted) transaction.

        ``observed_at`` is left to the database's ``now()`` (collection time);
        ``source_timestamp`` records the source's own publication/update time
        only when it actually supplied one. Optional metrics stay NULL when
        absent (never zero).
        """
        self._session.add(
            ProductObservation(
                product_id=product_id,
                source=source,
                source_product_id=source_product_id,
                collection_run_id=run_id,
                raw_source_record_id=raw_id,
                payload_hash=payload_hash,
                source_timestamp=product.observed_at,
                price=product.price,
                currency=product.currency,
                availability=product.availability,
            )
        )

    def upsert_product(
        self,
        *,
        product: NormalizedProduct,
        run_id: UUID,
        source: str,
        source_product_id: str,
        raw_id: UUID,
        payload_hash: str,
    ) -> IdentityDecision:
        mapping = self._session.execute(
            select(ProductSourceMap).where(
                ProductSourceMap.source == source,
                ProductSourceMap.source_product_id == source_product_id,
            )
        ).scalar_one_or_none()

        if mapping is not None:
            # Exact source identity re-observed: refresh canonical values but
            # keep first_seen_at (discovery time) intact. The new observation
            # records the change history.
            self._update_product_fields(mapping.product_id, product)
            mapping.raw_source_record_id = raw_id
            mapping.observed_at = product.observed_at
            self._record_observation(
                product_id=mapping.product_id,
                product=product,
                run_id=run_id,
                source=source,
                source_product_id=source_product_id,
                raw_id=raw_id,
                payload_hash=payload_hash,
            )
            self._session.commit()
            return IdentityDecision(MATCH_EXACT, mapping.product_id)

        decision = resolve_identity(
            product,
            IdentityCandidates(
                stable_id_product_id=self._product_id_by_gtin(product.gtin),
                possible_match_product_ids=self._possible_match_product_ids(product),
            ),
        )

        if decision.match_status == MATCH_VERIFIED:
            # Verified cross-source listing: attach another mapping to the
            # existing product. Its canonical fields belong to the first
            # listing and are NOT overwritten by a different source.
            self._session.add(
                ProductSourceMap(
                    product_id=decision.product_id,
                    source=source,
                    source_product_id=source_product_id,
                    raw_source_record_id=raw_id,
                    observed_at=product.observed_at,
                )
            )
            self._record_observation(
                product_id=decision.product_id,
                product=product,
                run_id=run_id,
                source=source,
                source_product_id=source_product_id,
                raw_id=raw_id,
                payload_hash=payload_hash,
            )
            self._session.commit()
            return decision

        row = Product(
            title=product.title,
            brand=product.brand,
            category=product.category,
            subcategory=product.subcategory,
            attributes=self._db_attributes(product),
            price=product.price,
            currency=product.currency,
            availability=product.availability,
            product_url=product.product_url,
            image_urls=list(product.image_urls),
        )
        self._session.add(row)
        self._session.flush()
        self._session.add(
            ProductSourceMap(
                product_id=row.id,
                source=source,
                source_product_id=source_product_id,
                raw_source_record_id=raw_id,
                observed_at=product.observed_at,
            )
        )
        self._record_observation(
            product_id=row.id,
            product=product,
            run_id=run_id,
            source=source,
            source_product_id=source_product_id,
            raw_id=raw_id,
            payload_hash=payload_hash,
        )
        self._session.commit()
        return decision

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        fetched: int,
        inserted: int,
        updated: int,
        skipped: int,
        failed: int,
        error_summary: Optional[str],
    ) -> None:
        if error_summary is not None:
            error_summary = error_summary[:2000]
        self._session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == run_id)
            .values(
                status=status,
                finished_at=func.now(),
                fetched_count=fetched,
                inserted_count=inserted,
                updated_count=updated,
                skipped_count=skipped,
                failed_count=failed,
                error_summary=error_summary,
                updated_at=func.now(),
            )
        )
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _to_catalog_product(row: Product) -> CatalogProductRecord:
        """Convert a SQLAlchemy Product row into an immutable CatalogProductRecord."""
        return CatalogProductRecord(
            id=row.id,
            title=row.title,
            brand=row.brand,
            category=row.category,
            subcategory=row.subcategory,
            attributes=dict(row.attributes or {}),
            price=float(row.price) if row.price is not None else None,
            currency=row.currency,
            availability=row.availability,
            product_url=row.product_url,
            image_urls=tuple(row.image_urls or ()),
            first_seen_at=row.first_seen_at,
            last_verified_at=row.last_verified_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get_by_id(self, product_id: UUID) -> Optional[CatalogProductRecord]:
        """Fetch a single catalog product by its canonical UUID."""
        row = self._session.get(Product, product_id)
        if row is None:
            return None
        return self._to_catalog_product(row)

    def _build_filter_clauses(self, criteria: ProductFilterCriteria) -> list[Any]:
        """Compile hard filter criteria into SQLAlchemy WHERE expressions."""
        clauses: list[Any] = []

        # Synthetic fixture filtering
        if not criteria.include_synthetic:
            clauses.append(
                func.coalesce(
                    cast(Product.attributes["synthetic"].astext, Boolean), False
                ).is_(False)
            )
            clauses.append(
                func.coalesce(
                    cast(Product.attributes["fixture"].astext, Boolean), False
                ).is_(False)
            )

        # Categories inclusion / exclusion
        if criteria.categories:
            clauses.append(
                func.lower(Product.category).in_([c.lower().strip() for c in criteria.categories])
            )
        if criteria.exclude_categories:
            clauses.append(
                func.lower(Product.category).not_in([c.lower().strip() for c in criteria.exclude_categories])
            )

        # Subcategories inclusion / exclusion
        if criteria.subcategories:
            clauses.append(
                func.lower(Product.subcategory).in_([s.lower().strip() for s in criteria.subcategories])
            )
        if criteria.exclude_subcategories:
            clauses.append(
                func.lower(Product.subcategory).not_in([s.lower().strip() for s in criteria.exclude_subcategories])
            )

        # Brands inclusion / exclusion
        if criteria.brands:
            clauses.append(
                func.lower(Product.brand).in_([b.lower().strip() for b in criteria.brands])
            )
        if criteria.exclude_brands:
            clauses.append(
                func.lower(Product.brand).not_in([b.lower().strip() for b in criteria.exclude_brands])
            )

        # Price boundaries
        if criteria.has_price is True:
            clauses.append(Product.price.is_not(None))
        elif criteria.has_price is False:
            clauses.append(Product.price.is_(None))

        if criteria.min_price is not None:
            clauses.append(Product.price >= criteria.min_price)
        if criteria.max_price is not None:
            clauses.append(Product.price <= criteria.max_price)

        # Currency match
        if criteria.currency is not None:
            clauses.append(Product.currency == criteria.currency.strip().upper())

        # Stock / availability
        if criteria.in_stock_only is True:
            clauses.append(Product.availability.is_(True))
        elif criteria.in_stock_only is False:
            clauses.append(Product.availability.is_(False))

        # Images
        if criteria.has_images is True:
            clauses.append(func.jsonb_array_length(Product.image_urls) > 0)
        elif criteria.has_images is False:
            clauses.append(func.jsonb_array_length(Product.image_urls) == 0)

        # Normalized attributes (materials, colors, fits, silhouettes)
        if criteria.materials:
            clauses.append(
                func.lower(Product.attributes["material"].astext).in_(
                    [m.lower().strip() for m in criteria.materials]
                )
            )
        if criteria.colors:
            clauses.append(
                func.lower(Product.attributes["color"].astext).in_(
                    [c.lower().strip() for c in criteria.colors]
                )
            )
        if criteria.fits:
            clauses.append(
                func.lower(Product.attributes["fit"].astext).in_(
                    [f.lower().strip() for f in criteria.fits]
                )
            )
        if criteria.silhouettes:
            clauses.append(
                func.lower(Product.attributes["silhouette"].astext).in_(
                    [s.lower().strip() for s in criteria.silhouettes]
                )
            )

        # Search query (q) across title, brand, category, subcategory
        if criteria.q:
            clean_q = criteria.q.strip()
            if clean_q:
                # Escape SQL LIKE wildcards % and _ and escape character \
                escaped_q = (
                    clean_q.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                pattern = f"%{escaped_q}%"
                clauses.append(
                    or_(
                        Product.title.ilike(pattern, escape="\\"),
                        Product.brand.ilike(pattern, escape="\\"),
                        Product.category.ilike(pattern, escape="\\"),
                        Product.subcategory.ilike(pattern, escape="\\"),
                    )
                )

        return clauses

    @staticmethod
    def _order_by_terms(sort_order: str) -> list[Any]:
        """Deterministic ordering terms; always tie-breaks by Product.id ASC."""
        sort = sort_order.lower().strip()
        if sort in ("newest", "created_at_desc"):
            return [Product.created_at.desc(), Product.id.asc()]
        if sort in ("oldest", "created_at_asc"):
            return [Product.created_at.asc(), Product.id.asc()]
        if sort == "price_asc":
            return [Product.price.asc().nulls_last(), Product.id.asc()]
        if sort == "price_desc":
            return [Product.price.desc().nulls_last(), Product.id.asc()]
        if sort == "title_asc":
            return [Product.title.asc(), Product.id.asc()]
        if sort == "id_asc":
            return [Product.id.asc()]
        return [Product.created_at.desc(), Product.id.asc()]

    def count_candidates(self, criteria: ProductFilterCriteria) -> int:
        """Count total matching catalog candidates under hard filters."""
        clauses = self._build_filter_clauses(criteria)
        stmt = select(func.count(Product.id))
        if clauses:
            stmt = stmt.where(and_(*clauses))
        return int(self._session.execute(stmt).scalar_one())

    def get_candidates(
        self,
        criteria: ProductFilterCriteria,
        *,
        sort_order: str = "newest",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[CatalogProductRecord, ...]:
        """Retrieve a bounded, deterministically ordered slice of catalog candidates."""
        clauses = self._build_filter_clauses(criteria)
        stmt = select(Product)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        order_terms = self._order_by_terms(sort_order)
        stmt = stmt.order_by(*order_terms).offset(max(0, offset)).limit(max(1, limit))
        rows = self._session.execute(stmt).scalars().all()
        return tuple(self._to_catalog_product(row) for row in rows)


ProductCandidateRepositorySQL = DiscoveryRepositorySQL
ProductCatalogRepositorySQL = DiscoveryRepositorySQL


class TrendRepositorySQL:
    """Read-only SQL adapter for the D6 trend engine over ``product_observations``.

    Shapes each observation into :class:`ObservationEvidence`, joining the
    canonical product for its ``category`` concept key and its fixture marker
    (``products.attributes.fixture``). No writes; the window is half-open
    ``[window_start, window_end)`` so adjacent windows never double-count.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def observations_in_window(
        self, *, window_start: datetime, window_end: datetime
    ) -> tuple[ObservationEvidence, ...]:
        is_fixture = func.coalesce(
            cast(Product.attributes["fixture"].astext, Boolean), False
        )
        rows = self._session.execute(
            select(
                ProductObservation.product_id,
                Product.category,
                ProductObservation.source,
                ProductObservation.observed_at,
                ProductObservation.price,
                ProductObservation.availability,
                is_fixture.label("is_fixture"),
            )
            .join(Product, Product.id == ProductObservation.product_id)
            .where(
                ProductObservation.observed_at >= window_start,
                ProductObservation.observed_at < window_end,
            )
            .order_by(ProductObservation.observed_at)
        ).all()
        return tuple(
            ObservationEvidence(
                product_id=row.product_id,
                category=row.category,
                source=row.source,
                observed_at=row.observed_at,
                price=float(row.price) if row.price is not None else None,
                availability=row.availability,
                is_fixture=bool(row.is_fixture),
            )
            for row in rows
        )


class SearchInterestRepositorySQL:
    """SQL adapter for concept-level search-interest observations (D9B).

    Deliberately separate from the product path: no canonical product, no
    price/availability. ``insert_observation`` is one committed unit of work;
    dedup is enforced by the unique raw-record index and the unique natural key,
    so repeated collection never duplicates or inflates a series. Reads are
    half-open on the observation period ``[start, end)`` (fully contained).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_observation(
        self,
        *,
        observation: SearchInterestObservation,
        run_id: UUID,
        raw_id: UUID,
        payload_hash: str,
    ) -> tuple[UUID, bool]:
        row = SearchInterestObservationModel(
            collection_run_id=run_id,
            raw_source_record_id=raw_id,
            source=observation.source,
            metric=observation.metric,
            query_kind=observation.query_kind,
            query_key=observation.query_key,
            query_display=observation.query_display,
            geo_scope=observation.geo_scope,
            geo_scope_type=observation.geo_scope_type,
            aggregation_interval=observation.aggregation_interval,
            period_start=observation.period_start,
            period_end=observation.period_end,
            value=observation.value,
            value_scale=observation.value_scale,
            value_status=observation.value_status,
            is_relative=observation.is_relative,
            source_timestamp=observation.source_timestamp,
            query_config_version=observation.query_config_version,
            synthetic=observation.synthetic,
            payload_hash=payload_hash,
        )
        self._session.add(row)
        try:
            self._session.commit()
            return row.id, True
        except IntegrityError:
            # Duplicate raw record, or the same natural key reached from a
            # differently-hashed payload — keep the first observation.
            self._session.rollback()
            existing_id = self._session.execute(
                select(SearchInterestObservationModel.id).where(
                    SearchInterestObservationModel.source == observation.source,
                    SearchInterestObservationModel.metric == observation.metric,
                    SearchInterestObservationModel.query_kind == observation.query_kind,
                    SearchInterestObservationModel.query_key == observation.query_key,
                    SearchInterestObservationModel.geo_scope == observation.geo_scope,
                    SearchInterestObservationModel.aggregation_interval
                    == observation.aggregation_interval,
                    SearchInterestObservationModel.period_start == observation.period_start,
                    SearchInterestObservationModel.period_end == observation.period_end,
                )
            ).scalar_one_or_none()
            if existing_id is None:
                existing_id = self._session.execute(
                    select(SearchInterestObservationModel.id).where(
                        SearchInterestObservationModel.raw_source_record_id == raw_id
                    )
                ).scalar_one()
            return existing_id, False

    def observations_in_window(
        self, *, window_start: datetime, window_end: datetime
    ) -> tuple[SearchInterestEvidence, ...]:
        rows = self._session.execute(
            select(
                SearchInterestObservationModel.source,
                SearchInterestObservationModel.metric,
                SearchInterestObservationModel.query_kind,
                SearchInterestObservationModel.query_key,
                SearchInterestObservationModel.query_display,
                SearchInterestObservationModel.geo_scope,
                SearchInterestObservationModel.geo_scope_type,
                SearchInterestObservationModel.aggregation_interval,
                SearchInterestObservationModel.period_start,
                SearchInterestObservationModel.period_end,
                SearchInterestObservationModel.value,
                SearchInterestObservationModel.value_scale,
                SearchInterestObservationModel.value_status,
                SearchInterestObservationModel.is_relative,
                SearchInterestObservationModel.source_timestamp,
                SearchInterestObservationModel.observed_at,
                SearchInterestObservationModel.query_config_version,
                SearchInterestObservationModel.synthetic,
            )
            .where(
                SearchInterestObservationModel.period_start >= window_start,
                SearchInterestObservationModel.period_end <= window_end,
            )
            .order_by(
                SearchInterestObservationModel.query_key,
                SearchInterestObservationModel.geo_scope,
                SearchInterestObservationModel.period_start,
            )
        )
        return tuple(
            SearchInterestEvidence(
                source=row.source,
                metric=row.metric,
                query_kind=row.query_kind,
                query_key=row.query_key,
                query_display=row.query_display,
                geo_scope=row.geo_scope,
                geo_scope_type=row.geo_scope_type,
                aggregation_interval=row.aggregation_interval,
                period_start=row.period_start,
                period_end=row.period_end,
                value=float(row.value) if row.value is not None else None,
                value_scale=row.value_scale,
                value_status=row.value_status,
                is_relative=bool(row.is_relative),
                source_timestamp=row.source_timestamp,
                observed_at=row.observed_at,
                query_config_version=row.query_config_version,
                synthetic=bool(row.synthetic),
            )
            for row in rows
        )


class MediaAttentionRepositorySQL:
    """SQL adapter for concept-level media-attention observations (D9B).

    Deliberately separate from the product and search-interest paths.
    Enforces atomic persistence between observations and contributing records,
    natural-key idempotency with version coexistence, savepoint rollback handling,
    provenance cascade awareness, and safe relinking.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_observation_with_contributing_records(
        self,
        *,
        observation: MediaAttentionObservation,
        run_id: Optional[UUID],
        contributing_records: Sequence[ContributingRecordAssignment] = (),
    ) -> tuple[UUID, bool]:
        """Atomically persist one observation and its contributing records.

        Returns (observation_id, created). If a natural-key collision occurs,
        the nested savepoint rolls back cleanly without leaving orphan or partial
        rows, leaves the existing observation untouched, optionally relinks any
        unlinked contributing records, and returns (existing_id, False).
        """
        obs_row = MediaAttentionObservationModel(
            collection_run_id=run_id,
            source=observation.source,
            metric=observation.metric,
            query_kind=observation.query_kind,
            query_key=observation.query_key,
            query_display=observation.query_display,
            geo_scope=observation.geo_scope,
            geo_scope_type=observation.geo_scope_type,
            aggregation_interval=observation.aggregation_interval,
            period_start=observation.period_start,
            period_end=observation.period_end,
            value=observation.value,
            value_scale=observation.value_scale,
            value_status=observation.value_status,
            completeness_status=observation.completeness_status,
            raw_article_count=observation.raw_article_count,
            distinct_outlet_count=observation.distinct_outlet_count,
            estimated_deduplicated_story_count=observation.estimated_deduplicated_story_count,
            query_config_version=observation.query_config_version,
            clustering_version=observation.clustering_version,
            contributing_raw_record_count=len(contributing_records),
            provenance_pruned=False,
            source_timestamp=observation.source_timestamp,
            is_relative=observation.is_relative,
            synthetic=observation.synthetic,
        )

        try:
            with self._session.begin_nested():
                self._session.add(obs_row)
                self._session.flush()

                for cr in contributing_records:
                    contrib_row = MediaAttentionContributingRecordModel(
                        observation_id=obs_row.id,
                        raw_source_record_id=cr.raw_source_record_id,
                        similarity_cluster_id=cr.similarity_cluster_id,
                        is_canonical=cr.is_canonical,
                        outlet_domain=cr.outlet_domain,
                    )
                    self._session.add(contrib_row)
                self._session.flush()

            self._session.commit()
            return obs_row.id, True

        except IntegrityError:
            # Savepoint was rolled back automatically by the context manager.
            # Query existing observation by natural key:
            existing_id = self._session.execute(
                select(MediaAttentionObservationModel.id).where(
                    MediaAttentionObservationModel.source == observation.source,
                    MediaAttentionObservationModel.metric == observation.metric,
                    MediaAttentionObservationModel.query_kind == observation.query_kind,
                    MediaAttentionObservationModel.query_key == observation.query_key,
                    MediaAttentionObservationModel.geo_scope == observation.geo_scope,
                    MediaAttentionObservationModel.aggregation_interval
                    == observation.aggregation_interval,
                    MediaAttentionObservationModel.period_start == observation.period_start,
                    MediaAttentionObservationModel.period_end == observation.period_end,
                    MediaAttentionObservationModel.query_config_version
                    == observation.query_config_version,
                    MediaAttentionObservationModel.clustering_version
                    == observation.clustering_version,
                )
            ).scalar_one_or_none()

            if existing_id is None:
                self._session.rollback()
                raise

            # Existing observation found; preserve it without modifying values.
            # If contributing records are provided, relink any unlinked ones.
            if contributing_records:
                self.relink_contributing_records(
                    observation_id=existing_id,
                    contributing_records=contributing_records,
                )
            else:
                self._session.commit()

            return existing_id, False

    def relink_contributing_records(
        self,
        *,
        observation_id: UUID,
        contributing_records: Sequence[ContributingRecordAssignment],
    ) -> int:
        """Insert missing join records for an existing observation.

        Returns count of newly linked records. Resets ``provenance_pruned = False``.
        """
        if not contributing_records:
            return 0

        new_links = 0
        with self._session.begin_nested():
            existing_raw_ids = set(
                self._session.execute(
                    select(
                        MediaAttentionContributingRecordModel.raw_source_record_id
                    ).where(
                        MediaAttentionContributingRecordModel.observation_id
                        == observation_id
                    )
                )
                .scalars()
                .all()
            )

            for cr in contributing_records:
                if cr.raw_source_record_id not in existing_raw_ids:
                    contrib_row = MediaAttentionContributingRecordModel(
                        observation_id=observation_id,
                        raw_source_record_id=cr.raw_source_record_id,
                        similarity_cluster_id=cr.similarity_cluster_id,
                        is_canonical=cr.is_canonical,
                        outlet_domain=cr.outlet_domain,
                    )
                    self._session.add(contrib_row)
                    existing_raw_ids.add(cr.raw_source_record_id)
                    new_links += 1

            self._session.flush()

            if new_links > 0:
                obs = self._session.get(MediaAttentionObservationModel, observation_id)
                if obs is not None:
                    obs.contributing_raw_record_count = len(existing_raw_ids)
                    obs.provenance_pruned = False
                    self._session.flush()

        self._session.commit()
        return new_links

    def observations_in_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        query_key: Optional[str] = None,
        geo_scope: Optional[str] = None,
    ) -> tuple[MediaAttentionEvidence, ...]:
        """Observations whose period is fully contained in ``[window_start, window_end)``.

        Read-only; ordered by ``(query_key, geo_scope, period_start)``.
        """
        stmt = select(MediaAttentionObservationModel).where(
            MediaAttentionObservationModel.period_start >= window_start,
            MediaAttentionObservationModel.period_end <= window_end,
        )
        if query_key is not None:
            stmt = stmt.where(MediaAttentionObservationModel.query_key == query_key)
        if geo_scope is not None:
            stmt = stmt.where(MediaAttentionObservationModel.geo_scope == geo_scope)

        stmt = stmt.order_by(
            MediaAttentionObservationModel.query_key,
            MediaAttentionObservationModel.geo_scope,
            MediaAttentionObservationModel.period_start,
        )

        rows = self._session.execute(stmt).scalars().all()
        return tuple(
            MediaAttentionEvidence(
                observation_id=row.id,
                source=row.source,
                metric=row.metric,
                query_kind=row.query_kind,
                query_key=row.query_key,
                query_display=row.query_display,
                geo_scope=row.geo_scope,
                geo_scope_type=row.geo_scope_type,
                aggregation_interval=row.aggregation_interval,
                period_start=row.period_start,
                period_end=row.period_end,
                value=float(row.value) if row.value is not None else None,
                value_scale=row.value_scale,
                value_status=row.value_status,
                completeness_status=row.completeness_status,
                raw_article_count=row.raw_article_count,
                distinct_outlet_count=row.distinct_outlet_count,
                estimated_deduplicated_story_count=row.estimated_deduplicated_story_count,
                query_config_version=row.query_config_version,
                clustering_version=row.clustering_version,
                contributing_raw_record_count=row.contributing_raw_record_count,
                provenance_pruned=bool(row.provenance_pruned),
                observed_at=row.observed_at,
                source_timestamp=row.source_timestamp,
                synthetic=bool(row.synthetic),
            )
            for row in rows
        )

    def get_contributing_records(
        self,
        *,
        observation_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ContributingRecordAssignment, ...]:
        """Read drill-down contributing record assignments for an observation."""
        stmt = (
            select(MediaAttentionContributingRecordModel)
            .where(
                MediaAttentionContributingRecordModel.observation_id == observation_id
            )
            .order_by(
                MediaAttentionContributingRecordModel.is_canonical.desc(),
                MediaAttentionContributingRecordModel.outlet_domain,
                MediaAttentionContributingRecordModel.raw_source_record_id,
            )
            .limit(limit)
            .offset(offset)
        )
        rows = self._session.execute(stmt).scalars().all()
        return tuple(
            ContributingRecordAssignment(
                raw_source_record_id=row.raw_source_record_id,
                similarity_cluster_id=row.similarity_cluster_id,
                is_canonical=row.is_canonical,
                outlet_domain=row.outlet_domain,
            )
            for row in rows
        )

    def prune_expired_raw_records(
        self,
        *,
        older_than: datetime,
    ) -> int:
        """Prune raw source records older than a cutoff date.

        Cascades link removal, marks parent observations as ``provenance_pruned = True``,
        and returns the number of pruned raw records.
        """
        # 1. Identify observation IDs linked to raw records about to be deleted
        subq = (
            select(MediaAttentionContributingRecordModel.observation_id)
            .join(
                RawSourceRecord,
                MediaAttentionContributingRecordModel.raw_source_record_id
                == RawSourceRecord.id,
            )
            .where(RawSourceRecord.created_at < older_than)
            .distinct()
        )
        affected_obs_ids = set(self._session.execute(subq).scalars().all())

        # 2. Delete the raw records
        raw_ids_to_del = list(
            self._session.execute(
                select(RawSourceRecord.id).where(RawSourceRecord.created_at < older_than)
            )
            .scalars()
            .all()
        )
        if not raw_ids_to_del:
            return 0

        for raw_id in raw_ids_to_del:
            raw_rec = self._session.get(RawSourceRecord, raw_id)
            if raw_rec is not None:
                self._session.delete(raw_rec)

        self._session.flush()

        # 3. Mark affected observations as provenance_pruned and update retained link count
        for obs_id in affected_obs_ids:
            obs = self._session.get(MediaAttentionObservationModel, obs_id)
            if obs is not None:
                obs.provenance_pruned = True
                retained_count = self._session.execute(
                    select(func.count())
                    .select_from(MediaAttentionContributingRecordModel)
                    .where(
                        MediaAttentionContributingRecordModel.observation_id
                        == obs_id
                    )
                ).scalar_one()
                obs.contributing_raw_record_count = retained_count

        self._session.commit()
        return len(raw_ids_to_del)


class DiscoveryEventRepositorySQL:
    """SQLAlchemy implementation of DiscoveryEventRepository (DISCOVERY-10A)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_existing_product_ids(self, product_ids: set[UUID]) -> set[UUID]:
        if not product_ids:
            return set()
        stmt = select(Product.id).where(Product.id.in_(product_ids))
        return set(self._session.execute(stmt).scalars().all())

    def persist_events_batch(
        self,
        *,
        events: Sequence[dict[str, Any]],
        user_id: Optional[UUID],
        guest_session_id: Optional[UUID],
    ) -> list[tuple[UUID, str, bool]]:
        if not events:
            return []

        # Enforce identity mutual exclusivity
        if (user_id is not None and guest_session_id is not None) or (
            user_id is None and guest_session_id is None
        ):
            from app.api.errors import validation

            raise validation(
                [
                    {
                        "field": "identity",
                        "error": "Event batch must belong to an authenticated user OR a guest session, never both or neither.",
                    }
                ]
            )

        from app.api.errors import ApiError

        # Intra-batch conflict check
        seen_batch_ids: dict[UUID, str] = {}
        for ev in events:
            cid = ev["client_event_id"]
            phash = ev["payload_hash"]
            if cid in seen_batch_ids:
                if seen_batch_ids[cid] != phash:
                    raise ApiError(
                        status_code=409,
                        code="CONFLICT",
                        message="Event ID collision with conflicting payload in batch.",
                        details={
                            "kind": "duplicate_event_id_conflict",
                            "eventId": str(cid),
                        },
                    )
            else:
                seen_batch_ids[cid] = phash

        # Query existing rows for this identity
        client_event_ids = list({ev["client_event_id"] for ev in events})
        identity_clause = (
            DiscoveryEvent.user_id == user_id
            if user_id is not None
            else DiscoveryEvent.guest_session_id == guest_session_id
        )

        stmt = select(
            DiscoveryEvent.client_event_id, DiscoveryEvent.payload_hash
        ).where(
            identity_clause,
            DiscoveryEvent.client_event_id.in_(client_event_ids),
        )
        existing_rows = dict(self._session.execute(stmt).all())

        results: list[tuple[UUID, str, bool]] = []
        rows_to_insert: list[DiscoveryEvent] = []
        already_handled_in_batch: set[UUID] = set()

        for ev in events:
            cid = ev["client_event_id"]
            phash = ev["payload_hash"]

            if cid in existing_rows:
                db_hash = existing_rows[cid]
                if db_hash == phash:
                    results.append((cid, "acknowledged", True))
                else:
                    raise ApiError(
                        status_code=409,
                        code="CONFLICT",
                        message="Event ID collision with conflicting payload.",
                        details={
                            "kind": "duplicate_event_id_conflict",
                            "eventId": str(cid),
                        },
                    )
            elif cid in already_handled_in_batch:
                # Same payload repeated in same batch
                results.append((cid, "acknowledged", True))
            else:
                row = DiscoveryEvent(
                    user_id=user_id,
                    guest_session_id=guest_session_id,
                    event_type=ev["event_type"],
                    target_type=ev["target_type"],
                    target_id=ev["target_id"],
                    product_id=ev.get("product_id"),
                    surface=ev["surface"],
                    position=ev.get("position"),
                    client_event_id=cid,
                    payload_hash=phash,
                    metadata_=ev.get("metadata", {}),
                    client_occurred_at=ev["client_occurred_at"],
                )
                rows_to_insert.append(row)
                already_handled_in_batch.add(cid)
                results.append((cid, "accepted", False))

        if rows_to_insert:
            try:
                for row in rows_to_insert:
                    self._session.add(row)
                self._session.commit()
            except IntegrityError:
                self._session.rollback()
                # A concurrent insert took place for one of these events
                # Re-check database state to determine if it was identical replay or conflicting payload
                stmt = select(
                    DiscoveryEvent.client_event_id, DiscoveryEvent.payload_hash
                ).where(
                    identity_clause,
                    DiscoveryEvent.client_event_id.in_(client_event_ids),
                )
                concurrent_rows = dict(self._session.execute(stmt).all())
                for ev in events:
                    cid = ev["client_event_id"]
                    if cid in concurrent_rows:
                        if concurrent_rows[cid] != ev["payload_hash"]:
                            raise ApiError(
                                status_code=409,
                                code="CONFLICT",
                                message="Event ID collision with conflicting payload.",
                                details={
                                    "kind": "duplicate_event_id_conflict",
                                    "eventId": str(cid),
                                },
                            )
                # If concurrent rows are identical, update results to reflect replayed status
                updated_results: list[tuple[UUID, str, bool]] = []
                for cid, status, replayed in results:
                    if (
                        cid in concurrent_rows
                        and concurrent_rows[cid] == seen_batch_ids.get(cid)
                    ):
                        updated_results.append((cid, "acknowledged", True))
                    else:
                        updated_results.append((cid, status, replayed))
                return updated_results

        return results


