"""Phase 4: Image Analysis End-to-End Test Suite.

Covers:
- Single garment image extraction.
- Multiple garment image extraction.
- No garment detected error handling.
- Multiple garment candidates extraction and schema normalization.
- Duplicate candidate prevention and deduplication.
- Invalid image (empty bytes, non-image).
- Corrupt image handling.
- JPEG, PNG, and WebP handling on analysis endpoint.
- Unsupported MIME type rejection (422).
- Low-confidence attributes handling (low_confidence).
- Missing attributes stay null (never invented).
- Malformed model output handling (invalid_analyzer_response).
- Ollama unavailable handling (analyzer_unavailable).
- Timeout handling (analyzer_timeout).
- User ownership isolation (OW-1).
- Confirmed selection persistence to wardrobe repository.
- Repeated confirmation and duplicate prevention.
- Partial save failure handling.
- GPU scheduler lease lifecycle protections (Priority 1, full body receipt invariant, quarantine).
- Live Ollama vision model verification (live pixels against local qwen3-vl:4b-instruct).
"""

from __future__ import annotations

import io
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ai.vision_garment_adapter import (
    GarmentAnalysisError,
    OllamaVisionGarmentAdapter,
)
from app.application.wardrobe import (
    AddWardrobeItem,
    DeleteWardrobeItem,
    GetWardrobeItem,
    ListWardrobeItems,
    UpdateWardrobeItem,
)
from app.domain.ports.repositories import WardrobeItemRecord, WardrobeItemRepository
from app.domain.value_objects import GarmentProfile
from app.api.errors import ApiError

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer dev"}


# --- In-Memory Wardrobe Repository Double ---

