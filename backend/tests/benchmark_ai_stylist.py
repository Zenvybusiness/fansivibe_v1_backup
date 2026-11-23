"""Benchmark script to measure real performance of the AI Stylist end-to-end journey."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user_id
from app.domain.ports.repositories import (
    SavedLookRecord,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.infrastructure.db.session import get_db

from app.ai import llm_backend

USER_ID = UUID("33333333-3333-4333-8333-333333333333")


def make_item(item_id: str, name: str, category: str, color: str, material: str) -> WardrobeItemRecord:
    now = datetime.now(timezone.utc)
    return WardrobeItemRecord(
        id=UUID(item_id) if len(item_id) == 36 else uuid.uuid5(uuid.NAMESPACE_DNS, item_id),
        user_id=USER_ID,
        name=name,
        category=category,
        color=color,
        material=material,
        is_favorite=False,
        image_ref=None,
        created_at=now,
        updated_at=now,
    )


class TimedWardrobeRepo:
    def __init__(self, items: list[WardrobeItemRecord]):
        self.items = items
        self.last_duration_ms: float = 0.0

    def get_for_user(self, *, user_id: UUID, page: int = 1, page_size: int = 100, **kwargs):
        t0 = time.perf_counter()
        # Simulate slight DB latency
        time.sleep(0.002)
        res = self.items[(page - 1) * page_size : page * page_size], len(self.items)
        self.last_duration_ms = (time.perf_counter() - t0) * 1000
        return res

    def get_by_id(self, *, user_id: UUID, item_id: UUID):
        for item in self.items:
            if item.id == item_id:
                return item
        return None


class SimpleUserStateRepo:
    def get_profile(self, *, user_id: UUID):
        return UserProfileRecord(
            user_id=user_id,
            display_name="Benchmark User",
            style_profile={},
            preferences={"preferred_occasions": ["casual", "formal"]},
            settings={},
            flags={},
            version=1,
        )


class SimpleSavedLookRepo:
    def list_for_user(self, *, user_id: UUID, page: int = 1, page_size: int = 100):
        return [], 0


def run_benchmark():
    capsule = [
        make_item("00000000-0000-0000-0000-000000000001", "White Oxford Shirt", "tops", "white", "cotton"),
        make_item("00000000-0000-0000-0000-000000000002", "Navy Wool Trousers", "bottoms", "navy", "wool"),
        make_item("00000000-0000-0000-0000-000000000003", "Charcoal Tailored Blazer", "outerwear", "charcoal", "wool"),
        make_item("00000000-0000-0000-0000-000000000004", "Brown Leather Oxfords", "footwear", "brown", "leather"),
        make_item("00000000-0000-0000-0000-000000000005", "White Minimalist Leather Sneakers", "footwear", "white", "leather"),
    ]

    wardrobe_repo = TimedWardrobeRepo(capsule)
    user_state_repo = SimpleUserStateRepo()
    saved_look_repo = SimpleSavedLookRepo()

    main_module.WardrobeItemRepositorySQL = lambda db: wardrobe_repo
    main_module.UserStateRepositorySQL = lambda db: user_state_repo
    main_module.SavedLookRepositorySQL = lambda db: saved_look_repo

    dummy_session = type("DummySession", (), {"execute": lambda self, *a, **k: None})()
    main_module.app.dependency_overrides[get_db] = lambda: dummy_session
    main_module.get_current_user_id = lambda auth, db=None: USER_ID

    client = TestClient(main_module.app)

    print("=== LIVE AI STYLIST PERFORMANCE BENCHMARK ===")
    print(f"Model: {llm_backend.get_active_model()}")

    # Run 1: Initial natural-language request ("What should I wear today?")
    t_start = time.perf_counter()
    res1 = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer bench-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
    )
    t_end = time.perf_counter()
    total_duration_1 = (t_end - t_start) * 1000

    assert res1.status_code == 200, f"Error {res1.status_code}: {res1.text}"
    data1 = res1.json()

    # Run 2: Follow-up conversational turn ("Make it more formal")
    t_followup_start = time.perf_counter()
    res2 = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer bench-token"},
        json={
            "messages": [
                {"role": "user", "content": "What should I wear today?"},
                {"role": "assistant", "content": data1["text"]},
                {"role": "user", "content": "Make it more formal"},
            ]
        },
    )
    t_followup_end = time.perf_counter()
    total_duration_2 = (t_followup_end - t_followup_start) * 1000

    assert res2.status_code == 200, f"Error {res2.status_code}: {res2.text}"
    data2 = res2.json()

    print("\n--- Turn 1: Initial Request ('What should I wear today?') ---")
    print(f"Total Response Duration: {total_duration_1:.2f} ms ({total_duration_1/1000:.2f} s)")
    print(f"Wardrobe Retrieval Duration: {wardrobe_repo.last_duration_ms:.2f} ms")
    print(f"Estimated Inference Duration: {max(0.0, total_duration_1 - wardrobe_repo.last_duration_ms - 15):.2f} ms")
    print(f"Selected Cards: {[c['title'] for c in data1.get('cards', [])]}")
    print(f"AI Stylist Text: {data1.get('text')}")

    print("\n--- Turn 2: Follow-up Request ('Make it more formal') ---")
    print(f"Total Follow-up Duration: {total_duration_2:.2f} ms ({total_duration_2/1000:.2f} s)")
    print(f"Wardrobe Retrieval Duration: {wardrobe_repo.last_duration_ms:.2f} ms")
    print(f"Estimated Inference Duration: {max(0.0, total_duration_2 - wardrobe_repo.last_duration_ms - 15):.2f} ms")
    print(f"Selected Cards: {[c['title'] for c in data2.get('cards', [])]}")
    print(f"Follow-up Text: {data2.get('text')}")


if __name__ == "__main__":
    run_benchmark()
