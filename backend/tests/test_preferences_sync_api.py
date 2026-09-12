"""API tests for the preferences sync chain (P1-2 hardening).

The Flutter preferences screen syncs mapped occasion codes through the
frozen `PATCH /v1/users/me` (endpoint #06, `UpdatePreferences`, JSONB
merge — no code change in this task). These tests prove the exact server
contract the sync relies on: auth, validation, replace persistence,
round-trip reads, R36 append-interop (event creation preserves UI-synced
values), and consumption by today's-look derivation (pref-only occasion).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import Users
from app.infrastructure.db.session import DATABASE_URL

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}


def _patch(occasions, headers=HEADERS):
    return client.patch(
        "/v1/users/me", headers=headers, json={"preferredOccasions": occasions}
    )


def _prefs():
    return client.get("/v1/users/me", headers=HEADERS).json()["preferences"][
        "preferredOccasions"
    ]


# Module-shared engine for helpers: one small pool for the whole file
# (per-call engines exhaust connection slots across a full-file run).
_HELPER_SESSIONS = sessionmaker(
    bind=create_engine(DATABASE_URL, pool_size=3, max_overflow=0),
    expire_on_commit=False,
)


def _session():
    return _HELPER_SESSIONS()


def _dev_user_id():
    from app.infrastructure.db.models import UserState

    with _session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(auth_provider="dev", auth_subject="dev-user", display_name="Dev User")
            session.add(user)
            session.flush()
            session.add(UserState(user_id=user.id))
            session.commit()
        return user.id


def _seed_wardrobe(user_id):
    with _session() as session:
        for name, category in (("Sync Tee", "tops"), ("Sync Jeans", "bottoms")):
            session.execute(
                text(
                    "INSERT INTO wardrobe_items "
                    "(user_id, name, category_id, color_id, material_id, is_favorite) "
                    "VALUES (:u, :n, :c, 'black', NULL, false)"
                ),
                {"u": str(user_id), "n": name, "c": category},
            )
        session.commit()


def _error(response):
    return response.json()["error"]


def test_patch_requires_auth():
    response = client.patch("/v1/users/me", json={"preferredOccasions": ["casual"]})
    assert response.status_code == 401
    assert _error(response)["code"] == "AUTHENTICATION_ERROR"


def test_patch_rejects_non_list():
    response = client.patch(
        "/v1/users/me", headers=HEADERS, json={"preferredOccasions": "casual"}
    )
    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_patch_persists_and_round_trips():
    response = _patch(["casual"])
    assert response.status_code == 200
    assert _prefs() == ["casual"]


def test_patch_replaces_and_empty_clears():
    assert _patch(["casual"]).status_code == 200
    assert _patch(["formal", "business"]).status_code == 200
    assert _prefs() == ["formal", "business"]
    assert _patch([]).status_code == 200
    assert _prefs() == []


def test_r36_append_preserves_synced_value():
    """The UI-synced code survives the contracted R36 event feed (P1-2:
    the synced value reaches the R36 path instead of being clobbered)."""
    assert _patch(["casual"]).status_code == 200
    created = client.post(
        "/v1/events",
        headers=HEADERS,
        json={"title": "Sync Gala", "eventType": "date", "eventDate": "2026-10-01"},
    )
    assert created.status_code == 201
    assert _prefs() == ["casual", "date"]


def test_synced_preference_is_consumed_by_today_derivation():
    """Pref-only occasion: with no events, today's look derives the
    synced code (P1-2: the value reaches the generation path)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    assert _patch(["date"]).status_code == 200
    response = client.get("/v1/looks/today", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["occasion"] == "date"


def test_patch_writes_only_user_state():
    with _session() as session:
        before = {
            table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            for table in (
                "wardrobe_items",
                "saved_looks",
                "learning_signals",
                "user_events",
                "feedback_events",
            )
        }
    assert _patch(["travel"]).status_code == 200
    with _session() as session:
        after = {
            table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            for table in before
        }
    assert after == before
