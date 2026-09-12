"""M10-B backend tests — `GET /v1/learning/summary` (#34, STEP 19.15).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; schema migrates to `head`).

Acceptance matrix (DEC-019/DEC-020/DEC-021):
A. unauthenticated → 401
B. empty user → 200 zero summary (exact zero state)
C. wardrobe contributes one point per item up to 20
D. saved looks contribute two points each up to 20
E. combined score is exactly base + wardrobe + saved
F. score never exceeds 100
G. score never drops below 60
H. breakdown total equals styleScore
I. breakdown has exactly the frozen fields
J. today's activity gives streak 1
K. consecutive today+yesterday gives streak 2
L. missing day breaks streak
M. future activity is ignored
N. no activity gives streak 0
O. recent signals newest first
P. recent signals capped at 20
Q. raw feedback/reason text is not returned
R. signal context/type/timestamp are not returned
S. user A cannot see user B's score inputs
T. user A cannot see user B's signals/activity
U. GET performs no writes
V. existing learning-signal rows remain unchanged
W. existing activity_days rows remain unchanged

M10-B is backend only — no Flutter coverage here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.learning import utc_today
from app.infrastructure.db.models import (
    ActivityDays,
    LearningSignals,
    SavedLooks,
    Users,
    WardrobeItems,
)
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
)
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}
PATH = "/v1/learning/summary"

ZERO_BODY = {
    "styleScore": 60,
    "breakdown": {
        "base": 60,
        "wardrobePoints": 0,
        "savedPoints": 0,
        "total": 60,
    },
    "streak": 0,
    "recentSignals": [],
}


def _dev_user_id():
    Session = make_session()
    with Session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(
                auth_provider="dev",
                auth_subject="dev-user",
                display_name="Dev User",
            )
            session.add(user)
            session.commit()
        return user.id


def _seed_user(session, subject: str):
    user = Users(
        auth_provider="m10b", auth_subject=subject, display_name="M10-B User"
    )
    session.add(user)
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


def _add_saved(session, user_id, count: int, start: int = 0) -> None:
    repo = SavedLookRepositorySQL(session)
    for i in range(start, start + count):
        repo.insert(
            user_id=user_id,
            look_id=None,
            title=f"Saved {i}",
            source_context="hairstyle",
            snapshot={"kind": "hairstyle"},
            idempotency_key=f"m10b-{user_id}-save-{i}",
            source_run_id=None,
        )
    session.commit()


def _add_signal(
    session,
    user_id,
    label: str,
    signal_type: str = "look_saved",
    context: dict | None = None,
):
    repo = LearningSignalRepositorySQL(session)
    repo.insert_look_saved(
        user_id=user_id,
        signal_type=signal_type,
        label=label,
        context=context if context is not None else {"source_context": "hairstyle"},
    )
    session.commit()


def _add_day(session, user_id, day, styled: bool = True) -> None:
    ActivityDayRepositorySQL(session).upsert_styled_day(
        user_id=user_id, day=day
    )
    if not styled:
        row = session.execute(
            select(ActivityDays).where(
                ActivityDays.user_id == user_id, ActivityDays.day == day
            )
        ).scalar_one()
        row.styled = False
    session.commit()


def _table_counts(session) -> dict:
    return {
        "wardrobe": session.execute(
            select(func.count()).select_from(WardrobeItems)
        ).scalar_one(),
        "saved": session.execute(
            select(func.count()).select_from(SavedLooks)
        ).scalar_one(),
        "signals": session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one(),
        "days": session.execute(
            select(func.count()).select_from(ActivityDays)
        ).scalar_one(),
    }


# ---------------------------------------------------------------------------
# A–B: auth + zero state
# ---------------------------------------------------------------------------


def test_A_unauthenticated_returns_401():
    """A. Bearer auth is required (existing dep, no new auth logic)."""
    resp = client.get(PATH)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_B_empty_user_receives_exact_zero_summary():
    """B. Zero-data user → 200 with the exact frozen zero state."""
    _dev_user_id()
    resp = client.get(PATH, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == ZERO_BODY


# ---------------------------------------------------------------------------
# C–I: score math (DEC-019 §B, DEC-021)
# ---------------------------------------------------------------------------


def test_C_wardrobe_contributes_one_point_per_item_capped_at_20():
    """C. +1 per owned item; the 21st item adds nothing."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 3)
    assert client.get(PATH, headers=HEADERS).json()["breakdown"][
        "wardrobePoints"
    ] == 3
    with Session() as session:
        _add_wardrobe(session, user_id, 22)
    body = client.get(PATH, headers=HEADERS).json()
    assert body["breakdown"]["wardrobePoints"] == 20
    assert body["styleScore"] == 80


