"""Looks API router — endpoint #23 (`POST /v1/looks/saved`).

Requires the contract's `Idempotency-Key` header (C-12/API-33). On replay
returns the original save; on a conflicting replay returns 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.schemas.saved_looks import SaveLookRequest, SavedLook
from app.application.saved_looks import SaveRecommendation
from app.infrastructure.db.repositories import (
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
)
from app.infrastructure.db.session import get_db
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

router = APIRouter(prefix="/v1/looks", tags=["looks"])


def _record_to_schema(record) -> SavedLook:
    return SavedLook(
        id=record.id,
        lookId=record.look_id,
        title=record.title,
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
