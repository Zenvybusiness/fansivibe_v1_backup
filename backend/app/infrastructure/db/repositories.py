"""SQLAlchemy repository implementations (Persistence adapters).

All reads are owner-scoped (`user_id`) — OW-1. `complete` uses the server-side
`complete_analysis_run` function (TRX-5 write-once guard).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.domain.ports.repositories import (
    AnalysisRunRecord,
    AnalysisRunSummary,
    SavedLookRecord,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.infrastructure.db.models import (
    AnalysisRuns,
    LearningSignals,
    SavedLooks,
    UserState,
    Users,
    WardrobeItems,
    WardrobeCategories,
    Colors,
    Materials,
)

_ENGINE_VERSION = "rules-v1"


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
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list["WardrobeItemRecord"], int]:
        base = select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        total = self._session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        rows = self._session.execute(
            base.order_by(WardrobeItems.created_at.desc())
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
        if material is not None:
            row.material_id = material
        if isFavorite is not None:
            row.is_favorite = isFavorite
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
