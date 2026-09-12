"""Learning summary router — endpoint #34 (`GET /v1/learning/summary`, M10-B).

The derived M10 read surface: style score + breakdown + streak + recent
signals for the caller (DEC-019 §A, DEC-020 §§A–E, DEC-021). Thin by
design — `GetLearningSummary` owns the derivation; this module only maps
the application dataclass to the wire DTO.

Read-only: no commit, no mutation. Empty user → 200 zero-valued summary,
never 204, never 404 (DEC-020 §A).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.schemas.learning import LearningBreakdown, LearningSummary
from app.application.learning import GetLearningSummary
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/learning", tags=["learning"])


def _summary_to_wire(summary) -> LearningSummary:
    """Map the application summary to the frozen wire DTO (DEC-021)."""
    return LearningSummary(
        styleScore=summary.style_score,
        breakdown=LearningBreakdown(
            base=summary.breakdown.base,
            wardrobePoints=summary.breakdown.wardrobe_points,
            savedPoints=summary.breakdown.saved_points,
            total=summary.breakdown.total,
        ),
        streak=summary.streak,
        recentSignals=list(summary.recent_signals),
    )


@router.get(
    "/summary",
    response_model=LearningSummary,
    responses={401: {"model": dict}, 429: {"model": dict}},
)
def get_learning_summary(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LearningSummary:
    """Serve the caller's derived learning summary (M10-B, read-only)."""
    use_case = GetLearningSummary(
        wardrobe_items=WardrobeItemRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
        signals=LearningSignalRepositorySQL(db),
        activity_days=ActivityDayRepositorySQL(db),
    )
    return _summary_to_wire(use_case(user_id=user_id))
