"""SJ1 — Style Journey weekly progress history and immutable snapshots.

Extends M10 (`GetLearningSummary`) with personal weekly progress history,
timezone-aware ISO week boundaries (Monday..Sunday in the user's timezone),
immutable/idempotent weekly snapshots, and personal-only comparisons:

- Current week vs. previous week (never fabricated when previous week is absent).
- Best historical week (strictly from persisted historical snapshots).
- Personal weekly position (1-based competition ranking across the user's own
  weeks, with deterministic ties).
- Score improvement or decline (`score_delta` and `trend`).

All queries and snapshots are strictly owner-scoped (`user_id`). No user-to-user
comparison or community ranking exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.api.errors import validation
from app.application.learning import (
    _BASE_SCORE,
    _MAX_SAVED_POINTS,
    _MAX_WARDROBE_POINTS,
    StyleScoreBreakdown,
)
from app.domain.ports.repositories import (
    LearningSignalRepository,
    SavedLookRepository,
    StyleJourneySnapshotRepository,
    UserProfileRecord,
    UserStateRepository,
    WardrobeItemRepository,
    WeeklySnapshotRecord,
)

AGGREGATION_POLICY_V1 = "end_of_week_score_v1"


def utc_now() -> datetime:
    """Current aware UTC timestamp (patchable in tests)."""
    return datetime.now(timezone.utc)


def resolve_user_timezone(
    explicit_tz: Optional[str] = None,
    profile: Optional[UserProfileRecord] = None,
) -> ZoneInfo:
    """Resolve and validate the user's IANA timezone.

    Precedence:
    1. Explicit `explicit_tz` parameter (raises 422 VALIDATION_ERROR if invalid).
    2. Persisted `profile.settings["timezone"]` (falls back to UTC if invalid).
    3. Default `"UTC"`.
    """
    if explicit_tz is not None and explicit_tz.strip():
        candidate = explicit_tz.strip()
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, KeyError, ValueError) as exc:
            raise validation(
                [{"field": "timezone", "error": "must be a valid IANA timezone"}]
            ) from exc

    if profile is not None and isinstance(profile.settings, dict):
        saved_tz = profile.settings.get("timezone")
        if isinstance(saved_tz, str) and saved_tz.strip():
            try:
                return ZoneInfo(saved_tz.strip())
            except (ZoneInfoNotFoundError, KeyError, ValueError):
                pass

    return ZoneInfo("UTC")


def week_bounds_for_date(local_day: date) -> tuple[date, date]:
    """Return ISO week `(week_start_monday, week_end_sunday)` for a local date."""
    week_start = local_day - timedelta(days=local_day.weekday())
    return week_start, week_start + timedelta(days=6)


def week_bounds_for_instant(instant_utc: datetime, tz: ZoneInfo) -> tuple[date, date]:
    """Return ISO week `(week_start_monday, week_end_sunday)` in `tz`."""
    aware = (
        instant_utc.replace(tzinfo=timezone.utc)
        if instant_utc.tzinfo is None
        else instant_utc
    )
    local_day = aware.astimezone(tz).date()
    return week_bounds_for_date(local_day)


def week_utc_range(week_start: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return `[start_utc, end_utc)` covering `[week_start, week_start + 6]` in `tz`."""
    start_local = datetime.combine(week_start, time.min, tzinfo=tz)
    end_local = datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def count_week_activity(
    signal_instants: Iterable[datetime],
    *,
    tz: ZoneInfo,
    week_start: date,
) -> tuple[int, int]:
    """Count `(styled_days_count, signals_count)` within the user's local week."""
    start_utc, end_utc = week_utc_range(week_start, tz)
    local_days: set[date] = set()
    signals_count = 0
    for instant in signal_instants:
        aware = (
            instant.replace(tzinfo=timezone.utc)
            if instant.tzinfo is None
            else instant
        )
        if start_utc <= aware < end_utc:
            signals_count += 1
            local_days.add(aware.astimezone(tz).date())
    return min(len(local_days), 7), signals_count


@dataclass(frozen=True)
class WeeklyProgressEntry:
    """One week of Style Journey progress (live current week or historical snapshot)."""

    week_start: date
    week_end: date
    timezone: str
    style_score: int
    breakdown: StyleScoreBreakdown
    styled_days_count: int
    signals_count: int
    is_current: bool
    personal_rank: int
    recorded_at: Optional[datetime]
    aggregation_policy: str


@dataclass(frozen=True)
class StyleJourneyComparison:
    """Personal-only weekly comparison metrics (never cross-user)."""

    score_delta: Optional[int]
    trend: Optional[str]
    current_week_rank: int
    total_ranked_weeks: int
    is_tied_with_best: bool


