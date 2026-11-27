"""SJ3 — Style Journey End-to-End Verification (Backend Integration Suite).

Verifies the complete Style Journey flow against the disposable PostgreSQL
database using supported application HTTP endpoints:
1. Authenticate a test user (`POST /v1/auth/register` & `POST /v1/auth/login`).
2. Generate valid learning activity via supported flows:
   - `POST /v1/wardrobe/items`
   - `POST /v1/looks/today/save`
3. Record weekly snapshots using the SJ1 mechanism (`POST /v1/learning/journey/snapshots`),
   and verify idempotency + immutability.
4. Fetch `GET /v1/learning/journey/history`.
5. Verify current week, previous week, score delta, personal ranking, and best week,
   while preserving M10 `GET /v1/learning/summary` score & streak.
6. Verify a new user with no history sees the empty state (`hasHistory: False`).
7. Verify another user cannot access the first user's history.
8. Verify authentication expiry/revocation (`POST /v1/auth/logout` -> 401)
   and re-authentication refresh (`POST /v1/auth/login` -> 200).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.style_journey import week_bounds_for_instant
from app.infrastructure.db.models import StyleJourneyWeeklySnapshots
from tests.conftest import make_session

from app.main import app  # noqa: E402

client = TestClient(app)


def _register_user(email: str, password: str, display_name: str) -> dict:
    resp = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "displayName": display_name,
        },
        headers={"Idempotency-Key": f"sj3-reg-{uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _login_user(email: str, password: str) -> dict:
    resp = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("db")
def test_sj3_end_to_end_style_journey_flow(db):
    # 1. Authenticate User 1 via supported /v1/auth/register
    email_1 = f"sj3-user1-{uuid4().hex[:8]}@example.com"
    password_1 = "FansivibeSJ3Test!1"
    reg_1 = _register_user(email_1, password_1, "SJ3 Tester One")
    token_1 = reg_1["accessToken"]
    user_1_id = UUID(jwt.decode(token_1, options={"verify_signature": False})["sub"])

    # Configure timezone preference via supported PATCH /v1/users/me
    tz_resp = client.patch(
        "/v1/users/me",
        json={"settings": {"timezone": "UTC"}},
        headers=_bearer(token_1),
    )
    assert tz_resp.status_code == 200, tz_resp.text
    assert tz_resp.json()["settings"]["timezone"] == "UTC"

    # 2. Generate valid learning activity using supported application flows
    # Add 5 wardrobe items (+5 wardrobePoints)
    for i in range(5):
        item_resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": f"SJ3 Piece {i}",
                "category": "tops",
                "color": "black",
            },
            headers=_bearer(token_1),
        )
        assert item_resp.status_code == 201, item_resp.text

    # Save 2 today looks (+4 savedPoints, streak=1, signals & activity_days)
    for i in range(2):
        save_resp = client.post(
            "/v1/looks/today/save",
            json={
                "title": f"SJ3 Daily Look {i}",
                "sourceContext": "daily",
                "snapshot": {"kind": "daily", "index": i},
            },
            headers={
                **_bearer(token_1),
                "Idempotency-Key": f"sj3-save-{i}-{uuid4()}",
            },
        )
        assert save_resp.status_code == 201, save_resp.text

    # Verify M10 GET /v1/learning/summary reflects 60 + 5 + 4 = 69, streak >= 1
    summary_before = client.get("/v1/learning/summary", headers=_bearer(token_1))
    assert summary_before.status_code == 200, summary_before.text
    summary_before_body = summary_before.json()
    assert summary_before_body["styleScore"] == 69
    assert summary_before_body["breakdown"] == {
        "base": 60,
        "wardrobePoints": 5,
        "savedPoints": 4,
        "total": 69,
    }
    assert summary_before_body["streak"] >= 1
    assert len(summary_before_body["recentSignals"]) > 0

    # 3. Record weekly snapshot for previous week using SJ1 mechanism
    cur_start, _ = week_bounds_for_instant(datetime.now(timezone.utc), ZoneInfo("UTC"))
    prev_start = cur_start - timedelta(days=7)

    snap_resp_1 = client.post(
        "/v1/learning/journey/snapshots",
        json={"weekStart": prev_start.isoformat()},
        headers=_bearer(token_1),
    )
    assert snap_resp_1.status_code == 200, snap_resp_1.text
    snap_1_body = snap_resp_1.json()
    assert snap_1_body["created"] is True
    assert snap_1_body["snapshot"]["weekStart"] == prev_start.isoformat()
    assert snap_1_body["snapshot"]["styleScore"] == 69

    # Verify idempotency on replay
    snap_resp_2 = client.post(
        "/v1/learning/journey/snapshots",
        json={"weekStart": prev_start.isoformat()},
        headers=_bearer(token_1),
    )
    assert snap_resp_2.status_code == 200, snap_resp_2.text
    assert snap_resp_2.json()["created"] is False
    assert snap_resp_2.json()["snapshot"]["styleScore"] == 69

    # Add 3 more wardrobe items in current week (+3 -> current score 72)
    # and verify previous week snapshot remains immutable at 69
    for i in range(3):
        item_resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": f"SJ3 Current Piece {i}",
                "category": "bottoms",
                "color": "navy",
            },
            headers=_bearer(token_1),
        )
        assert item_resp.status_code == 201, item_resp.text

    snap_resp_3 = client.post(
        "/v1/learning/journey/snapshots",
        json={"weekStart": prev_start.isoformat()},
        headers=_bearer(token_1),
    )
    assert snap_resp_3.status_code == 200, snap_resp_3.text
    assert snap_resp_3.json()["created"] is False
    assert snap_resp_3.json()["snapshot"]["styleScore"] == 69

    # 4 & 5. Fetch GET /v1/learning/journey/history and verify all fields
    history_resp = client.get("/v1/learning/journey/history", headers=_bearer(token_1))
    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()

    assert history["hasHistory"] is True
    assert history["timezone"] == "UTC"
    assert history["currentWeek"]["weekStart"] == cur_start.isoformat()
    assert history["currentWeek"]["styleScore"] == 72
    assert history["currentWeek"]["isCurrent"] is True
    assert history["currentWeek"]["styledDaysCount"] >= 1
    assert history["currentWeek"]["signalsCount"] >= 10  # 8 wardrobe + 2 saved

    assert history["previousWeek"] is not None
    assert history["previousWeek"]["weekStart"] == prev_start.isoformat()
    assert history["previousWeek"]["styleScore"] == 69
    assert history["previousWeek"]["isCurrent"] is False

    assert history["bestHistoricalWeek"] is not None
    assert history["bestHistoricalWeek"]["weekStart"] == prev_start.isoformat()
    assert history["bestHistoricalWeek"]["styleScore"] == 69

    assert history["comparison"] == {
        "scoreDelta": 3,
        "trend": "up",
        "currentWeekRank": 1,
        "totalRankedWeeks": 2,
        "isTiedWithBest": False,
    }
    assert len(history["weeks"]) == 2

    # Verify M10 summary matches current week score & preserves streak
    summary_after = client.get("/v1/learning/summary", headers=_bearer(token_1))
    assert summary_after.status_code == 200, summary_after.text
    assert summary_after.json()["styleScore"] == 72
    assert summary_after.json()["streak"] == summary_before_body["streak"]

    # 6 & 7. Register User 2 with no history -> empty state & user isolation
    email_2 = f"sj3-user2-{uuid4().hex[:8]}@example.com"
    reg_2 = _register_user(email_2, "FansivibeSJ3Test!2", "SJ3 New User")
    token_2 = reg_2["accessToken"]
    user_2_id = UUID(jwt.decode(token_2, options={"verify_signature": False})["sub"])
    assert user_2_id != user_1_id

    history_2_resp = client.get("/v1/learning/journey/history", headers=_bearer(token_2))
    assert history_2_resp.status_code == 200, history_2_resp.text
    history_2 = history_2_resp.json()
    assert history_2["hasHistory"] is False
    assert history_2["previousWeek"] is None
    assert history_2["bestHistoricalWeek"] is None
    assert history_2["currentWeek"]["styleScore"] == 60
    assert history_2["comparison"] == {
        "scoreDelta": None,
        "trend": None,
        "currentWeekRank": 1,
        "totalRankedWeeks": 1,
        "isTiedWithBest": False,
    }
    assert len(history_2["weeks"]) == 1

    # Confirm DB has 1 snapshot for User 1 and 0 snapshots for User 2
    Session = make_session()
    with Session() as session:
        count_1 = session.execute(
            select(func.count())
            .select_from(StyleJourneyWeeklySnapshots)
            .where(StyleJourneyWeeklySnapshots.user_id == user_1_id)
        ).scalar_one()
        count_2 = session.execute(
            select(func.count())
            .select_from(StyleJourneyWeeklySnapshots)
            .where(StyleJourneyWeeklySnapshots.user_id == user_2_id)
        ).scalar_one()
        assert count_1 == 1
        assert count_2 == 0

    # 8. Auth expiry/revocation & refresh/re-login behavior
    logout_resp = client.post("/v1/auth/logout", headers=_bearer(token_1))
    assert logout_resp.status_code == 204, logout_resp.text

    expired_hist = client.get("/v1/learning/journey/history", headers=_bearer(token_1))
    assert expired_hist.status_code == 401
    expired_snap = client.post(
        "/v1/learning/journey/snapshots",
        json={"weekStart": prev_start.isoformat()},
        headers=_bearer(token_1),
    )
    assert expired_snap.status_code == 401

    # Re-login issues a fresh token that restores access
    login_1 = _login_user(email_1, password_1)
    fresh_token_1 = login_1["accessToken"]
    assert fresh_token_1 != token_1

    refreshed_hist = client.get(
        "/v1/learning/journey/history", headers=_bearer(fresh_token_1)
    )
    assert refreshed_hist.status_code == 200
    assert refreshed_hist.json()["currentWeek"]["styleScore"] == 72
    assert refreshed_hist.json()["previousWeek"]["styleScore"] == 69