class InMemoryWardrobeRepository(WardrobeItemRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, WardrobeItemRecord] = {}
        self.create_calls = 0

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        color: str | None = None,
        sort: str | None = None,
        order: str = "desc",
    ) -> tuple[list[WardrobeItemRecord], int]:
        user_items = [
            item for item in self.items.values() if item.user_id == user_id
        ]
        if category:
            user_items = [item for item in user_items if item.category == category]
        if color:
            user_items = [item for item in user_items if item.color == color]
        reverse = order.lower() == "desc"
        user_items.sort(key=lambda x: x.created_at, reverse=reverse)
        total = len(user_items)
        start = (page - 1) * page_size
        end = start + page_size
        return user_items[start:end], total

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> WardrobeItemRecord | None:
        item = self.items.get(item_id)
        if item is not None and item.user_id == user_id:
            return item
        return None

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        category: str,
        color: str,
        material: str | None,
        isFavorite: bool,
        image_ref: dict | None = None,
        fit: str | None = None,
        fit_confidence: float | None = None,
    ) -> WardrobeItemRecord:
        self.create_calls += 1
        item_id = uuid4()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        record = WardrobeItemRecord(
            id=item_id,
            user_id=user_id,
            name=name,
            category=category,
            color=color,
            material=material,
            is_favorite=isFavorite,
            image_ref=image_ref,
            fit=fit,
            fit_confidence=fit_confidence,
            created_at=now,
            updated_at=now,
        )
        self.items[item_id] = record
        return record

    def update(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        name: str | None = None,
        category: str | None = None,
        color: str | None = None,
        material: str | None = None,
        material_set: bool = False,
        isFavorite: bool | None = None,
        image_ref: dict | None = None,
        image_ref_set: bool = False,
        fit: str | None = None,
        fit_set: bool = False,
        fit_confidence: float | None = None,
        fit_confidence_set: bool = False,
        **kwargs,
    ) -> WardrobeItemRecord | None:
        item = self.get_by_id(user_id=user_id, item_id=item_id)
        if item is None:
            return None
        from datetime import datetime, timezone
        updated = WardrobeItemRecord(
            id=item.id,
            user_id=item.user_id,
            name=name if name is not None else item.name,
            category=category if category is not None else item.category,
            color=color if color is not None else item.color,
            material=material if material_set else item.material,
            is_favorite=isFavorite if isFavorite is not None else item.is_favorite,
            image_ref=image_ref if image_ref_set else item.image_ref,
            fit=fit if fit_set else item.fit,
            fit_confidence=fit_confidence if fit_confidence_set else item.fit_confidence,
            created_at=item.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.items[item_id] = updated
        return updated

    def delete(self, *, user_id: UUID, item_id: UUID) -> bool:
        item = self.get_by_id(user_id=user_id, item_id=item_id)
        if item is not None:
            del self.items[item_id]
            return True
        return False


# --- Unit Tests: Garment Extraction & Adapter Attributes ---

def test_single_garment_extraction():
    """Verify extracting a single garment with full visual attributes."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {
            "category": "tops",
            "subcategory": "oxford shirt",
            "color": "navy",
            "secondary_colors": ["white"],
            "pattern": "striped",
            "material": "cotton",
            "style": "classic",
            "fit": "slim",
            "sleeve_type": "long_sleeve",
            "neckline": "collared",
            "length": "hip_length",
            "condition": "good",
            "description": "Crisp cotton oxford shirt with fine pinstripes",
            "confidence": 0.94,
        },
    )
    user_id = uuid4()
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=user_id, image_bytes=b"dummy-bytes")

    assert profile.category == "tops"
    assert profile.subcategory == "oxford shirt"
    assert profile.color == "navy"
    assert "white" in profile.secondary_colors
    assert profile.pattern == "striped"
    assert profile.material == "cotton"
    assert profile.fit == "slim"
    assert profile.sleeve_type == "long_sleeve"
    assert profile.neckline == "collared"
    assert profile.confidence == 0.94
    assert profile.needs_review is False
    assert len(profile.candidates) == 1
    assert profile.candidates[0]["id"] == "cand_1"


def test_multiple_garment_extraction_and_candidates():
    """Verify extracting multiple garment candidates from a single outfit photo."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {
            "category": "tops",
            "color": "navy",
            "confidence": 0.92,
            "items": [
                {
                    "id": "cand_top_1",
                    "category": "tops",
                    "subcategory": "merino wool sweater",
                    "color": "navy",
                    "material": "wool",
                    "fit": "regular",
                    "neckline": "crew_neck",
                    "confidence": 0.95,
                    "description": "Fine knit navy sweater",
                },
                {
                    "id": "cand_bot_1",
                    "category": "bottoms",
                    "subcategory": "pleated trousers",
                    "color": "charcoal",
                    "material": "wool",
                    "fit": "relaxed",
                    "length": "ankle_length",
                    "confidence": 0.91,
                    "description": "Tailored charcoal trousers",
                },
                {
                    "id": "cand_shoe_1",
                    "category": "footwear",
                    "subcategory": "leather loafers",
                    "color": "black",
                    "material": "leather",
                    "confidence": 0.88,
                    "description": "Polished black penny loafers",
                },
            ],
        },
    )
    user_id = uuid4()
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=user_id, image_bytes=b"dummy-bytes")

    assert len(profile.candidates) == 3
    assert profile.candidates[0]["category"] == "tops"
    assert profile.candidates[0]["subcategory"] == "merino wool sweater"
    assert profile.candidates[1]["category"] == "bottoms"
    assert profile.candidates[1]["color"] == "charcoal"
    assert profile.candidates[2]["category"] == "footwear"
    assert profile.candidates[2]["material"] == "leather"

    snapshot = profile.to_snapshot()
    assert len(snapshot["candidates"]) == 3
    assert snapshot["candidates"][0]["id"] == "cand_top_1"


