"""Repository ports — persistence seams the application layer depends on.

Implementations live in `app/infrastructure/db/repositories.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID


@dataclass(frozen=True)
class AnalysisRunRecord:
    """A bare `analysis_runs` row (owner-scoped read)."""

    id: UUID
    run_type: str
    status: str
    engine_version: str
    created_at: datetime
    completed_at: Optional[datetime]
    input_media: Optional[dict]
    result: Optional[dict]
    error: Optional[dict]


@dataclass(frozen=True)
class AnalysisRunSummary:
    """A list-row summary (no `result`, no `error`)."""

    id: UUID
    run_type: str
    status: str
    engine_version: str
    created_at: datetime
    completed_at: Optional[datetime]
    input_media: Optional[dict]


@dataclass(frozen=True)
class SavedLookRecord:
    """A `saved_looks` row (owner-scoped read)."""

    id: UUID
    look_id: Optional[str]
    title: str
    snapshot: dict
    source_run_id: Optional[UUID]
    created_at: datetime


class AnalysisRunRepository(Protocol):
    def create(
        self,
        *,
        user_id: UUID,
        run_type: str,
        engine_version: str,
        input_media: Optional[dict] = None,
    ) -> UUID: ...

    def get_for_user(self, *, user_id: UUID, run_id: UUID) -> Optional[AnalysisRunRecord]: ...

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[AnalysisRunSummary], int]: ...

    def complete(
        self, *, run_id: UUID, user_id: UUID, status: str, result: Optional[dict]
    ) -> bool: ...


class UserStateRepository(Protocol):
    def get_style_profile(self, *, user_id: UUID) -> Optional[dict]: ...


class SavedLookRepository(Protocol):
    def insert(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        snapshot: dict,
        idempotency_key: str,
        source_run_id: Optional[UUID],
    ) -> SavedLookRecord: ...

    def get_for_user(self, *, user_id: UUID, saved_look_id: UUID) -> Optional[SavedLookRecord]: ...

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[SavedLookRecord]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class LearningSignalRepository(Protocol):
    def insert_look_saved(
        self, *, user_id: UUID, label: str, context: Optional[dict]
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