@dataclass(frozen=True)
class StyleJourneyHistoryResult:
    """Complete SJ1 read result."""

    timezone: str
    aggregation_policy: str
    current_week: WeeklyProgressEntry
    previous_week: Optional[WeeklyProgressEntry]
    best_historical_week: Optional[WeeklyProgressEntry]
    comparison: StyleJourneyComparison
    weeks: list[WeeklyProgressEntry]
    has_history: bool


def _entry_from_snapshot(
    snap: WeeklySnapshotRecord,
    *,
    is_current: bool = False,
    personal_rank: int = 1,
) -> WeeklyProgressEntry:
    return WeeklyProgressEntry(
        week_start=snap.week_start,
        week_end=snap.week_end,
        timezone=snap.timezone,
        style_score=snap.style_score,
        breakdown=StyleScoreBreakdown(
            base=snap.base_points,
            wardrobe_points=snap.wardrobe_points,
            saved_points=snap.saved_points,
            total=snap.style_score,
        ),
        styled_days_count=snap.styled_days_count,
        signals_count=snap.signals_count,
        is_current=is_current,
        personal_rank=personal_rank,
        recorded_at=snap.recorded_at,
        aggregation_policy=snap.aggregation_policy,
    )


def rank_weekly_entries(
    entries: Sequence[WeeklyProgressEntry],
) -> list[WeeklyProgressEntry]:
    """Compute 1-based standard competition ranking (1, 1, 3) across a user's weeks.

    Ties receive identical `personal_rank`. Returned sorted newest-first
    (`week_start` descending).
    """
    ordered = sorted(entries, key=lambda e: e.week_start, reverse=True)
    ranked: list[WeeklyProgressEntry] = []
    for entry in ordered:
        rank = 1 + sum(1 for other in ordered if other.style_score > entry.style_score)
        ranked.append(
            WeeklyProgressEntry(
                week_start=entry.week_start,
                week_end=entry.week_end,
                timezone=entry.timezone,
                style_score=entry.style_score,
                breakdown=entry.breakdown,
                styled_days_count=entry.styled_days_count,
                signals_count=entry.signals_count,
                is_current=entry.is_current,
                personal_rank=rank,
                recorded_at=entry.recorded_at,
                aggregation_policy=entry.aggregation_policy,
            )
        )
    return ranked


def select_best_historical_week(
    historical_entries: Sequence[WeeklyProgressEntry],
) -> Optional[WeeklyProgressEntry]:
    """Return the highest-scoring historical week (tie-break: most recent week_start)."""
    if not historical_entries:
        return None
    return max(
        historical_entries,
        key=lambda e: (e.style_score, e.week_start),
    )


def _compute_live_score_breakdown(
    *,
    user_id: UUID,
    wardrobe_items: WardrobeItemRepository,
    saved_looks: SavedLookRepository,
) -> StyleScoreBreakdown:
    _, wardrobe_count = wardrobe_items.get_for_user(
        user_id=user_id, page=1, page_size=1
    )
    _, saved_count = saved_looks.list_for_user(
        user_id=user_id, page=1, page_size=1
    )
    wardrobe_points = min(wardrobe_count, _MAX_WARDROBE_POINTS)
    saved_points = min(saved_count * 2, _MAX_SAVED_POINTS)
    total = _BASE_SCORE + wardrobe_points + saved_points
    return StyleScoreBreakdown(
        base=_BASE_SCORE,
        wardrobe_points=wardrobe_points,
        saved_points=saved_points,
        total=total,
    )


