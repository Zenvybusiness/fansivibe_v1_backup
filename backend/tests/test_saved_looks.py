"""API tests for the save surface (#23, `POST /v1/looks/saved`).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

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
        "sourceRunId": "00000000-0000-0000-0000-000000000001",
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


def _counts():
    Session = make_session()
    with Session() as session:
        looks = session.execute(select(func.count()).select_from(SavedLooks)).scalar_one()
        signals = session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one()
        return looks, signals


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


def _payload(**overrides):
    body = {
        "lookId": "textured_quiff",
        "title": "Textured Quiff",
        "sourceContext": "hairstyle",
        "snapshot": SNAPSHOT,
    }
    body.update(overrides)
    return body


def test_save_requires_idempotency_key(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_save_creates_saved_look_and_signal_together(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lookId"] == "textured_quiff"
    assert body["title"] == "Textured Quiff"
    assert body["sourceRunId"] == "00000000-0000-0000-0000-000000000001"
    assert body["createdAt"] is not None

    looks, signals = _counts()
    assert looks == 1
    assert signals == 1


def test_save_idempotent_replay_returns_original(db):
    _make_user()
    first = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-replay"},
    )
    assert first.status_code == 201
    replay = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-replay"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    looks, signals = _counts()
    assert looks == 1
    assert signals == 1


def test_save_conflicting_replay_returns_409(db):
    _make_user()
    client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-conflict"},
    )
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(title="Different Title"),
        headers={**HEADERS, "Idempotency-Key": "key-conflict"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_save_unknown_look_returns_404(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(lookId="no_such_look"),
        headers={**HEADERS, "Idempotency-Key": "key-x"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_save_unknown_source_context_returns_422(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(sourceContext="wardrobe"),
        headers={**HEADERS, "Idempotency-Key": "key-y"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_save_title_bounds_validate(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(title=""),
        headers={**HEADERS, "Idempotency-Key": "key-z"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET /v1/looks/saved (endpoint #24) --------------------------------------


def test_list_returns_saved_looks_for_owner(db):
    _make_user()
    client.post(
        "/v1/looks/saved",
        json=_payload(title="Textured Quiff"),
        headers={**HEADERS, "Idempotency-Key": "list-key-1"},
    )
    client.post(
        "/v1/looks/saved",
        json=_payload(title="Classic Pompadour", lookId="classic_pompadour"),
        headers={**HEADERS, "Idempotency-Key": "list-key-2"},
    )

    resp = client.get("/v1/looks/saved", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    titles = [item["title"] for item in body["items"]]
    assert set(titles) == {"Textured Quiff", "Classic Pompadour"}
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_list_respects_pagination(db):
    _make_user()
    for i in range(5):
        client.post(
            "/v1/looks/saved",
            json=_payload(title=f"Look {i}"),
            headers={**HEADERS, "Idempotency-Key": f"page-key-{i}"},
        )

    resp = client.get("/v1/looks/saved?page=2&page_size=2", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 2


def test_list_is_empty_for_owner_without_saves(db):
    _make_user()
    resp = client.get("/v1/looks/saved", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
