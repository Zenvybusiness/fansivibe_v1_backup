"""SJ1 — Style Journey Weekly Progress History & Immutable Snapshots tests.

Covers:
1. Weekly aggregation (score, breakdown, styledDaysCount, signalsCount).
2. Week boundaries & timezone handling (UTC vs America/New_York vs Asia/Tokyo,
   persisted settings.timezone, invalid timezone 422).
3. Missing historical records (new user, gap week -> never fabricated).
4. Current vs previous week (up / down / flat).
5. Best-week calculation & tie-breaking.
6. Personal ranking and ties (1, 1, 3 competition ranking; no cross-user ranking).
7. User isolation & cascade delete.
8. Idempotent & immutable snapshot creation + read-only GET.
9. Existing Style Journey / M10 summary regression (`GET /v1/learning/summary`).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.style_journey import (
    AGGREGATION_POLICY_V1,
    WeeklyProgressEntry,
    count_week_activity,
    rank_weekly_entries,
    select_best_historical_week,
    week_bounds_for_instant,
)
from app.application.learning import StyleScoreBreakdown
from app.config.settings import get_settings
from app.infrastructure.auth import mint_access_token, token_digest
from app.infrastructure.db.models import (
    LearningSignals,
    StyleJourneyWeeklySnapshots,
    Users,
    UserSession,
    UserState,
    WardrobeItems,
)
from app.infrastructure.db.repositories import (
    SavedLookRepositorySQL,
    StyleJourneySnapshotRepositorySQL,
)
from tests.conftest import make_session

from app.main import app  # noqa: E402

client = TestClient(app)
HISTORY_PATH = "/v1/learning/journey/history"
SNAPSHOTS_PATH = "/v1/learning/journey/snapshots"
SUMMARY_PATH = "/v1/learning/summary"


def _auth_header(user_id) -> dict[str, str]:
    session_id = uuid4()
    token = mint_access_token(
        user_id=user_id,
        session_id=session_id,
        secret=get_settings().auth_secret,
        expires_in_s=3600,
    )
    Session = make_session()
    with Session() as session:
        session.add(
            UserSession(
                id=session_id,
                user_id=user_id,
                token_digest=token_digest(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        session.commit()
    return {"Authorization": f"Bearer {token}"}


def _seed_user(session, subject: str, *, tz: str | None = None):
    user = Users(
        auth_provider="sj1", auth_subject=subject, display_name=f"User {subject}"
    )
    session.add(user)
    session.flush()
    settings = {"timezone": tz} if tz is not None else {}
    session.add(
        UserState(
            user_id=user.id,
            style_profile={},
            preferences={"settings": settings} if settings else {},
            flags={},
        )
    )
    session.commit()
    return user.id


def _add_wardrobe(session, user_id, count: int) -> None:
    for i in range(count):
        session.add(
            WardrobeItems(
                user_id=user_id,
                name=f"Item {i}",
                category_id="tops",
                color_id="black",
            )
        )
    session.commit()


def _add_saved(session, user_id, count: int) -> None:
    repo = SavedLookRepositorySQL(session)
    for i in range(count):
        repo.insert(
            user_id=user_id,
            look_id=None,
            title=f"Look {i}",
            source_context="daily",
            snapshot={"kind": "daily"},
            idempotency_key=f"sj1-{user_id}-save-{i}-{uuid4()}",
            source_run_id=None,
        )
    session.commit()


def _insert_snapshot(
    session,
    *,
    user_id,
    week_start: date,
    style_score: int,
    wardrobe_points: int,
    saved_points: int,
    styled_days_count: int = 3,
    signals_count: int = 4,
    tz_name: str = "UTC",
) -> None:
    repo = StyleJourneySnapshotRepositorySQL(session)
    repo.record_if_absent(
        user_id=user_id,
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        timezone_name=tz_name,
        style_score=style_score,
        base_points=60,
        wardrobe_points=wardrobe_points,
        saved_points=saved_points,
        styled_days_count=styled_days_count,
        signals_count=signals_count,
        aggregation_policy=AGGREGATION_POLICY_V1,
    )
    session.commit()


# ---------------------------------------------------------------------------
# Pure unit tests (no DB required)
# ---------------------------------------------------------------------------


def test_week_boundaries_respect_user_timezone():
    """2026-11-23T01:30:00Z is Monday in UTC, Sunday night in America/New_York."""
    instant = datetime(2026, 11, 23, 1, 30, tzinfo=timezone.utc)
    utc_start, utc_end = week_bounds_for_instant(instant, ZoneInfo("UTC"))
    ny_start, ny_end = week_bounds_for_instant(instant, ZoneInfo("America/New_York"))

    assert utc_start == date(2026, 11, 23)
    assert utc_end == date(2026, 11, 29)
    assert ny_start == date(2026, 11, 16)
    assert ny_end == date(2026, 11, 22)


def test_count_week_activity_groups_signals_by_local_calendar_day():
    """Two signals on different UTC days that fall on the same NY day count as 1 styled day."""
    ny = ZoneInfo("America/New_York")  # UTC-5 in late Nov
    week_start = date(2026, 11, 16)
    instants = [
        # 2026-11-17 02:00 UTC -> 2026-11-16 21:00 NY (Mon)
        datetime(2026, 11, 17, 2, 0, tzinfo=timezone.utc),
        # 2026-11-17 04:30 UTC -> 2026-11-16 23:30 NY (Mon)
        datetime(2026, 11, 17, 4, 30, tzinfo=timezone.utc),
        # 2026-11-18 15:00 UTC -> 2026-11-18 10:00 NY (Wed)
        datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc),
        # Outside week: 2026-11-23 06:00 UTC -> 2026-11-23 01:00 NY (next Mon)
        datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc),
    ]
    styled_days, signals_count = count_week_activity(
        instants, tz=ny, week_start=week_start
    )
    assert styled_days == 2
    assert signals_count == 3


def test_personal_ranking_handles_ties_deterministically():
    """Competition ranking (1, 1, 3, 4) across user's own weeks."""
    def _mk(ws: date, score: int, is_cur: bool = False) -> WeeklyProgressEntry:
        return WeeklyProgressEntry(
            week_start=ws,
            week_end=ws + timedelta(days=6),
            timezone="UTC",
            style_score=score,
            breakdown=StyleScoreBreakdown(
                base=60, wardrobe_points=score - 60, saved_points=0, total=score
            ),
            styled_days_count=2,
            signals_count=2,
            is_current=is_cur,
            personal_rank=1,
            recorded_at=None,
            aggregation_policy=AGGREGATION_POLICY_V1,
        )

    entries = [
        _mk(date(2026, 11, 23), 74, is_cur=True),
        _mk(date(2026, 11, 16), 80),
        _mk(date(2026, 11, 9), 80),
        _mk(date(2026, 11, 2), 68),
    ]
    ranked = rank_weekly_entries(entries)
    by_week = {e.week_start: e for e in ranked}
    assert by_week[date(2026, 11, 16)].personal_rank == 1
    assert by_week[date(2026, 11, 9)].personal_rank == 1
    assert by_week[date(2026, 11, 23)].personal_rank == 3
    assert by_week[date(2026, 11, 2)].personal_rank == 4

    best = select_best_historical_week([e for e in ranked if not e.is_current])
    assert best is not None
    assert best.week_start == date(2026, 11, 16)
    assert best.style_score == 80


