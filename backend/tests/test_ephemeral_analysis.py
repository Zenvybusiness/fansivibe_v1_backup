"""D-01 STEP 1 ephemeral guest analysis tests (DB-free).

Covers the four unauthenticated synchronous endpoints
(`POST /v1/analysis/{hairstyle,outfit,grooming,garment}/ephemeral`):
guest result without sign-in, no Bearer, no `user_id` consumption, zero
database rows (the `get_db` dependency raises if touched), validation
before AI work, per-IP rate limiting, honest provider failures, and
untouched authenticated endpoints + migration HEAD 0025.

Vision adapters are stubbed at the router namespace (garment-test
precedent); the knowledge source is the real frozen catalog.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.routers.analysis as analysis_router
from app.ai.vision_appearance_adapter import AppearanceAnalysisError
from app.ai.vision_garment_adapter import GarmentAnalysisError
from app.application.analysis import (
    EphemeralGarmentAnalysis,
    EphemeralGroomingAnalysis,
    EphemeralHairstyleAnalysis,
)
from app.config.settings import clear_settings_cache
from app.domain.value_objects import AppearanceProfile, GarmentProfile
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

EPH_HAIR = "/v1/analysis/hairstyle/ephemeral"
EPH_OUTFIT = "/v1/analysis/outfit/ephemeral"
EPH_GROOM = "/v1/analysis/grooming/ephemeral"
EPH_GARMENT = "/v1/analysis/garment/ephemeral"

JPEG = ("face.jpg", b"ephemeral-scan-bytes", "image/jpeg")


# --- stubs ------------------------------------------------------------------


class StubAppearancePort:
    """Recording appearance port. `mode`: ok | typed-failure | crash | no-face."""

    instances: list = []
    mode: str = "ok"

    adapter_id = "ollama-vision-v1"

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list = []
        StubAppearancePort.instances.append(self)

    def analyze(self, *, media_ref, user_id, image_bytes=None):
        self.calls.append(
            {"media_ref": media_ref, "user_id": user_id, "image_bytes": image_bytes}
        )
        if StubAppearancePort.mode == "typed-failure":
            raise AppearanceAnalysisError("vision_unavailable")
        if StubAppearancePort.mode == "crash":
            raise RuntimeError("boom")
        face = "" if StubAppearancePort.mode == "no-face" else "oval"
        return AppearanceProfile(
            faceShape=face,
            skinTone="",
            bodyType="",
            styleType="",
            sourceRunId="",
        )


class StubGarmentPort:
    """Recording garment port. `mode`: ok | no-garment | crash."""

    instances: list = []
    mode: str = "ok"

    adapter_id = "ollama-garment-v1"

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list = []
        StubGarmentPort.instances.append(self)

    def analyze(self, *, media_ref, user_id, image_bytes=None):
        self.calls.append(
            {"media_ref": media_ref, "user_id": user_id, "image_bytes": image_bytes}
        )
        if StubGarmentPort.mode == "no-garment":
            raise GarmentAnalysisError("no_garment_detected")
        if StubGarmentPort.mode == "crash":
            raise RuntimeError("boom")
        return GarmentProfile(
            category="tops",
            subcategory="oxford shirt",
            color="light blue",
            pattern="solid",
            material="cotton",
            style=None,
            fit=None,
            confidence=0.84,
            needs_review=False,
        )

    def validate_result(self, result) -> bool:
        return True


def _no_db():
    raise AssertionError("ephemeral request must never touch the database")


def _client(monkeypatch) -> TestClient:
    from app.main import app
    from app.infrastructure.db.session import get_db

    StubAppearancePort.instances = []
    StubAppearancePort.mode = "ok"
    StubGarmentPort.instances = []
    StubGarmentPort.mode = "ok"

    monkeypatch.setattr(
        analysis_router, "OllamaVisionAppearanceAdapter", StubAppearancePort
    )
    monkeypatch.setattr(
        analysis_router, "OllamaVisionGarmentAdapter", StubGarmentPort
    )
    # Proof of zero DB access: any session resolution explodes the request.
    monkeypatch.setitem(app.dependency_overrides, get_db, _no_db)
    return TestClient(app)


def _auth_client(monkeypatch) -> TestClient:
    """Client without the DB tripwire, for the authenticated endpoints
    (which legitimately resolve `get_db` after their auth dependency —
    unauthenticated calls 401 before ever reaching it)."""
    from app.main import app

    StubAppearancePort.mode = "ok"
    StubGarmentPort.mode = "ok"
    monkeypatch.setattr(
        analysis_router, "OllamaVisionAppearanceAdapter", StubAppearancePort
    )
    monkeypatch.setattr(
        analysis_router, "OllamaVisionGarmentAdapter", StubGarmentPort
    )
    return TestClient(app)


def _post_image(client: TestClient, path: str, files=None, **kwargs):
    return client.post(path, files=files or {"image": JPEG}, **kwargs)


# --- 200 results, no auth ----------------------------------------------------


def test_hairstyle_ephemeral_returns_snapshot_without_bearer(monkeypatch):
    resp = _post_image(_client(monkeypatch), EPH_HAIR)
    assert resp.status_code == 200
    body = resp.json()
    assert body["appearance"]["faceShape"] == "oval"
    assert body["recommendations"]["top"]["id"]
    assert "run_id" not in body
    assert "user_id" not in body
    # Transient correlation id: a UUID that names no persisted run.
    uuid.UUID(body["appearance"]["sourceRunId"])


def test_outfit_ephemeral_returns_snapshot_without_bearer(monkeypatch):
    resp = _post_image(_client(monkeypatch), EPH_OUTFIT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["appearance"]["faceShape"] == "oval"
    assert body["recommendations"]["top"]["id"]
    assert "run_id" not in body
    uuid.UUID(body["appearance"]["sourceRunId"])


def test_grooming_ephemeral_returns_snapshot_for_request_profile(monkeypatch):
    resp = _client(monkeypatch).post(
        EPH_GROOM, json={"face_shape": "Oval", "skin_tone": "medium"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["appearance"]["faceShape"] == "Oval"
    assert body["recommendations"]["top"]["id"]
    assert "run_id" not in body
    uuid.UUID(body["appearance"]["sourceRunId"])


def test_garment_ephemeral_returns_observation_without_bearer(monkeypatch):
    resp = _post_image(_client(monkeypatch), EPH_GARMENT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "tops"
    assert body["color"] == "light blue"
    assert body["confidence"] == 0.84
    assert "run_id" not in body
    uuid.UUID(body["sourceRunId"])


def test_garbage_bearer_is_ignored_not_required(monkeypatch):
    client = _client(monkeypatch)
    for path, kwargs in (
        (EPH_HAIR, {}),
        (EPH_OUTFIT, {}),
        (EPH_GARMENT, {}),
    ):
        resp = client.post(
            path,
            files={"image": JPEG},
            headers={"Authorization": "Bearer nonsense"},
        )
        assert resp.status_code == 200, path
    resp = client.post(
        EPH_GROOM,
        json={"face_shape": "Oval"},
        headers={"Authorization": "Bearer nonsense"},
    )
    assert resp.status_code == 200


def test_correlation_ids_are_unique_per_request(monkeypatch):
    client = _client(monkeypatch)
    first = _post_image(client, EPH_GARMENT).json()["sourceRunId"]
    second = _post_image(client, EPH_GARMENT).json()["sourceRunId"]
    assert first != second


def test_adapter_receives_transient_key_seed_never_a_user(monkeypatch):
    client = _client(monkeypatch)
    _post_image(client, EPH_HAIR)
    call = StubAppearancePort.instances[0].calls[0]
    assert call["image_bytes"] == b"ephemeral-scan-bytes"
    # Transient UUID seed: parseable, used for the media key only.
    seed = str(call["user_id"])
    uuid.UUID(seed)
    assert call["media_ref"]["key"].startswith(f"users/{seed}/scans/")
    assert "contentHash" in call["media_ref"]


# --- no user_id accepted ------------------------------------------------------


def test_user_id_query_param_is_ignored(monkeypatch):
    client = _client(monkeypatch)
    ghost = str(uuid.uuid4())
    resp = client.post(f"{EPH_HAIR}?user_id={ghost}", files={"image": JPEG})
    assert resp.status_code == 200
    assert ghost not in resp.text


def test_user_id_json_field_is_ignored(monkeypatch):
    resp = _client(monkeypatch).post(
        EPH_GROOM,
        json={"face_shape": "Oval", "user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert "user_id" not in resp.json()


# --- zero database writes (proven by the raising get_db override) -------------


def test_ephemeral_requests_never_touch_the_database(monkeypatch):
    # Every 200 above already passed through the raising get_db override;
    # this pins the proof explicitly across all four endpoints.
    client = _client(monkeypatch)
    assert _post_image(client, EPH_HAIR).status_code == 200
    assert _post_image(client, EPH_OUTFIT).status_code == 200
    assert _post_image(client, EPH_GARMENT).status_code == 200
    assert (
        client.post(EPH_GROOM, json={"face_shape": "Oval"}).status_code == 200
    )


# --- validation before AI work -------------------------------------------------


def test_invalid_image_type_rejected(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        EPH_HAIR, files={"image": ("face.txt", b"not-an-image", "text/plain")}
    )
    assert resp.status_code == 422
    assert StubAppearancePort.instances == []


def test_missing_image_rejected(monkeypatch):
    assert _client(monkeypatch).post(EPH_HAIR).status_code == 422


def test_empty_image_rejected(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(EPH_GARMENT, files={"image": ("empty.jpg", b"", "image/jpeg")})
    assert resp.status_code == 422
    # Port may be constructed by the router, but analyze must never run.
    assert sum(len(i.calls) for i in StubGarmentPort.instances) == 0


def test_invalid_grooming_profile_rejected(monkeypatch):
    client = _client(monkeypatch)
    # Missing face_shape (pydantic).
    assert client.post(EPH_GROOM, json={}).status_code == 422
    # Empty / whitespace face_shape (use-case honesty: no invented default).
    assert client.post(EPH_GROOM, json={"face_shape": "   "}).status_code == 422
    # Wrong type (pydantic).
    assert client.post(EPH_GROOM, json={"face_shape": 5}).status_code == 422
    # Overlong input (bounded request contract).
    assert (
        client.post(EPH_GROOM, json={"face_shape": "x" * 201}).status_code == 422
    )


def test_no_face_detected_is_honest_failure(monkeypatch):
    client = _client(monkeypatch)
    StubAppearancePort.mode = "no-face"
    resp = _post_image(client, EPH_HAIR)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- honest provider failures --------------------------------------------------


def test_typed_analyzer_failure_keeps_reason(monkeypatch):
    client = _client(monkeypatch)
    StubAppearancePort.mode = "typed-failure"
    resp = _post_image(client, EPH_HAIR)
    assert resp.status_code == 422
    assert "vision_unavailable" in resp.text


def test_adapter_crash_is_503_never_fake(monkeypatch):
    client = _client(monkeypatch)
    StubAppearancePort.mode = "crash"
    resp = _post_image(client, EPH_OUTFIT)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "AI_FAILURE"


def test_no_garment_detected_is_honest_failure(monkeypatch):
    client = _client(monkeypatch)
    StubGarmentPort.mode = "no-garment"
    resp = _post_image(client, EPH_GARMENT)
    assert resp.status_code == 422
    assert "no_garment_detected" in resp.text


def test_garment_crash_is_503_never_fake(monkeypatch):
    client = _client(monkeypatch)
    StubGarmentPort.mode = "crash"
    resp = _post_image(client, EPH_GARMENT)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "AI_FAILURE"


# --- rate limiting --------------------------------------------------------------


def test_ephemeral_rate_limit_returns_429(monkeypatch):
    from app.api import rate_limit

    monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_EPHEMERAL_PER_MINUTE", "1")
    monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_WINDOW_S", "60")
    clear_settings_cache()
    rate_limit.reset()
    try:
        client = _client(monkeypatch)
        assert _post_image(client, EPH_GARMENT).status_code == 200
        limited = _post_image(client, EPH_GARMENT)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMITED"
    finally:
        rate_limit.reset()
        clear_settings_cache()


# --- use-case units --------------------------------------------------------------


def test_hairstyle_use_case_writes_nothing_by_construction():
    import inspect

    # No repository/session port exists on the constructor or call: the
    # use case is incapable of database writes by construction.
    params = inspect.signature(EphemeralHairstyleAnalysis.__init__).parameters
    assert set(params) == {"self", "knowledge", "appearance_port", "enrich"}
    call_params = inspect.signature(EphemeralHairstyleAnalysis.__call__).parameters
    assert set(call_params) == {"self", "image"}
    use_case = EphemeralHairstyleAnalysis(
        knowledge=CatalogKnowledgeSource(),
        appearance_port=StubAppearancePort(),
    )
    assert use_case is not None


def test_grooming_engine_failure_is_503():
    class _EmptyKnowledge:
        knowledge_version = "test"

        def lookup_grooming_look(self, look_id):
            return None

    # Empty catalog → no candidates → KnowledgeError → honest 503.
    use_case = EphemeralGroomingAnalysis(knowledge=_EmptyKnowledge())
    with pytest.raises(Exception) as exc_info:
        use_case(face_shape="Oval")
    assert getattr(exc_info.value, "status_code", None) == 503


def test_garment_use_case_takes_no_repositories():
    import inspect

    params = inspect.signature(EphemeralGarmentAnalysis.__init__).parameters
    assert set(params) == {"self", "garment_port"}


# --- authenticated surface + migrations untouched ---------------------------------


def test_authenticated_endpoints_still_require_auth(monkeypatch):
    client = _auth_client(monkeypatch)
    for path, kwargs in (
        ("/v1/analysis/hairstyle", {"data": {}}),
        ("/v1/analysis/outfit", {}),
        ("/v1/analysis/grooming", {"json": {}}),
        ("/v1/analysis/garment", {}),
    ):
        resp = client.post(path, **kwargs)
        assert resp.status_code in (401, 422), (path, resp.status_code)
    # No-auth image submits are 401, never routed to ephemeral logic.
    resp = client.post(
        "/v1/analysis/garment", files={"image": JPEG}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_migration_head_remains_0025():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    assert tuple(script.get_heads()) == ("0025",)
    rev25 = script.get_revision("0025")
    assert rev25 is not None
    assert rev25.down_revision == "0024"
