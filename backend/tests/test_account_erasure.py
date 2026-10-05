"""Erasure tests — O-6 `DELETE /v1/users/me` (AUTH_API §5.6, TRX-8).

DB-backed API tests run when PostgreSQL is reachable, else skip
(see `tests/conftest.py`). Use-case unit tests run everywhere.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.db.models import (
    LearningSignals,
    UserSession,
    UserState,
    Users,
    WardrobeCategories,
    WardrobeItems,
)
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)


def _register(email, password="Passw0rd1"):
    return client.post(
        "/v1/auth/register",
        json={"email": email, "password": password},
        headers={"Idempotency-Key": f"reg-{uuid.uuid4()}"},
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _rows(model, user_id):
    Session = make_session()
    with Session() as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(model)
                .where(model.user_id == user_id)
            ).scalar_one()
        )


def _seed_dependent(user_id):
    Session = make_session()
    with Session() as session:
        session.add(
            WardrobeItems(
                user_id=user_id,
                name="Doomed Top",
                category_id="tops",
                color_id="charcoal",
            )
        )
        session.add(
            LearningSignals(
                user_id=user_id,
                signal_type="item_added",
                label="added",
                context={},
            )
        )
        session.commit()


# --- API: authorized self-erasure -------------------------------------------


def test_delete_me_erases_account_and_dependents(db):
    email = f"erase-{uuid.uuid4()}@example.com"
    token = _register(email).json()["accessToken"]
    me = client.get("/v1/users/me", headers=_auth(token)).json()
    assert me["memorySummary"]["savedLooksCount"] == 0

    Session = make_session()
    with Session() as session:
        user_id = session.execute(
            select(Users.id).where(Users.auth_subject == email)
        ).scalar_one()
    _seed_dependent(user_id)
    assert _rows(WardrobeItems, user_id) == 1

    resp = client.delete("/v1/users/me", headers=_auth(token))
    assert resp.status_code == 204, resp.text

    with Session() as session:
        assert (
            session.execute(select(Users).where(Users.id == user_id)).scalar_one_or_none()
            is None
        )
        assert (
            session.execute(
                select(UserState).where(UserState.user_id == user_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            session.execute(
                select(UserSession).where(UserSession.user_id == user_id)
            ).scalar_one_or_none()
            is None
        )
    assert _rows(WardrobeItems, user_id) == 0
    assert _rows(LearningSignals, user_id) == 0
    # System-owned knowledge survives erasure (TRX-8).
    with Session() as session:
        assert (
            session.execute(
                select(func.count()).select_from(WardrobeCategories)
            ).scalar_one()
            > 0
        )


def test_delete_me_requires_auth(db):
    resp = client.delete("/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_delete_me_retry_with_dead_token_is_401_not_oracle(db):
    email = f"erase-{uuid.uuid4()}@example.com"
    token = _register(email).json()["accessToken"]
    assert client.delete("/v1/users/me", headers=_auth(token)).status_code == 204
    # Session died with the account: retry is 401 like any dead token —
    # never another user's data, never a 404 oracle on someone else.
    retry = client.delete("/v1/users/me", headers=_auth(token))
    assert retry.status_code == 401


def test_delete_me_cross_user_isolation(db):
    token_a = _register(f"a-{uuid.uuid4()}@example.com").json()["accessToken"]
    token_b = _register(f"b-{uuid.uuid4()}@example.com").json()["accessToken"]
    Session = make_session()
    with Session() as session:
        id_b = session.execute(
            select(Users.id).where(Users.auth_subject.like("b-%"))
        ).scalar_one()
    _seed_dependent(id_b)
    assert client.delete("/v1/users/me", headers=_auth(token_a)).status_code == 204
    assert _rows(WardrobeItems, id_b) == 1
    assert (
        client.get("/v1/users/me", headers=_auth(token_b)).status_code == 200
    )
