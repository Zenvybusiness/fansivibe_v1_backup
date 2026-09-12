"""API tests for real authentication (D-AUTH-1, M1, endpoints #02–05).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).

Covers `POST /v1/auth/register` (O-1/UC-1), `POST /v1/auth/login`
(O-3/UC-3), `POST /v1/auth/logout` (O-4/UC-4), `POST /v1/auth/social`
(O-2/UC-2, honestly 502), plus the mandatory two-user isolation
proof across wardrobe / saved looks / events / feedback /
preferences: user B cannot read or mutate user A's rows, and the
frozen 404-not-403 semantics hold under real authentication.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config.settings import get_settings
from app.infrastructure.db.models import (
    FeedbackEvents,
    SavedLooks,
    UserEvent,
    UserSession,
    Users,
    WardrobeItems,
)
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
_SECRET = get_settings().auth_secret


# --- helpers --------------------------------------------------------------


def _register(email, password="Passw0rd1", display_name=None, key=None):
    body: dict = {"email": email, "password": password}
    if display_name is not None:
        body["displayName"] = display_name
    return client.post(
        "/v1/auth/register",
        json=body,
        headers={"Idempotency-Key": key or f"reg-{uuid.uuid4()}"},
    )


def _login(email, password="Passw0rd1"):
    return client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user_count() -> int:
    Session = make_session()
    with Session() as session:
        return int(session.execute(select(func.count()).select_from(Users)).scalar_one())


def _session_count() -> int:
    Session = make_session()
    with Session() as session:
        return int(
            session.execute(select(func.count()).select_from(UserSession)).scalar_one()
        )


# --- register --------------------------------------------------------------


def test_register_returns_201_auth_response(db):
    resp = _register("alex@example.com", display_name="Alex")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"accessToken", "tokenType", "expiresIn", "profile"}
    assert body["tokenType"] == "bearer"
    assert isinstance(body["accessToken"], str) and len(body["accessToken"]) > 20
    assert body["expiresIn"] == get_settings().auth_expires_in_s
    assert body["profile"]["displayName"] == "Alex"
    # The session works immediately: who-am-I resolves the new account.
    me = client.get("/v1/users/me", headers=_auth(body["accessToken"]))
    assert me.status_code == 200
    assert me.json()["displayName"] == "Alex"


def test_register_requires_idempotency_key(db):
    resp = client.post(
        "/v1/auth/register",
        json={"email": "nokey@example.com", "password": "Passw0rd1"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_rejects_malformed_fields(db):
    bad_bodies = [
        {"email": "not-an-email", "password": "Passw0rd1"},
        {"email": "a@b", "password": "Passw0rd1"},
        {"email": "ok@example.com", "password": "short1"},
        {"email": "ok@example.com", "password": "nonumbershere"},
        {"email": "ok@example.com", "password": "12345678"},
        {"email": "ok@example.com", "password": "Passw0rd1", "displayName": ""},
        {"email": "ok@example.com", "password": "Passw0rd1", "displayName": "  "},
        {"email": "ok@example.com"},
        {"password": "Passw0rd1"},
        {},
    ]
    for body in bad_bodies:
        resp = client.post(
            "/v1/auth/register",
            json=body,
            headers={"Idempotency-Key": f"bad-{uuid.uuid4()}"},
        )
        assert resp.status_code == 422, body
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_duplicate_email_is_409(db):
    first = _register("dupe@example.com", display_name="Dupe")
    assert first.status_code == 201
    second = _register("dupe@example.com", display_name="Dupe")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"
    assert second.json()["error"]["details"]["kind"] == "duplicate"
    assert _user_count() == 1


def test_register_replay_same_key_same_payload_returns_same_account(db):
    key = f"replay-{uuid.uuid4()}"
    first = _register("replay@example.com", display_name="Replay", key=key)
    assert first.status_code == 201
    token_a = first.json()["accessToken"]
    second = _register("replay@example.com", display_name="Replay", key=key)
    assert second.status_code == 201
    assert _user_count() == 1
    # Same account: both tokens resolve to the same identity.
    me_a = client.get("/v1/users/me", headers=_auth(token_a)).json()
    me_b = client.get(
        "/v1/users/me", headers=_auth(second.json()["accessToken"])
    ).json()
    assert me_a["displayName"] == me_b["displayName"] == "Replay"


def test_register_replay_same_key_different_payload_is_409(db):
    key = f"conflict-{uuid.uuid4()}"
    assert _register("clash@example.com", key=key).status_code == 201
    clash = _register("clash@example.com", password="Otherpass9", key=key)
    assert clash.status_code == 409
    assert _user_count() == 1


def test_register_email_is_case_insensitive(db):
    assert _register("Case@Example.COM", display_name="Case").status_code == 201
    dupe = _register("case@example.com", display_name="Case")
    assert dupe.status_code == 409
    login = _login("CASE@example.com")
    assert login.status_code == 200


def test_register_never_stores_plaintext_password(db):
    _register("hashme@example.com", password="Secretpass9")
    Session = make_session()
    with Session() as session:
        row = session.execute(
            select(Users).where(Users.auth_subject == "hashme@example.com")
        ).scalar_one()
        assert row.auth_provider == "email"
        assert row.password_hash is not None
        assert row.password_hash != "Secretpass9"
        assert "Secretpass9" not in row.password_hash


# --- login -----------------------------------------------------------------


def test_login_returns_200_and_usable_session(db):
    _register("login@example.com", display_name="Login")
    resp = _login("login@example.com")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tokenType"] == "bearer"
    me = client.get("/v1/users/me", headers=_auth(body["accessToken"]))
    assert me.status_code == 200
    assert me.json()["displayName"] == "Login"


def test_login_wrong_password_is_uniform_401(db):
    _register("victim@example.com")
    resp = _login("victim@example.com", password="Wrongpass9")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_login_unknown_email_is_uniform_401_not_404(db):
    resp = _login("nobody-here@example.com")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_login_malformed_request_is_422(db):
    resp = client.post(
        "/v1/auth/login", json={"email": "bad", "password": "Passw0rd1"}
    )
    assert resp.status_code == 422
    resp = client.post("/v1/auth/login", json={"email": "a@b.co"})
    assert resp.status_code == 422


# --- token semantics ---------------------------------------------------------


def test_missing_token_is_401_with_challenge(db):
    resp = client.get("/v1/users/me")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_invalid_token_is_401(db):
    resp = client.get("/v1/users/me", headers=_auth("not-a-real-token"))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_tampered_token_is_401(db):
    token = _register("tamper@example.com").json()["accessToken"]
    tampered = token[:-2] + ("ab" if not token.endswith("ab") else "cd")
    resp = client.get("/v1/users/me", headers=_auth(tampered))
    assert resp.status_code == 401


def test_expired_token_is_401(db):
    past = int(time.time()) - 10
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "jti": str(uuid.uuid4()),
            "iat": past - 3600,
            "exp": past,
        },
        _SECRET,
        algorithm="HS256",
    )
    resp = client.get("/v1/users/me", headers=_auth(forged))
    assert resp.status_code == 401


def test_wrong_secret_token_is_401(db):
    future = int(time.time()) + 3600
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "jti": str(uuid.uuid4()),
            "iat": future - 3600,
            "exp": future,
        },
        "some-other-secret",
        algorithm="HS256",
    )
    resp = client.get("/v1/users/me", headers=_auth(forged))
    assert resp.status_code == 401


# --- logout ------------------------------------------------------------------


def test_logout_revokes_session(db):
    token = _register("bye@example.com").json()["accessToken"]
    assert client.get("/v1/users/me", headers=_auth(token)).status_code == 200
    out = client.post("/v1/auth/logout", headers=_auth(token))
    assert out.status_code == 204
    assert out.content == b""
    gone = client.get("/v1/users/me", headers=_auth(token))
    assert gone.status_code == 401


def test_logout_with_dead_token_is_401(db):
    assert (
        client.post("/v1/auth/logout", headers=_auth("dead-token")).status_code
        == 401
    )
    token = _register("twice@example.com").json()["accessToken"]
    assert client.post("/v1/auth/logout", headers=_auth(token)).status_code == 204
    assert client.post("/v1/auth/logout", headers=_auth(token)).status_code == 401


def test_logout_without_token_is_401(db):
    assert client.post("/v1/auth/logout").status_code == 401


def test_logout_only_revokes_caller_session(db):
    _register("multi@example.com")
    first = _login("multi@example.com").json()["accessToken"]
    second = _login("multi@example.com").json()["accessToken"]
    assert client.post("/v1/auth/logout", headers=_auth(first)).status_code == 204
    assert client.get("/v1/users/me", headers=_auth(first)).status_code == 401
    # The other device session survives (per-device sessions, AUTH_API §5.3).
    assert client.get("/v1/users/me", headers=_auth(second)).status_code == 200


# --- social (honestly gated) ---------------------------------------------------


def test_social_rejects_unknown_provider_with_allowed(db):
    resp = client.post(
        "/v1/auth/social",
        json={"provider": "facebook", "providerToken": "tok"},
    )
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]["field_errors"]
    assert details[0]["field"] == "provider"
    assert set(details[0]["allowed"]) == {"google", "apple"}


def test_social_rejects_missing_provider_token(db):
    resp = client.post("/v1/auth/social", json={"provider": "google"})
    assert resp.status_code == 422
    resp = client.post(
        "/v1/auth/social", json={"provider": "apple", "providerToken": "  "}
    )
    assert resp.status_code == 422


def test_social_valid_shape_is_honest_502_without_minting(db):
    before = _session_count()
    resp = client.post(
        "/v1/auth/social",
        json={"provider": "google", "providerToken": "some-provider-jwt"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "EXTERNAL_SERVICE_FAILURE"
    assert _session_count() == before


# --- two-user isolation (mandatory) --------------------------------------------


def _two_users(db):
    token_a = _register("usera@example.com", display_name="User A").json()[
        "accessToken"
    ]
    token_b = _register("userb@example.com", display_name="User B").json()[
        "accessToken"
    ]
    return token_a, token_b


def test_two_users_are_isolated_across_surfaces(db):
    token_a, token_b = _two_users(db)

    # A builds state on every contracted surface.
    item = client.post(
        "/v1/wardrobe/items",
        json={"name": "A Blazer", "category": "outerwear", "color": "black"},
        headers=_auth(token_a),
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]

    event = client.post(
        "/v1/events",
        json={"title": "A Gala", "eventType": "formal", "eventDate": "2027-05-01"},
        headers=_auth(token_a),
    )
    assert event.status_code == 201, event.text
    event_id = event.json()["id"]

    saved = client.post(
        "/v1/looks/saved",
        json={
            "title": "A Look",
            "sourceContext": "outfit",
            "snapshot": {"selectedItemIds": [item_id]},
        },
        headers={**_auth(token_a), "Idempotency-Key": f"a-save-{uuid.uuid4()}"},
    )
    assert saved.status_code == 201, saved.text
    saved_id = saved.json()["id"]

    feedback = client.post(
        "/v1/feedback",
        json={"rating": "like", "targetSavedLookId": saved_id},
        headers={**_auth(token_a), "Idempotency-Key": f"a-fb-{uuid.uuid4()}"},
    )
    assert feedback.status_code == 204, feedback.text

    prefs = client.patch(
        "/v1/users/me",
        json={"preferredOccasions": ["formal"]},
        headers=_auth(token_a),
    )
    assert prefs.status_code == 200, prefs.text

    # A reads back exactly her own rows.
    assert client.get("/v1/wardrobe/items", headers=_auth(token_a)).json()["total"] == 1
    assert (
        client.get("/v1/looks/saved", headers=_auth(token_a)).json()["total"] == 1
    )
    assert len(client.get("/v1/events", headers=_auth(token_a)).json()["items"]) == 1

    # B sees none of A's data (own empty collections, never A's rows).
    assert client.get("/v1/wardrobe/items", headers=_auth(token_b)).json()["total"] == 0
    assert client.get("/v1/looks/saved", headers=_auth(token_b)).json()["total"] == 0
    assert client.get("/v1/events", headers=_auth(token_b)).json()["items"] == []
    assert (
        client.get("/v1/users/me", headers=_auth(token_b)).json()["displayName"]
        == "User B"
    )

    # B cannot read A's rows by UUID: 404-not-403 everywhere. (Events
    # expose no GET-by-id in M8 — the foreign PUT/DELETE probes below
    # are the event read guards; there is no GET-by-id on saved looks
    # either — DEC-013 delete-only.)
    assert (
        client.get(f"/v1/wardrobe/items/{item_id}", headers=_auth(token_b)).status_code
        == 404
    )

    # B cannot mutate A's rows: 404-not-403, nothing changed.
    assert (
        client.patch(
            f"/v1/wardrobe/items/{item_id}",
            json={"name": "Hijacked"},
            headers=_auth(token_b),
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/v1/wardrobe/items/{item_id}", headers=_auth(token_b)
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/v1/looks/saved/{saved_id}", headers=_auth(token_b)
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v1/events/{event_id}", headers=_auth(token_b)).status_code
        == 404
    )
    assert (
        client.put(
            f"/v1/events/{event_id}",
            json={
                "title": "Hijacked",
                "eventType": "formal",
                "eventDate": "2027-05-01",
            },
            headers=_auth(token_b),
        ).status_code
        == 404
    )

    # A's data is byte-intact after B's attempts.
    assert (
        client.get(f"/v1/wardrobe/items/{item_id}", headers=_auth(token_a)).json()[
            "name"
        ]
        == "A Blazer"
    )
    Session = make_session()
    with Session() as session:
        assert (
            session.execute(
                select(func.count())
                .select_from(WardrobeItems)
                .where(WardrobeItems.user_id != WardrobeItems.user_id)
            ).scalar_one()
            == 0
        )
        for model in (WardrobeItems, SavedLooks, UserEvent, FeedbackEvents):
            rows = session.execute(select(model)).scalars().all()
            assert len(rows) >= 1
            owners = {row.user_id for row in rows}
            assert len(owners) == 1  # every row belongs to A


def test_user_cannot_save_foreign_wardrobe_uuid(db):
    token_a, token_b = _two_users(db)
    item = client.post(
        "/v1/wardrobe/items",
        json={"name": "A Coat", "category": "outerwear", "color": "black"},
        headers=_auth(token_a),
    ).json()
    # B references A's item id in her own save: foreign → 404, nothing stored.
    resp = client.post(
        "/v1/looks/saved",
        json={
            "title": "Stolen",
            "sourceContext": "outfit",
            "snapshot": {"selectedItemIds": [item["id"]]},
        },
        headers={**_auth(token_b), "Idempotency-Key": f"steal-{uuid.uuid4()}"},
    )
    assert resp.status_code == 404
    assert client.get("/v1/looks/saved", headers=_auth(token_b)).json()["total"] == 0


# --- dev seam stays test-only ----------------------------------------------------


def test_dev_token_still_resolves_in_tests(db):
    resp = client.get("/v1/users/me", headers={"Authorization": "Bearer dev"})
    assert resp.status_code == 200
    assert resp.json()["displayName"] == "Dev User"
