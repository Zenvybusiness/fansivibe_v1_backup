"""Learning summary router — endpoint #34 (`GET /v1/learning/summary`, M10-B).

The derived M10 read surface: style score + breakdown + streak + recent
signals for the caller (DEC-019 §A, DEC-020 §§A–E, DEC-021). Thin by
design — `GetLearningSummary` owns the derivation; this module only maps
the application dataclass to the wire DTO.

Read-only: no commit, no mutation. Empty user → 200 zero-valued summary,
never 204, never 404 (DEC-020 §A).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.api.schemas.learning import (
    LearningBreakdown,
    LearningSummary,
    RecordWeeklySnapshotRequest,
    StyleJourneyComparisonSchema,
    StyleJourneyHistoryResponse,
    WeeklyProgressItem,
    WeeklySnapshotResponse,
)
from app.application.learning import GetLearningSummary
from app.application.style_journey import (
    GetStyleJourneyHistory,
    RecordWeeklySnapshot,
    WeeklyProgressEntry,
)
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
    StyleJourneySnapshotRepositorySQL,
    UserStateRepositorySQL,
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


def _entry_to_wire(entry: WeeklyProgressEntry) -> WeeklyProgressItem:
    return WeeklyProgressItem(
        weekStart=entry.week_start,
        weekEnd=entry.week_end,
        timezone=entry.timezone,
        styleScore=entry.style_score,
        breakdown=LearningBreakdown(
            base=entry.breakdown.base,
            wardrobePoints=entry.breakdown.wardrobe_points,
            savedPoints=entry.breakdown.saved_points,
            total=entry.breakdown.total,
        ),
        styledDaysCount=entry.styled_days_count,
        signalsCount=entry.signals_count,
        isCurrent=entry.is_current,
        personalRank=entry.personal_rank,
        recordedAt=entry.recorded_at,
        aggregationPolicy=entry.aggregation_policy,
    )


@router.get(
    "/journey/history",
    response_model=StyleJourneyHistoryResponse,
    responses={401: {"model": dict}, 422: {"model": dict}, 429: {"model": dict}},
)
def get_style_journey_history(
    timezone: Optional[str] = Query(default=None),
    limit: int = Query(default=12, ge=1, le=52),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StyleJourneyHistoryResponse:
    """Serve the caller's personal Style Journey weekly progress history (SJ1, read-only)."""
    use_case = GetStyleJourneyHistory(
        wardrobe_items=WardrobeItemRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
        signals=LearningSignalRepositorySQL(db),
        snapshots=StyleJourneySnapshotRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    result = use_case(user_id=user_id, timezone_override=timezone, limit=limit)
    return StyleJourneyHistoryResponse(
        timezone=result.timezone,
        aggregationPolicy=result.aggregation_policy,
        currentWeek=_entry_to_wire(result.current_week),
        previousWeek=(
            _entry_to_wire(result.previous_week)
            if result.previous_week is not None
            else None
        ),
        bestHistoricalWeek=(
            _entry_to_wire(result.best_historical_week)
            if result.best_historical_week is not None
            else None
        ),
        comparison=StyleJourneyComparisonSchema(
            scoreDelta=result.comparison.score_delta,
            trend=result.comparison.trend,  # type: ignore[arg-type]
            currentWeekRank=result.comparison.current_week_rank,
            totalRankedWeeks=result.comparison.total_ranked_weeks,
            isTiedWithBest=result.comparison.is_tied_with_best,
        ),
        weeks=[_entry_to_wire(w) for w in result.weeks],
        hasHistory=result.has_history,
    )


@router.post(
    "/journey/snapshots",
    response_model=WeeklySnapshotResponse,
    responses={401: {"model": dict}, 422: {"model": dict}, 429: {"model": dict}},
)
def record_weekly_snapshot(
    request: RecordWeeklySnapshotRequest = RecordWeeklySnapshotRequest(),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WeeklySnapshotResponse:
    """Idempotently record an immutable weekly Style Journey snapshot (SJ1)."""
    use_case = RecordWeeklySnapshot(
        wardrobe_items=WardrobeItemRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
        signals=LearningSignalRepositorySQL(db),
        snapshots=StyleJourneySnapshotRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    entry, created = use_case(
        user_id=user_id,
        week_start=request.weekStart,
        timezone_override=request.timezone,
    )
    return WeeklySnapshotResponse(
        snapshot=_entry_to_wire(entry),
        created=created,
    )
