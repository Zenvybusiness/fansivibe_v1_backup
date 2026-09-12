"""API tests for the user/profile foundation (endpoint #06, `GET /v1/users/me`).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.db.models import UserState, Users
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}


def _dev_user_id(session):
    user = session.execute(
        select(Users).where(
            Users.auth_provider == "dev", Users.auth_subject == "dev-user"
        )
    ).scalar_one_or_none()
    if user is None:
        user = Users(
            auth_provider="dev", auth_subject="dev-user", display_name="Dev User"
        )
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
    return user.id


def _seed_state(db, style_profile=None, preferences=None):
    Session = db
    with Session() as session:
        user_id = _dev_user_id(session)
        state = session.get(UserState, user_id)
        if style_profile is not None:
            state.style_profile = style_profile
        if preferences is not None:
            state.preferences = preferences
        session.commit()
        return user_id


def _make_other_user():
    Session = make_session()
    with Session() as session:
        other = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other User"
        )
        session.add(other)
        session.flush()
        session.add(
            UserState(
                user_id=other.id,
                style_profile={"face_shape": "Round"},
            )
        )
        session.commit()
        return other.id


# --- auth / unauthorized -----------------------------------------------------


def test_get_profile_requires_auth():
    resp = client.get("/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_get_profile_rejects_invalid_token():
    resp = client.get("/v1/users/me", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


# --- authenticated user / missing profile ------------------------------------


def test_get_profile_returns_empty_profile_for_fresh_user(db):
    # A valid token resolves to the authenticated user even when no profile
    # data exists yet (e.g. "Explore Without Scanning" onboarding) — 200, not
    # an error, and nothing is fabricated.
    _seed_state(db)
    resp = client.get("/v1/users/me", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["displayName"] == "Dev User"
    assert body["styleProfile"] == {
        "faceShape": None,
        "skinTone": None,
        "bodyType": None,
        "styleType": None,
        "sourceRunId": None,
    }
    assert body["preferences"] == {}
    assert body["settings"] == {}
    assert body["flags"] == {}
    assert body["version"] == 0


def test_get_profile_returns_404_when_projection_missing(db):
    user_id = _seed_state(db)
    Session = make_session()
    with Session() as session:
        state = session.get(UserState, user_id)
        session.delete(state)
        session.commit()

    resp = client.get("/v1/users/me", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# --- valid profile retrieval --------------------------------------------------


def test_get_profile_returns_valid_profile(db):
    _seed_state(
        db,
        style_profile={
            "face_shape": "Oval",
            "skin_tone": "Warm Medium",
            "body_type": "Athletic",
            "style_type": "Modern Classic",
            "source_run_id": str(uuid.uuid4()),
        },
        preferences={"preferred_occasions": ["smart_casual", "business"]},
    )
    resp = client.get("/v1/users/me", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()

    assert body["displayName"] == "Dev User"
    assert body["styleProfile"] == {
        "faceShape": "Oval",
        "skinTone": "Warm Medium",
        "bodyType": "Athletic",
        "styleType": "Modern Classic",
        "sourceRunId": body["styleProfile"]["sourceRunId"],
    }
    assert body["preferences"] == {"preferredOccasions": ["smart_casual", "business"]}
    assert body["settings"] == {}
    assert body["flags"] == {}
    assert body["version"] == 0
    assert set(body.keys()) == {
        "displayName",
        "styleProfile",
        "preferences",
        "settings",
        "flags",
        "version",
        "memorySummary",
    }


# --- user ownership (OW-1, 404-not-403) --------------------------------------


def test_get_profile_is_owner_scoped(db):
    _seed_state(db, style_profile={"face_shape": "Oval"})
    _make_other_user()

    # `/users/me` always returns the authenticated user's own profile — never
    # another user's data.
    resp = client.get("/v1/users/me", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["displayName"] == "Dev User"
    assert body["styleProfile"] == {
        "faceShape": "Oval",
        "skinTone": None,
        "bodyType": None,
        "styleType": None,
        "sourceRunId": None,
    }
