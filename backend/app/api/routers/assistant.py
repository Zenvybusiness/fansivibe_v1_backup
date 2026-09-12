"""Assistant API router — endpoint #17 (`POST /v1/assistant/feedback`, UC-23).

The single client-facing signal input: records one append-only
`learning_signals` row per call (`suggestion_opened` / `assistant_navigation`).
Deliberately NOT idempotency-keyed — retries append another row.

The conversational surface (`POST /v1/assistant/chat`) stays in `main.py`
untouched (frozen wire F-13/F-5).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.schemas.assistant import AssistantCardFeedback
from app.application.assistant import SubmitAssistantCardFeedback
from app.infrastructure.db.repositories import ActivityDayRepositorySQL, LearningSignalRepositorySQL
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


@router.post(
    "/feedback",
    status_code=204,
    responses={401: {"model": dict}, 422: {"model": dict}, 429: {"model": dict}},
)
def submit_assistant_card_feedback(
    request: AssistantCardFeedback,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Record one assistant card interaction (UC-23)."""
    use_case = SubmitAssistantCardFeedback(
        signals=LearningSignalRepositorySQL(db),
        activity_days=ActivityDayRepositorySQL(db),
    )
    use_case(
        user_id=user_id,
        card_id=request.cardId,
        card_title=request.cardTitle,
        interaction_type=request.interactionType,
    )
    return None