def test_D_saved_looks_contribute_two_points_each_capped_at_20():
    """D. +2 per saved look; points stop at 20 (10+ saves)."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_saved(session, user_id, 3)
    assert client.get(PATH, headers=HEADERS).json()["breakdown"][
        "savedPoints"
    ] == 6
    with Session() as session:
        _add_saved(session, user_id, 12, start=3)
    body = client.get(PATH, headers=HEADERS).json()
    assert body["breakdown"]["savedPoints"] == 20
    assert body["styleScore"] == 80


def test_E_combined_score_is_base_plus_wardrobe_plus_saved():
    """E. 5 items + 4 saves → 60 + 5 + 8 = 73."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 5)
        _add_saved(session, user_id, 4)
    body = client.get(PATH, headers=HEADERS).json()
    assert body["styleScore"] == 73
    assert body["breakdown"] == {
        "base": 60,
        "wardrobePoints": 5,
        "savedPoints": 8,
        "total": 73,
    }


def test_F_score_never_exceeds_100():
    """F. 30 items + 30 saves still clamp to 100."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 30)
        _add_saved(session, user_id, 30)
    body = client.get(PATH, headers=HEADERS).json()
    assert body["styleScore"] == 100
    assert body["breakdown"]["total"] == 100


def test_G_score_never_drops_below_60():
    """G. The floor holds for a user with no countable inputs."""
    _dev_user_id()
    body = client.get(PATH, headers=HEADERS).json()
    assert body["styleScore"] == 60
    assert body["styleScore"] >= 60


def test_H_breakdown_total_equals_style_score():
    """H. total is the identity base + wardrobe + saved == styleScore."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 7)
        _add_saved(session, user_id, 2)
    body = client.get(PATH, headers=HEADERS).json()
    breakdown = body["breakdown"]
    assert breakdown["total"] == body["styleScore"]
    assert (
        breakdown["base"]
        + breakdown["wardrobePoints"]
        + breakdown["savedPoints"]
        == body["styleScore"]
    )


def test_I_breakdown_has_exactly_the_frozen_fields():
    """I. Four top-level keys; four breakdown keys — nothing invented."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 1)
        _add_saved(session, user_id, 1)
    body = client.get(PATH, headers=HEADERS).json()
    assert set(body.keys()) == {
        "styleScore",
        "breakdown",
        "streak",
        "recentSignals",
    }
    assert set(body["breakdown"].keys()) == {
        "base",
        "wardrobePoints",
        "savedPoints",
        "total",
    }


# ---------------------------------------------------------------------------
# J–N: streak (M10-A derivation, DEC-020 §D)
# ---------------------------------------------------------------------------


def test_J_today_activity_gives_streak_1():
    """J. Today's styled day → streak 1."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_day(session, user_id, utc_today())
    assert client.get(PATH, headers=HEADERS).json()["streak"] == 1


def test_K_consecutive_today_plus_yesterday_gives_2():
    """K. Unbroken run ending today counts every consecutive day."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_day(session, user_id, utc_today() - timedelta(days=1))
        _add_day(session, user_id, utc_today())
    assert client.get(PATH, headers=HEADERS).json()["streak"] == 2


def test_L_missing_day_breaks_streak():
    """L. Gap yesterday with older history → trailing run only."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_day(session, user_id, utc_today() - timedelta(days=3))
        _add_day(session, user_id, utc_today() - timedelta(days=2))
        _add_day(session, user_id, utc_today())
    assert client.get(PATH, headers=HEADERS).json()["streak"] == 1


def test_M_future_activity_is_ignored():
    """M. Future-dated rows never contribute to the streak."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_day(session, user_id, utc_today() + timedelta(days=1))
    assert client.get(PATH, headers=HEADERS).json()["streak"] == 0


def test_N_no_activity_gives_streak_0():
    """N. Countable inputs without any activity day → streak 0."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 4)
        _add_saved(session, user_id, 2)
    body = client.get(PATH, headers=HEADERS).json()
    assert body["streak"] == 0
    assert body["styleScore"] == 60 + 4 + 4


# ---------------------------------------------------------------------------
# O–R: recent signals (DEC-020 §E)
# ---------------------------------------------------------------------------


def _retime_labels(session, ordered: list[tuple[str, int]]) -> None:
    """Pin distinct occurred_at instants so recency order is exact.

    `ordered` is [(label, hours_ago)] — oldest first for readability.
    """
    now = datetime.now(timezone.utc)
    for label, hours_ago in ordered:
        row = session.execute(
            select(LearningSignals).where(LearningSignals.label == label)
        ).scalar_one()
        row.occurred_at = now - timedelta(hours=hours_ago)
    session.commit()


