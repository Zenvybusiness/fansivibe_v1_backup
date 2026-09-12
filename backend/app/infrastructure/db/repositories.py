"""SQLAlchemy repository implementations (Persistence adapters).

All reads are owner-scoped (`user_id`) — OW-1. `complete` uses the server-side
`complete_analysis_run` function (TRX-5 write-once guard).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.domain.ports.repositories import (
    AnalysisRunRecord,
    AnalysisRunSummary,
    SavedLookCoverage,
    SavedLookRecord,
    UserProfileRecord,
    WardrobeInsightSummary,
    WardrobeItemRecord,
    WearEventRecord,
    WearGroupRecord,
    WearSummary,
)
from app.infrastructure.db.models import (
    AnalysisRuns,
    LearningSignals,
    SavedLooks,
    UserState,
    Users,
    WardrobeItems,
    WardrobeCategories,
    WardrobeWearEvents,
    WardrobeWearGroups,
    Colors,
    Materials,
)

_ENGINE_VERSION = "rules-v1"


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
    ) -> UUID:
        row = AnalysisRuns(
            user_id=user_id,
            run_type=run_type,
            status="pending",
            engine_version=engine_version,
            knowledge_version=knowledge_version,
            input_media=input_media,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row.id

    def get_for_user(self, *, user_id: UUID, run_id: UUID) -> Optional[AnalysisRunRecord]:
        row = self._session.execute(
            select(AnalysisRuns).where(
                AnalysisRuns.id == run_id, AnalysisRuns.user_id == user_id
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return self._to_record(row)

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
        face_shape: str,
        skin_tone: str,
        body_type: str,
        style_type: str,
        source_run_id: str,
    ) -> None:
        """Update user_state.style_profile with image-derived appearance attributes (TRX-6).

        Only the approved appearance fields are updated; other profile data is preserved.
        This is the profile projection update step that makes the appearance data reusable
        for future hairstyle/grooming runs without needing re-capture.
        """
        self._session.execute(
            update(UserState)
            .where(UserState.user_id == user_id)
            .values(
                style_profile={
                    "face_shape": face_shape,
                    "skin_tone": skin_tone,
                    "body_type": body_type,
                    "style_type": style_type,
                    "source_run_id": source_run_id,
                }
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
    ) -> "WardrobeItemRecord":
        row = WardrobeItems(
            user_id=user_id,
            name=name,
            category_id=category,
            color_id=color,
            material_id=material,
            is_favorite=isFavorite,
            image_ref=None,
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
