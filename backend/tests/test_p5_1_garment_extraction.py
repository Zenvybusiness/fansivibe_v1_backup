"""Comprehensive P5.1 AI Garment Extraction tests.

Covers all P5.1 requirements across image validation, Pillow cropping,
VisionGarmentAdapter bounding-box extraction, honest segmentation reporting,
FastAPI endpoints, OW-1 cross-user isolation, PostgreSQL persistence,
selective Digital Wardrobe saving, idempotent retries & partial-failure retries,
temporary asset cleanup (on save, cancel/discard, and expiration), and live
local Ollama `qwen3-vl:4b-instruct` inference + cropping.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
import os
import urllib.request
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import select

from app.ai.vision_garment_adapter import (
    GarmentAnalysisError,
    OllamaVisionGarmentAdapter,
)
from app.api.deps import get_current_user_id, get_storage_adapter
from app.api.routers import analysis as analysis_router
from app.application.garment_extraction import (
    GarmentImageValidationError,
    cleanup_expired_extraction_assets,
    crop_garment_candidate,
    persist_extraction_crops,
    validate_and_normalize_garment_image,
)
from app.domain.ports.garment_analysis import GarmentAnalysisPort
from app.domain.ports.storage import StorageError
from app.domain.value_objects import GarmentProfile
from app.infrastructure.db.models import (
    AnalysisRuns,
    MediaUploadAuthorization,
    UserState,
    Users,
    WardrobeItems,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter


def _make_image_bytes(
    *,
    fmt: str = "JPEG",
    size: tuple[int, int] = (600, 800),
    color: tuple[int, int, int] = (25, 45, 95),
    with_two_garments: bool = False,
) -> bytes:
    """Create a real in-memory image (optionally with two clear garment blocks)."""
    img = Image.new("RGB", size, (242, 240, 236))
    if with_two_garments and size[0] >= 200 and size[1] >= 200:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        w, h = size
        # Top garment: navy t-shirt silhouette
        draw.rectangle([int(w * 0.25), int(h * 0.12), int(w * 0.75), int(h * 0.44)], fill=(22, 42, 92))
        draw.rectangle([int(w * 0.14), int(h * 0.12), int(w * 0.27), int(h * 0.28)], fill=(22, 42, 92))
        draw.rectangle([int(w * 0.73), int(h * 0.12), int(w * 0.86), int(h * 0.28)], fill=(22, 42, 92))
        # Bottom garment: khaki/beige trousers silhouette
        draw.rectangle([int(w * 0.30), int(h * 0.48), int(w * 0.48), int(h * 0.90)], fill=(195, 175, 138))
        draw.rectangle([int(w * 0.52), int(h * 0.48), int(w * 0.70), int(h * 0.90)], fill=(195, 175, 138))
        draw.rectangle([int(w * 0.30), int(h * 0.48), int(w * 0.70), int(h * 0.57)], fill=(195, 175, 138))
    elif size != (600, 800) or color != (25, 45, 95):
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        w, h = size
        draw.rectangle([int(w * 0.15), int(h * 0.15), int(w * 0.85), int(h * 0.85)], fill=color)

    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _exif_rotated_jpeg_bytes() -> bytes:
    """Create a 300x100 JPEG tagged with EXIF orientation 6 (90 deg CW -> 100x300)."""
    img = Image.new("RGB", (300, 100), (40, 80, 140))
    exif = Image.Exif()
    exif[274] = 6  # Orientation = Rotate 90 CW
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


class _FakeVisionGarmentAnalyzer(GarmentAnalysisPort):
    """Configurable test double for OllamaVisionGarmentAdapter."""

    adapter_id = "test_vision_garment"
    validates_image_signature = True

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[bytes] = []

    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> GarmentProfile:
        self.calls.append(image_bytes or b"")
        return self._handler(media_ref, user_id, image_bytes)


def _create_user(SessionLocal, label: str) -> UUID:
    with SessionLocal() as session:
        user = Users(
            auth_provider="dev",
            auth_subject=f"p51-{label}-{uuid4()}",
            display_name=f"P5.1 User {label}",
        )
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
        session.commit()
        return user.id


@pytest.fixture
def api_env(db, monkeypatch):
    """Provide FastAPI TestClient, two isolated users, and FakeStorageAdapter."""
    SessionLocal = db
    user_a = _create_user(SessionLocal, "A")
    user_b = _create_user(SessionLocal, "B")
    active_user = {"id": user_a}
    fake_storage = FakeStorageAdapter()

    app.dependency_overrides[get_current_user_id] = lambda: active_user["id"]
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage

    client = TestClient(app)
    yield {
        "client": client,
        "db": SessionLocal,
        "user_a": user_a,
        "user_b": user_b,
        "active_user": active_user,
        "storage": fake_storage,
        "monkeypatch": monkeypatch,
    }


# ---------------------------------------------------------------------------
# Pure image validation, cropping & Ollama adapter unit tests (always run)
# ---------------------------------------------------------------------------


def test_validate_image_rejects_corrupted_empty_and_unsupported_formats():
    with pytest.raises(GarmentImageValidationError) as exc_empty:
        validate_and_normalize_garment_image(b"", "image/jpeg")
    assert exc_empty.value.reason == "invalid_image"

    with pytest.raises(GarmentImageValidationError) as exc_mime:
        validate_and_normalize_garment_image(b"GIF89a......", "image/gif")
    assert exc_mime.value.reason == "unsupported_format"

    # PNG magic bytes pretending to be JPEG -> invalid_image
    png_bytes = _make_image_bytes(fmt="PNG", size=(120, 120))
    with pytest.raises(GarmentImageValidationError) as exc_mismatch:
        validate_and_normalize_garment_image(png_bytes, "image/jpeg")
    assert exc_mismatch.value.reason == "invalid_image"

    # Corrupted JPEG magic prefix
    with pytest.raises(GarmentImageValidationError) as exc_corrupt:
        validate_and_normalize_garment_image(b"\xff\xd8\xff\xe0corrupted-jpeg", "image/jpeg")
    assert exc_corrupt.value.reason == "invalid_image"


def test_validate_image_rejects_oversized_bytes_and_dimensions():
    huge = b"\xff\xd8\xff" + (b"\x00" * (20 * 1024 * 1024 + 8))
    with pytest.raises(GarmentImageValidationError) as exc_bytes:
        validate_and_normalize_garment_image(huge, "image/jpeg")
    assert exc_bytes.value.reason == "oversized_image"

    # Oversized edge (> 4096 px) PNG compresses cleanly in RAM while hitting dimension guard
    wide_png = _make_image_bytes(fmt="PNG", size=(4200, 100))
    with pytest.raises(GarmentImageValidationError) as exc_dim:
        validate_and_normalize_garment_image(wide_png, "image/png")
    assert exc_dim.value.reason == "oversized_image"


def test_validate_image_applies_exif_transpose_and_crop_bounds():
    rotated_bytes = _exif_rotated_jpeg_bytes()
    validated = validate_and_normalize_garment_image(rotated_bytes, "image/jpeg")
    # 300x100 rotated 90 deg -> upright 100x300
    assert (validated.width, validated.height) == (100, 300)
    assert validated.pil_image.info == {}

    cropped = crop_garment_candidate(
        validated.pil_image,
        {"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.7, "scale": "normalized_0_1"},
    )
    assert cropped.webp_bytes[:4] == b"RIFF"
    assert cropped.webp_bytes[8:12] == b"WEBP"
    assert cropped.width > 0 and cropped.height > 0


def test_ollama_vision_garment_adapter_multi_and_partial_and_honest_masks():
    def fake_ollama_chat(*, host, model, prompt, image_b64, timeout_s):
        assert image_b64
        return {
            "candidates": [
                {
                    "id": "cand_1",
                    "category": "tops",
                    "subcategory": "crewneck sweater",
                    "color": "navy",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "knit",
                    "season_tags": ["autumn"],
                    "confidence": 0.91,
                    "bbox_2d": [200, 100, 800, 480],
                },
                {
                    "id": "cand_broken",
                    "category": "tops",
                    "color": "beige",
                    "confidence": 0.05,  # Below LOW_CONFIDENCE_FLOOR -> partial failure
                    "bbox_2d": [300, 500, 700, 900],
                },
                {
                    "id": "cand_2",
                    "category": "bottoms",
                    "subcategory": "chinos",
                    "color": "beige",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": None,
                    "season_tags": ["spring", "summer"],
                    "confidence": 0.87,
                    "bbox_2d": [280, 470, 720, 920],
                },
            ],
        }

    adapter = OllamaVisionGarmentAdapter(chat_fn=fake_ollama_chat)
    raw = _make_image_bytes(fmt="JPEG", size=(400, 500), with_two_garments=True)
    profile = adapter.analyze(
        media_ref={"source": "unit_test"},
        user_id=uuid4(),
        image_bytes=raw,
    )

    assert len(profile.candidates) == 2
    assert profile.has_segmentation_mask is False
    assert profile.to_snapshot()["mask"] is None
    assert profile.extraction_method == "vlm_bounding_box_crop"
    assert profile.segmentation is not None and profile.segmentation["supported"] is False
    assert profile.partial_failures == (
        {"candidate_id": "cand_broken", "reason": "low_confidence"},
    )
    assert profile.candidates[0]["bounding_box"] == {
        "x1": 0.2,
        "y1": 0.1,
        "x2": 0.8,
        "y2": 0.48,
        "coord_space": "normalized_0_1",
    }
    assert profile.candidates[1]["material"] is None


# ---------------------------------------------------------------------------
# Full FastAPI + PostgreSQL + FakeStorageAdapter end-to-end tests
# ---------------------------------------------------------------------------


def test_single_garment_extraction_does_not_auto_save_and_returns_crop(api_env):
    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    cand = {
        "id": "cand_1",
        "category": "tops",
        "subcategory": "cotton tee",
        "color": "navy",
        "secondary_colors": [],
        "pattern": "solid",
        "material": "cotton",
        "season_tags": ["summer"],
        "confidence": 0.93,
        "bounding_box": {"x1": 0.2, "y1": 0.12, "x2": 0.8, "y2": 0.5, "scale": "normalized_0_1"},
    }
    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="cotton tee",
            color="navy",
            pattern="solid",
            material="cotton",
            confidence=0.93,
            needs_review=False,
            candidates=(cand,),
            extraction_method="vlm_bounding_box_crop",
            has_segmentation_mask=False,
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(500, 600), with_two_garments=True)
    submit = client.post(
        "/v1/analysis/garment",
        files={"image": ("shirt.jpg", img_bytes, "image/jpeg")},
    )
    assert submit.status_code == 202
    run_id = submit.json()["run_id"]

    poll = client.get(f"/v1/analysis/runs/{run_id}")
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "completed", f"Unexpected failure: {body}"
    result = body["result"]
    assert result["has_segmentation_mask"] is False
    assert result["mask"] is None
    assert len(result["candidates"]) == 1

    res_cand = result["candidates"][0]
    assert res_cand["has_crop"] is True
    assert res_cand["crop_url"] == f"/v1/analysis/runs/{run_id}/candidates/cand_1/image"
    assert res_cand["crop_key"] == f"users/{user_a}/extractions/{run_id}/candidates/cand_1.webp"
    assert res_cand["has_segmentation_mask"] is False
    assert res_cand["mask"] is None

    # Fetch crop bytes through authenticated endpoint
    crop_resp = client.get(res_cand["crop_url"])
    assert crop_resp.status_code == 200
    assert crop_resp.headers["content-type"] == "image/webp"
    assert crop_resp.headers["cache-control"] == "private, no-store"
    assert crop_resp.content[:4] == b"RIFF"

    # Must NEVER auto-save candidates into Digital Wardrobe
    with SessionLocal() as session:
        rows = session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all()
        assert rows == []
    assert any(f"users/{user_a}/extractions/{run_id}/" in k for k in storage.get_stored_keys())


def test_multiple_garments_select_subset_saves_only_selected_and_cleans_up_temp(api_env):
    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="oxford shirt",
            color="light_blue",
            pattern="striped",
            material="cotton",
            confidence=0.92,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_top",
                    "category": "tops",
                    "subcategory": "oxford shirt",
                    "color": "light_blue",
                    "secondary_colors": [],
                    "pattern": "striped",
                    "material": "cotton",
                    "season_tags": ["all_season"],
                    "confidence": 0.92,
                    "bounding_box": {"x1": 0.2, "y1": 0.1, "x2": 0.8, "y2": 0.45, "scale": "normalized_0_1"},
                },
                {
                    "id": "cand_bottom",
                    "category": "bottoms",
                    "subcategory": "chino trousers",
                    "color": "beige",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": None,
                    "season_tags": ["spring"],
                    "confidence": 0.88,
                    "bounding_box": {"x1": 0.25, "y1": 0.48, "x2": 0.75, "y2": 0.92, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="PNG", size=(600, 800), with_two_garments=True)
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("outfit.png", img_bytes, "image/png")},
    ).json()["run_id"]

    poll = client.get(f"/v1/analysis/runs/{run_id}").json()
    assert len(poll["result"]["candidates"]) == 2
    assert storage.object_exists_sync(f"users/{user_a}/extractions/{run_id}/candidates/cand_top.webp")
    assert storage.object_exists_sync(f"users/{user_a}/extractions/{run_id}/candidates/cand_bottom.webp")

    # User selects ONLY cand_top to save
    save_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "save-batch-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_top",
                    "name": "Oxford Shirt",
                    "category": "tops",
                    "color": "Light Blue",
                    "material": "Cotton",
                    "fit": "Regular",
                    "fitConfidence": 0.9,
                    "isFavorite": True,
                }
            ]
        },
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()
    assert len(save_data["savedItems"]) == 1
    assert save_data["failedItems"] == []
    assert save_data["cleanedUpAssets"] is True

    saved_item = save_data["savedItems"][0]
    assert saved_item["name"] == "Oxford Shirt"
    assert saved_item["category"] == "tops"
    assert saved_item["color"] == "light_blue"
    assert saved_item["material"] == "cotton"
    assert saved_item["isFavorite"] is True
    canonical_key = saved_item["imageRef"]["objectKey"]
    assert canonical_key.startswith(f"users/{user_a}/wardrobe/")

    # DB has ONLY 1 row, and MediaUploadAuthorization is published
    with SessionLocal() as session:
        rows = session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all()
        assert len(rows) == 1
        assert rows[0].name == "Oxford Shirt"
        auths = session.execute(select(MediaUploadAuthorization).where(MediaUploadAuthorization.user_id == user_a)).scalars().all()
        assert len(auths) == 1
        assert auths[0].status == "published"

    # Both temporary extraction crops (selected AND unselected) were cleaned up, while canonical wardrobe crop remains
    remaining_keys = set(storage.get_stored_keys())
    assert canonical_key in remaining_keys
    assert not any(f"users/{user_a}/extractions/{run_id}/" in k for k in remaining_keys)


def test_no_recognizable_garments_returns_honest_failure_and_zero_crops(api_env):
    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    def raise_no_garment(_m, _u, _b):
        raise GarmentAnalysisError("no_garment_detected")

    api_env["monkeypatch"].setattr(
        analysis_router,
        "OllamaVisionGarmentAdapter",
        lambda: _FakeVisionGarmentAnalyzer(raise_no_garment),
    )

    img_bytes = _make_image_bytes(fmt="WEBP", size=(400, 400), color=(210, 210, 210))
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("empty.webp", img_bytes, "image/webp")},
    ).json()["run_id"]

    poll = client.get(f"/v1/analysis/runs/{run_id}")
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["reason"] == "no_garment_detected"
    assert not any(f"users/{user_a}/extractions/{run_id}/" in k for k in storage.get_stored_keys())
    with SessionLocal() as session:
        assert session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all() == []


def test_api_rejects_invalid_unsupported_and_oversized_images(api_env):
    client: TestClient = api_env["client"]
    analyzer = _FakeVisionGarmentAnalyzer(lambda _m, _u, _b: GarmentProfile())
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    # Unsupported MIME format rejected synchronously before queuing
    r_mime = client.post(
        "/v1/analysis/garment",
        files={"image": ("anim.gif", b"GIF89a1234567890", "image/gif")},
    )
    assert r_mime.status_code == 422

    # Invalid / corrupted bytes claiming to be image/jpeg fail validation BEFORE calling VLM
    r_bad = client.post(
        "/v1/analysis/garment",
        files={"image": ("corrupt.jpg", b"\xff\xd8\xffbroken-payload", "image/jpeg")},
    )
    assert r_bad.status_code == 202
    bad_run = client.get(f"/v1/analysis/runs/{r_bad.json()['run_id']}").json()
    assert bad_run["status"] == "failed"
    assert bad_run["error"]["details"]["reason"] == "invalid_image"

    # Oversized dimensions (4200px wide PNG) fail safety bounds BEFORE calling VLM
    wide_png = _make_image_bytes(fmt="PNG", size=(4200, 120))
    r_wide = client.post(
        "/v1/analysis/garment",
        files={"image": ("wide.png", wide_png, "image/png")},
    )
    assert r_wide.status_code == 202
    wide_run = client.get(f"/v1/analysis/runs/{r_wide.json()['run_id']}").json()
    assert wide_run["status"] == "failed"
    assert wide_run["error"]["details"]["reason"] == "oversized_image"

    # VLM was NEVER invoked on any invalid/oversized payload
    assert analyzer.calls == []


def test_ai_timeout_and_unavailable_model_transition_run_to_failed(api_env):
    client: TestClient = api_env["client"]

    def raise_timeout(_m, _u, _b):
        raise GarmentAnalysisError("analyzer_timeout")

    api_env["monkeypatch"].setattr(
        analysis_router,
        "OllamaVisionGarmentAdapter",
        lambda: _FakeVisionGarmentAnalyzer(raise_timeout),
    )

    img_bytes = _make_image_bytes(fmt="JPEG", size=(300, 300))
    run1 = client.post(
        "/v1/analysis/garment",
        files={"image": ("a.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]
    poll1 = client.get(f"/v1/analysis/runs/{run1}").json()
    assert poll1["status"] == "failed"
    assert poll1["error"]["code"] == "PROCESSING_FAILURE"
    assert poll1["error"]["details"]["reason"] == "analyzer_timeout"

    def raise_unavailable(_m, _u, _b):
        raise GarmentAnalysisError("analyzer_unavailable")

    api_env["monkeypatch"].setattr(
        analysis_router,
        "OllamaVisionGarmentAdapter",
        lambda: _FakeVisionGarmentAnalyzer(raise_unavailable),
    )
    run2 = client.post(
        "/v1/analysis/garment",
        files={"image": ("b.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]
    poll2 = client.get(f"/v1/analysis/runs/{run2}").json()
    assert poll2["status"] == "failed"
    assert poll2["error"]["code"] == "PROCESSING_FAILURE"
    assert poll2["error"]["details"]["reason"] == "analyzer_unavailable"


def test_partial_extraction_failure_and_partial_save_retry(api_env):
    client: TestClient = api_env["client"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    # Candidate 1 has valid bbox, Candidate 2 has invalid/degenerate bbox -> partial extraction
    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="linen blazer",
            color="navy",
            confidence=0.9,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_good",
                    "category": "tops",
                    "subcategory": "linen blazer",
                    "color": "navy",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "linen",
                    "season_tags": ["spring"],
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.15, "y1": 0.1, "x2": 0.85, "y2": 0.6, "scale": "normalized_0_1"},
                },
                {
                    "id": "cand_no_box",
                    "category": "accessories",
                    "subcategory": "leather belt",
                    "color": "black",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "leather",
                    "season_tags": [],
                    "confidence": 0.72,
                    "bounding_box": {"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.6, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(500, 600), with_two_garments=True)
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("partial.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    poll = client.get(f"/v1/analysis/runs/{run_id}").json()
    cands = {c["id"]: c for c in poll["result"]["candidates"]}
    assert cands["cand_good"]["has_crop"] is True
    assert cands["cand_no_box"]["has_crop"] is False
    assert cands["cand_no_box"]["extraction_method"] == "vlm_attribute_only"
    assert any(
        f["candidate_id"] == "cand_no_box" and f["reason"] == "crop_extraction_failed"
        for f in poll["result"]["partial_failures"]
    )

    # Partial save failure + retry: cand_good succeeds, bogus cand_missing fails
    save_partial = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        json={
            "items": [
                {
                    "candidateId": "cand_good",
                    "name": "Linen Blazer",
                    "category": "outerwear",
                    "color": "Navy",
                    "material": "Linen",
                    "isFavorite": False,
                },
                {
                    "candidateId": "cand_missing",
                    "name": "Ghost Item",
                    "category": "tops",
                    "color": "Black",
                    "isFavorite": False,
                },
            ]
        },
    )
    assert save_partial.status_code == 200
    body = save_partial.json()
    assert len(body["savedItems"]) == 1
    assert len(body["failedItems"]) == 1
    assert body["failedItems"][0]["candidateId"] == "cand_missing"

    # Retry saving cand_good + cand_no_box: cand_good must NOT duplicate!
    retry = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        json={
            "items": [
                {
                    "candidateId": "cand_good",
                    "name": "Linen Blazer",
                    "category": "outerwear",
                    "color": "Navy",
                    "material": "Linen",
                    "isFavorite": False,
                },
                {
                    "candidateId": "cand_no_box",
                    "name": "Leather Belt",
                    "category": "accessories",
                    "color": "Black",
                    "material": "Leather",
                    "isFavorite": False,
                },
            ]
        },
    )
    assert retry.status_code == 200
    assert len(retry.json()["savedItems"]) == 2
    assert retry.json()["failedItems"] == []

    with SessionLocal() as session:
        rows = session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all()
        assert len(rows) == 2

    # Storage upload failure marks only the failing crop in persist_extraction_crops
    class _FailingStorage(FakeStorageAdapter):
        async def put_object(self, **kwargs):
            raise StorageError("simulated disk full")

    res = asyncio.run(
        persist_extraction_crops(
            _FailingStorage(),
            {"candidates": [{"id": "c1", "has_crop": True, "crop_key": "k"}]},
            [("c1", "k", b"RIFF1234WEBP", {})],
        )
    )
    assert res["candidates"][0]["has_crop"] is False
    assert res["candidates"][0]["crop_error"] == "storage_upload_failed"


def test_cross_user_isolation_across_run_crop_save_and_cleanup(api_env):
    client: TestClient = api_env["client"]
    active_user = api_env["active_user"]
    user_a = api_env["user_a"]
    user_b = api_env["user_b"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="knit polo",
            color="olive",
            confidence=0.9,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_1",
                    "category": "tops",
                    "subcategory": "knit polo",
                    "color": "olive",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "cotton",
                    "season_tags": [],
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.2, "y1": 0.15, "x2": 0.8, "y2": 0.55, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    active_user["id"] = user_a
    img_bytes = _make_image_bytes(fmt="JPEG", size=(400, 500))
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("polo.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    # Switch active caller to User B -> every OW-1 endpoint must return 404
    active_user["id"] = user_b
    assert client.get(f"/v1/analysis/runs/{run_id}").status_code == 404
    assert client.get(f"/v1/analysis/runs/{run_id}/candidates/cand_1/image").status_code == 404
    assert (
        client.post(
            f"/v1/analysis/garment/runs/{run_id}/save",
            json={
                "items": [
                    {"candidateId": "cand_1", "name": "Stolen Polo", "category": "tops", "color": "Olive"}
                ]
            },
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/analysis/garment/runs/{run_id}/assets").status_code == 404

    with SessionLocal() as session:
        assert session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_b)).scalars().all() == []


def test_duplicate_submission_and_save_idempotency_conflict_and_replay(api_env):
    client: TestClient = api_env["client"]
    user_a = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="outerwear",
            subcategory="denim jacket",
            color="indigo",
            confidence=0.94,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_1",
                    "category": "outerwear",
                    "subcategory": "denim jacket",
                    "color": "indigo",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "denim",
                    "season_tags": [],
                    "confidence": 0.94,
                    "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.85, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_a = _make_image_bytes(fmt="JPEG", size=(400, 500), color=(30, 50, 120))
    img_b = _make_image_bytes(fmt="JPEG", size=(400, 500), color=(180, 40, 40))

    r1 = client.post(
        "/v1/analysis/garment",
        headers={"Idempotency-Key": "upload-key-1"},
        files={"image": ("jacket.jpg", img_a, "image/jpeg")},
    )
    r2 = client.post(
        "/v1/analysis/garment",
        headers={"Idempotency-Key": "upload-key-1"},
        files={"image": ("jacket.jpg", img_a, "image/jpeg")},
    )
    assert r1.status_code == 202 and r2.status_code == 202
    run_id = r1.json()["run_id"]
    assert r2.json()["run_id"] == run_id
    assert len(analyzer.calls) == 1  # Inference executed once despite duplicate upload

    r_conflict = client.post(
        "/v1/analysis/garment",
        headers={"Idempotency-Key": "upload-key-1"},
        files={"image": ("different.jpg", img_b, "image/jpeg")},
    )
    assert r_conflict.status_code == 409

    # Save replay & conflict
    payload1 = {
        "items": [
            {
                "candidateId": "cand_1",
                "name": "Denim Jacket",
                "category": "outerwear",
                "color": "Indigo",
                "material": "Denim",
                "isFavorite": False,
            }
        ]
    }
    s1 = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "save-key-1"},
        json=payload1,
    )
    s2 = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "save-key-1"},
        json=payload1,
    )
    assert s1.status_code == 200 and s2.status_code == 200
    assert s1.json()["savedItems"][0]["id"] == s2.json()["savedItems"][0]["id"]

    # Different payload under same Idempotency-Key -> 409
    s_conflict = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "save-key-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Changed Name",
                    "category": "outerwear",
                    "color": "Indigo",
                    "material": "Denim",
                    "isFavorite": True,
                }
            ]
        },
    )
    assert s_conflict.status_code == 409

    with SessionLocal() as session:
        rows = session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all()
        assert len(rows) == 1


def test_cleanup_on_cancel_and_expired_runs(api_env):
    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="sweater",
            color="grey",
            confidence=0.9,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_1",
                    "category": "tops",
                    "subcategory": "sweater",
                    "color": "grey",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "wool",
                    "season_tags": [],
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.15, "y1": 0.15, "x2": 0.85, "y2": 0.65, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(400, 400))
    run_cancel = client.post(
        "/v1/analysis/garment",
        files={"image": ("cancel.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]
    assert any(f"users/{user_a}/extractions/{run_cancel}/" in k for k in storage.get_stored_keys())

    # Cancel / discard -> explicit DELETE cleanup
    d1 = client.delete(f"/v1/analysis/garment/runs/{run_cancel}/assets")
    assert d1.status_code == 200
    assert d1.json()["deletedCount"] == 1
    assert d1.json()["alreadyCleaned"] is False
    assert not any(f"users/{user_a}/extractions/{run_cancel}/" in k for k in storage.get_stored_keys())

    # Idempotent repeat delete
    d2 = client.delete(f"/v1/analysis/garment/runs/{run_cancel}/assets")
    assert d2.status_code == 200
    assert d2.json()["deletedCount"] == 0
    assert d2.json()["alreadyCleaned"] is True

    # Expiration job test: create run, age its created_at by 48 hours in DB, run sweeper
    run_old = client.post(
        "/v1/analysis/garment",
        files={"image": ("old.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]
    run_fresh = client.post(
        "/v1/analysis/garment",
        files={"image": ("fresh.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    with SessionLocal() as session:
        row = session.get(AnalysisRuns, UUID(run_old))
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
        session.commit()

    with SessionLocal() as session:
        purged = asyncio.run(cleanup_expired_extraction_assets(storage, session, older_than_hours=24))
    assert purged == 1
    assert not any(f"users/{user_a}/extractions/{run_old}/" in k for k in storage.get_stored_keys())
    assert any(f"users/{user_a}/extractions/{run_fresh}/" in k for k in storage.get_stored_keys())


def _ollama_has_vision_model(model_name: str = "qwen3-vl:4b-instruct") -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", [])]
        return any(
            name == model_name or name == f"{model_name}:latest"
            for name in models
        )
    except Exception:
        return False


def test_live_local_ollama_qwen3_vl_multi_garment_e2e(api_env):
    """Real runtime verification using local Ollama `qwen3-vl:4b-instruct` + Pillow crops + PG save."""
    if os.getenv("FANSIVIBE_SKIP_LIVE_OLLAMA") == "1" or not _ollama_has_vision_model():
        pytest.skip("Local Ollama qwen3-vl:4b-instruct not reachable")

    from app.config.settings import get_settings

    api_env["monkeypatch"].setenv("FANSIVIBE_VISION_MODEL", "qwen3-vl:4b-instruct")
    api_env["monkeypatch"].setenv("FANSIVIBE_VISION_TIMEOUT_S", "60.0")
    api_env["monkeypatch"].delenv("FANSIVIBE_DISABLE_VISION", raising=False)
    get_settings.cache_clear()

    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    # Do NOT monkeypatch OllamaVisionGarmentAdapter: hit the real local model
    img_bytes = _make_image_bytes(fmt="JPEG", size=(600, 800), with_two_garments=True)
    submit = client.post(
        "/v1/analysis/garment",
        files={"image": ("live_outfit.jpg", img_bytes, "image/jpeg")},
    )
    assert submit.status_code == 202
    run_id = submit.json()["run_id"]

    poll = client.get(f"/v1/analysis/runs/{run_id}")
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "completed", f"Live Ollama extraction failed: {body}"
    result = body["result"]
    assert result["has_segmentation_mask"] is False
    assert result["mask"] is None
    candidates = result["candidates"]
    assert len(candidates) >= 1

    cropped_cands = [c for c in candidates if c.get("has_crop") is True]
    assert len(cropped_cands) >= 1
    first = cropped_cands[0]
    crop_resp = client.get(first["crop_url"])
    assert crop_resp.status_code == 200
    assert crop_resp.content[:4] == b"RIFF"

    # Save ONLY the first detected candidate and assert temp cleanup + canonical promotion
    save_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        json={
            "items": [
                {
                    "candidateId": first["id"],
                    "name": first.get("subcategory") or first.get("category") or "Extracted Item",
                    "category": first.get("category") or "tops",
                    "color": first.get("color") or "navy",
                    "material": first.get("material"),
                    "isFavorite": False,
                }
            ]
        },
    )
    assert save_resp.status_code == 200
    save_json = save_resp.json()
    assert len(save_json["savedItems"]) == 1
    saved_item = save_json["savedItems"][0]
    assert saved_item["candidateId"] == first["id"]
    assert saved_item["extractionConfidence"] == pytest.approx(first["confidence"])
    assert save_json["cleanedUpAssets"] is True
    assert not any(f"users/{user_a}/extractions/{run_id}/" in k for k in storage.get_stored_keys())

    with SessionLocal() as session:
        rows = session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == UUID(saved_item["id"])

    # Reopen wardrobe via API and verify persistence
    wardrobe_resp = client.get("/v1/wardrobe/items")
    assert wardrobe_resp.status_code == 200
    wardrobe_items = wardrobe_resp.json()["items"]
    assert len(wardrobe_items) == 1
    assert wardrobe_items[0]["id"] == saved_item["id"]


def test_partial_save_a_fails_b_c_succeed_preserves_identity_crops_and_idempotent_retry(api_env):
    """P5.1A: A fails, B succeeds, C succeeds -> B & C keep exact crops/metadata, A stays retryable."""
    import hashlib

    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="jacket",
            color="black",
            confidence=0.88,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_a",
                    "category": "tops",
                    "subcategory": "Candidate A Shirt",
                    "color": "white",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "cotton",
                    "fit": "Regular",
                    "confidence": 0.71,
                    "bounding_box": {"x1": 0.05, "y1": 0.05, "x2": 0.35, "y2": 0.45, "scale": "normalized_0_1"},
                },
                {
                    "id": "cand_b",
                    "category": "outerwear",
                    "subcategory": "Candidate B Blazer",
                    "color": "navy",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "linen",
                    "fit": "Tailored",
                    "confidence": 0.86,
                    "bounding_box": {"x1": 0.38, "y1": 0.08, "x2": 0.68, "y2": 0.60, "scale": "normalized_0_1"},
                },
                {
                    "id": "cand_c",
                    "category": "bottoms",
                    "subcategory": "Candidate C Jeans",
                    "color": "indigo",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "denim",
                    "fit": "Slim",
                    "confidence": 0.94,
                    "bounding_box": {"x1": 0.25, "y1": 0.50, "x2": 0.80, "y2": 0.95, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    # Create an image with distinct colors in each candidate's region so every crop hash is unique
    from PIL import ImageDraw

    img = Image.new("RGB", (600, 800), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 40, 210, 360], fill=(245, 245, 245))   # cand_a white
    draw.rectangle([228, 64, 408, 480], fill=(20, 40, 95))    # cand_b navy
    draw.rectangle([150, 400, 480, 760], fill=(60, 85, 145))  # cand_c indigo
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("three_items.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    key_a = f"users/{user_a}/extractions/{run_id}/candidates/cand_a.webp"
    key_b = f"users/{user_a}/extractions/{run_id}/candidates/cand_b.webp"
    key_c = f"users/{user_a}/extractions/{run_id}/candidates/cand_c.webp"
    crop_a = asyncio.run(storage.read_object(key_a))
    crop_b = asyncio.run(storage.read_object(key_b))
    crop_c = asyncio.run(storage.read_object(key_c))
    sha_a = hashlib.sha256(crop_a).hexdigest()
    sha_b = hashlib.sha256(crop_b).hexdigest()
    sha_c = hashlib.sha256(crop_c).hexdigest()
    assert len({sha_a, sha_b, sha_c}) == 3

    # Step 1: Save [A, B, C] where A fails (invalid category) while B and C succeed.
    first_save = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p51a-batch-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_a",
                    "name": "Candidate A Shirt",
                    "category": "invalid_category_a",
                    "color": "white",
                    "material": "cotton",
                    "fit": "Regular",
                    "extractionConfidence": 0.71,
                    "isFavorite": False,
                },
                {
                    "candidateId": "cand_b",
                    "name": "Candidate B Blazer",
                    "category": "outerwear",
                    "color": "navy",
                    "material": "linen",
                    "fit": "Tailored",
                    "extractionConfidence": 0.86,
                    "isFavorite": False,
                },
                {
                    "candidateId": "cand_c",
                    "name": "Candidate C Jeans",
                    "category": "bottoms",
                    "color": "indigo",
                    "material": "denim",
                    "fit": "Slim",
                    "extractionConfidence": 0.94,
                    "isFavorite": True,
                },
            ]
        },
    )
    assert first_save.status_code == 200
    body1 = first_save.json()
    assert body1["cleanedUpAssets"] is False
    assert [f["candidateId"] for f in body1["failedItems"]] == ["cand_a"]
    assert [item["candidateId"] for item in body1["savedItems"]] == ["cand_b", "cand_c"]

    saved_by_cid = {item["candidateId"]: item for item in body1["savedItems"]}
    item_b = saved_by_cid["cand_b"]
    item_c = saved_by_cid["cand_c"]

    # B points strictly to B's crop and metadata; C points strictly to C's crop and metadata
    assert item_b["name"] == "Candidate B Blazer"
    assert item_b["category"] == "outerwear"
    assert item_b["imageRef"]["candidateId"] == "cand_b"
    assert item_b["imageRef"]["sourceRunId"] == run_id
    assert item_b["imageRef"]["contentHash"] == sha_b
    assert item_b["extractionConfidence"] == pytest.approx(0.86)
    assert item_b["imageRef"]["extractionConfidence"] == pytest.approx(0.86)
    assert item_b["fitConfidence"] is None
    assert asyncio.run(storage.read_object(item_b["imageRef"]["objectKey"])) == crop_b

    assert item_c["name"] == "Candidate C Jeans"
    assert item_c["category"] == "bottoms"
    assert item_c["imageRef"]["candidateId"] == "cand_c"
    assert item_c["imageRef"]["sourceRunId"] == run_id
    assert item_c["imageRef"]["contentHash"] == sha_c
    assert item_c["extractionConfidence"] == pytest.approx(0.94)
    assert item_c["imageRef"]["extractionConfidence"] == pytest.approx(0.94)
    assert item_c["fitConfidence"] is None
    assert asyncio.run(storage.read_object(item_c["imageRef"]["objectKey"])) == crop_c

    # B & C temp crops cleaned up; A's temp crop preserved so A remains retryable
    assert not storage.object_exists_sync(key_b)
    assert not storage.object_exists_sync(key_c)
    assert storage.object_exists_sync(key_a)

    # Step 2: Retry with fixed A alongside B and C (idempotent retry must not duplicate or overwrite B/C)
    retry_save = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p51a-batch-2"},
        json={
            "items": [
                {
                    "candidateId": "cand_a",
                    "name": "Candidate A Shirt",
                    "category": "tops",
                    "color": "white",
                    "material": "cotton",
                    "fit": "Regular",
                    "extractionConfidence": 0.71,
                    "isFavorite": False,
                },
                {
                    "candidateId": "cand_b",
                    "name": "Attempted Overwrite B",
                    "category": "outerwear",
                    "color": "black",
                    "material": "wool",
                    "extractionConfidence": 0.11,
                    "isFavorite": True,
                },
                {
                    "candidateId": "cand_c",
                    "name": "Candidate C Jeans",
                    "category": "bottoms",
                    "color": "indigo",
                    "material": "denim",
                    "extractionConfidence": 0.94,
                    "isFavorite": True,
                },
            ]
        },
    )
    assert retry_save.status_code == 200
    body2 = retry_save.json()
    assert body2["failedItems"] == []
    assert body2["cleanedUpAssets"] is True
    assert [item["candidateId"] for item in body2["savedItems"]] == ["cand_a", "cand_b", "cand_c"]

    retried_by_cid = {item["candidateId"]: item for item in body2["savedItems"]}
    assert retried_by_cid["cand_a"]["name"] == "Candidate A Shirt"
    assert retried_by_cid["cand_a"]["imageRef"]["contentHash"] == sha_a
    assert retried_by_cid["cand_a"]["extractionConfidence"] == pytest.approx(0.71)
    assert retried_by_cid["cand_a"]["fitConfidence"] is None
    assert asyncio.run(storage.read_object(retried_by_cid["cand_a"]["imageRef"]["objectKey"])) == crop_a

    # B & C were NOT duplicated and NOT overwritten by retry
    assert retried_by_cid["cand_b"]["id"] == item_b["id"]
    assert retried_by_cid["cand_b"]["name"] == "Candidate B Blazer"
    assert retried_by_cid["cand_b"]["imageRef"]["contentHash"] == sha_b
    assert retried_by_cid["cand_b"]["extractionConfidence"] == pytest.approx(0.86)
    assert retried_by_cid["cand_c"]["id"] == item_c["id"]
    assert retried_by_cid["cand_c"]["imageRef"]["contentHash"] == sha_c

    assert not storage.object_exists_sync(key_a)
    with SessionLocal() as session:
        rows = session.execute(select(WardrobeItems).where(WardrobeItems.user_id == user_a)).scalars().all()
        assert len(rows) == 3
        for row in rows:
            assert row.fit_confidence is None
            assert isinstance(row.image_ref, dict)
            assert row.image_ref["sourceRunId"] == run_id
            assert row.image_ref["candidateId"] in {"cand_a", "cand_b", "cand_c"}


def test_save_confidence_semantics_never_mixes_extraction_and_fit_confidence(api_env):
    """P5.1A: extraction confidence is preserved in extraction metadata and never copied to fitConfidence."""
    client: TestClient = api_env["client"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="crewneck",
            color="navy",
            confidence=0.83,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_ext_only",
                    "category": "tops",
                    "subcategory": "crewneck",
                    "color": "navy",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "cotton",
                    "fit": "Regular",
                    "confidence": 0.83,
                    "bounding_box": {"x1": 0.2, "y1": 0.1, "x2": 0.8, "y2": 0.5, "scale": "normalized_0_1"},
                },
                {
                    "id": "cand_both",
                    "category": "bottoms",
                    "subcategory": "trousers",
                    "color": "charcoal",
                    "secondary_colors": [],
                    "pattern": "solid",
                    "material": "wool",
                    "fit": "Tailored",
                    "confidence": 0.91,
                    "bounding_box": {"x1": 0.2, "y1": 0.5, "x2": 0.8, "y2": 0.9, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(400, 500), with_two_garments=True)
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("conf.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        json={
            "items": [
                {
                    "candidateId": "cand_ext_only",
                    "name": "Navy Crewneck",
                    "category": "tops",
                    "color": "navy",
                    "material": "cotton",
                    "fit": "Regular",
                    # Omitting extractionConfidence tests fallback to run candidate confidence;
                    # omitting fitConfidence must leave fitConfidence=None (never fabricated).
                },
                {
                    "candidateId": "cand_both",
                    "name": "Charcoal Trousers",
                    "category": "bottoms",
                    "color": "charcoal",
                    "material": "wool",
                    "fit": "Tailored",
                    "extractionConfidence": 0.91,
                    "fitConfidence": 0.65,
                },
            ]
        },
    )
    assert resp.status_code == 200
    items_by_cid = {it["candidateId"]: it for it in resp.json()["savedItems"]}

    assert items_by_cid["cand_ext_only"]["extractionConfidence"] == pytest.approx(0.83)
    assert items_by_cid["cand_ext_only"]["imageRef"]["extractionConfidence"] == pytest.approx(0.83)
    assert items_by_cid["cand_ext_only"]["fitConfidence"] is None

    assert items_by_cid["cand_both"]["extractionConfidence"] == pytest.approx(0.91)
    assert items_by_cid["cand_both"]["imageRef"]["extractionConfidence"] == pytest.approx(0.91)
    assert items_by_cid["cand_both"]["fitConfidence"] == pytest.approx(0.65)

    with SessionLocal() as session:
        rows = {
            r.name: r
            for r in session.execute(
                select(WardrobeItems).where(WardrobeItems.user_id == user_a)
            ).scalars().all()
        }
        assert rows["Navy Crewneck"].fit_confidence is None
        assert rows["Navy Crewneck"].image_ref["extractionConfidence"] == pytest.approx(0.83)
        assert rows["Charcoal Trousers"].fit_confidence == pytest.approx(0.65)
        assert rows["Charcoal Trousers"].image_ref["extractionConfidence"] == pytest.approx(0.91)


# ---------------------------------------------------------------------------
# P5.1C — Extraction Lifecycle, Cleanup Pagination, Bounded Idempotency & Erasure
# ---------------------------------------------------------------------------


def _seed_expired_garment_run(
    session,
    storage: FakeStorageAdapter,
    *,
    user_id: UUID,
    age_hours: int = 48,
    num_crops: int = 1,
) -> tuple[UUID, list[str]]:
    run_id = uuid4()
    created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    keys: list[str] = []
    candidates: list[dict] = []
    for idx in range(num_crops):
        cid = f"cand_{idx}"
        key = f"users/{user_id}/extractions/{run_id}/{cid}.webp"
        keys.append(key)
        asyncio.run(storage.put_object(key=key, data=b"RIFFxxxxWEBP", content_type="image/webp"))
        candidates.append({"id": cid, "crop_key": key, "has_crop": True})

    row = AnalysisRuns(
        id=run_id,
        user_id=user_id,
        run_type="garment",
        status="completed",
        engine_version="p5.1-test",
        result={"candidates": candidates},
        created_at=created_at,
        completed_at=created_at,
    )
    session.add(row)
    return run_id, keys


def test_p5_1c_cleanup_more_than_200_expired_runs(api_env):
    """More than 200 expired runs are eventually processed across bounded batches."""
    from app.application.garment_extraction import cleanup_expired_extraction_assets_detailed

    SessionLocal = api_env["db"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]

    expired_keys: list[str] = []
    with SessionLocal() as session:
        for _ in range(215):
            _, keys = _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=48)
            expired_keys.extend(keys)
        _, active_keys = _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=1)
        session.commit()

    with SessionLocal() as session:
        s1 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(
                storage, session, older_than_hours=24, batch_limit=200
            )
        )
    assert s1.runs_claimed == 200
    assert s1.runs_cleaned == 200
    assert s1.assets_deleted == 200

    with SessionLocal() as session:
        s2 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(
                storage, session, older_than_hours=24, batch_limit=200
            )
        )
    assert s2.runs_claimed == 15
    assert s2.runs_cleaned == 15
    assert s2.assets_deleted == 15

    with SessionLocal() as session:
        s3 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(
                storage, session, older_than_hours=24, batch_limit=200
            )
        )
    assert s3.runs_claimed == 0
    assert s3.assets_deleted == 0

    remaining = storage.get_stored_keys()
    for k in expired_keys:
        assert k not in remaining
    for k in active_keys:
        assert k in remaining


def test_p5_1c_cleanup_repeated_calls_do_not_reprocess_cleaned_runs(api_env):
    """Successfully cleaned runs are marked cleaned and never reprocessed on repeat calls."""
    from app.application.garment_extraction import cleanup_expired_extraction_assets_detailed

    SessionLocal = api_env["db"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]

    with SessionLocal() as session:
        for _ in range(5):
            _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=48)
        session.commit()

    delete_calls = 0
    orig_delete = storage.delete_object

    async def counting_delete(key: str) -> bool:
        nonlocal delete_calls
        delete_calls += 1
        return await orig_delete(key)

    storage.delete_object = counting_delete  # type: ignore[method-assign]

    with SessionLocal() as session:
        s1 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(storage, session, older_than_hours=24)
        )
    assert s1.runs_cleaned == 5
    assert delete_calls == 5

    with SessionLocal() as session:
        s2 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(storage, session, older_than_hours=24)
        )
    assert s2.runs_claimed == 0
    assert s2.runs_cleaned == 0
    assert delete_calls == 5  # Zero storage calls for already-cleaned runs


def test_p5_1c_cleanup_partial_object_deletion_failure_remains_retryable(api_env):
    """One failing object does not block others; failed run remains retryable and succeeds later."""
    from app.application.garment_extraction import cleanup_expired_extraction_assets_detailed

    SessionLocal = api_env["db"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]

    with SessionLocal() as session:
        run_fail, fail_keys = _seed_expired_garment_run(
            session, storage, user_id=user_a, age_hours=48, num_crops=2
        )
        run_ok, ok_keys = _seed_expired_garment_run(
            session, storage, user_id=user_a, age_hours=47, num_crops=1
        )
        session.commit()

    flaky_key = fail_keys[0]
    should_fail = True
    orig_delete = storage.delete_object

    async def flaky_delete(key: str) -> bool:
        if should_fail and key == flaky_key:
            raise StorageError("transient R2 error", key=key)
        return await orig_delete(key)

    storage.delete_object = flaky_delete  # type: ignore[method-assign]

    with SessionLocal() as session:
        s1 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(storage, session, older_than_hours=24)
        )
    assert s1.runs_claimed == 2
    assert s1.runs_cleaned == 1
    assert s1.runs_failed == 1
    assert s1.assets_deleted == 2  # fail_keys[1] + ok_keys[0]
    assert s1.storage_errors == 1
    assert flaky_key in storage.get_stored_keys()
    assert fail_keys[1] not in storage.get_stored_keys()
    assert ok_keys[0] not in storage.get_stored_keys()

    # Clear transient error and retry: failed run is retried, ok run is not.
    should_fail = False
    with SessionLocal() as session:
        s2 = asyncio.run(
            cleanup_expired_extraction_assets_detailed(storage, session, older_than_hours=24)
        )
    assert s2.runs_claimed == 1
    assert s2.runs_cleaned == 1
    assert s2.runs_failed == 0
    assert s2.assets_deleted == 1
    assert flaky_key not in storage.get_stored_keys()

    with SessionLocal() as session:
        row = session.get(AnalysisRuns, run_fail)
        assert row.result["assets_cleanup"]["status"] == "cleaned"


def test_p5_1c_cleanup_concurrent_workers_disjoint_and_safe(api_env):
    """Concurrent cleanup workers claim disjoint batches and never delete active assets."""
    from app.application.garment_extraction import cleanup_expired_extraction_assets_detailed

    SessionLocal = api_env["db"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]

    with SessionLocal() as session:
        for _ in range(12):
            _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=48)
        _, active_keys = _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=2)
        session.commit()

    def _run_worker():
        with SessionLocal() as s:
            return asyncio.run(
                cleanup_expired_extraction_assets_detailed(
                    storage, s, older_than_hours=24, batch_limit=6
                )
            )

    async def _run_both():
        return await asyncio.gather(
            asyncio.to_thread(_run_worker),
            asyncio.to_thread(_run_worker),
        )

    r1, r2 = asyncio.run(_run_both())
    assert r1.runs_claimed + r2.runs_claimed == 12
    assert r1.runs_cleaned + r2.runs_cleaned == 12
    assert r1.assets_deleted + r2.assets_deleted == 12
    for k in active_keys:
        assert k in storage.get_stored_keys()


def test_p5_1c_cleanup_resumes_after_process_restart_expired_lease(api_env):
    """A run left in 'cleaning' with an expired lease (crashed worker) is reclaimed on restart."""
    from app.application.garment_extraction import cleanup_expired_extraction_assets_detailed

    SessionLocal = api_env["db"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]

    with SessionLocal() as session:
        run_id, keys = _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=48)
        row = session.get(AnalysisRuns, run_id)
        updated = dict(row.result)
        updated["assets_cleanup"] = {
            "status": "cleaning",
            "claim_token": "crashed-worker-token",
            "lease_expires_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            "attempts": 1,
        }
        row.result = updated
        session.commit()

    with SessionLocal() as session:
        summary = asyncio.run(
            cleanup_expired_extraction_assets_detailed(storage, session, older_than_hours=24)
        )
    assert summary.runs_claimed == 1
    assert summary.runs_cleaned == 1
    assert summary.assets_deleted == 1
    assert keys[0] not in storage.get_stored_keys()
    with SessionLocal() as session:
        row = session.get(AnalysisRuns, run_id)
        assert row.result["assets_cleanup"]["status"] == "cleaned"
        assert row.result["assets_cleanup"]["attempts"] == 2


def test_p5_1c_bounded_save_batch_cache_eviction_ttl_and_in_progress_protection():
    """_BoundedSaveBatchCache bounds entries via LRU, expires via TTL, and protects in-progress keys."""
    from app.application.garment_extraction import _BoundedSaveBatchCache

    cache = _BoundedSaveBatchCache(max_entries=2, ttl_seconds=60.0)
    u = uuid4()
    r = uuid4()
    k1 = (u, r, "k1")
    k2 = (u, r, "k2")
    k3 = (u, r, "k3")

    cache.mark_in_progress(k1)
    cache[k1] = {"fingerprint": "f1", "response": {"ok": 1}}
    cache[k2] = {"fingerprint": "f2", "response": {"ok": 2}}
    # k1 is in_progress, so inserting k3 must evict k2 instead of k1.
    cache[k3] = {"fingerprint": "f3", "response": {"ok": 3}}
    assert k1 in cache
    assert k2 not in cache
    assert k3 in cache

    # Once k1 finishes, inserting k2 evicts k1 (oldest).
    cache.clear_in_progress(k1)
    cache[k2] = {"fingerprint": "f2", "response": {"ok": 2}}
    assert k1 not in cache
    assert k2 in cache
    assert k3 in cache

    # TTL expiration
    ttl_cache = _BoundedSaveBatchCache(max_entries=10, ttl_seconds=0.05)
    ttl_cache[k1] = {"fingerprint": "f1", "response": {"ok": 1}}
    assert k1 in ttl_cache
    import time as _time

    _time.sleep(0.08)
    assert ttl_cache.get(k1) is None
    assert len(ttl_cache) == 0


def test_p5_1c_concurrent_duplicate_save_requests_no_duplicates(api_env):
    """Concurrent duplicate save requests with the same Idempotency-Key never duplicate wardrobe items."""
    from app.application.garment_extraction import SaveExtractedGarments
    from app.infrastructure.db.repositories import (
        AnalysisRunRepositorySQL,
        LearningSignalRepositorySQL,
        WardrobeItemRepositorySQL,
    )

    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="outerwear",
            subcategory="jacket",
            color="navy",
            material="cotton",
            confidence=0.9,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_dup",
                    "category": "outerwear",
                    "subcategory": "jacket",
                    "color": "navy",
                    "material": "cotton",
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(300, 400))
    run_id = UUID(
        client.post(
            "/v1/analysis/garment",
            files={"image": ("dup.jpg", img_bytes, "image/jpeg")},
        ).json()["run_id"]
    )

    items_payload = [
        {
            "candidateId": "cand_dup",
            "name": "Navy Jacket",
            "category": "outerwear",
            "color": "navy",
            "material": "cotton",
            "fit": "Regular",
        }
    ]

    def _do_save(key: str):
        with SessionLocal() as s:
            uc = SaveExtractedGarments(
                runs=AnalysisRunRepositorySQL(s),
                wardrobe=WardrobeItemRepositorySQL(s),
                storage=storage,
                signals=LearningSignalRepositorySQL(s),
                db=s,
            )
            return asyncio.run(
                uc.execute(
                    user_id=user_a,
                    run_id=run_id,
                    items=items_payload,
                    idempotency_key=key,
                )
            )

    async def _concurrent():
        return await asyncio.gather(
            asyncio.to_thread(_do_save, "concurrent-save-key-1"),
            asyncio.to_thread(_do_save, "concurrent-save-key-1"),
        )

    res1, res2 = asyncio.run(_concurrent())
    assert len(res1["saved_records"]) == 1
    assert len(res2["saved_records"]) == 1
    assert res1["saved_records"][0].id == res2["saved_records"][0].id

    with SessionLocal() as session:
        rows = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_a)
        ).scalars().all()
        assert len(rows) == 1

    # Conflicting payload with same key still returns 409 conflict
    conflict_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "concurrent-save-key-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_dup",
                    "name": "Different Name",
                    "category": "outerwear",
                    "color": "navy",
                }
            ]
        },
    )
    assert conflict_resp.status_code == 409


def test_p5_1c_retry_after_partial_save_with_same_key_preserves_saved(api_env):
    """Retrying with the same Idempotency-Key after a partial save retries only failed items."""
    client: TestClient = api_env["client"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="shirt",
            color="navy",
            material="cotton",
            confidence=0.88,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_fail_first",
                    "category": "tops",
                    "subcategory": "shirt",
                    "color": "navy",
                    "confidence": 0.85,
                    "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5, "scale": "normalized_0_1"},
                },
                {
                    "id": "cand_ok_first",
                    "category": "tops",
                    "subcategory": "shirt",
                    "color": "navy",
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.5, "y1": 0.1, "x2": 0.9, "y2": 0.5, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(400, 400), with_two_garments=True)
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("partial_retry.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    # First attempt: cand_fail_first has unsupported category -> partial failure
    r1 = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "retry-same-key"},
        json={
            "items": [
                {
                    "candidateId": "cand_fail_first",
                    "name": "Mystery Item",
                    "category": "hats_unsupported",
                    "color": "navy",
                },
                {
                    "candidateId": "cand_ok_first",
                    "name": "Navy Shirt",
                    "category": "tops",
                    "color": "navy",
                },
            ]
        },
    )
    assert r1.status_code == 200
    assert len(r1.json()["savedItems"]) == 1
    assert len(r1.json()["failedItems"]) == 1
    ok_id = r1.json()["savedItems"][0]["id"]

    # Retry with same key and fixed category -> both returned, cand_ok_first not duplicated
    r2 = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "retry-same-key"},
        json={
            "items": [
                {
                    "candidateId": "cand_fail_first",
                    "name": "Fixed Cap",
                    "category": "accessories",
                    "color": "navy",
                },
                {
                    "candidateId": "cand_ok_first",
                    "name": "Navy Shirt",
                    "category": "tops",
                    "color": "navy",
                },
            ]
        },
    )
    assert r2.status_code == 200
    assert r2.json()["failedItems"] == []
    assert r2.json()["cleanedUpAssets"] is True
    ids_by_cid = {it["candidateId"]: it["id"] for it in r2.json()["savedItems"]}
    assert ids_by_cid["cand_ok_first"] == ok_id
    assert len(ids_by_cid) == 2

    with SessionLocal() as session:
        rows = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_a)
        ).scalars().all()
        assert len(rows) == 2


def test_p5_1c_account_erasure_deletes_extraction_assets(api_env):
    """Account erasure deletes temporary extraction assets along with user data."""
    from app.application.auth import EraseAccount
    from app.infrastructure.db.repositories import AuthRepositorySQL

    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="shirt",
            color="navy",
            material="cotton",
            confidence=0.9,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_erase",
                    "category": "tops",
                    "subcategory": "shirt",
                    "color": "navy",
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(300, 400))
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("erase.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]
    assert any(f"users/{user_a}/extractions/{run_id}/" in k for k in storage.get_stored_keys())

    with SessionLocal() as session:
        eraser = EraseAccount(auth=AuthRepositorySQL(session), storage=storage)
        asyncio.run(eraser(user_id=user_a))

    assert not any(f"users/{user_a}/extractions/" in k for k in storage.get_stored_keys())
    with SessionLocal() as session:
        assert session.get(Users, user_a) is None


def test_p5_1c_cleanup_preserves_saved_wardrobe_media(api_env):
    """Expired extraction cleanup never deletes promoted canonical wardrobe media."""
    from app.application.garment_extraction import cleanup_expired_extraction_assets_detailed

    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    analyzer = _FakeVisionGarmentAnalyzer(
        lambda _m, _u, _b: GarmentProfile(
            category="tops",
            subcategory="shirt",
            color="navy",
            material="cotton",
            confidence=0.9,
            needs_review=False,
            candidates=(
                {
                    "id": "cand_keep",
                    "category": "tops",
                    "subcategory": "shirt",
                    "color": "navy",
                    "confidence": 0.9,
                    "bounding_box": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9, "scale": "normalized_0_1"},
                },
            ),
        )
    )
    api_env["monkeypatch"].setattr(analysis_router, "OllamaVisionGarmentAdapter", lambda: analyzer)

    img_bytes = _make_image_bytes(fmt="JPEG", size=(300, 400))
    run_id = client.post(
        "/v1/analysis/garment",
        files={"image": ("keep.jpg", img_bytes, "image/jpeg")},
    ).json()["run_id"]

    save_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        json={
            "items": [
                {
                    "candidateId": "cand_keep",
                    "name": "Saved Shirt",
                    "category": "tops",
                    "color": "navy",
                }
            ]
        },
    )
    assert save_resp.status_code == 200
    wardrobe_key = save_resp.json()["savedItems"][0]["imageRef"]["objectKey"]
    assert wardrobe_key.startswith(f"users/{user_a}/wardrobe/")
    assert wardrobe_key in storage.get_stored_keys()

    # Age the run past 24h and also plant a stray temp key under extractions/
    stray_key = f"users/{user_a}/extractions/{run_id}/stray.webp"
    asyncio.run(storage.put_object(key=stray_key, data=b"RIFFxxxxWEBP", content_type="image/webp"))
    with SessionLocal() as session:
        row = session.get(AnalysisRuns, UUID(run_id))
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
        updated = dict(row.result)
        updated.pop("assets_cleanup", None)
        row.result = updated
        session.commit()

    with SessionLocal() as session:
        summary = asyncio.run(
            cleanup_expired_extraction_assets_detailed(storage, session, older_than_hours=24)
        )
    assert summary.assets_deleted == 1
    assert stray_key not in storage.get_stored_keys()
    assert wardrobe_key in storage.get_stored_keys()


def test_p5_1c_maintenance_retention_cleanup_integrates_extraction_cleanup(api_env):
    """POST /v1/tryon/maintenance/retention-cleanup executes extraction cleanup in the same lifecycle."""
    from app.config.settings import get_settings

    api_env["monkeypatch"].setenv(
        "FANSIVIBE_OPERATOR_API_KEY", "test-operator-key-0123456789abcdef012345"
    )
    get_settings.cache_clear()

    client: TestClient = api_env["client"]
    storage: FakeStorageAdapter = api_env["storage"]
    user_a: UUID = api_env["user_a"]
    SessionLocal = api_env["db"]

    with SessionLocal() as session:
        _, expired_keys = _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=48)
        _, fresh_keys = _seed_expired_garment_run(session, storage, user_id=user_a, age_hours=1)
        session.commit()

    resp = client.post(
        "/v1/tryon/maintenance/retention-cleanup",
        headers={"X-Operator-Key": "test-operator-key-0123456789abcdef012345"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_runs_cleaned"] == 1
    assert body["extraction_assets_deleted"] == 1
    assert body["extraction_runs_failed"] == 0
    assert expired_keys[0] not in storage.get_stored_keys()
    assert fresh_keys[0] in storage.get_stored_keys()
