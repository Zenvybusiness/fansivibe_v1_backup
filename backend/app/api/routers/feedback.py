"""Feedback API router — M11 reactions (#35 `POST /v1/feedback`, UC-32).

Accepts one user reaction (rating + optional why + at most one
look/saved-look target) and appends exactly one `feedback_events` row
(tier 1). Always answers 204 accepted-ack: no representation DTO is
frozen for this endpoint, so none is invented. A repeated
`Idempotency-Key` with the same payload replays the ack without
re-inserting; a conflicting replay is a 409.

Requires the contract's `Idempotency-Key` header (C-12/API-33, M7
precedent): a missing key is a 422. Nothing here writes learning
signals, activity days, wears, saves, or preferences.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.schemas.feedback import FeedbackCreate
from app.application.feedback import SubmitRecommendationFeedback
from app.infrastructure.db.repositories import (
    FeedbackRepositorySQL,
    LookRepositorySQL,
    SavedLookRepositorySQL,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


@router.post(
    "",
    status_code=204,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
    },
)
def submit_recommendation_feedback(
    request: FeedbackCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Append one reaction row (UC-32, tier 1, 204 ack)."""
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )

    use_case = SubmitRecommendationFeedback(
        feedback=FeedbackRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
        looks=LookRepositorySQL(db),
    )
    use_case(
        user_id=user_id,
        rating=request.rating,
        reason=request.reason,
        target_look_id=request.targetLookId,
        target_saved_look_id=request.targetSavedLookId,
        idempotency_key=idempotency_key,
    )
    return Response(status_code=204)
