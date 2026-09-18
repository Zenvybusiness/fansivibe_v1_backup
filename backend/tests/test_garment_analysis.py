"""M11 garment-analysis contract tests (DB-free).

`OllamaVisionGarmentAdapter` is exercised with a fake `chat_fn` (no Ollama);
`POST /v1/analysis/garment` runs on in-memory fakes patched into the router
namespace (hairstyle-image-router precedent). Wardrobe `imageRef` unseal is
covered at the use-case layer with an in-memory repo double.

Honesty assertions: unknown attributes stay null (never invented), a
non-garment image fails the run (never scores), bytes are never logged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi.testclient import TestClient

import app.api.routers.analysis as analysis_router
from app.ai.vision_garment_adapter import (
    GarmentAnalysisError,
    OllamaVisionGarmentAdapter,
)
from app.application.wardrobe import AddWardrobeItem, UpdateWardrobeItem
from app.domain.ports.repositories import AnalysisRunRecord, WardrobeItemRecord
from app.domain.value_objects import GarmentProfile

USER = uuid.uuid4()


# --- adapter unit tests -------------------------------------------------------


def _adapter(reply: dict) -> OllamaVisionGarmentAdapter:
    return OllamaVisionGarmentAdapter(
        host="http://test",
        model="test-model",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: reply,
    )


def _analyze(reply: dict) -> GarmentProfile:
    return _adapter(reply).analyze(
        media_ref={"key": "k"}, user_id=USER, image_bytes=b"garment-bytes"
    )


def test_valid_garment_observation():
    profile = _analyze(
        {
            "category": "tops",
            "subcategory": "oxford shirt",
            "color": "light blue",
            "pattern": "solid",
            "material": "cotton",
            "style": "casual",
            "fit": "regular",
            "confidence": 0.84,
        }
    )
    assert profile.category == "tops"
    assert profile.color == "light blue"
    assert profile.material == "cotton"
    assert profile.confidence == 0.84
    assert profile.needs_review is False


def test_missing_attributes_stay_null_never_invented():
    profile = _analyze({"category": "footwear", "confidence": 0.9})
    assert profile.category == "footwear"
    assert profile.subcategory is None
    assert profile.color is None
    assert profile.material is None
    # Missing core facts always route through user confirmation.
    assert profile.needs_review is True


def test_no_garment_image_fails_never_scores():
    try:
        _analyze({"category": "no_garment", "confidence": 0})
    except GarmentAnalysisError as exc:
        assert exc.reason == "no_garment_detected"
    else:
        raise AssertionError("no_garment must raise")


def test_ambiguous_subject_fails():
    try:
        _analyze({"category": "ambiguous", "confidence": 0})
    except GarmentAnalysisError as exc:
        assert exc.reason == "ambiguous_subject"
    else:
        raise AssertionError("ambiguous must raise")


def test_descriptive_category_coerces_to_none_not_failure():
    # The model describing ("shirt") instead of classifying is not a run
    # failure — the user confirms the category.
    profile = _analyze({"category": "shirt", "color": "red", "confidence": 0.7})
    assert profile.category is None
    assert profile.color == "red"
    assert profile.needs_review is True


def test_wrong_types_fail_the_run():
    for reply in (
        {"category": 5, "confidence": 0.8},
        {"category": "tops", "confidence": "high"},
        {"category": "tops", "confidence": True},
        {"category": "tops", "confidence": 1.5},
        {"category": "tops"},
    ):
        try:
            _analyze(reply)
        except GarmentAnalysisError as exc:
            assert exc.reason == "invalid_analyzer_response", reply
        else:
            raise AssertionError(f"must raise: {reply}")


def test_low_confidence_refused():
    try:
        _analyze({"category": "tops", "confidence": 0.2})
    except GarmentAnalysisError as exc:
        assert exc.reason == "low_confidence"
    else:
        raise AssertionError("low confidence must raise")


def test_prompt_guards_face_first_portraits():
    from app.ai.vision_garment_adapter import _prompt

    prompt = _prompt()
    assert "no_garment" in prompt
    assert "portrait" in prompt


def test_missing_bytes_is_programming_error():
    try:
        _adapter({}).analyze(media_ref={"key": "k"}, user_id=USER)
    except ValueError:
        pass
    else:
        raise AssertionError("missing bytes must raise ValueError")


def test_validate_result_contract():
    adapter = _adapter({})
    good = GarmentProfile(
        category="tops",
        color="blue",
        material="cotton",
        confidence=0.8,
        needs_review=False,
    ).to_snapshot()
    assert adapter.validate_result(good) is True
    assert adapter.validate_result({**good, "category": "shirt"}) is False
    assert adapter.validate_result({**good, "confidence": 2.0}) is False
    assert adapter.validate_result({**good, "needs_review": "yes"}) is False
    dropped = dict(good)
    del dropped["color"]
    assert adapter.validate_result(dropped) is False


# --- router tests (in-memory fakes) -------------------------------------------


class FakeRuns:
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


class RecordingGarmentPort:
    instances: list = []
    mode: str = "ok"  # "ok" | "no_garment"

    adapter_id = "ollama-garment-v1"

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list = []
        RecordingGarmentPort.instances.append(self)

    def analyze(self, *, media_ref, user_id, image_bytes=None):
        self.calls.append(
            {"media_ref": media_ref, "user_id": user_id, "image_bytes": image_bytes}
        )
        if RecordingGarmentPort.mode == "no_garment":
            raise GarmentAnalysisError("no_garment_detected")
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


def _client(monkeypatch) -> TestClient:
    from app.main import app

    FakeRuns.rows = {}
    RecordingGarmentPort.instances = []
    RecordingGarmentPort.mode = "ok"

    monkeypatch.setattr(analysis_router, "AnalysisRunRepositorySQL", FakeRuns)
    monkeypatch.setattr(
        analysis_router, "OllamaVisionGarmentAdapter", RecordingGarmentPort
    )

    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: object())
    monkeypatch.setitem(app.dependency_overrides, get_current_user_id, lambda: USER)
    return TestClient(app)


def _post_garment(client: TestClient, payload: bytes = b"garment-scan-bytes"):
    return client.post(
        "/v1/analysis/garment",
        files={"image": ("shirt.jpg", payload, "image/jpeg")},
    )


def test_garment_image_returns_202_with_run_id(monkeypatch):
    resp = _post_garment(_client(monkeypatch))
    assert resp.status_code == 202
    assert resp.json()["run_id"]
    assert len(FakeRuns.rows) == 1


def test_garment_run_uses_garment_adapter_and_bytes(monkeypatch):
    client = _client(monkeypatch)
    payload = b"actual-garment-bytes"
    run_id = _post_garment(client, payload).json()["run_id"]
    assert len(RecordingGarmentPort.instances) == 1
    row = FakeRuns.rows[UUID(run_id)]
    assert row["run_type"] == "garment"
    assert row["input_media"]["analyzer"] == "ollama-garment-v1"
    calls = RecordingGarmentPort.instances[0].calls
    assert len(calls) == 1
    assert calls[0]["image_bytes"] == payload
    assert calls[0]["user_id"] == USER


def test_completed_garment_run_carries_observation_snapshot(monkeypatch):
    client = _client(monkeypatch)
    run_id = _post_garment(client).json()["run_id"]
    got = client.get(f"/v1/analysis/runs/{run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "completed"
    result = body["result"]
    assert result["category"] == "tops"
    assert result["color"] == "light blue"
    assert result["material"] == "cotton"
    assert result["style"] is None
    assert result["confidence"] == 0.84
    assert result["needs_review"] is False


def test_non_garment_image_produces_terminal_failed_run(monkeypatch):
    client = _client(monkeypatch)
    RecordingGarmentPort.mode = "no_garment"
    run_id = _post_garment(client).json()["run_id"]
    got = client.get(f"/v1/analysis/runs/{run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["reason"] == "no_garment_detected"
    # Never poses a fake garment score.
    assert body["result"] is None


def test_garment_rejects_non_image(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/v1/analysis/garment",
        files={"image": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 422


# --- wardrobe imageRef unseal (use-case layer, in-memory double) --------------


class FakeWardrobe:
    def __init__(self) -> None:
        self.created: dict = {}
        self.updated: dict = {}
        self.row = WardrobeItemRecord(
            id=uuid.uuid4(),
            user_id=USER,
            name="Shirt",
            category="tops",
            color="blue",
            material=None,
            is_favorite=False,
            image_ref=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def create(self, **kwargs):
        self.created = kwargs
        return self.row

    def update(self, **kwargs):
        self.updated = kwargs
        return self.row

    def get_by_id(self, *, user_id, item_id):
        return self.row

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_add_item_persists_image_ref():
    repo = FakeWardrobe()
    record = AddWardrobeItem(wardrobe=repo)(
        user_id=USER,
        name="Shirt",
        category="tops",
        color="blue",
        material=None,
        isFavorite=False,
        image_ref={"key": "users/x/scans/y/input.jpg", "contentHash": "abc"},
    )
    assert record is not None
    assert repo.created["image_ref"] == {
        "key": "users/x/scans/y/input.jpg",
        "contentHash": "abc",
    }


def test_add_item_without_image_ref_stays_null():
    repo = FakeWardrobe()
    AddWardrobeItem(wardrobe=repo)(
        user_id=USER,
        name="Shirt",
        category="tops",
        color="blue",
        material=None,
        isFavorite=False,
    )
    assert repo.created["image_ref"] is None


def test_update_item_sets_image_ref_only_when_present():
    repo = FakeWardrobe()
    item_id = uuid.uuid4()
    UpdateWardrobeItem(wardrobe=repo)(
        user_id=USER,
        item_id=item_id,
        name=None,
        category=None,
        color=None,
        material=None,
        isFavorite=None,
        image_ref={"key": "k"},
        image_ref_set=True,
    )
    assert repo.updated["image_ref"] == {"key": "k"}
    assert repo.updated["image_ref_set"] is True

    repo2 = FakeWardrobe()
    UpdateWardrobeItem(wardrobe=repo2)(
        user_id=USER,
        item_id=item_id,
        name="Renamed",
        category=None,
        color=None,
        material=None,
        isFavorite=None,
    )
    assert repo2.updated["image_ref_set"] is False
