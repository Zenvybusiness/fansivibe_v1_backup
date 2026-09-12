"""M10 learning foundation — styled-day recording + streak derivation (M10-A).

Reusable application/domain logic for the learning summary (endpoint #34,
DEC-019/DEC-020/DEC-021). M10-A scope only:

- `mark_styled_today`: the one-line record path the existing
  learning-signal writers call after their signal INSERT(s), before their
  existing commit — the activity-day upsert rides the signal's own commit
  (DEC-020 §F, same-commit rule). No new commit, no new signal types, no
  backfill.
- `derive_current_streak`: the pure C11 streak math (DEC-020 §D,
  D1–D10) over persisted styled days. Read-time derivation; a GET never
  writes (TRX §5).
- `DeriveCurrentStreak`: the repo-backed use case M10-B will reuse.

Richer streak fields and score history are deferred (DEC-020 §§C/I);
the `GetLearningSummary` use case below is M10-B.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from app.domain.ports.repositories import (
    ActivityDayRepository,
    LearningSignalRepository,
    SavedLookRepository,
    WardrobeItemRepository,
)


def utc_today() -> date:
    """Server-UTC calendar date (DEC-020 §D2 day datum)."""
    return datetime.now(timezone.utc).date()


def derive_current_streak(*, styled_days: Collection[date], today: date) -> int:
    """Current consecutive styled-day streak ending at the anchor (DEC-020 §D).

    - Only days on/before `today` count (future rows ignored, D7).
    - Anchor = `today` if styled, else yesterday; unstyled anchor → 0 (D6).
    - Walk backwards through consecutive calendar days (day-diff exactly
      1, D4); a missing day breaks the run (D5). Today counts (D3).
    - A lone styled anchor day yields 1 (D10).
    """
    days = {day for day in styled_days if day <= today}
    if not days:
        return 0
    anchor = today if today in days else today - timedelta(days=1)
    if anchor not in days:
        return 0
    streak = 0
    cursor = anchor
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def mark_styled_today(*, activity_days: ActivityDayRepository, user_id: UUID) -> None:
    """Record the caller's server-UTC day as styled (M10-A record path).

    Idempotent per (user, day) via the repository upsert (BC-4): repeated
    same-day signal writes keep exactly one row and never double-count.
    Executes on the caller's session without committing — the owning use
    case's existing commit persists it with the signal INSERT.
    """
    activity_days.upsert_styled_day(user_id=user_id, day=utc_today())


class DeriveCurrentStreak:
    """Derive the caller's current streak from persisted activity days."""

    def __init__(self, *, activity_days: ActivityDayRepository) -> None:
        self._activity_days = activity_days

    def __call__(self, *, user_id: UUID) -> int:
        """Returns the current consecutive styled-day streak (≥ 0)."""
        return derive_current_streak(
            styled_days=self._activity_days.list_styled_days(user_id=user_id),
            today=utc_today(),
        )


# M10-B scoring constants (DEC-019 §B, DEC-021: base 60, caps +20/+20).
_BASE_SCORE = 60
_MAX_WARDROBE_POINTS = 20
_MAX_SAVED_POINTS = 20
_RECENT_SIGNALS_LIMIT = 20


@dataclass(frozen=True)
class StyleScoreBreakdown:
    """Score component contributions (DEC-021 wire object, snake_case here;
    the router maps to the camelCase wire names)."""

    base: int
    wardrobe_points: int
    saved_points: int
    total: int


@dataclass(frozen=True)
class LearningSummary:
    """Derived M10 summary value (endpoint #34, DEC-019 §A)."""

    style_score: int
    breakdown: StyleScoreBreakdown
    streak: int
    recent_signals: list[str]


class GetLearningSummary:
    """Serve the caller's derived learning summary (endpoint #34, M10-B).

    Strictly read-only: four owner-scoped SELECTs (wardrobe total, saved
    total, styled days, recent labels), no commit, no mutation — a GET
    never creates signals, activity rows, or history (DEC-020 §§A/F).
    Score math consumes live counts only (DEC-019 §B): wear, favorites,
    feedback, profile, assistant, TodayLook, events, weather, and history
    are never read. An empty user receives the zero-valued summary
    (`styleScore 60`, zero breakdown, streak 0, `[]` — DEC-020 §A).
    """

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        saved_looks: SavedLookRepository,
        signals: LearningSignalRepository,
        activity_days: ActivityDayRepository,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._saved_looks = saved_looks
        self._signals = signals
        self._activity_days = activity_days

    def __call__(self, *, user_id: UUID) -> LearningSummary:
        # Reused paged-list totals (page_size=1): exact owner-scoped
        # COUNT(*) queries without new port surface.
        _, wardrobe_count = self._wardrobe_items.get_for_user(
            user_id=user_id, page=1, page_size=1
        )
        _, saved_count = self._saved_looks.list_for_user(
            user_id=user_id, page=1, page_size=1
        )
        wardrobe_points = min(wardrobe_count, _MAX_WARDROBE_POINTS)
        saved_points = min(saved_count * 2, _MAX_SAVED_POINTS)
        style_score = _BASE_SCORE + wardrobe_points + saved_points
        return LearningSummary(
            style_score=style_score,
            breakdown=StyleScoreBreakdown(
                base=_BASE_SCORE,
                wardrobe_points=wardrobe_points,
                saved_points=saved_points,
                total=style_score,
            ),
            streak=derive_current_streak(
                styled_days=self._activity_days.list_styled_days(
                    user_id=user_id
                ),
                today=utc_today(),
            ),
            recent_signals=self._signals.list_recent_labels(
                user_id=user_id, limit=_RECENT_SIGNALS_LIMIT
            ),
        )
