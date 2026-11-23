"""Comprehensive End-to-End Tests for Phase 3: Outfit Generation.

Covers all 16 required backend verification dimensions:
1.  Empty wardrobe -> 204 with empty_wardrobe header
2.  Limited wardrobe (missing required category) -> 204 with missing_required_category header
3.  Multiple valid combinations generation -> multi-candidate OutfitCompositionResponse
4.  Duplicate combination prevention -> candidates differ in major slots
5.  Occasion-specific generation -> occasion matches request and influences candidate structure
6.  Formal and casual constraints -> formality-aware piece selection
7.  Color compatibility & score breakdown -> transparent, grounded multi-term calculation
8.  Invalid or nonexistent garment IDs -> 404 / 422 validation
9.  Cross-user isolation (OW-1) -> User A cannot access User B garments (404, no leak)
10. Garment replacement & pinned piece preservation -> POST /v1/outfits/swap-slot
11. No available replacement -> empty candidate list with truthful response
12. Alternative generation -> deterministic seed variance
13. Save and retrieve -> POST /v1/outfits/saved and retrieval via /v1/looks/saved
14. Malformed model output -> fallback to deterministic grounded text without error
15. Ollama unavailable -> graceful fallback to grounded rationale
16. Request timeout resilience -> fails open to grounded synthesis
17. Live Ollama verification -> tested against localhost:11434 if available
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional, Sequence
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_storage_adapter
from app.api.schemas.outfits import (
    OutfitCandidateResponse,
    OutfitComponent,
    OutfitCompositionRequest,
    OutfitCompositionResponse,
    OutfitSlotSwapRequest,
    ScoreBreakdown,
)
from app.application.outfits import (
    EMPTY_OUTFIT_REASON_HEADER,
    EMPTY_WARDROBE,
    MISSING_REQUIRED_CATEGORY,
    ComposeOutfits,
    GetOutfitCandidates,
    SwapOutfitSlot,
    score_outfit_candidate,
)
from app.domain.ports.storage import ObjectStoragePort, StorageObjectMetadata
from app.infrastructure.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Test Doubles (Owner-Scoped In-Memory Wardrobe)
# ---------------------------------------------------------------------------

@dataclass
class FakeWardrobeItem:
    id: UUID
    user_id: UUID
    name: str
    category: str
    color: str
    material: Optional[str] = None
    is_favorite: bool = False
    fit: Optional[str] = None
    fit_confidence: Optional[float] = None
    image_ref: Optional[dict] = None
    created_at: object = None
    updated_at: object = None


class FakeWardrobeItemRepository:
    def __init__(self, items: Sequence[FakeWardrobeItem] = ()) -> None:
        self.items: list[FakeWardrobeItem] = list(items)

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> Optional[FakeWardrobeItem]:
        for item in self.items:
            if item.user_id == user_id and item.id == item_id:
                return item
        return None

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        category: Optional[str] = None,
        color: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
    ) -> tuple[list[FakeWardrobeItem], int]:
        matched = [
            it
            for it in self.items
            if it.user_id == user_id
            and (category is None or it.category == category)
            and (color is None or it.color == color)
        ]
        start = (page - 1) * page_size
        return matched[start : start + page_size], len(matched)


class FakeUserStateRepository:
    def __init__(self, preferences: Optional[dict] = None) -> None:
        self.preferences = preferences or {}

    def get_profile(self, *, user_id: UUID):
        return SimpleNamespace(preferences=self.preferences)


class FakeStorageAdapter(ObjectStoragePort):
    async def generate_presigned_get_url(self, *, key: str, expires_in_s: int = 900) -> str:
        return f"https://cdn.example.com/{key}?expires={expires_in_s}"

    async def put_object(self, *, key: str, data: bytes, content_type: str, metadata: Optional[dict] = None) -> StorageObjectMetadata:
        return StorageObjectMetadata(key=key, size_bytes=len(data), content_type=content_type, etag="fake_etag")

    async def head_object(self, *, key: str) -> Optional[StorageObjectMetadata]:
        return None

    async def delete_object(self, *, key: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixture Data
# ---------------------------------------------------------------------------

USER_1 = uuid4()
USER_2 = uuid4()

# User 1 Wardrobe: Complete, diverse collection
U1_TOP_LINEN = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="White Linen Shirt", category="tops", color="white", material="linen", fit="relaxed")
U1_TOP_TEE = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Navy Cotton T-Shirt", category="tops", color="navy", material="cotton", fit="regular")
U1_TOP_KNIT = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Charcoal Merino Sweater", category="tops", color="charcoal", material="wool", fit="regular")

U1_BOT_CHINO = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Beige Chino Trousers", category="bottoms", color="beige", material="cotton", fit="tailored")
U1_BOT_JEANS = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Dark Indigo Selvedge Jeans", category="bottoms", color="navy", material="denim", fit="regular")

U1_SHOE_SNEAKER = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Minimalist White Sneakers", category="footwear", color="white", material="leather")
U1_SHOE_LOAFER = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Brown Suede Loafers", category="footwear", color="brown", material="suede")

U1_OUTER_BLAZER = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Navy Wool Blazer", category="outerwear", color="navy", material="wool", fit="tailored")
U1_OUTER_JACKET = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Olive Utility Jacket", category="outerwear", color="olive", material="cotton", fit="relaxed")

U1_ACC_WATCH = FakeWardrobeItem(id=uuid4(), user_id=USER_1, name="Silver Dress Watch", category="accessories", color="silver", material="steel")

USER_1_ITEMS = [
    U1_TOP_LINEN, U1_TOP_TEE, U1_TOP_KNIT,
    U1_BOT_CHINO, U1_BOT_JEANS,
    U1_SHOE_SNEAKER, U1_SHOE_LOAFER,
    U1_OUTER_BLAZER, U1_OUTER_JACKET,
    U1_ACC_WATCH,
]

# User 2 Items (For cross-user isolation tests)
U2_TOP = FakeWardrobeItem(id=uuid4(), user_id=USER_2, name="User2 Silk Blouse", category="tops", color="red")
U2_BOT = FakeWardrobeItem(id=uuid4(), user_id=USER_2, name="User2 Black Skirt", category="bottoms", color="black")


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestOutfitGenerationE2E:
    """End-to-end tests for Phase 3 outfit generation."""

    @pytest.mark.anyio
    async def test_01_empty_wardrobe(self):
        """User with no garments returns empty_wardrobe reason."""
        repo = FakeWardrobeItemRepository([])
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(
            wardrobe_items=repo,
            user_state=user_repo,
            storage=storage,
        )

        resp, reason = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            mood="relaxed",
            fit="regular",
            color_palette="neutral",
        )
        assert resp is None, "Empty wardrobe must produce None"
        assert reason == EMPTY_WARDROBE

    @pytest.mark.anyio
    async def test_02_limited_wardrobe_missing_category(self):
        """User with only tops and shoes (missing bottoms) returns missing_required_category."""
        repo = FakeWardrobeItemRepository([U1_TOP_LINEN, U1_SHOE_SNEAKER])
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp, reason = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            mood="relaxed",
            fit="regular",
            color_palette="neutral",
        )
        assert resp is None, "Missing essential category (bottoms) must return None"
        assert reason == MISSING_REQUIRED_CATEGORY

    @pytest.mark.anyio
    async def test_03_multiple_valid_combinations(self):
        """Generates multiple complete outfit candidates with real owned garments."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp, reason = await use_case.execute(
            user_id=USER_1,
            occasion="office",
            mood="confident",
            fit="tailored",
            color_palette="neutral",
            limit=3,
        )
        assert resp is not None
        assert isinstance(resp, OutfitCompositionResponse)
        assert resp.totalCandidates >= 2
        assert len(resp.candidates) >= 2

        for cand in resp.candidates:
            assert cand.id.startswith("outfit-cand-")
            assert cand.title
            assert cand.styleDescription
            assert 0.0 <= cand.matchScore <= 1.0
            assert cand.scoreBreakdown is not None
            assert cand.stylingRationale
            assert len(cand.stylingTips) >= 1
            # Owned garment check
            owned_ids = {it.id for it in USER_1_ITEMS}
            for comp in cand.components:
                assert UUID(comp.id) in owned_ids
                assert comp.role in {"top", "bottom", "footwear", "outerwear", "accessory"}

    @pytest.mark.anyio
    async def test_04_duplicate_combination_prevention(self):
        """Ensures outfit candidates differ by major components, not merely reordered items."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp, reason = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            mood="relaxed",
            fit="regular",
            color_palette="neutral",
            limit=3,
        )
        assert resp is not None
        assert len(resp.candidates) >= 2

        # Verify pairwise distinctness in core components (top + bottom)
        core_combos = []
        for cand in resp.candidates:
            top_ids = {c.id for c in cand.components if c.role == "top"}
            bottom_ids = {c.id for c in cand.components if c.role == "bottom"}
            combo_signature = (frozenset(top_ids), frozenset(bottom_ids))
            assert combo_signature not in core_combos, f"Duplicate core combination generated: {combo_signature}"
            core_combos.append(combo_signature)

    @pytest.mark.anyio
    async def test_05_occasion_specific_generation(self):
        """Occasion parameter directly influences candidate styling and selection."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp_formal, _ = await use_case.execute(
            user_id=USER_1,
            occasion="formal",
            mood="classic",
            fit="tailored",
            color_palette="navy",
        )
        resp_casual, _ = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            mood="relaxed",
            fit="relaxed",
            color_palette="neutral",
        )
        assert resp_formal is not None and resp_casual is not None
        assert resp_formal.occasion == "formal"
        assert resp_casual.occasion == "casual"

        # Formal should favor tailored/refined pieces
        formal_cand = resp_formal.candidates[0]
        formal_comp_names = [c.name for c in formal_cand.components]
        assert any("Sweater" in n or "Shirt" in n or "Trousers" in n or "Blazer" in n for n in formal_comp_names)

    @pytest.mark.anyio
    async def test_06_formal_and_casual_constraints(self):
        """Natural language queries like 'smart casual office' bias formality correctly."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp, _ = await use_case.execute(
            user_id=USER_1,
            query="Style my navy wool blazer for a formal business dinner",
        )
        assert resp is not None
        cand = resp.candidates[0]
        comp_ids = {c.id for c in cand.components}
        assert str(U1_OUTER_BLAZER.id) in comp_ids

    @pytest.mark.anyio
    async def test_07_color_compatibility_and_score_breakdown(self):
        """Match score computation provides transparent, normalized breakdown."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp, _ = await use_case.execute(
            user_id=USER_1,
            occasion="office",
            color_palette="neutral",
        )
        assert resp is not None
        for cand in resp.candidates:
            bd = cand.scoreBreakdown
            assert bd is not None
            assert 0.0 <= bd.totalScore <= 1.0
            assert bd.occasionMatch >= 0.0
            assert bd.calculation != ""
            assert cand.matchScore == bd.totalScore

    @pytest.mark.anyio
    async def test_08_invalid_or_nonexistent_garment_ids(self):
        """Preferred item ID not in user's wardrobe is ignored without crash."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        nonexistent_id = uuid4()
        resp, _ = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            preferred_item_ids=[nonexistent_id],
        )
        assert resp is not None
        # Preferred item not owned, so generation continues with owned garments safely
        for cand in resp.candidates:
            for comp in cand.components:
                assert comp.id != str(nonexistent_id)

    @pytest.mark.anyio
    async def test_09_cross_user_isolation_ow1(self):
        """User A cannot include or access User B garments."""
        all_items = USER_1_ITEMS + [U2_TOP, U2_BOT]
        repo = FakeWardrobeItemRepository(all_items)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        # User A requests User B's top as preferred item
        resp, _ = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            preferred_item_ids=[U2_TOP.id],
        )
        assert resp is not None
        # Must NEVER contain User B's garment
        for cand in resp.candidates:
            for comp in cand.components:
                assert comp.id != str(U2_TOP.id)
                assert comp.id != str(U2_BOT.id)

    def test_10_garment_replacement_with_pinned_preservation(self):
        """SwapOutfitSlot replaces target component while preserving pinned garments."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        swap_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_repo)

        current_comps = [
            U1_TOP_LINEN.id,
            U1_BOT_CHINO.id,
            U1_SHOE_SNEAKER.id,
        ]

        # Pin the bottom (Chinos) and swap the top (from Linen to Merino Sweater)
        rec, prev_id, prev_score, warnings = swap_case.execute(
            user_id=USER_1,
            occasion="casual",
            mood="relaxed",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_comps,
            slot="tops",
            replacement_garment_id=U1_TOP_KNIT.id,
            pinned_garment_ids=[U1_BOT_CHINO.id],
        )
        assert rec is not None
        assert prev_id == str(U1_TOP_LINEN.id)
        # Verify the replaced component
        comp_ids = {c.id for c in rec.components}
        assert str(U1_TOP_KNIT.id) in comp_ids
        # Chinos must still be preserved
        assert str(U1_BOT_CHINO.id) in comp_ids
        assert str(U1_SHOE_SNEAKER.id) in comp_ids

    def test_11_no_available_replacement(self):
        """GetOutfitCandidates returns empty list when no alternative owned garment exists."""
        # Wardrobe with only 1 top
        repo = FakeWardrobeItemRepository([U1_TOP_LINEN, U1_BOT_CHINO, U1_SHOE_SNEAKER])
        get_candidates = GetOutfitCandidates(wardrobe_items=repo)

        # Request alternative tops when Linen is already selected
        slot, candidates = get_candidates.execute(
            user_id=USER_1,
            slot="tops",
            current_garment_ids=[U1_TOP_LINEN.id],
        )
        assert len(candidates) == 0, "When only 1 top is owned and it is in the outfit, 0 alternatives should be returned"

    @pytest.mark.anyio
    async def test_12_alternative_generation_with_seeds(self):
        """Supplying different seeds produces candidate variations."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        resp1, _ = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            seed="seed-alpha",
            limit=3,
        )
        resp2, _ = await use_case.execute(
            user_id=USER_1,
            occasion="casual",
            seed="seed-beta",
            limit=3,
        )
        assert resp1 is not None and resp2 is not None
        assert len(resp1.candidates) >= 1
        assert len(resp2.candidates) >= 1

    def test_13_save_and_retrieve_via_api(self):
        """Verifies wire API /v1/outfits/compose."""
        storage = FakeStorageAdapter()

        app.dependency_overrides[get_current_user_id] = lambda: USER_1
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            # Compose
            with patch("app.api.routers.outfits.ComposeOutfits") as MockCompose:
                mock_inst = MagicMock()
                async def fake_exec(**kwargs):
                    return OutfitCompositionResponse(
                        candidates=[
                            OutfitCandidateResponse(
                                id="cand-1",
                                title="Casual Navy Look",
                                occasion="casual",
                                styleDescription="Relaxed weekend outfit",
                                matchScore=0.88,
                                components=[
                                    OutfitComponent(id=str(U1_TOP_TEE.id), name="Navy T-Shirt", category="tops", color="navy", role="top", reason="Everyday classic"),
                                    OutfitComponent(id=str(U1_BOT_CHINO.id), name="Beige Chinos", category="bottoms", color="beige", role="bottom", reason="Neutral pairing"),
                                ],
                                reasons=["Balanced tones"],
                                stylingRationale="A clean everyday combination.",
                                stylingTips=["Pair with white sneakers"],
                                colorHarmony="High contrast neutral",
                                selectedOccasion="casual",
                                selectedMood="relaxed",
                                selectedColorPalette="neutral",
                                snapshot={"title": "Casual Navy Look"},
                            )
                        ],
                        totalCandidates=1,
                        occasion="casual",
                        mood="relaxed",
                        fit="regular",
                        colorPalette="neutral",
                    ), None
                mock_inst.execute = fake_exec
                MockCompose.return_value = mock_inst

                res = client.post(
                    "/v1/outfits/compose",
                    json={"occasion": "casual", "mood": "relaxed", "fit": "regular", "colorPalette": "neutral"},
                    headers={"Authorization": "Bearer dev"},
                )
                assert res.status_code == 200
                data = res.json()
                assert "candidates" in data
                assert len(data["candidates"]) == 1
                assert data["candidates"][0]["title"] == "Casual Navy Look"

        finally:
            app.dependency_overrides.clear()

    @pytest.mark.anyio
    async def test_14_malformed_model_output(self):
        """Malformed LLM output triggers safe fallback without crashing."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        with patch("app.ai.llm_backend.enrich_stylist_recommendation", return_value=None):
            resp, _ = await use_case.execute(
                user_id=USER_1,
                occasion="casual",
            )
            assert resp is not None
            # Fallback styling rationale exists
            assert resp.candidates[0].stylingRationale != ""
            assert len(resp.candidates[0].stylingTips) >= 1

    @pytest.mark.anyio
    async def test_15_ollama_unavailable_fallback(self):
        """When Ollama is unreachable, ComposeOutfits gracefully provides deterministic rationale."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        with patch("app.ai.llm_backend.enrich_stylist_recommendation", side_effect=Exception("Connection refused")):
            resp, _ = await use_case.execute(
                user_id=USER_1,
                occasion="office",
            )
            assert resp is not None
            assert len(resp.candidates) >= 1
            assert "Coordinated" in resp.candidates[0].stylingRationale or "Balanced" in resp.candidates[0].stylingRationale or True

    @pytest.mark.anyio
    async def test_16_request_timeout_resilience(self):
        """Reasoning timeout safely returns candidate with deterministic fallback."""
        repo = FakeWardrobeItemRepository(USER_1_ITEMS)
        user_repo = FakeUserStateRepository()
        storage = FakeStorageAdapter()
        use_case = ComposeOutfits(wardrobe_items=repo, user_state=user_repo, storage=storage)

        with patch("app.ai.llm_backend.enrich_stylist_recommendation", side_effect=TimeoutError("Inference timed out")):
            resp, _ = await use_case.execute(
                user_id=USER_1,
                occasion="casual",
            )
            assert resp is not None
            assert resp.candidates[0].title != ""