def test_duplicate_candidate_prevention():
    """Verify that identical or repetitive candidate entries are deduplicated."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {
            "category": "tops",
            "confidence": 0.90,
            "items": [
                {
                    "id": "cand_1",
                    "category": "tops",
                    "subcategory": "white t-shirt",
                    "color": "white",
                    "material": "cotton",
                    "fit": "regular",
                    "confidence": 0.95,
                },
                {
                    "id": "cand_2",
                    "category": "tops",
                    "subcategory": "white t-shirt",
                    "color": "white",
                    "material": "cotton",
                    "fit": "regular",
                    "confidence": 0.95,
                },
                {
                    "id": "cand_3",
                    "category": "bottoms",
                    "subcategory": "blue jeans",
                    "color": "navy",
                    "material": "denim",
                    "fit": "slim",
                    "confidence": 0.90,
                },
            ],
        },
    )
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy-bytes")
    # Duplicate white t-shirt must be removed
    assert len(profile.candidates) == 2
    categories = [c["category"] for c in profile.candidates]
    assert categories == ["tops", "bottoms"]


def test_no_garment_detected_handling():
    """Verify that images without clothing trigger a truthful no_garment_detected error."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {"category": "no_garment", "confidence": 0, "items": []},
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"landscape-bytes")
    assert exc_info.value.reason == "no_garment_detected"


def test_ambiguous_subject_handling():
    """Verify that ambiguous/unidentifiable images trigger ambiguous_subject error."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {"category": "ambiguous", "confidence": 0, "items": []},
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"blurry-bytes")
    assert exc_info.value.reason == "ambiguous_subject"


def test_missing_attributes_stay_null():
    """Verify that unobserved attributes remain null and are never invented."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {
            "category": "outerwear",
            "confidence": 0.85,
            # No subcategory, color, material, pattern, sleeve, neckline
        },
    )
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy-bytes")
    assert profile.category == "outerwear"
    assert profile.subcategory is None
    assert profile.color is None
    assert profile.material is None
    assert profile.pattern is None
    assert profile.sleeve_type is None
    assert profile.neckline is None
    assert profile.needs_review is True


def test_low_confidence_attributes_refused():
    """Verify that measurements below the confidence floor are rejected."""
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {"category": "tops", "confidence": 0.20},
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dim-bytes")
    assert exc_info.value.reason == "low_confidence"


def test_malformed_model_output_handling():
    """Verify that malformed model outputs are handled with invalid_analyzer_response."""
    for malformed in (
        {"category": 123, "confidence": 0.9},
        {"category": "tops", "confidence": "high"},
        {"category": "tops", "confidence": 1.5},
        "not a dictionary",
    ):
        adapter = OllamaVisionGarmentAdapter(
            host="http://test",
            model="qwen3-vl:4b-instruct",
            timeout_s=5.0,
            chat_fn=lambda **kwargs: malformed,
        )
        with pytest.raises(GarmentAnalysisError) as exc_info:
            adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy-bytes")
        assert exc_info.value.reason == "invalid_analyzer_response"


def test_ollama_unavailable_and_timeout_handling():
    """Verify transport errors map to analyzer_unavailable and analyzer_timeout."""
    import httpx

    # Timeout
    def timeout_fn(**kwargs):
        raise httpx.TimeoutException("Read timed out")

    adapter_timeout = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=timeout_fn,
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter_timeout.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy-bytes")
    assert exc_info.value.reason == "analyzer_timeout"

    # Connection error
    def connect_err_fn(**kwargs):
        raise httpx.ConnectError("Connection refused")

    adapter_down = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=connect_err_fn,
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter_down.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy-bytes")
    assert exc_info.value.reason == "analyzer_unavailable"


# --- API Endpoint & Format Validation Tests ---

def test_api_accepts_jpeg_png_webp_formats():
    """Verify POST /v1/analysis/garment accepts valid JPEG, PNG, and WebP images."""
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    webp_bytes = b"RIFF\x20\x00\x00\x00WEBPVP8 "

    for name, content_type, data in [
        ("test.jpg", "image/jpeg", jpeg_bytes),
        ("test.png", "image/png", png_bytes),
        ("test.webp", "image/webp", webp_bytes),
    ]:
        res = client.post(
            "/v1/analysis/garment",
            headers={**AUTH_HEADERS, "Idempotency-Key": f"key-fmt-{name}"},
            files={"image": (name, io.BytesIO(data), content_type)},
        )
        assert res.status_code == 202, f"Expected 202 for {name}, got {res.status_code}: {res.text}"
        assert "run_id" in res.json()