class GetStyleJourneyHistory:
    """Read-only SJ1 use case returning personal weekly progress & comparisons."""

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        saved_looks: SavedLookRepository,
        signals: LearningSignalRepository,
        snapshots: StyleJourneySnapshotRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._saved_looks = saved_looks
        self._signals = signals
        self._snapshots = snapshots
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        timezone_override: Optional[str] = None,
        limit: int = 12,
        now: Optional[datetime] = None,
    ) -> StyleJourneyHistoryResult:
        profile = self._user_state.get_profile(user_id=user_id)
        tz = resolve_user_timezone(timezone_override, profile)
        tz_name = tz.key
        reference_now = now or utc_now()
        current_week_start, current_week_end = week_bounds_for_instant(
            reference_now, tz
        )
        previous_week_start = current_week_start - timedelta(days=7)

        breakdown = _compute_live_score_breakdown(
            user_id=user_id,
            wardrobe_items=self._wardrobe_items,
            saved_looks=self._saved_looks,
        )
        start_utc, end_utc = week_utc_range(current_week_start, tz)
        week_instants = self._signals.list_occurred_at_in_range(
            user_id=user_id,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        styled_days_count, signals_count = count_week_activity(
            week_instants, tz=tz, week_start=current_week_start
        )

        all_snapshots = self._snapshots.list_for_user(user_id=user_id)
        # Historical weeks are strictly prior to current_week_start.
        historical_raw = [
            _entry_from_snapshot(s, is_current=False)
            for s in all_snapshots
            if s.week_start < current_week_start
        ]
        current_snap = next(
            (s for s in all_snapshots if s.week_start == current_week_start), None
        )
        current_raw = WeeklyProgressEntry(
            week_start=current_week_start,
            week_end=current_week_end,
            timezone=tz_name,
            style_score=breakdown.total,
            breakdown=breakdown,
            styled_days_count=styled_days_count,
            signals_count=signals_count,
            is_current=True,
            personal_rank=1,
            recorded_at=current_snap.recorded_at if current_snap else None,
            aggregation_policy=AGGREGATION_POLICY_V1,
        )

        ranked_all = rank_weekly_entries([current_raw, *historical_raw])
        current_entry = next(e for e in ranked_all if e.is_current)
        ranked_historical = [e for e in ranked_all if not e.is_current]

        previous_entry = next(
            (e for e in ranked_historical if e.week_start == previous_week_start),
            None,
        )
        best_historical = select_best_historical_week(ranked_historical)

        if previous_entry is not None:
            score_delta = current_entry.style_score - previous_entry.style_score
            if score_delta > 0:
                trend = "up"
            elif score_delta < 0:
                trend = "down"
            else:
                trend = "flat"
        else:
            score_delta = None
            trend = None

        is_tied_with_best = (
            best_historical is not None
            and current_entry.style_score == best_historical.style_score
        )

        return StyleJourneyHistoryResult(
            timezone=tz_name,
            aggregation_policy=AGGREGATION_POLICY_V1,
            current_week=current_entry,
            previous_week=previous_entry,
            best_historical_week=best_historical,
            comparison=StyleJourneyComparison(
                score_delta=score_delta,
                trend=trend,
                current_week_rank=current_entry.personal_rank,
                total_ranked_weeks=len(ranked_all),
                is_tied_with_best=is_tied_with_best,
            ),
            weeks=ranked_all[:limit],
            has_history=bool(ranked_historical),
        )


class RecordWeeklySnapshot:
    """Idempotent, immutable weekly Style Journey snapshot creation (SJ1)."""

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        saved_looks: SavedLookRepository,
        signals: LearningSignalRepository,
        snapshots: StyleJourneySnapshotRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._saved_looks = saved_looks
        self._signals = signals
        self._snapshots = snapshots
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        week_start: Optional[date] = None,
        timezone_override: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> tuple[WeeklyProgressEntry, bool]:
        profile = self._user_state.get_profile(user_id=user_id)
        tz = resolve_user_timezone(timezone_override, profile)
        tz_name = tz.key
        reference_now = now or utc_now()
        current_week_start, _ = week_bounds_for_instant(reference_now, tz)

        if week_start is None:
            target_week_start = current_week_start - timedelta(days=7)
        else:
            if week_start.weekday() != 0:
                raise validation(
                    [
                        {
                            "field": "weekStart",
                            "error": "must be a Monday (ISO week start)",
                        }
                    ]
                )
            if week_start > current_week_start:
                raise validation(
                    [
                        {
                            "field": "weekStart",
                            "error": "cannot record a snapshot for a future week",
                        }
                    ]
                )
            target_week_start = week_start

        existing = self._snapshots.get_for_week(
            user_id=user_id, week_start=target_week_start
        )
        if existing is not None:
            return (
                _entry_from_snapshot(
                    existing,
                    is_current=(target_week_start == current_week_start),
                ),
                False,
            )

        target_week_end = target_week_start + timedelta(days=6)
        breakdown = _compute_live_score_breakdown(
            user_id=user_id,
            wardrobe_items=self._wardrobe_items,
            saved_looks=self._saved_looks,
        )
        start_utc, end_utc = week_utc_range(target_week_start, tz)
        week_instants = self._signals.list_occurred_at_in_range(
            user_id=user_id,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        styled_days_count, signals_count = count_week_activity(
            week_instants, tz=tz, week_start=target_week_start
        )

        record, created = self._snapshots.record_if_absent(
            user_id=user_id,
            week_start=target_week_start,
            week_end=target_week_end,
            timezone_name=tz_name,
            style_score=breakdown.total,
            base_points=breakdown.base,
            wardrobe_points=breakdown.wardrobe_points,
            saved_points=breakdown.saved_points,
            styled_days_count=styled_days_count,
            signals_count=signals_count,
            aggregation_policy=AGGREGATION_POLICY_V1,
        )
        self._snapshots.commit()

        return (
            _entry_from_snapshot(
                record,
                is_current=(target_week_start == current_week_start),
            ),
            created,
        )

