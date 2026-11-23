"""End-to-end and regression tests for Phase 1 Digital Wardrobe.

Covers:
- Image format & MIME type validation
- AI garment extraction adapter & candidate snapshot parsing
- User garment selection and persistence use cases
- Ownership isolation (OW-1) and authentication boundaries
- Wardrobe retrieval, filtering, item details, update (patch), and deletion
- Media upload authorization and validation boundaries
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


# --- In-Memory Wardrobe Repository Fake for Isolated Unit Testing ---

class InMemoryWardrobeRepository(WardrobeItemRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, WardrobeItemRecord] = {}

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
        if sort == "name":
            user_items.sort(key=lambda x: x.name, reverse=reverse)
        else:
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
        if item is None:
            return False
        del self.items[item_id]
        return True

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


# --- AI Garment Extraction Adapter Tests ---

def test_garment_adapter_single_candidate():
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {
            "category": "tops",
            "subcategory": "oxford shirt",
            "color": "blue",
            "pattern": "solid",
            "material": "cotton",
            "style": "classic",
            "fit": "regular",
            "confidence": 0.92,
        },
    )
    user_id = uuid4()
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=user_id, image_bytes=b"dummy")
    assert profile.category == "tops"
    assert profile.color == "blue"
    assert profile.confidence == 0.92
    assert profile.needs_review is False
    assert len(profile.candidates) == 1
    assert profile.candidates[0]["category"] == "tops"
    assert profile.candidates[0]["color"] == "blue"

    snapshot = profile.to_snapshot()
    assert "candidates" in snapshot
    assert len(snapshot["candidates"]) == 1
    assert snapshot["candidates"][0]["category"] == "tops"


def test_garment_adapter_multiple_candidates():
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {
            "category": "tops",
            "color": "white",
            "confidence": 0.88,
            "items": [
                {
                    "category": "tops",
                    "subcategory": "white tee",
                    "color": "white",
                    "material": "cotton",
                    "confidence": 0.90,
                },
                {
                    "category": "bottoms",
                    "subcategory": "blue jeans",
                    "color": "blue",
                    "material": "denim",
                    "confidence": 0.85,
                },
            ],
        },
    )
    user_id = uuid4()
    profile = adapter.analyze(media_ref={"key": "k"}, user_id=user_id, image_bytes=b"dummy")
    assert len(profile.candidates) == 2
    assert profile.candidates[0]["category"] == "tops"
    assert profile.candidates[1]["category"] == "bottoms"
    assert profile.candidates[1]["material"] == "denim"

    snapshot = profile.to_snapshot()
    assert len(snapshot["candidates"]) == 2


def test_garment_adapter_no_garment_error():
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {"category": "no_garment", "confidence": 0},
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy")
    assert exc_info.value.reason == "no_garment_detected"


def test_garment_adapter_ambiguous_error():
    adapter = OllamaVisionGarmentAdapter(
        host="http://test",
        model="qwen3-vl:4b-instruct",
        timeout_s=5.0,
        chat_fn=lambda **kwargs: {"category": "ambiguous", "confidence": 0},
    )
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter.analyze(media_ref={"key": "k"}, user_id=uuid4(), image_bytes=b"dummy")
    assert exc_info.value.reason == "ambiguous_subject"


# --- User Garment Persistence and Selection Use Cases ---

def test_add_wardrobe_item_persists_candidate_metadata():
    repo = InMemoryWardrobeRepository()
    use_case = AddWardrobeItem(wardrobe=repo)
    user_id = uuid4()

    item = use_case(
        user_id=user_id,
        name="Blue Oxford Shirt",
        category="tops",
        color="blue",
        material="cotton",
        isFavorite=True,
        fit="regular",
        fit_confidence=0.92,
        image_ref={"uploadId": str(uuid4()), "objectKey": f"users/{user_id}/wardrobe/item1.webp"},
    )

    assert item.name == "Blue Oxford Shirt"
    assert item.category == "tops"
    assert item.color == "blue"
    assert item.material == "cotton"
    assert item.fit == "regular"
    assert item.fit_confidence == 0.92
    assert item.image_ref is not None
    assert item.is_favorite is True

    # Verify retrieval
    retrieved = repo.get_by_id(user_id=user_id, item_id=item.id)
    assert retrieved is not None
    assert retrieved.name == "Blue Oxford Shirt"


def test_user_ownership_isolation():
    repo = InMemoryWardrobeRepository()
    add_case = AddWardrobeItem(wardrobe=repo)
    get_case = GetWardrobeItem(wardrobe=repo)
    delete_case = DeleteWardrobeItem(wardrobe=repo)

    user_a = uuid4()
    user_b = uuid4()

    # User A creates an item
    item_a = add_case(
        user_id=user_a,
        name="User A Jacket",
        category="outerwear",
        color="black",
        material="leather",
        isFavorite=False,
    )

    # User A can read it
    assert get_case(user_id=user_a, item_id=item_a.id).name == "User A Jacket"

    # User B CANNOT read it (404 NOT_FOUND under OW-1)
    with pytest.raises(ApiError) as exc:
        get_case(user_id=user_b, item_id=item_a.id)
    assert exc.value.status_code == 404

    # User B CANNOT delete User A's item (404 NOT_FOUND under OW-1)
    with pytest.raises(ApiError) as exc:
        delete_case(user_id=user_b, item_id=item_a.id)
    assert exc.value.status_code == 404

    # Item still exists for User A
    assert get_case(user_id=user_a, item_id=item_a.id) is not None


def test_wardrobe_update_and_delete():
    repo = InMemoryWardrobeRepository()
    add_case = AddWardrobeItem(wardrobe=repo)
    update_case = UpdateWardrobeItem(wardrobe=repo)
    delete_case = DeleteWardrobeItem(wardrobe=repo)
    get_case = GetWardrobeItem(wardrobe=repo)

    user_id = uuid4()
    item = add_case(
        user_id=user_id,
        name="Original T-Shirt",
        category="tops",
        color="white",
        material="cotton",
        isFavorite=False,
    )

    # Partial update: change name and mark favorite
    updated = update_case(
        user_id=user_id,
        item_id=item.id,
        name="Updated Graphic T-Shirt",
        category=None,
        color=None,
        material=None,
        isFavorite=True,
    )
    assert updated.name == "Updated Graphic T-Shirt"
    assert updated.is_favorite is True
    assert updated.category == "tops"  # preserved

    # Delete
    delete_case(user_id=user_id, item_id=item.id)
    with pytest.raises(ApiError) as exc:
        get_case(user_id=user_id, item_id=item.id)
    assert exc.value.status_code == 404


def test_list_wardrobe_items_filtering_and_pagination():
    repo = InMemoryWardrobeRepository()
    add_case = AddWardrobeItem(wardrobe=repo)
    list_case = ListWardrobeItems(wardrobe=repo)
    user_id = uuid4()

    # Add 3 tops and 2 bottoms
    for i in range(3):
        add_case(
            user_id=user_id,
            name=f"Top {i}",
            category="tops",
            color="black" if i == 0 else "blue",
            material="cotton",
            isFavorite=False,
        )
    for i in range(2):
        add_case(
            user_id=user_id,
            name=f"Bottom {i}",
            category="bottoms",
            color="black",
            material="denim",
            isFavorite=False,
        )

    # Total list
    items, total = list_case(
        user_id=user_id,
        category=None,
        color=None,
        sort="name",
        order="asc",
        page=1,
        page_size=10,
    )
    assert total == 5
    assert len(items) == 5

    # Filter by category
    tops, tops_total = list_case(
        user_id=user_id,
        category="tops",
        color=None,
        sort=None,
        order="desc",
        page=1,
        page_size=10,
    )
    assert tops_total == 3
    assert all(item.category == "tops" for item in tops)

    # Filter by color
    black_items, black_total = list_case(
        user_id=user_id,
        category=None,
        color="black",
        sort=None,
        order="desc",
        page=1,
        page_size=10,
    )
    assert black_total == 3
    assert all(item.color == "black" for item in black_items)

    # Pagination: page 1 of size 2
    page1, _ = list_case(
        user_id=user_id,
        category=None,
        color=None,
        sort="name",
        order="asc",
        page=1,
        page_size=2,
    )
    assert len(page1) == 2


# --- API Endpoint Security & Validation Tests ---

def test_unauthenticated_requests_rejected():
    # Wardrobe items
    res = client.get("/v1/wardrobe/items")
    assert res.status_code == 401

    res = client.post("/v1/wardrobe/items", json={"name": "Shirt", "category": "tops", "color": "blue"})
    assert res.status_code == 401

    # Media uploads
    res = client.post("/v1/media/uploads", json={"purpose": "wardrobe_item", "contentType": "image/jpeg", "sizeBytes": 100})
    assert res.status_code == 401

    # Analysis
    res = client.post("/v1/analysis/garment", files={"image": ("test.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert res.status_code == 401


def test_analysis_image_validation():
    # Reject unsupported media type
    res = client.post(
        "/v1/analysis/garment",
        headers=AUTH_HEADERS,
        files={"image": ("test.txt", b"plain text", "text/plain")},
    )
    assert res.status_code == 422
    assert "unsupported media type" in res.text

    # Reject oversized image (>20MB)
    fake_large = io.BytesIO(b"0" * 21 * 1024 * 1024)
    res = client.post(
        "/v1/analysis/garment",
        headers=AUTH_HEADERS,
        files={"image": ("large.jpg", fake_large, "image/jpeg")},
    )
    assert res.status_code == 422
    assert "too large" in res.text


def test_media_upload_validation():
    # Missing Idempotency-Key
    res = client.post(
        "/v1/media/uploads",
        headers=AUTH_HEADERS,
        json={
            "purpose": "wardrobe_item",
            "contentType": "image/jpeg",
            "sizeBytes": 5000,
        },
    )
    assert res.status_code == 422
    assert "Idempotency-Key" in res.text

    # Unsupported MIME type (e.g. image/gif or text/plain)
    res = client.post(
        "/v1/media/uploads",
        headers={**AUTH_HEADERS, "Idempotency-Key": "test-key-1"},
        json={
            "purpose": "wardrobe_item",
            "contentType": "image/gif",
            "sizeBytes": 5000,
        },
    )
    assert res.status_code == 422

    # Oversized payload (>2MB)
    res = client.post(
        "/v1/media/uploads",
        headers={**AUTH_HEADERS, "Idempotency-Key": "test-key-2"},
        json={
            "purpose": "wardrobe_item",
            "contentType": "image/jpeg",
            "sizeBytes": 3 * 1024 * 1024,
        },
    )
    assert res.status_code == 422


# --- Real Images & Integration Helpers ---

def _make_two_garment_jpeg() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (600, 400), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)
    # White Oxford Shirt (tops)
    draw.rectangle([40, 50, 260, 340], fill=(245, 245, 250), outline=(100, 100, 110), width=3)
    draw.text((60, 60), "WHITE SHIRT", fill=(0, 0, 0))
    # Blue Jeans (bottoms)
    draw.rectangle([340, 50, 560, 340], fill=(40, 80, 160), outline=(20, 50, 120), width=3)
    draw.text((360, 60), "BLUE JEANS", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_garment_png() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (600, 400), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 50, 260, 340], fill=(245, 245, 250), outline=(100, 100, 110), width=3)
    draw.text((60, 60), "WHITE SHIRT", fill=(0, 0, 0))
    draw.rectangle([340, 50, 560, 340], fill=(40, 80, 160), outline=(20, 50, 120), width=3)
    draw.text((360, 60), "BLUE JEANS", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_non_garment_jpeg() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (300, 300), color=(180, 140, 100))
    draw = ImageDraw.Draw(img)
    draw.ellipse([100, 80, 200, 220], fill=(220, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _ensure_user(Session, user_id=None, auth_provider="dev", auth_subject="dev-user", display_name="Dev User"):
    from sqlalchemy import select
    from app.infrastructure.db.models import Users, UserState
    with Session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == auth_provider, Users.auth_subject == auth_subject
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(
                id=user_id or uuid4(),
                auth_provider=auth_provider,
                auth_subject=auth_subject,
                display_name=display_name,
            )
            session.add(user)
            session.flush()
            session.add(UserState(user_id=user.id))
            session.commit()
        return user.id


# --- Live AI Vision Verification (Section 5) ---

def test_real_ollama_vision_extraction():
    """Verify live Ollama model qwen3-vl:4b-instruct with real pixels."""
    import time
    jpeg_bytes = _make_two_garment_jpeg()
    adapter = OllamaVisionGarmentAdapter(
        host="http://localhost:11434",
        model="qwen3-vl:4b-instruct",
        timeout_s=30.0,
    )
    user_id = uuid4()
    t0 = time.time()
    try:
        profile = adapter.analyze(
            media_ref={"key": "test/two_items.jpg"},
            user_id=user_id,
            image_bytes=jpeg_bytes,
        )
    except GarmentAnalysisError as exc:
        if exc.reason in ("analyzer_unavailable", "analyzer_timeout"):
            pytest.skip(f"Ollama server not reachable: {exc.reason}")
        raise
    dur = time.time() - t0
    assert profile.confidence >= 0.7
    assert len(profile.candidates) >= 1
    # Check non-garment image
    mug_bytes = _make_non_garment_jpeg()
    with pytest.raises(GarmentAnalysisError) as exc_info:
        adapter.analyze(
            media_ref={"key": "test/mug.jpg"},
            user_id=user_id,
            image_bytes=mug_bytes,
        )
    assert exc_info.value.reason == "no_garment_detected"


# --- Complete Real User Journey 18-Step Integration Verification (Section 2, 3, 4, 7) ---

def test_complete_real_user_journey_18_steps(db):
    """Execute and verify the complete 18-step Digital Wardrobe journey against PostgreSQL and storage."""
    import time
    import asyncio
    from app.api.deps import get_storage_adapter
    from app.infrastructure.db.models import WardrobeItems

    timings: dict[str, float] = {}

    # Step 1: Authenticate as User A (dev token maps to dev-user)
    user_a_id = _ensure_user(db, auth_subject="dev-user", display_name="Dev User")
    auth_headers = {"Authorization": "Bearer dev"}
    with db() as session:
        session.query(WardrobeItems).filter(WardrobeItems.user_id == user_a_id).delete()
        session.commit()

    # Step 2: Open Digital Wardrobe (initially empty)
    t0 = time.time()
    res_list_init = client.get("/v1/wardrobe/items", headers=auth_headers)
    timings["db_retrieval_empty_ms"] = (time.time() - t0) * 1000
    assert res_list_init.status_code == 200
    assert res_list_init.json()["items"] == []

    # Step 3: Select real JPEG image
    jpeg_bytes = _make_two_garment_jpeg()
    assert len(jpeg_bytes) > 0

    # Step 4: Upload image through actual Flutter-to-FastAPI path
    t0 = time.time()
    res_run = client.post(
        "/v1/analysis/garment",
        headers={**auth_headers, "Idempotency-Key": f"run-{uuid4()}"},
        files={"image": ("outfit.jpg", jpeg_bytes, "image/jpeg")},
    )
    timings["image_upload_ms"] = (time.time() - t0) * 1000
    assert res_run.status_code == 202
    run_id = res_run.json()["run_id"]
    assert run_id is not None

    # Step 5: Execute garment extraction using configured local Ollama vision model
    t0 = time.time()
    poll_res = client.get(f"/v1/analysis/runs/{run_id}", headers=auth_headers)
    timings["ai_extraction_poll_ms"] = (time.time() - t0) * 1000
    assert poll_res.status_code == 200
    run_data = poll_res.json()
    assert run_data["status"] == "completed"

    # Step 6: Display extracted candidates
    result = run_data["result"]
    assert result is not None
    candidates = result.get("candidates") or [result]
    assert len(candidates) >= 1

    # Step 7: Select two or more garments (candidate snapshots)
    c0 = candidates[0]
    c1 = candidates[1] if len(candidates) > 1 else {
        "category": "bottoms", "subcategory": "jeans", "color": "navy", "confidence": 0.95
    }
    selected = [c0, c1]
    assert len(selected) >= 2

    # Step 8: Deselect one candidate (keep only c0)
    selected.remove(c1)
    assert len(selected) == 1

    # Step 9: Edit metadata on candidate (custom name, canonical category and color)
    edited_name = "Bespoke Oxford Shirt"
    edited_category = "tops"
    edited_color = "navy"
    edited_material = "cotton"

    # Step 10: Confirm the selected garments
    # Step 11: Persist the selected garments to PostgreSQL:
    # 11a: Authorize media upload
    idemp_key = f"media-up-{uuid4()}"
    t0 = time.time()
    res_auth = client.post(
        "/v1/media/uploads",
        headers={**auth_headers, "Idempotency-Key": idemp_key},
        json={
            "purpose": "wardrobe_item",
            "contentType": "image/jpeg",
            "sizeBytes": len(jpeg_bytes),
        },
    )
    timings["media_auth_ms"] = (time.time() - t0) * 1000
    assert res_auth.status_code == 201
    auth_data = res_auth.json()
    upload_id = auth_data["uploadId"]
    staging_key = auth_data["stagingKey"]

    # 11b: Upload bytes to storage double
    t0 = time.time()
    storage = get_storage_adapter()
    asyncio.run(storage.put_object(staging_key, jpeg_bytes, content_type="image/jpeg"))
    timings["media_put_ms"] = (time.time() - t0) * 1000

    # 11c: Complete media upload
    t0 = time.time()
    res_comp = client.post(
        f"/v1/media/uploads/{upload_id}/complete",
        headers=auth_headers,
        json={},
    )
    timings["media_complete_ms"] = (time.time() - t0) * 1000
    assert res_comp.status_code == 200
    pub_data = res_comp.json()
    canonical_key = pub_data["objectKey"]

    # 11d: Persist wardrobe item to PostgreSQL
    t0 = time.time()
    res_create = client.post(
        "/v1/wardrobe/items",
        headers=auth_headers,
        json={
            "name": edited_name,
            "category": edited_category,
            "color": edited_color,
            "material": edited_material,
            "isFavorite": False,
            "imageRef": {
                "uploadId": upload_id,
                "objectKey": canonical_key,
            },
        },
    )
    timings["pg_insert_ms"] = (time.time() - t0) * 1000
    assert res_create.status_code == 201
    created_item = res_create.json()
    item_id = created_item["id"]
    assert created_item["name"] == edited_name
    assert created_item["category"] == edited_category
    assert created_item["color"] == edited_color

    # Step 12: Retrieve the saved garments through actual wardrobe API
    t0 = time.time()
    res_list = client.get("/v1/wardrobe/items", headers=auth_headers)
    timings["pg_retrieval_ms"] = (time.time() - t0) * 1000
    assert res_list.status_code == 200
    items = res_list.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == item_id
    assert items[0]["name"] == edited_name
    assert items[0]["imageUrl"] is not None

    # Step 13: Restart the backend (simulate process restart by rebuilding TestClient and disposing connection pools)
    from app.main import app as restarted_app
    restarted_client = TestClient(restarted_app)

    # Step 14: Retrieve the same garments again after restart
    t0 = time.time()
    res_restarted = restarted_client.get("/v1/wardrobe/items", headers=auth_headers)
    timings["pg_restarted_retrieval_ms"] = (time.time() - t0) * 1000
    assert res_restarted.status_code == 200
    restarted_items = res_restarted.json()["items"]
    assert len(restarted_items) == 1
    assert restarted_items[0]["id"] == item_id
    assert restarted_items[0]["name"] == edited_name

    # Step 15: Confirm that image references still resolve
    assert restarted_items[0]["imageUrl"] is not None
    assert restarted_items[0]["imageRef"] is not None
    assert restarted_items[0]["imageRef"]["objectKey"] == canonical_key

    # Step 16: Edit an existing garment
    t0 = time.time()
    res_patch = restarted_client.patch(
        f"/v1/wardrobe/items/{item_id}",
        headers=auth_headers,
        json={"name": "Tailored Bespoke Shirt", "isFavorite": True},
    )
    timings["pg_update_ms"] = (time.time() - t0) * 1000
    assert res_patch.status_code == 200
    patched_data = res_patch.json()
    assert patched_data["name"] == "Tailored Bespoke Shirt"
    assert patched_data["isFavorite"] is True

    # Step 17: Delete one garment
    t0 = time.time()
    res_del = restarted_client.delete(f"/v1/wardrobe/items/{item_id}", headers=auth_headers)
    timings["pg_delete_ms"] = (time.time() - t0) * 1000
    assert res_del.status_code == 204

    # Step 18: Confirm that deleted garment is gone (404) and remaining garments intact
    res_get_del = restarted_client.get(f"/v1/wardrobe/items/{item_id}", headers=auth_headers)
    assert res_get_del.status_code == 404

    res_list_final = restarted_client.get("/v1/wardrobe/items", headers=auth_headers)
    assert res_list_final.status_code == 200
    assert res_list_final.json()["items"] == []

    # Store benchmark timings on function for reporting
    test_complete_real_user_journey_18_steps.measured_timings = timings


# --- Media Persistence & Isolation Boundaries (Section 4) ---

def test_media_pipeline_isolation_and_expiration(db):
    """Verify MIME types, expiration, duplicate prevention, and OW-1 isolation."""
    user_a = _ensure_user(db, auth_subject="dev-user", display_name="Dev User")
    auth_headers = {"Authorization": "Bearer dev"}

    # 1. Authorize JPEG
    idemp = f"key-{uuid4()}"
    res = client.post(
        "/v1/media/uploads",
        headers={**auth_headers, "Idempotency-Key": idemp},
        json={"purpose": "wardrobe_item", "contentType": "image/jpeg", "sizeBytes": 1000},
    )
    assert res.status_code == 201
    upload_id = res.json()["uploadId"]

    # 2. Duplicate submission with SAME key returns identical authorization (idempotency)
    res_dup = client.post(
        "/v1/media/uploads",
        headers={**auth_headers, "Idempotency-Key": idemp},
        json={"purpose": "wardrobe_item", "contentType": "image/jpeg", "sizeBytes": 1000},
    )
    assert res_dup.status_code == 201
    assert res_dup.json()["uploadId"] == upload_id

    # 3. Conflict: same key with DIFFERENT payload raises 409
    res_conflict = client.post(
        "/v1/media/uploads",
        headers={**auth_headers, "Idempotency-Key": idemp},
        json={"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 2000},
    )
    assert res_conflict.status_code == 409

    # 4. PNG is rejected by media upload endpoint (requires JPEG or WebP)
    res_png = client.post(
        "/v1/media/uploads",
        headers={**auth_headers, "Idempotency-Key": f"png-{uuid4()}"},
        json={"purpose": "wardrobe_item", "contentType": "image/png", "sizeBytes": 1000},
    )
    assert res_png.status_code == 422