# ---------------------------------------------------------------------------
# PostgreSQL-backed integration tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("db")
def test_unauthenticated_requests_return_401(db):
    assert client.get(HISTORY_PATH).status_code == 401
    assert client.post(SNAPSHOTS_PATH, json={}).status_code == 401


@pytest.mark.usefixtures("db")
def test_new_user_with_no_history_never_fabricates_data(db):
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "new-user", tz="America/New_York")

    resp = client.get(HISTORY_PATH, headers=_auth_header(user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/New_York"
    assert body["aggregationPolicy"] == AGGREGATION_POLICY_V1
    assert body["hasHistory"] is False
    assert body["previousWeek"] is None
    assert body["bestHistoricalWeek"] is None
    assert body["currentWeek"]["styleScore"] == 60
    assert body["currentWeek"]["isCurrent"] is True
    assert body["currentWeek"]["personalRank"] == 1
    assert body["comparison"] == {
        "scoreDelta": None,
        "trend": None,
        "currentWeekRank": 1,
        "totalRankedWeeks": 1,
        "isTiedWithBest": False,
    }
    assert len(body["weeks"]) == 1


@pytest.mark.usefixtures("db")
def test_invalid_timezone_returns_422(db):
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "bad-tz")

    resp = client.get(
        f"{HISTORY_PATH}?timezone=Invalid/Nowhere", headers=_auth_header(user_id)
    )
    assert resp.status_code == 422

    patch_resp = client.patch(
        "/v1/users/me",
        json={"settings": {"timezone": "Invalid/Nowhere"}},
        headers=_auth_header(user_id),
    )
    assert patch_resp.status_code == 422


@pytest.mark.usefixtures("db")
def test_current_vs_previous_week_improvement_decline_and_gap(db):
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "cmp-user")
        now_utc = datetime.now(timezone.utc)
        cur_start, _ = week_bounds_for_instant(now_utc, ZoneInfo("UTC"))
        prev_start = cur_start - timedelta(days=7)
        older_start = cur_start - timedelta(days=14)

        # Previous week score = 70, older week score = 78 (best)
        _insert_snapshot(
            session,
            user_id=user_id,
            week_start=prev_start,
            style_score=70,
            wardrobe_points=10,
            saved_points=0,
        )
        _insert_snapshot(
            session,
            user_id=user_id,
            week_start=older_start,
            style_score=78,
            wardrobe_points=10,
            saved_points=8,
        )
        # Current live score = 60 + 12 + 4 = 76 (up +6 vs prev 70, rank 2 behind 78)
        _add_wardrobe(session, user_id, 12)
        _add_saved(session, user_id, 2)

    resp = client.get(HISTORY_PATH, headers=_auth_header(user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["hasHistory"] is True
    assert body["currentWeek"]["styleScore"] == 76
    assert body["previousWeek"]["styleScore"] == 70
    assert body["bestHistoricalWeek"]["styleScore"] == 78
    assert body["comparison"] == {
        "scoreDelta": 6,
        "trend": "up",
        "currentWeekRank": 2,
        "totalRankedWeeks": 3,
        "isTiedWithBest": False,
    }

    # Test gap week: user has only an older week (t-14d) and NO previous week (t-7d)
    with Session() as session:
        gap_user = _seed_user(session, "gap-user")
        _insert_snapshot(
            session,
            user_id=gap_user,
            week_start=older_start,
            style_score=72,
            wardrobe_points=12,
            saved_points=0,
        )
        _add_wardrobe(session, gap_user, 5)  # live score 65

    gap_resp = client.get(HISTORY_PATH, headers=_auth_header(gap_user))
    assert gap_resp.status_code == 200
    gap_body = gap_resp.json()
    assert gap_body["hasHistory"] is True
    assert gap_body["previousWeek"] is None
    assert gap_body["bestHistoricalWeek"]["styleScore"] == 72
    assert gap_body["comparison"]["scoreDelta"] is None
    assert gap_body["comparison"]["trend"] is None
    assert gap_body["comparison"]["currentWeekRank"] == 2
    assert gap_body["comparison"]["totalRankedWeeks"] == 2


@pytest.mark.usefixtures("db")
def test_idempotent_and_immutable_snapshot_creation(db):
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "snap-user", tz="UTC")
        _add_wardrobe(session, user_id, 5)  # score 65
        cur_start, _ = week_bounds_for_instant(
            datetime.now(timezone.utc), ZoneInfo("UTC")
        )
        prev_start = cur_start - timedelta(days=7)

    first = client.post(
        SNAPSHOTS_PATH,
        json={"weekStart": prev_start.isoformat()},
        headers=_auth_header(user_id),
    )
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert first.json()["snapshot"]["styleScore"] == 65

    # Mutate wardrobe after snapshot was recorded; replay must stay immutable!
    with Session() as session:
        _add_wardrobe(session, user_id, 10)  # live score now 75

    second = client.post(
        SNAPSHOTS_PATH,
        json={"weekStart": prev_start.isoformat()},
        headers=_auth_header(user_id),
    )
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["snapshot"]["styleScore"] == 65

    with Session() as session:
        count = session.execute(
            select(func.count())
            .select_from(StyleJourneyWeeklySnapshots)
            .where(StyleJourneyWeeklySnapshots.user_id == user_id)
        ).scalar_one()
        assert count == 1


@pytest.mark.usefixtures("db")
def test_user_isolation_and_get_performs_no_writes(db):
    Session = make_session()
    with Session() as session:
        user_a = _seed_user(session, "user-a")
        user_b = _seed_user(session, "user-b")
        cur_start, _ = week_bounds_for_instant(
            datetime.now(timezone.utc), ZoneInfo("UTC")
        )
        _insert_snapshot(
            session,
            user_id=user_b,
            week_start=cur_start - timedelta(days=7),
            style_score=95,
            wardrobe_points=20,
            saved_points=15,
        )
        _add_wardrobe(session, user_b, 20)

    resp_a = client.get(HISTORY_PATH, headers=_auth_header(user_a))
    assert resp_a.status_code == 200
    body_a = resp_a.json()
    assert body_a["hasHistory"] is False
    assert body_a["currentWeek"]["styleScore"] == 60
    assert body_a["previousWeek"] is None
    assert body_a["bestHistoricalWeek"] is None
    assert body_a["comparison"]["totalRankedWeeks"] == 1

    # Verify GET performed no writes
    with Session() as session:
        count_a = session.execute(
            select(func.count())
            .select_from(StyleJourneyWeeklySnapshots)
            .where(StyleJourneyWeeklySnapshots.user_id == user_a)
        ).scalar_one()
        assert count_a == 0


@pytest.mark.usefixtures("db")
def test_existing_learning_summary_regression(db):
    """GET /v1/learning/summary remains unchanged when SJ1 snapshots exist."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "reg-user")
        cur_start, _ = week_bounds_for_instant(
            datetime.now(timezone.utc), ZoneInfo("UTC")
        )
        _insert_snapshot(
            session,
            user_id=user_id,
            week_start=cur_start - timedelta(days=7),
            style_score=88,
            wardrobe_points=20,
            saved_points=8,
        )
        _add_wardrobe(session, user_id, 4)
        _add_saved(session, user_id, 1)
        session.add(
            LearningSignals(
                user_id=user_id,
                signal_type="look_saved",
                label="Saved look",
            )
        )
        session.commit()

    resp = client.get(SUMMARY_PATH, headers=_auth_header(user_id))
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {
        "styleScore",
        "breakdown",
        "streak",
        "recentSignals",
    }
    assert resp.json()["styleScore"] == 66  # 60 + 4 + 2
    assert resp.json()["recentSignals"] == ["Saved look"]


@pytest.mark.usefixtures("db")
def test_decline_flat_tie_with_best_and_snapshot_validation(db):
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "decline-user")
        cur_start, _ = week_bounds_for_instant(
            datetime.now(timezone.utc), ZoneInfo("UTC")
        )
        prev_start = cur_start - timedelta(days=7)
        # Previous week = 70, current live = 64 -> down -6
        _insert_snapshot(
            session,
            user_id=user_id,
            week_start=prev_start,
            style_score=70,
            wardrobe_points=10,
            saved_points=0,
        )
        _add_wardrobe(session, user_id, 4)

    down_resp = client.get(HISTORY_PATH, headers=_auth_header(user_id))
    assert down_resp.status_code == 200
    assert down_resp.json()["comparison"]["scoreDelta"] == -6
    assert down_resp.json()["comparison"]["trend"] == "down"
    assert down_resp.json()["comparison"]["isTiedWithBest"] is False

    # Add 6 more wardrobe items -> live score 70 (flat vs 70, tied with best!)
    with Session() as session:
        _add_wardrobe(session, user_id, 6)

    flat_resp = client.get(HISTORY_PATH, headers=_auth_header(user_id))
    assert flat_resp.status_code == 200
    assert flat_resp.json()["comparison"]["scoreDelta"] == 0
    assert flat_resp.json()["comparison"]["trend"] == "flat"
    assert flat_resp.json()["comparison"]["currentWeekRank"] == 1
    assert flat_resp.json()["comparison"]["isTiedWithBest"] is True

    # Non-Monday and future week validation
    tuesday = cur_start + timedelta(days=1)
    future_monday = cur_start + timedelta(days=7)
    assert (
        client.post(
            SNAPSHOTS_PATH,
            json={"weekStart": tuesday.isoformat()},
            headers=_auth_header(user_id),
        ).status_code
        == 422
    )
    assert (
        client.post(
            SNAPSHOTS_PATH,
            json={"weekStart": future_monday.isoformat()},
            headers=_auth_header(user_id),
        ).status_code
        == 422
    )


@pytest.mark.usefixtures("db")
def test_saved_user_timezone_preference_and_cascade_delete(db):
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "tz-pref-user")
        cur_start, _ = week_bounds_for_instant(
            datetime.now(timezone.utc), ZoneInfo("UTC")
        )
        _insert_snapshot(
            session,
            user_id=user_id,
            week_start=cur_start - timedelta(days=7),
            style_score=72,
            wardrobe_points=12,
            saved_points=0,
        )

    patch_resp = client.patch(
        "/v1/users/me",
        json={"settings": {"timezone": "Asia/Tokyo"}},
        headers=_auth_header(user_id),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["settings"]["timezone"] == "Asia/Tokyo"

    hist_resp = client.get(HISTORY_PATH, headers=_auth_header(user_id))
    assert hist_resp.status_code == 200
    assert hist_resp.json()["timezone"] == "Asia/Tokyo"

    # Deleting user cascades to style_journey_weekly_snapshots
    with Session() as session:
        user_obj = session.get(Users, user_id)
        assert user_obj is not None
        session.delete(user_obj)
        session.commit()
        remaining = session.execute(
            select(func.count())
            .select_from(StyleJourneyWeeklySnapshots)
            .where(StyleJourneyWeeklySnapshots.user_id == user_id)
        ).scalar_one()
        assert remaining == 0
