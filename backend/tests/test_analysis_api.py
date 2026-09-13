"""API tests for the analysis surface (#37/#39/#40).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.db.models import UserState, Users

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


def _seed_profile(db, profile: dict):
    Session = db
    with Session() as session:
        user_id = _dev_user_id(session)
        state = session.get(UserState, user_id)
        state.style_profile = profile
        session.commit()


# --- auth / validation ------------------------------------------------------


def test_submit_requires_auth():
    resp = client.post("/v1/analysis/hairstyle", data={})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_submit_requires_face_profile_ref(db):
    resp = client.post("/v1/analysis/hairstyle", data={}, headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_rejects_malformed_profile_ref(db):
    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": "not-a-uuid"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_image_upload_reaches_production_image_run(db, monkeypatch):
    # STEP 10.5: the hairstyle image branch now wires CreateHairstyleImageRun
    # with the production adapter (202 {run_id}) instead of refusing honestly.
    seen: dict = {}

    from app.domain.value_objects import AppearanceProfile

    class RecordingVisionPort:
        adapter_id = "ollama-vision-v1"

        def analyze(self, *, media_ref, user_id, image_bytes=None):
            seen["image_bytes"] = image_bytes
            seen["media_ref"] = media_ref
            return AppearanceProfile(
                faceShape="oval",
                skinTone="",
                bodyType="",
                styleType="",
                sourceRunId="",
            )

        def validate_result(self, result) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routers.analysis.OllamaVisionAppearanceAdapter",
        RecordingVisionPort,
    )
    payload = b"real-scan-bytes-for-api-test"
    resp = client.post(
        "/v1/analysis/hairstyle",
        files={"image": ("face.jpg", payload, "image/jpeg")},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    assert run_id
    # The actual received bytes reached the production analyzer.
    assert seen["image_bytes"] == payload

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["run_type"] == "hairstyle"
    assert body["status"] == "completed"
    assert body["result"]["appearance"]["faceShape"] == "oval"
    assert body["result"]["appearance"]["sourceRunId"] == run_id
    assert body["input_media"]["analyzer"] == "ollama-vision-v1"


def test_hairstyle_image_does_not_route_through_outfit(db, monkeypatch):
    # STEP 10.5: the hairstyle image branch must invoke CreateHairstyleImageRun
    # with the production adapter — never CreateOutfitRun and never the
    # development/hash adapter.
    def _boom(*args, **kwargs):
        raise AssertionError("hairstyle image must not route through CreateOutfitRun")

    monkeypatch.setattr(
        "app.api.routers.analysis.CreateOutfitRun", _boom
    )

    def _boom_dev(*args, **kwargs):
        raise AssertionError(
            "hairstyle image must not use DevelopmentAppearanceAnalysisAdapter"
        )

    monkeypatch.setattr(
        "app.api.routers.analysis.DevelopmentAppearanceAnalysisAdapter", _boom_dev
    )

    from app.domain.value_objects import AppearanceProfile

    class RecordingVisionPort:
        adapter_id = "ollama-vision-v1"

        def analyze(self, *, media_ref, user_id, image_bytes=None):
            return AppearanceProfile(
                faceShape="oval",
                skinTone="",
                bodyType="",
                styleType="",
                sourceRunId="",
            )

        def validate_result(self, result) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routers.analysis.OllamaVisionAppearanceAdapter",
        RecordingVisionPort,
    )
    resp = client.post(
        "/v1/analysis/hairstyle",
        files={"image": ("face.jpg", b"fakebytes", "image/jpeg")},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    assert resp.json()["run_id"]


def test_hairstyle_image_xor_still_rejects_both(db):
    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": str(uuid.uuid4())},
        files={"image": ("face.jpg", b"fakebytes", "image/jpeg")},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_hairstyle_image_failed_analyzer_marks_run_failed(db, monkeypatch):
    # Analyzer failure → honest terminal `failed` run with PROCESSING_FAILURE.
    from app.ai.vision_appearance_adapter import AppearanceAnalysisError

    class FailingVisionPort:
        adapter_id = "ollama-vision-v1"

        def analyze(self, *, media_ref, user_id, image_bytes=None):
            raise AppearanceAnalysisError("no_face_detected")

        def validate_result(self, result) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routers.analysis.OllamaVisionAppearanceAdapter",
        FailingVisionPort,
    )
    resp = client.post(
        "/v1/analysis/hairstyle",
        files={"image": ("face.jpg", b"no-face-bytes", "image/jpeg")},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["run_id"] == run_id
    assert body["error"]["details"]["reason"] == "no_face_detected"


def test_submit_without_profile_returns_insufficient_data(db):
    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "INSUFFICIENT_USER_DATA"
    assert body["details"]["missing"] == "face"


# --- happy path -------------------------------------------------------------


def test_full_flow_202_then_completed_with_result(db):
    _seed_profile(
        db,
        {"face_shape": "Oval", "skin_tone": "Warm Medium", "style_type": "Modern Classic"},
    )
    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["run_id"] == run_id
    assert body["run_type"] == "hairstyle"
    assert body["status"] == "completed"
    assert body["completed_at"] is not None
    assert body["engine_version"] is not None
    assert body["input_media"] is None

    result = body["result"]
    assert result["appearance"]["faceShape"] == "Oval"
    assert result["appearance"]["sourceRunId"] == run_id
    recs = result["recommendations"]
    assert recs["top"]["id"] == "textured_quiff"
    assert recs["top"]["matchScore"] <= 1.0
    assert len(recs["alternatives"]) == 3


def test_round_profile_ranks_pompadour(db):
    _seed_profile(db, {"face_shape": "Round"})
    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": str(uuid.uuid4())},
        headers=HEADERS,
    )
    run_id = resp.json()["run_id"]
    body = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS).json()
    assert body["result"]["recommendations"]["top"]["id"] == "classic_pompadour"


def test_recommendation_failure_marks_run_failed_with_processsing_failure(db, monkeypatch):
    # Pipeline failure (empty knowledge → engine raises) must yield a `failed`
    # run with PROCESSING_FAILURE + details.run_id — never a stuck pending run.
    _seed_profile(db, {"face_shape": "Oval"})

    def _empty_retrieve(self):
        return []

    monkeypatch.setattr(
        "app.infrastructure.external.knowledge.CatalogKnowledgeSource.retrieve_hairstyle_looks",
        _empty_retrieve,
    )

    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["completed_at"] is not None
    assert body["result"] is None
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["run_id"] == run_id


# --- owner scoping / errors -------------------------------------------------


def test_get_foreign_or_missing_run_returns_404(db):
    _seed_profile(db, {"face_shape": "Oval"})
    resp = client.get(f"/v1/analysis/runs/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_get_malformed_run_id_returns_422():
    resp = client.get("/v1/analysis/runs/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_runs_returns_summaries_without_result(db):
    _seed_profile(db, {"face_shape": "Oval"})
    for _ in range(3):
        run_id = client.post(
            "/v1/analysis/hairstyle",
            data={"faceProfileRef": str(uuid.uuid4())},
            headers=HEADERS,
        ).json()["run_id"]
        assert run_id

    resp = client.get("/v1/analysis/runs", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["page"] == 1
    assert body["page_size"] == 20
    for item in body["items"]:
        assert "result" not in item
        assert "error" not in item
        assert item["status"] == "completed"


def test_create_outfit_run_success_db(db, monkeypatch):
    from app.domain.value_objects import AppearanceProfile

    seen: dict = {}

    class RecordingOutfitVisionPort:
        adapter_id = "ollama-vision-v1"

        def analyze(self, *, media_ref, user_id, image_bytes=None):
            seen["image_bytes"] = image_bytes
            seen["media_ref"] = media_ref
            return AppearanceProfile(
                faceShape="oval",
                skinTone="",
                bodyType="",
                styleType="",
                sourceRunId="",
            )

        def validate_result(self, result) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routers.analysis.OllamaVisionAppearanceAdapter",
        RecordingOutfitVisionPort,
    )

    image_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
    files = {"image": ("outfit.jpg", image_bytes, "image/jpeg")}
    resp = client.post("/v1/analysis/outfit", files=files, headers=HEADERS)
    assert resp.status_code == 202
    body = resp.json()
    assert "run_id" in body
    run_id = body["run_id"]
    assert seen["image_bytes"] == image_bytes

    # Verify GET /v1/analysis/runs/{run_id}
    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    run_data = got.json()
    assert run_data["run_id"] == run_id
    assert run_data["run_type"] == "outfit"
    assert run_data["status"] == "completed"

    # Verify GET /v1/analysis/runs lists the outfit run
    runs_resp = client.get("/v1/analysis/runs", headers=HEADERS)
    assert runs_resp.status_code == 200
    runs_data = runs_resp.json()
    matching = [r for r in runs_data["items"] if r["run_id"] == run_id]
    assert len(matching) == 1
    assert matching[0]["run_type"] == "outfit"


def test_create_outfit_run_does_not_use_development_adapter(db, monkeypatch):
    # P0-2: the outfit production path must use OllamaVisionAppearanceAdapter
    # — never DevelopmentAppearanceAnalysisAdapter.

    def _boom_dev(*args, **kwargs):
        raise AssertionError(
            "outfit production path must not use DevelopmentAppearanceAnalysisAdapter"
        )

    monkeypatch.setattr(
        "app.api.routers.analysis.DevelopmentAppearanceAnalysisAdapter", _boom_dev
    )

    from app.domain.value_objects import AppearanceProfile

    class RecordingOutfitVisionPort:
        adapter_id = "ollama-vision-v1"

        def analyze(self, *, media_ref, user_id, image_bytes=None):
            return AppearanceProfile(
                faceShape="oval",
                skinTone="",
                bodyType="",
                styleType="",
                sourceRunId="",
            )

        def validate_result(self, result) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routers.analysis.OllamaVisionAppearanceAdapter",
        RecordingOutfitVisionPort,
    )
    image_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
    resp = client.post(
        "/v1/analysis/outfit",
        files={"image": ("outfit.jpg", image_bytes, "image/jpeg")},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    assert resp.json()["run_id"]


def test_create_outfit_failed_analyzer_marks_run_failed(db, monkeypatch):
    # P0-2: analyzer failure → honest terminal `failed` run with
    # PROCESSING_FAILURE + details.run_id + reason (existing error contract).
    from app.ai.vision_appearance_adapter import AppearanceAnalysisError

    class FailingOutfitVisionPort:
        adapter_id = "ollama-vision-v1"

        def analyze(self, *, media_ref, user_id, image_bytes=None):
            raise AppearanceAnalysisError("no_face_detected")

        def validate_result(self, result) -> bool:
            return True

    monkeypatch.setattr(
        "app.api.routers.analysis.OllamaVisionAppearanceAdapter",
        FailingOutfitVisionPort,
    )
    resp = client.post(
        "/v1/analysis/outfit",
        files={"image": ("outfit.jpg", b"outfit-no-face-bytes", "image/jpeg")},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["run_id"] == run_id
    assert body["error"]["details"]["reason"] == "no_face_detected"


