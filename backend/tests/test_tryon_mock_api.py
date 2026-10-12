"""Stage F0 mock try-on tests (DB-free).

Covers `POST /v1/tryon/jobs`, `GET /v1/tryon/jobs/{id}`, and
`GET /v1/tryon/jobs/{id}/image`: deterministic mock lifecycle, auth
(guests get 401 server-side), consent gate, idempotency replay/409,
typed validation, quota 429, provider kill-switch 503, and owner
isolation. Zero database rows (the `get_db` dependency raises if
touched) and zero provider calls (no paid path exists in F0).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.application.tryon as tryon_app
from app.api.deps import get_current_user_id
from app.infrastructure.db.session import get_db

USER_A = uuid4()
USER_B = uuid4()
JPEG = ("person.jpg", b"\xff\xd8fake-person-bytes", "image/jpeg")


def _settings(**overrides):
    base = {
        "tryon_enabled": True,
        "tryon_provider": "mock",
        "tryon_consent_version": "tryon-v1",
        "tryon_daily_quota_per_user": 20,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _no_db():
    raise AssertionError("mock try-on must never touch the database")


def _client(monkeypatch, user=USER_A, settings=None) -> TestClient:
    from app.main import app

    tryon_app.reset_for_tests()
    if user is None:
        # Unauthenticated: the auth dep rejects before touching the DB, so
        # leave get_db alone (FastAPI resolves it first) and only drop
        # any auth override.
        monkeypatch.delitem(
            app.dependency_overrides, get_current_user_id, raising=False
        )
    else:
        monkeypatch.setitem(app.dependency_overrides, get_db, _no_db)
        monkeypatch.setitem(
            app.dependency_overrides, get_current_user_id, lambda: user
        )
    monkeypatch.setattr(
        tryon_app, "get_settings", lambda: settings or _settings()
    )
    return TestClient(app)


def _post(client: TestClient, files=None, data=None, key="key-1"):
    return client.post(
        "/v1/tryon/jobs",
        files=files if files is not None else {"person_image": JPEG},
        data=data
        if data is not None
        else {
            "outfit_source": "today",
            "garment_ids": '["wardrobe-1", "wardrobe-2"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": key} if key else {},
    )


# --- happy path ---------------------------------------------------------------

def test_submit_returns_202_mock_job(monkeypatch):
    resp = _post(_client(monkeypatch))
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"]
    assert body["status"] == "processing"
    assert body["is_mock"] is True


def test_poll_processing_then_completed_with_banner(monkeypatch):
    client = _client(monkeypatch)
    job_id = _post(client).json()["job_id"]
    first = client.get(f"/v1/tryon/jobs/{job_id}").json()
    assert first["status"] == "processing"
    assert first["is_mock"] is True
    second = client.get(f"/v1/tryon/jobs/{job_id}").json()
    assert second["status"] == "completed"
    assert second["progress"] == 100
    img = client.get(f"/v1/tryon/jobs/{job_id}/image")
    assert img.status_code == 200
    assert "TEST DATA" in img.text
    assert "NOT AI TRY-ON" in img.text


def test_image_before_complete_is_409(monkeypatch):
    client = _client(monkeypatch)
    job_id = _post(client).json()["job_id"]
    resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
    assert resp.status_code == 409


# --- auth ---------------------------------------------------------------------

def test_missing_bearer_is_401(monkeypatch):
    resp = _post(_client(monkeypatch, user=None))
    assert resp.status_code == 401


def test_unknown_job_is_404(monkeypatch):
    resp = _client(monkeypatch).get("/v1/tryon/jobs/does-not-exist")
    assert resp.status_code == 404


def test_foreign_user_job_is_404(monkeypatch):
    client_a = _client(monkeypatch, user=USER_A)
    job_id = _post(client_a).json()["job_id"]
    client_b = _client(monkeypatch, user=USER_B)
    assert client_b.get(f"/v1/tryon/jobs/{job_id}").status_code == 404
    assert client_b.get(f"/v1/tryon/jobs/{job_id}/image").status_code == 404


# --- consent + validation -----------------------------------------------------

def test_missing_idempotency_key_is_422(monkeypatch):
    resp = _post(_client(monkeypatch), key="")
    assert resp.status_code == 422


def test_consent_not_accepted_is_422(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(
        client,
        data={
            "outfit_source": "today",
            "garment_ids": '["a"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "false",
        },
    )
    assert resp.status_code == 422


def test_wrong_consent_version_is_422(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(
        client,
        data={
            "outfit_source": "today",
            "garment_ids": '["a"]',
            "consent_version": "tryon-v0",
            "consent_accepted": "true",
        },
    )
    assert resp.status_code == 422


def test_unknown_outfit_source_is_422(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(
        client,
        data={
            "outfit_source": "runway",
            "garment_ids": '["a"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
    )
    assert resp.status_code == 422


def test_bad_image_type_is_422(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(client, files={"person_image": ("p.gif", b"bytes", "image/gif")})
    assert resp.status_code == 422


def test_empty_image_is_422(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(client, files={"person_image": ("p.jpg", b"", "image/jpeg")})
    assert resp.status_code == 422


def test_malformed_garment_ids_is_422(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(
        client,
        data={
            "outfit_source": "today",
            "garment_ids": "not-json",
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
    )
    assert resp.status_code == 422


# --- idempotency --------------------------------------------------------------

def test_same_key_same_payload_replays_original(monkeypatch):
    client = _client(monkeypatch)
    first = _post(client, key="replay-1").json()
    second = _post(client, key="replay-1").json()
    assert first["job_id"] == second["job_id"]


def test_same_key_changed_payload_is_409(monkeypatch):
    client = _client(monkeypatch)
    _post(client, key="conflict-1")
    resp = _post(
        client,
        data={
            "outfit_source": "outfit",
            "garment_ids": '["other"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        key="conflict-1",
    )
    assert resp.status_code == 409


# --- quota + kill switch ------------------------------------------------------

def test_quota_exceeded_is_429(monkeypatch):
    limited = _settings(tryon_daily_quota_per_user=1)
    client = _client(monkeypatch, settings=limited)
    assert _post(client, key="q-1").status_code == 202
    assert _post(client, key="q-2").status_code == 429


def test_provider_off_is_503(monkeypatch):
    off = _settings(tryon_provider="off")
    assert _post(_client(monkeypatch, settings=off)).status_code == 503


def test_provider_disabled_flag_is_503(monkeypatch):
    disabled = _settings(tryon_enabled=False)
    assert _post(_client(monkeypatch, settings=disabled)).status_code == 503
