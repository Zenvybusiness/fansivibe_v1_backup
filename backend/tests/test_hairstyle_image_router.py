"""DB-free router tests for the STEP 10.5 real-appearance image wiring.

`POST /v1/analysis/hairstyle` with an image must reach
`CreateHairstyleImageRun` with the production `OllamaVisionAppearanceAdapter`
(never the development/hash adapter), return `202 {run_id}`, deliver the
actual bytes to the analyzer, and surface analyzer failure as a terminal
`failed` run. `faceProfileRef`-only and XOR behavior must be unchanged.

Runs entirely on in-memory fakes (SQL repos + auth + adapter are patched in
the router namespace), so these execute with no PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi.testclient import TestClient

import app.api.routers.analysis as analysis_router
from app.ai.vision_appearance_adapter import AppearanceAnalysisError
from app.domain.ports.repositories import AnalysisRunRecord
from app.domain.value_objects import AppearanceProfile

USER = uuid.uuid4()


class FakeRuns:
    """Shared in-memory run store (class-level so submit + poll share rows)."""

    rows: dict[UUID, dict] = {}

    def __init__(self, db=None) -> None:
        pass

    def create(self, *, user_id, run_type, engine_version="rules-v1", input_media=None, knowledge_version=None) -> UUID:
        run_id = uuid.uuid4()
        FakeRuns.rows[run_id] = {
            "id": run_id,
            "user_id": user_id,
            "run_type": run_type,
            "status": "pending",
            "engine_version": engine_version,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
            "input_media": input_media,
            "result": None,
            "error": None,
            "knowledge_version": knowledge_version,
        }
        return run_id

    def get_for_user(self, *, user_id, run_id) -> Optional[AnalysisRunRecord]:
        row = FakeRuns.rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        return AnalysisRunRecord(**{k: v for k, v in row.items() if k != "user_id"})

    def list_for_user(self, *, user_id, page, page_size):
        items = [r for r in FakeRuns.rows.values() if r["user_id"] == user_id]
        return [], len(items)

    def complete(self, *, run_id, user_id, status, result) -> bool:
        row = FakeRuns.rows.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "pending":
            return False
        row["status"] = status
        row["result"] = result
        row["completed_at"] = datetime.now(timezone.utc)
        return True

    def fail(self, *, run_id, user_id, error) -> bool:
        row = FakeRuns.rows.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "pending":
            return False
        row["status"] = "failed"
        row["error"] = error
        row["completed_at"] = datetime.now(timezone.utc)
        return True


class FakeUserState:
    profile: dict | None = {"face_shape": "Oval"}

    def __init__(self, db=None) -> None:
        pass

    def get_style_profile(self, *, user_id: UUID):
        return FakeUserState.profile

    def update_style_profile(
        self, *, user_id, face_shape, skin_tone, body_type, style_type, source_run_id
    ) -> None:
        FakeUserState.profile = {
            "face_shape": face_shape,
            "skin_tone": skin_tone,
            "body_type": body_type,
            "style_type": style_type,
            "source_run_id": source_run_id,
        }


class FakeLearningSignal:
    calls: list = []

    def __init__(self, db=None) -> None:
        pass

    def insert_look_saved(self, *, user_id, signal_type="look_saved", label, context):
        FakeLearningSignal.calls.append({"user_id": user_id, "signal_type": signal_type, "label": label, "context": context})

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class RecordingVisionPort:
    """Production-adapter stand-in: records construction + calls."""

    instances: list = []
    mode: str = "ok"  # "ok" | "no_face"

    adapter_id = "ollama-vision-v1"

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list = []
        RecordingVisionPort.instances.append(self)

    def analyze(self, *, media_ref, user_id, image_bytes=None):
        self.calls.append({"media_ref": media_ref, "user_id": user_id, "image_bytes": image_bytes})
        if RecordingVisionPort.mode == "no_face":
            raise AppearanceAnalysisError("no_face_detected")
        return AppearanceProfile(
            faceShape="oval", skinTone="", bodyType="", styleType="", sourceRunId=""
        )

    def validate_result(self, result) -> bool:
        return True


def _boom_dev(*args, **kwargs):
    raise AssertionError("DevelopmentAppearanceAnalysisAdapter must not be used for hairstyle image")


def _boom_outfit(*args, **kwargs):
    raise AssertionError("hairstyle image must not route through CreateOutfitRun")


def _client(monkeypatch) -> TestClient:
    from app.main import app

    FakeRuns.rows = {}
    FakeUserState.profile = {"face_shape": "Oval"}
    FakeLearningSignal.calls = []
    RecordingVisionPort.instances = []
    RecordingVisionPort.mode = "ok"

    monkeypatch.setattr(analysis_router, "AnalysisRunRepositorySQL", FakeRuns)
    monkeypatch.setattr(analysis_router, "UserStateRepositorySQL", FakeUserState)
    monkeypatch.setattr(analysis_router, "LearningSignalRepositorySQL", FakeLearningSignal)
    monkeypatch.setattr(analysis_router, "OllamaVisionAppearanceAdapter", RecordingVisionPort)
    monkeypatch.setattr(
        analysis_router, "DevelopmentAppearanceAnalysisAdapter", _boom_dev
    )
    monkeypatch.setattr(analysis_router, "CreateOutfitRun", _boom_outfit)

    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    # Re-applied per test (same values); no cleanup needed — every test
    # re-establishes these overrides before use.
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user_id] = lambda: USER
    return TestClient(app)


def _post_image(client: TestClient, payload: bytes = b"router-scan-bytes"):
    return client.post(
        "/v1/analysis/hairstyle",
        files={"image": ("face.jpg", payload, "image/jpeg")},
    )


# --- STEP 10.5 wiring --------------------------------------------------------


def test_image_returns_202_with_run_id(monkeypatch):
    client = _client(monkeypatch)
    resp = _post_image(client)
    assert resp.status_code == 202
    assert resp.json()["run_id"]
    assert len(FakeRuns.rows) == 1


def test_production_adapter_injected_not_development(monkeypatch):
    client = _client(monkeypatch)
    resp = _post_image(client)
    assert resp.status_code == 202
    # Exactly one production adapter constructed for the hairstyle branch.
    assert len(RecordingVisionPort.instances) == 1
    run_id = resp.json()["run_id"]
    row = FakeRuns.rows[UUID(run_id)]
    assert row["run_type"] == "hairstyle"
    assert row["input_media"]["analyzer"] == "ollama-vision-v1"
    # Development adapter / outfit path would have raised via the _boom patches.


def test_image_bytes_reach_analyzer(monkeypatch):
    client = _client(monkeypatch)
    payload = b"actual-bytes-must-reach-analyzer"
    resp = _post_image(client, payload)
    assert resp.status_code == 202
    calls = RecordingVisionPort.instances[0].calls
    assert len(calls) == 1
    assert calls[0]["image_bytes"] == payload
    assert calls[0]["user_id"] == USER


def test_completed_run_carries_measured_result(monkeypatch):
    client = _client(monkeypatch)
    run_id = _post_image(client).json()["run_id"]
    got = client.get(f"/v1/analysis/runs/{run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "completed"
    assert body["result"]["appearance"]["faceShape"] == "oval"
    assert body["result"]["appearance"]["sourceRunId"] == run_id
    labels = [c["label"] for c in FakeLearningSignal.calls]
    assert "analysis_updated" in labels
    assert "outfit_selected" not in labels


def test_failed_analyzer_produces_terminal_failed_run(monkeypatch):
    client = _client(monkeypatch)
    RecordingVisionPort.mode = "no_face"
    payload = b"no-face-payload"
    run_id = _post_image(client, payload).json()["run_id"]
    got = client.get(f"/v1/analysis/runs/{run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["run_id"] == run_id
    assert body["error"]["details"]["reason"] == "no_face_detected"
    # No image bytes leak into the persisted error payload.
    assert payload not in str(body["error"]).encode()


# --- unchanged behavior ------------------------------------------------------


def test_face_profile_only_behavior_unchanged(monkeypatch):
    client = _client(monkeypatch)
    ref = str(uuid.uuid4())
    resp = client.post("/v1/analysis/hairstyle", data={"faceProfileRef": ref})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    # Profile-only path never constructs the vision adapter.
    assert RecordingVisionPort.instances == []
    got = client.get(f"/v1/analysis/runs/{run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "completed"
    assert body["result"]["appearance"]["faceShape"] == "Oval"
    assert body["input_media"] is None


def test_xor_both_rejected(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/v1/analysis/hairstyle",
        data={"faceProfileRef": str(uuid.uuid4())},
        files={"image": ("face.jpg", b"bytes", "image/jpeg")},
    )
    assert resp.status_code == 422
    assert FakeRuns.rows == {}


def test_neither_rejected(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/v1/analysis/hairstyle", data={})
    assert resp.status_code == 422
    assert FakeRuns.rows == {}


def test_unsupported_media_type_rejected_before_adapter(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/v1/analysis/hairstyle",
        files={"image": ("face.gif", b"bytes", "image/gif")},
    )
    assert resp.status_code == 422
    # Rejected before the adapter or any run creation.
    assert RecordingVisionPort.instances == []
    assert FakeRuns.rows == {}
    # Oversize (declared-size) rejection is covered at the use-case level in
    # test_analysis_use_case.py::test_hairstyle_image_run_validation_unchanged.
