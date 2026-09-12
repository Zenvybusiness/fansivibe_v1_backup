"""API tests for the saved-look delete surface (#25, DEC-013).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).

Covers: owner delete → 204 with empty body and the row (snapshot
included) physically gone; repeated delete → 404; missing id → 404;
foreign id → 404 (never 403) with the row intact; malformed UUID → 422;
multi-row isolation; learning signals preserved with no new signal type;
auth required. POST/GET behavior is unchanged (covered by
`test_saved_looks.py` / `test_saved_looks_use_case.py`).
"""

from __future__ import annotations

import copy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.db.models import LearningSignals, SavedLooks, Users
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

SNAPSHOT = {
    "appearance": {
        "faceShape": "Oval",
    },
    "recommendations": {
        "top": {
            "id": "textured_quiff",
            "name": "Textured Quiff",
            "description": "A modern take on the classic quiff.",
            "matchScore": 0.94,
            "reasons": ["Oval face shapes benefit from volume on top"],
            "stylingTips": "Apply mousse.",
            "maintenance": "Medium",
            "bestFor": "Oval",
        },
        "alternatives": [],
    },
}


def _make_user():
    Session = make_session()
    with Session() as session:
        user = session.execute(
            select(Users).where(Users.auth_provider == "dev", Users.auth_subject == "dev-user")
        ).scalar_one_or_none()
        if user is None:
            user = Users(auth_provider="dev", auth_subject="dev-user", display_name="Dev User")
            session.add(user)
            session.commit()
        return user.id


def _clean_snapshot():
    # No sourceRunId so no analysis_runs FK is involved.
    return copy.deepcopy(SNAPSHOT)


def _payload(**overrides):
    body = {
        "lookId": "textured_quiff",
        "title": "Textured Quiff",
        "sourceContext": "hairstyle",
        "snapshot": _clean_snapshot(),
    }
    body.update(overrides)
    return body


def _save(title, key):
    """Save one look via POST; returns its backend id."""
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(title=title),
        headers={**HEADERS, "Idempotency-Key": key},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _counts():
    Session = make_session()
    with Session() as session:
        looks = session.execute(select(func.count()).select_from(SavedLooks)).scalar_one()
        signals = session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one()
        return looks, signals


def _row_by_id(saved_look_id):
    Session = make_session()
    with Session() as session:
        return session.execute(
            select(SavedLooks).where(SavedLooks.id == saved_look_id)
        ).scalar_one_or_none()


def test_delete_owned_look_returns_204_and_removes_row():
    """A. Owner DELETE → 204, empty body, row (snapshot included) gone."""
    _make_user()
    saved_id = _save("Delete Me", "del-own-1")

    resp = client.delete(f"/v1/looks/saved/{saved_id}", headers=HEADERS)
    assert resp.status_code == 204
    assert resp.content == b""

    listed = client.get("/v1/looks/saved", headers=HEADERS).json()
    assert listed["total"] == 0
    assert listed["items"] == []
    assert _row_by_id(saved_id) is None
    looks, _ = _counts()
    assert looks == 0


def test_repeated_delete_returns_404():
    """B. Second DELETE of the same id → 404 NOT_FOUND."""
    _make_user()
    saved_id = _save("Delete Twice", "del-repeat-1")

    first = client.delete(f"/v1/looks/saved/{saved_id}", headers=HEADERS)
    assert first.status_code == 204

    second = client.delete(f"/v1/looks/saved/{saved_id}", headers=HEADERS)
    assert second.status_code == 404
    assert second.json()["error"]["code"] == "NOT_FOUND"


def test_delete_missing_id_returns_404():
    """C. DELETE of a random valid UUID → 404 NOT_FOUND."""
    _make_user()
    resp = client.delete(f"/v1/looks/saved/{uuid4()}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_delete_foreign_look_returns_404_and_preserves_row():
    """D. DELETE of another user's look → 404 (never 403), row intact."""
    _make_user()
    Session = make_session()
    with Session() as session:
        other = Users(
            auth_provider="dev",
            auth_subject="other-delete-user",
            display_name="Other",
        )
        session.add(other)
        session.flush()
        row = SavedLooks(
            user_id=other.id,
            look_id=None,
            title="Other User Look",
            source_context="hairstyle",
            snapshot=_clean_snapshot(),
            idempotency_key="other-del-1",
            source_run_id=None,
        )
        session.add(row)
        session.commit()
        foreign_id = row.id

    resp = client.delete(f"/v1/looks/saved/{foreign_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.status_code != 403
    assert resp.json()["error"]["code"] == "NOT_FOUND"

    surviving = _row_by_id(foreign_id)
    assert surviving is not None
    assert surviving.title == "Other User Look"


def test_delete_malformed_uuid_returns_422():
    """E. DELETE with a non-UUID path id → existing 422 validation behavior."""
    _make_user()
    resp = client.delete("/v1/looks/saved/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_one_of_many_leaves_rest_unchanged():
    """F. Deleting one of three saves removes exactly that row."""
    _make_user()
    first_id = _save("First Look", "del-iso-1")
    middle_id = _save("Middle Look", "del-iso-2")
    last_id = _save("Last Look", "del-iso-3")

    resp = client.delete(f"/v1/looks/saved/{middle_id}", headers=HEADERS)
    assert resp.status_code == 204

    listed = client.get("/v1/looks/saved", headers=HEADERS).json()
    assert listed["total"] == 2
    remaining = {item["id"]: item for item in listed["items"]}
    assert set(remaining) == {first_id, last_id}
    assert remaining[first_id]["title"] == "First Look"
    assert remaining[last_id]["title"] == "Last Look"
    assert remaining[first_id]["snapshot"] == _payload()["snapshot"]
    assert _row_by_id(middle_id) is None


def test_delete_preserves_learning_signals_without_new_type():
    """G. DELETE keeps existing signals, adds none, introduces no type."""
    _make_user()
    saved_id = _save("Signal Look", "del-signal-1")
    looks, signals = _counts()
    assert (looks, signals) == (1, 1)

    resp = client.delete(f"/v1/looks/saved/{saved_id}", headers=HEADERS)
    assert resp.status_code == 204

    looks, signals = _counts()
    assert looks == 0
    assert signals == 1
    Session = make_session()
    with Session() as session:
        types = {
            row[0]
            for row in session.execute(
                select(LearningSignals.signal_type)
            ).all()
        }
    assert types == {"look_saved"}


def test_delete_requires_auth():
    """Unauthenticated DELETE → 401 AUTHENTICATION_ERROR."""
    resp = client.delete(f"/v1/looks/saved/{uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"
