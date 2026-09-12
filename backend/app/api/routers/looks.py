"""Looks API router — endpoints #23 (`POST /v1/looks/saved`), #24
(`GET /v1/looks/saved`), and #25 (`DELETE /v1/looks/saved/{saved_look_id}`,
DEC-013).

Requires the contract's `Idempotency-Key` header (C-12/API-33). On replay
returns the original save; on a conflicting replay returns 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.schemas.saved_looks import SaveLookRequest, SavedLook, SavedLookList
from app.application.saved_looks import (
    DeleteSavedLook,
    ListSavedLooks,
    SaveRecommendation,
)
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.db.session import get_db
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

router = APIRouter(prefix="/v1/looks", tags=["looks"])


def _record_to_schema(record) -> SavedLook:
    return SavedLook(
        id=record.id,
        lookId=record.look_id,
        title=record.title,
        sourceContext=record.source_context,
        snapshot=record.snapshot,
        sourceRunId=record.source_run_id,
        createdAt=record.created_at,
    )


@router.post(
    "/saved",
    response_model=SavedLook,
    status_code=201,
    responses={404: {"model": dict}, 409: {"model": dict}, 422: {"model": dict}, 401: {"model": dict}},
)
def save_look(
    request: SaveLookRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SavedLook:
    """Save a recommendation (TRX-3: saved look + `look_saved` signal)."""
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )

    use_case = SaveRecommendation(
        saved_looks=SavedLookRepositorySQL(db),
        signals=LearningSignalRepositorySQL(db),
        knowledge=CatalogKnowledgeSource(),
        wardrobe_items=WardrobeItemRepositorySQL(db),
        activity_days=ActivityDayRepositorySQL(db),
    )
    record, created = use_case(
        user_id=user_id,
        look_id=request.lookId,
        title=request.title,
        snapshot=request.snapshot,
        source_context=request.sourceContext,
        idempotency_key=idempotency_key,
    )
    return _record_to_schema(record)


@router.get(
    "/saved",
    response_model=SavedLookList,
    responses={422: {"model": dict}, 401: {"model": dict}},
)
def list_saved_looks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SavedLookList:
    """Paged saved-look list for the owner (createdAt desc; OW-1)."""
    use_case = ListSavedLooks(saved_looks=SavedLookRepositorySQL(db))
    items, total = use_case(user_id=user_id, page=page, page_size=page_size)
    return SavedLookList(
        items=[_record_to_schema(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.delete(
    "/saved/{saved_look_id}",
    status_code=204,
    responses={401: {"model": dict}, 404: {"model": dict}, 422: {"model": dict}},
)
def delete_saved_look(
    saved_look_id: UUID = Path(..., description="UUID of the saved look to delete"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Delete one owned saved look (DEC-013).

    Owner-scoped delete. Foreign/non-existent id → 404 (OW-1, 404-not-403).
    Successful delete → 204 No Content. The row (snapshot included) is
    physically removed; learning signals are preserved.
    """
    use_case = DeleteSavedLook(saved_looks=SavedLookRepositorySQL(db))
    use_case(user_id=user_id, saved_look_id=saved_look_id)
    return None