def test_O_recent_signals_newest_first():
    """O. Labels return occurred_at desc (id desc breaks ties)."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_signal(session, user_id, "old save")
        _add_signal(session, user_id, "mid save")
        _add_signal(session, user_id, "new save")
        _retime_labels(
            session, [("old save", 3), ("mid save", 2), ("new save", 1)]
        )
    body = client.get(PATH, headers=HEADERS).json()
    assert body["recentSignals"] == ["new save", "mid save", "old save"]


def test_P_recent_signals_capped_at_20():
    """P. 25 signals → newest 20 labels only, newest first."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        for i in range(25):
            _add_signal(session, user_id, f"sig-{i:02d}")
        _retime_labels(
            session, [(f"sig-{i:02d}", 25 - i) for i in range(25)]
        )
    body = client.get(PATH, headers=HEADERS).json()
    assert body["recentSignals"] == [f"sig-{i:02d}" for i in range(24, 4, -1)]
    assert len(body["recentSignals"]) == 20


def test_Q_raw_feedback_reason_text_is_not_returned():
    """Q. Private reason text stored in context never reaches the wire —
    only the server-owned label does."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_signal(
            session,
            user_id,
            "Textured Quiff",
            signal_type="suggestion_opened",
            context={
                "interaction_type": "opened",
                "reason": "super private why xyzzy",
            },
        )
    resp = client.get(PATH, headers=HEADERS)
    body = resp.json()
    assert body["recentSignals"] == ["Textured Quiff"]
    assert "super private why xyzzy" not in resp.text


def test_R_signal_context_type_timestamp_are_not_returned():
    """R. Elements are bare label strings — no objects, no metadata."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_signal(
            session,
            user_id,
            "Evening Linen",
            signal_type="assistant_navigation",
            context={"interaction_type": "navigated"},
        )
    resp = client.get(PATH, headers=HEADERS)
    body = resp.json()
    assert body["recentSignals"] == ["Evening Linen"]
    assert all(isinstance(item, str) for item in body["recentSignals"])
    for forbidden in (
        "signal_type",
        "occurred_at",
        "interaction_type",
        "run_id",
        "source_context",
        "context",
    ):
        assert forbidden not in resp.text


# ---------------------------------------------------------------------------
# S–T: cross-user isolation (OW-1)
# ---------------------------------------------------------------------------


def test_S_user_cannot_see_other_users_score_inputs():
    """S. Heavy user B activity is invisible to fresh user A (dev)."""
    _dev_user_id()
    Session = make_session()
    with Session() as session:
        user_b = _seed_user(session, "s-user-b")
        _add_wardrobe(session, user_b, 30)
        _add_saved(session, user_b, 30)
        _add_day(session, user_b, utc_today())
    assert client.get(PATH, headers=HEADERS).json() == ZERO_BODY


def test_T_user_cannot_see_other_users_signals_or_activity():
    """T. User B signals/days never leak into user A's summary."""
    _dev_user_id()
    Session = make_session()
    with Session() as session:
        user_b = _seed_user(session, "t-user-b")
        _add_signal(session, user_b, "B private save")
        _add_day(session, user_b, utc_today())
    body = client.get(PATH, headers=HEADERS).json()
    assert body["recentSignals"] == []
    assert body["streak"] == 0
    assert "B private save" not in client.get(PATH, headers=HEADERS).text


# ---------------------------------------------------------------------------
# U–W: GET performs no writes
# ---------------------------------------------------------------------------


def test_U_get_performs_no_writes():
    """U. Table counts are identical before and after the GET."""
    user_id = _dev_user_id()
    Session = make_session()
    with Session() as session:
        _add_wardrobe(session, user_id, 2)
        _add_saved(session, user_id, 1)
        _add_signal(session, user_id, "seed save")
        _add_day(session, user_id, utc_today())
    with Session() as session:
        before = _table_counts(session)
    assert client.get(PATH, headers=HEADERS).status_code == 200
    with Session() as session:
        assert _table_counts(session) == before


def test_V_existing_signal_rows_remain_unchanged():
    """V. Signal rows are byte-identical across the GET."""
    user_id = _dev_user_id()
    Session = make_session()

    def _snapshot(s):
        return s.execute(
            select(
                LearningSignals.signal_type,
                LearningSignals.label,
                LearningSignals.context,
                LearningSignals.occurred_at,
            )
            .where(LearningSignals.user_id == user_id)
            .order_by(LearningSignals.id.asc())
        ).all()

    with Session() as session:
        _add_signal(session, user_id, "keep me", context={"k": "v"})
        before = _snapshot(session)
    client.get(PATH, headers=HEADERS)
    with Session() as session:
        assert _snapshot(session) == before


def test_W_existing_activity_rows_remain_unchanged():
    """W. Activity rows are identical across the GET (no day creation)."""
    user_id = _dev_user_id()
    Session = make_session()

    def _snapshot(s):
        return s.execute(
            select(ActivityDays.day, ActivityDays.styled, ActivityDays.summary)
            .where(ActivityDays.user_id == user_id)
            .order_by(ActivityDays.day.asc())
        ).all()

    with Session() as session:
        _add_day(session, user_id, utc_today() - timedelta(days=1))
        before = _snapshot(session)
    body = client.get(PATH, headers=HEADERS).json()
    assert body["streak"] == 1
    with Session() as session:
        assert _snapshot(session) == before