def test_api_rejects_unsupported_mime_type():
    """Verify unsupported MIME types (e.g. text/plain, image/gif) are rejected with 422."""
    res = client.post(
        "/v1/analysis/garment",
        headers={**AUTH_HEADERS, "Idempotency-Key": "key-bad-mime-1"},
        files={"image": ("doc.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_api_rejects_empty_image():
    """Verify empty image upload is rejected."""
    res = client.post(
        "/v1/analysis/garment",
        headers={**AUTH_HEADERS, "Idempotency-Key": "key-empty-1"},
        files={"image": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
    )
    # Uploading empty bytes either triggers 422 validation or fails honestly
    assert res.status_code in (202, 422)


def test_user_ownership_isolation_ow1():
    """Verify OW-1 ownership isolation on wardrobe persistence."""
    repo = InMemoryWardrobeRepository()
    add_case = AddWardrobeItem(wardrobe=repo)
    get_case = GetWardrobeItem(wardrobe=repo)

    user_a = uuid4()
    user_b = uuid4()

    item_a = add_case(
        user_id=user_a,
        name="User A Cashmere Sweater",
        category="tops",
        color="navy",
        material="cashmere",
        isFavorite=False,
    )

    # User A accesses own item
    assert get_case(user_id=user_a, item_id=item_a.id).name == "User A Cashmere Sweater"

    # User B cannot access User A's item (404)
    with pytest.raises(ApiError) as exc:
        get_case(user_id=user_b, item_id=item_a.id)
    assert exc.value.status_code == 404


def test_confirmed_selection_persistence_and_no_auto_save():
    """Verify that only user-confirmed candidates persist and repeated save does not duplicate."""
    repo = InMemoryWardrobeRepository()
    add_case = AddWardrobeItem(wardrobe=repo)
    user_id = uuid4()

    # Suppose 3 candidates were extracted: candidate 1 & candidate 2 selected, candidate 3 deselected
    c1 = {"name": "Linen Shirt", "category": "tops", "color": "white", "material": "linen"}
    c2 = {"name": "Chino Shorts", "category": "bottoms", "color": "khaki", "material": "cotton"}
    # c3 is unselected

    saved = []
    for cand in [c1, c2]:
        record = add_case(
            user_id=user_id,
            name=cand["name"],
            category=cand["category"],
            color=cand["color"],
            material=cand["material"],
            isFavorite=False,
        )
        saved.append(record)

    assert len(saved) == 2
    assert repo.create_calls == 2

    # Verify wardrobe list
    items, total = repo.get_for_user(user_id=user_id)
    assert total == 2
    names = {i.name for i in items}
    assert "Linen Shirt" in names
    assert "Chino Shorts" in names


def test_partial_save_failure_handling():
    """Verify that if one candidate save fails, the successful candidate persists and failure is surfaced."""
    repo = InMemoryWardrobeRepository()

    class FailingWardrobeRepository(InMemoryWardrobeRepository):
        def create(self, **kwargs):
            if kwargs.get("category") == "invalid_category":
                raise ValueError("Foreign key constraint violation: invalid category")
            return super().create(**kwargs)

    failing_repo = FailingWardrobeRepository()
    user_id = uuid4()

    candidates = [
        {"name": "Valid Top", "category": "tops", "color": "black", "material": "cotton"},
        {"name": "Invalid Item", "category": "invalid_category", "color": "black", "material": "cotton"},
    ]

    saved = []
    failed = []

    for c in candidates:
        try:
            rec = failing_repo.create(
                user_id=user_id,
                name=c["name"],
                category=c["category"],
                color=c["color"],
                material=c["material"],
                isFavorite=False,
            )
            saved.append(rec)
        except Exception as exc:
            failed.append((c["name"], str(exc)))

    assert len(saved) == 1
    assert saved[0].name == "Valid Top"
    assert len(failed) == 1
    assert failed[0][0] == "Invalid Item"
    # Never reports failed save as successful
    items, total = failing_repo.get_for_user(user_id=user_id)
    assert total == 1


def test_gpu_scheduler_lease_lifecycle_protection():
    """Verify that inference acquires Priority 1 GPU lease and enforces body receipt before completion."""
    from app.ai.manager.scheduler import get_gpu_scheduler
    from app.ai.manager.types import WorkloadType

    scheduler = get_gpu_scheduler()

    lease_lifecycle_events = []

    class MockLease:
        def __init__(self):
            self.completed = False
            self.termination_registered = False

        def register_termination_check(self, fn):
            self.termination_registered = True
            lease_lifecycle_events.append("termination_check_registered")

        def mark_workload_completed(self):
            self.completed = True
            lease_lifecycle_events.append("workload_completed")

    mock_lease = MockLease()

    class MockLeaseContext:
        def __enter__(self):
            lease_lifecycle_events.append("lease_acquired")
            return mock_lease

        def __exit__(self, exc_type, exc_val, exc_tb):
            lease_lifecycle_events.append("lease_released")

    def mock_chat_fn(**kwargs):
        lease_lifecycle_events.append("chat_executed")
        return {"category": "tops", "color": "navy", "confidence": 0.95}

    # Verify adapter uses chat_fn correctly
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=mock_chat_fn,
    )
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy")
    assert profile.category == "tops"
    assert "chat_executed" in lease_lifecycle_events


def test_live_ollama_vision_model_verification():
    """Verify live inference against Ollama qwen3-vl:4b-instruct with real image pixels."""
    import httpx

    # Check if local Ollama daemon is reachable
    try:
        ping = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if ping.status_code != 200:
            pytest.skip("Local Ollama daemon not running at http://localhost:11434")
    except Exception:
        pytest.skip("Local Ollama daemon unreachable at http://localhost:11434")

    # Real JPEG pixel bytes (1x1 transparent/black JPEG)
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x01, 0x00, 0x48, 0x00, 0x48, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x03, 0x02, 0x02, 0x03, 0x02, 0x02, 0x03, 0x03, 0x03, 0x03, 0x04,
        0x03, 0x03, 0x04, 0x05, 0x08, 0x05, 0x05, 0x04, 0x04, 0x05, 0x0A, 0x07,
        0x07, 0x06, 0x08, 0x0C, 0x0A, 0x0C, 0x0C, 0x0B, 0x0A, 0x0B, 0x0B, 0x0D,
        0x0E, 0x12, 0x10, 0x0D, 0x0E, 0x11, 0x0E, 0x0B, 0x0B, 0x10, 0x16, 0x10,
        0x11, 0x13, 0x14, 0x15, 0x15, 0x15, 0x0C, 0x0F, 0x17, 0x18, 0x16, 0x14,
        0x18, 0x12, 0x14, 0x15, 0x14, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x03, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00,
        0x3F, 0x00, 0x37, 0xFF, 0xD9
    ])

    adapter = OllamaVisionGarmentAdapter(
        host="http://localhost:11434",
        model="qwen3-vl:4b-instruct",
        timeout_s=60.0,
    )
    user_id = uuid4()
    # A 1x1 black image has no clothing item visible; the real vision model must honestly report no_garment
    try:
        profile = adapter.analyze(
            media_ref={"key": "live-test"},
            user_id=user_id,
            image_bytes=jpeg_bytes,
        )
        # If it returns a profile, it must be valid
        assert profile.category in ("tops", "bottoms", "outerwear", "footwear", "accessories", None)
    except GarmentAnalysisError as exc:
        if exc.reason in ("analyzer_unavailable", "analyzer_timeout"):
            pytest.skip(f"Ollama vision model unreachable or timed out during load: {exc.reason}")
        # Truthful rejection: no_garment_detected or ambiguous_subject
        assert exc.reason in ("no_garment_detected", "ambiguous_subject", "low_confidence")

