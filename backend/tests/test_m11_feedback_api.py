"""API tests for M11 reactions (#35 `POST /v1/feedback`, UC-32).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers: auth, rating/reason validation, target cardinality, catalog
and saved-look target checks (malformed/foreign/unknown fail-closed),
general ratings, idempotent replay, conflicting-key 409, required key,
exact side-effect scope (one feedback_events row — no signals, no
activity, no wear/save/wardrobe/event mutation), target survival
(SET NULL) and user cascade.
"""

from __future__ import annotations

import json
from uuid import uuid4

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


def _catalog_look_code():
    with _session() as session:
        return session.execute(text("SELECT code FROM looks LIMIT 1")).scalar_one()


def _saved_look_id(user_id=None, title="Target Look"):
    """Persist one saved look via M7 (hairstyle context, no catalog link)."""
    resp = client.post(
        "/v1/looks/saved",
        json={"title": title, "sourceContext": "hairstyle", "snapshot": {}},
        headers={**HEADERS, "Idempotency-Key": f"m11-target-{uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _foreign_saved_look_id():
    """Direct-seeded other user with one saved look; returns its UUID."""
    with _session() as session:
        user = Users(
            auth_provider="m11", auth_subject=f"foreign-{uuid4()}", display_name="Foreign"
        )
        session.add(user)
        session.flush()
        row = session.execute(
            text(
                "INSERT INTO saved_looks "
                "(user_id, title, source_context, snapshot, idempotency_key) "
                "VALUES (:u, 'Foreign Save', 'outfit', '{}', :k) "
                "RETURNING id"
            ),
            {"u": str(user.id), "k": f"m11-foreign-{uuid4()}"},
        ).scalar_one()
        session.commit()
        return str(row)


def _snapshot(user_id):
    """DB-count snapshots proving the exact side-effect scope."""
    with _session() as session:
        counts = {}
        for table in (
            "feedback_events",
            "saved_looks",
            "learning_signals",
            "activity_days",
            "wardrobe_wear_events",
            "wardrobe_wear_groups",
            "wardrobe_items",
            "user_events",
        ):
            counts[table] = session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()
        prefs = session.execute(
            text("SELECT preferences FROM user_state WHERE user_id = :u"),
            {"u": str(user_id)},
        ).scalar_one_or_none()
        counts["preferences"] = json.dumps(prefs, sort_keys=True, default=str)
        return counts


def _feedback(payload, key="m11-key", headers=HEADERS):
    return client.post(
        "/v1/feedback",
        json=payload,
        headers={**headers, "Idempotency-Key": key},
    )


def _row(key):
    with _session() as session:
        return session.execute(
            text(
                "SELECT user_id, target_look_id, target_saved_look_id, rating, "
                "reason, idempotency_key FROM feedback_events "
                "WHERE idempotency_key = :k"
            ),
            {"k": key},
        ).mappings().one_or_none()


# A. authentication -------------------------------------------------------

def test_feedback_requires_auth():
    resp = client.post("/v1/feedback", json={"rating": "like"})
    assert resp.status_code == 401


# B. rating validation -> 422 ----------------------------------------------

def test_rating_missing_is_422():
    assert _feedback({}, key="m11-b1").status_code == 422


def test_rating_blank_is_422():
    _dev_user_id()
    for bad in ("", "   "):
        assert _feedback({"rating": bad}, key=f"m11-b2-{len(bad)}").status_code == 422


def test_rating_overlong_is_422():
    _dev_user_id()
    assert _feedback({"rating": "x" * 201}, key="m11-b3").status_code == 422


def test_rating_non_string_is_422():
    _dev_user_id()
    assert _feedback({"rating": 5}, key="m11-b4").status_code == 422


# C. reason validation -> 422 -----------------------------------------------

def test_reason_overlong_or_blank_is_422():
    _dev_user_id()
    assert _feedback(
        {"rating": "like", "reason": "x" * 2001}, key="m11-c1"
    ).status_code == 422
    assert _feedback(
        {"rating": "like", "reason": "  "}, key="m11-c2"
    ).status_code == 422


# D. target cardinality -> 422 -----------------------------------------------

def test_two_targets_is_422():
    user_id = _dev_user_id()
    saved_id = _saved_look_id(user_id)
    code = _catalog_look_code()
    resp = _feedback(
        {"rating": "like", "targetLookId": code, "targetSavedLookId": saved_id},
        key="m11-d1",
    )
    assert resp.status_code == 422


# E. look target: unknown -> 404, known -> 204 ----------------------------------

def test_unknown_look_code_is_404_with_nothing_stored():
    _dev_user_id()
    resp = _feedback(
        {"rating": "like", "targetLookId": "no-such-look"}, key="m11-e1"
    )
    assert resp.status_code == 404
    assert _row("m11-e1") is None


def test_known_look_code_is_204():
    user_id = _dev_user_id()
    code = _catalog_look_code()
    resp = _feedback({"rating": "like", "targetLookId": code}, key="m11-e2")
    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    row = _row("m11-e2")
    assert row is not None
    assert row["target_look_id"] == code
    assert row["target_saved_look_id"] is None
    assert row["rating"] == "like"
    assert str(row["user_id"]) == str(user_id)


# F. saved-look target: malformed -> 422, unknown/foreign -> 404 ------------------

def test_malformed_saved_look_id_is_422():
    _dev_user_id()
    resp = _feedback(
        {"rating": "dislike", "targetSavedLookId": "not-a-uuid"}, key="m11-f1"
    )
    assert resp.status_code == 422
    assert _row("m11-f1") is None


def test_unknown_saved_look_id_is_404_with_nothing_stored():
    _dev_user_id()
    resp = _feedback(
        {"rating": "dislike", "targetSavedLookId": str(uuid4())}, key="m11-f2"
    )
    assert resp.status_code == 404
    assert _row("m11-f2") is None


def test_foreign_saved_look_id_is_404_with_nothing_stored():
    _dev_user_id()
    foreign_id = _foreign_saved_look_id()
    resp = _feedback(
        {"rating": "dislike", "targetSavedLookId": foreign_id}, key="m11-f3"
    )
    assert resp.status_code == 404
    assert _row("m11-f3") is None


def test_owned_saved_look_id_is_204():
    user_id = _dev_user_id()
    saved_id = _saved_look_id(user_id)
    resp = _feedback(
        {"rating": "dislike", "reason": "Too formal for me",
         "targetSavedLookId": saved_id},
        key="m11-f4",
    )
    assert resp.status_code == 204, resp.text
    row = _row("m11-f4")
    assert row is not None
    assert str(row["target_saved_look_id"]) == saved_id
    assert row["target_look_id"] is None
    assert row["reason"] == "Too formal for me"
    assert str(row["user_id"]) == str(user_id)


# G. general rating (no targets) -> 204 ------------------------------------------

def test_general_rating_is_204():
    user_id = _dev_user_id()
    resp = _feedback({"rating": "helpful"}, key="m11-g1")
    assert resp.status_code == 204, resp.text
    row = _row("m11-g1")
    assert row is not None
    assert row["rating"] == "helpful"
    assert row["reason"] is None
    assert row["target_look_id"] is None
    assert row["target_saved_look_id"] is None
    assert str(row["user_id"]) == str(user_id)


# H. idempotency: replay + conflict + required key -----------------------------------

def test_replay_returns_ack_without_second_row():
    _dev_user_id()
    payload = {"rating": "like"}
    first = _feedback(payload, key="m11-h1")
    second = _feedback(payload, key="m11-h1")
    assert first.status_code == 204 and second.status_code == 204
    with _session() as session:
        total = session.execute(
            text("SELECT COUNT(*) FROM feedback_events WHERE idempotency_key = :k"),
            {"k": "m11-h1"},
        ).scalar_one()
        assert total == 1


def test_conflicting_key_is_409():
    _dev_user_id()
    first = _feedback({"rating": "like"}, key="m11-h2")
    assert first.status_code == 204
    conflict = _feedback({"rating": "dislike"}, key="m11-h2")
    assert conflict.status_code == 409
    with _session() as session:
        total = session.execute(
            text("SELECT COUNT(*) FROM feedback_events WHERE idempotency_key = :k"),
            {"k": "m11-h2"},
        ).scalar_one()
        assert total == 1


def test_missing_idempotency_key_is_422():
    _dev_user_id()
    resp = client.post(
        "/v1/feedback", json={"rating": "like"}, headers=HEADERS
    )
    assert resp.status_code == 422


# I. exact side-effect scope ---------------------------------------------------------

def test_submit_writes_exactly_one_row_and_nothing_else():
    user_id = _dev_user_id()
    before = _snapshot(user_id)
    resp = _feedback({"rating": "like"}, key="m11-i1")
    assert resp.status_code == 204
    after = _snapshot(user_id)
    assert after["feedback_events"] == before["feedback_events"] + 1
    for table in (
        "saved_looks",
        "learning_signals",
        "activity_days",
        "wardrobe_wear_events",
        "wardrobe_wear_groups",
        "wardrobe_items",
        "user_events",
    ):
        assert after[table] == before[table] == 0, table
    assert after["preferences"] == before["preferences"]


# J. target survival + user cascade -----------------------------------------------------

def test_feedback_survives_saved_look_delete_with_nulled_target():
    user_id = _dev_user_id()
    saved_id = _saved_look_id(user_id)
    resp = _feedback(
        {"rating": "like", "targetSavedLookId": saved_id}, key="m11-j1"
    )
    assert resp.status_code == 204
    deleted = client.delete(f"/v1/looks/saved/{saved_id}", headers=HEADERS)
    assert deleted.status_code == 204
    row = _row("m11-j1")
    assert row is not None
    assert row["target_saved_look_id"] is None


def test_user_delete_cascades_feedback():
    user_id = _dev_user_id()
    resp = _feedback({"rating": "like"}, key="m11-j2")
    assert resp.status_code == 204
    with _session() as session:
        session.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(user_id)})
        session.commit()
        total = session.execute(text("SELECT COUNT(*) FROM feedback_events")).scalar_one()
        assert total == 0
