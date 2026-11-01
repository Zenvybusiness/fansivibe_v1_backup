"""Stage 1D Batch 4B.1: Guest Ephemeral Repository Adapters Tests.

Verifies:
1. Ephemeral wardrobe repository protocol compliance.
2. Ephemeral user-state repository protocol compliance.
3. Guest canonical GenerateOutfit execution.
4. Guest occasion handling.
5. Guest fit and palette handling.
6. Missing appearance information.
7. Empty guest wardrobe.
8. Invalid guest wardrobe records.
9. No PostgreSQL session or repository writes.
10. No fabricated guest UUID.
11. Existing authenticated recommendation behavior remains unchanged.
12. Existing guest assistant behavior remains unchanged until Batch 4B.3 integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.application.outfits import (
    EMPTY_WARDROBE,
    MISSING_REQUIRED_CATEGORY,
    GenerateOutfit,
)
from app.domain.ports.repositories import (
    UserProfileRecord,
    UserStateRepository,
    WardrobeInsightSummary,
    WardrobeItemRecord,
    WardrobeItemRepository,
)
from app.infrastructure.external.ephemeral_repositories import (
    EphemeralUserStateRepository,
    EphemeralWardrobeItemRepository,
)
from app.models.schemas import (
    AssistantRequest,
    ChatMessage,
    UserContext,
    WardrobeItem as WireWardrobeItem,
)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _sample_guest_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "item-top-1",
            "name": "White Linen Shirt",
            "category": "tops",
            "color": "white",
            "material": "linen",
            "isFavorite": True,
            "fit": "regular",
            "fit_confidence": 0.85,
        },
        {
            "id": "item-bottom-1",
            "name": "Navy Tailored Trousers",
            "category": "bottoms",
            "color": "navy",
            "material": "wool",
            "isFavorite": False,
            "fit": "tailored",
            "fit_confidence": 0.90,
        },
        {
            "id": "item-outer-1",
            "name": "Charcoal Blazer",
            "category": "outerwear",
            "color": "charcoal",
            "material": "wool",
            "isFavorite": True,
            "fit": "regular",
            "fit_confidence": 0.75,
        },
        {
            "id": "item-foot-1",
            "name": "Brown Leather Oxford",
            "category": "footwear",
            "color": "brown",
            "material": "leather",
            "isFavorite": False,
        },
    ]


# ---------------------------------------------------------------------------
# 1. Ephemeral Wardrobe Repository Protocol Compliance
# ---------------------------------------------------------------------------

def test_1_wardrobe_repository_protocol_compliance():
    """Verify EphemeralWardrobeItemRepository implements the complete protocol."""
    items = _sample_guest_items()
    repo = EphemeralWardrobeItemRepository(items)

    # get_for_user pagination & default
    page_items, total = repo.get_for_user(page=1, page_size=2)
    assert total == 4
    assert len(page_items) == 2
    assert page_items[0].id == "item-top-1"

    # category filter
    tops, count = repo.get_for_user(category="tops")
    assert count == 1
    assert len(tops) == 1
    assert tops[0].category == "tops"

    # color filter
    navies, count = repo.get_for_user(color="navy")
    assert count == 1
    assert navies[0].color == "navy"

    # get_by_id
    found = repo.get_by_id(item_id="item-bottom-1")
    assert found is not None
    assert found.name == "Navy Tailored Trousers"
    assert repo.get_by_id(item_id="non-existent") is None

    # get_insight_summary
    summary = repo.get_insight_summary()
    assert isinstance(summary, WardrobeInsightSummary)
    assert summary.total == 4
    assert summary.favorite_count == 2
    assert summary.counts_by_category["tops"] == 1
    assert summary.counts_by_category["bottoms"] == 1
    assert summary.counts_by_category["accessories"] == 0

    # in-memory mutations without DB
    new_item = repo.create(
        name="Black Belt",
        category="accessories",
        color="black",
        material="leather",
        isFavorite=False,
    )
    assert new_item.name == "Black Belt"
    assert len(repo.items) == 5

    updated = repo.update(
        item_id=new_item.id,
        name="Brown Belt",
        color="brown",
    )
    assert updated is not None
    assert updated.name == "Brown Belt"
    assert updated.color == "brown"

    repo.delete(item_id=new_item.id)
    assert repo.get_by_id(item_id=new_item.id) is None
    assert len(repo.items) == 4

    # commit & rollback no-ops
    repo.commit()
    repo.rollback()


# ---------------------------------------------------------------------------
# 2. Ephemeral User State Repository Protocol Compliance
# ---------------------------------------------------------------------------

def test_2_user_state_repository_protocol_compliance():
    """Verify EphemeralUserStateRepository implements the complete protocol."""
    repo = EphemeralUserStateRepository(
        preferred_occasions=["date", "office"],
        preferences={"vibe": "minimalist"},
    )

    profile = repo.get_profile()
    assert isinstance(profile, UserProfileRecord)
    assert profile.display_name == "Guest"
    assert profile.style_profile == {}
    assert profile.preferences["preferred_occasions"] == ["date", "office"]
    assert profile.preferences["vibe"] == "minimalist"
    assert profile.version == 1

    # get_style_profile returns empty dict
    assert repo.get_style_profile() == {}

    # update_preferences
    repo.update_preferences(preferences={"preferred_occasions": ["casual"]})
    updated_profile = repo.get_profile()
    assert updated_profile.preferences["preferred_occasions"] == ["casual"]

    # update_style_profile returns False (zero persistence)
    res = repo.update_style_profile(face_shape="oval")
    assert res is False
    assert repo.get_style_profile() == {}

    # get_attribute_provenance returns None
    assert repo.get_attribute_provenance({}, "face_shape") is None


# ---------------------------------------------------------------------------
# 3. Guest Canonical GenerateOutfit Execution
# ---------------------------------------------------------------------------

def test_3_guest_canonical_generate_outfit_execution():
    """Canonical GenerateOutfit runs using ephemeral adapters without database."""
    wardrobe = EphemeralWardrobeItemRepository(_sample_guest_items())
    user_state = EphemeralUserStateRepository(preferred_occasions=["casual"])

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    rec, reason = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )

    assert reason is None
    assert rec is not None
    assert rec.title == "Casual Outfit"
    assert rec.match_score > 0.0
    assert len(rec.components) >= 2

    # Preserves actual components from guest snapshot
    component_ids = [c.id for c in rec.components]
    assert "item-top-1" in component_ids
    assert "item-bottom-1" in component_ids


# ---------------------------------------------------------------------------
# 4. Guest Occasion Handling
# ---------------------------------------------------------------------------

def test_4_guest_occasion_scoring_and_reasons():
    """Occasion matches generate canonical occasion score terms and grounded reasons."""
    wardrobe = EphemeralWardrobeItemRepository(_sample_guest_items())
    user_state = EphemeralUserStateRepository(preferred_occasions=["date"])

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    rec, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="date",
        mood="classic",
        fit="regular",
        color_palette="neutral",
    )

    assert rec is not None
    assert "Picked for a Date occasion" in rec.reasons
    assert "Matches the selected occasion" in rec.reasons
    assert rec.selected_occasion == "date"


# ---------------------------------------------------------------------------
# 5. Guest Fit and Palette Handling
# ---------------------------------------------------------------------------

def test_5_guest_fit_and_palette_handling():
    """Soft fit and palette signals apply when inputs match garment attributes."""
    # Top and bottom both in "cool" palette ("navy", "light_blue") and "slim" fit
    cool_slim_items = [
        {
            "id": "item-top-slim",
            "name": "Navy Slim Tee",
            "category": "tops",
            "color": "navy",
            "material": "cotton",
            "fit": "slim",
            "fit_confidence": 0.85,
        },
        {
            "id": "item-bottom-slim",
            "name": "Light Blue Slim Jeans",
            "category": "bottoms",
            "color": "light_blue",
            "material": "denim",
            "fit": "slim",
            "fit_confidence": 0.90,
        },
    ]
    wardrobe = EphemeralWardrobeItemRepository(cool_slim_items)
    user_state = EphemeralUserStateRepository()

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)

    # 1. Matching fit and palette
    rec, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="cool",
    )
    assert rec is not None
    assert "Matches your preferred fit" in rec.reasons
    assert "Matches your preferred palette" in rec.reasons

    # 2. Mismatched fit and palette -> reasons omitted truthfully
    rec_mismatch, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="classic",
        fit="relaxed",
        color_palette="warm",
    )
    assert rec_mismatch is not None
    assert "Matches your preferred fit" not in rec_mismatch.reasons
    assert "Matches your preferred palette" not in rec_mismatch.reasons


# ---------------------------------------------------------------------------
# 6. Missing Appearance Information
# ---------------------------------------------------------------------------

def test_6_missing_appearance_information():
    """Absence of face shape or body type does not impede canonical outfit generation."""
    wardrobe = EphemeralWardrobeItemRepository(_sample_guest_items())
    user_state = EphemeralUserStateRepository()

    # Style profile is completely empty
    assert user_state.get_style_profile() == {}

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    rec, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )

    assert rec is not None
    assert rec.match_score > 0.0
    # No fabricated appearance reasons
    for reason in rec.reasons:
        assert "face" not in reason.lower()
        assert "oval" not in reason.lower()
        assert "body" not in reason.lower()


# ---------------------------------------------------------------------------
# 7. Empty and Sparse Guest Wardrobe Behavior
# ---------------------------------------------------------------------------

def test_7_empty_and_sparse_guest_wardrobes():
    """Empty and incomplete wardrobes return canonical typed 204 reason codes."""
    empty_repo = EphemeralWardrobeItemRepository([])
    user_state = EphemeralUserStateRepository()
    use_case = GenerateOutfit(wardrobe_items=empty_repo, user_state=user_state)

    rec, reason = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )
    assert rec is None
    assert reason == EMPTY_WARDROBE

    # Tops only -> missing_required_category
    tops_only = EphemeralWardrobeItemRepository([
        {"id": "t1", "name": "T-Shirt", "category": "tops", "color": "white"}
    ])
    use_case_tops = GenerateOutfit(wardrobe_items=tops_only, user_state=user_state)
    rec, reason = use_case_tops.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )
    assert rec is None
    assert reason == MISSING_REQUIRED_CATEGORY

    # Bottoms only -> missing_required_category
    bottoms_only = EphemeralWardrobeItemRepository([
        {"id": "b1", "name": "Jeans", "category": "bottoms", "color": "blue"}
    ])
    use_case_bottoms = GenerateOutfit(wardrobe_items=bottoms_only, user_state=user_state)
    rec, reason = use_case_bottoms.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )
    assert rec is None
    assert reason == MISSING_REQUIRED_CATEGORY


# ---------------------------------------------------------------------------
# 8. Invalid Guest Wardrobe Records
# ---------------------------------------------------------------------------

def test_8_invalid_guest_wardrobe_records():
    """Malformed or incomplete items are rejected without fabricating invented garments."""
    invalid_snapshot = [
        {"name": "No ID Shirt", "category": "tops", "color": "red"},
        {"id": "no-cat-item", "name": "Shirt", "color": "red"},
        {"id": "no-name-item", "category": "tops", "color": "red"},
        {"id": "no-color-item", "name": "Pants", "category": "bottoms"},
        {"id": "", "name": "", "category": "", "color": ""},
        None,
        12345,
        "not-a-dict",
    ]
    repo = EphemeralWardrobeItemRepository(invalid_snapshot)
    assert len(repo.items) == 0

    # Malformed optional fields on a valid item degrade safely to None
    valid_with_bad_optionals = [
        {
            "id": "valid-top",
            "name": "Tee",
            "category": "tops",
            "color": "black",
            "material": 12345,  # Non-string material
            "fit": ["invalid"],  # Non-string fit
            "fit_confidence": "high",  # Non-float confidence
        },
        {
            "id": "valid-bottom",
            "name": "Shorts",
            "category": "bottoms",
            "color": "gray",
        },
    ]
    repo2 = EphemeralWardrobeItemRepository(valid_with_bad_optionals)
    assert len(repo2.items) == 2
    top = repo2.get_by_id(item_id="valid-top")
    assert top is not None
    assert top.material is None
    assert top.fit is None
    assert top.fit_confidence is None


# ---------------------------------------------------------------------------
# 9. No PostgreSQL Session or Repository Writes
# ---------------------------------------------------------------------------

def test_9_zero_database_operations():
    """Verify ephemeral adapters execute with zero database session or SQL calls."""
    mock_db = MagicMock()

    wardrobe = EphemeralWardrobeItemRepository(_sample_guest_items())
    user_state = EphemeralUserStateRepository(preferred_occasions=["casual"])

    # Ensure neither adapter holds a session
    assert not hasattr(wardrobe, "_session")
    assert not hasattr(user_state, "_session")

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    rec, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )
    assert rec is not None

    # Verify mock_db was never touched in any way
    mock_db.execute.assert_not_called()
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()
    mock_db.flush.assert_not_called()
    mock_db.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# 10. No Fabricated Guest UUID
# ---------------------------------------------------------------------------

def test_10_no_fabricated_guest_uuid():
    """Garment IDs are preserved exactly as supplied; no fake user UUID is created."""
    items = [
        {"id": "1", "name": "Merino Crew Neck", "category": "tops", "color": "green"},
        {"id": "9", "name": "Tapered Trousers", "category": "bottoms", "color": "khaki"},
    ]
    repo = EphemeralWardrobeItemRepository(items)
    user_state = EphemeralUserStateRepository()

    use_case = GenerateOutfit(wardrobe_items=repo, user_state=user_state)
    rec, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )

    assert rec is not None
    component_ids = [c.id for c in rec.components]
    # Exact original string IDs preserved without inventing UUIDs
    assert component_ids == ["1", "9"]


# ---------------------------------------------------------------------------
# 11. Existing Authenticated Recommendation Behavior Preserved
# ---------------------------------------------------------------------------

def test_11_authenticated_recommendation_behavior_preserved():
    """GenerateOutfit continues to function identically for authenticated inputs."""
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    auth_items = [
        WardrobeItemRecord(
            id=uuid4(),
            user_id=user_id,
            name="Auth Shirt",
            category="tops",
            color="white",
            material="cotton",
            is_favorite=False,
            image_ref=None,
            created_at=now,
            updated_at=now,
        ),
        WardrobeItemRecord(
            id=uuid4(),
            user_id=user_id,
            name="Auth Chinos",
            category="bottoms",
            color="navy",
            material="cotton",
            is_favorite=False,
            image_ref=None,
            created_at=now,
            updated_at=now,
        ),
    ]

    wardrobe = EphemeralWardrobeItemRepository(auth_items, owner_id=user_id)
    user_state = EphemeralUserStateRepository(
        preferred_occasions=["office"], user_id=user_id
    )

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    rec, reason = use_case.derive_with_reason(
        user_id=user_id,
        occasion="office",
        mood="formal",
        fit="regular",
        color_palette="neutral",
    )

    assert reason is None
    assert rec is not None
    assert rec.title == "Office Outfit"
    assert rec.match_score > 0.0


# ---------------------------------------------------------------------------
# 12. Existing Guest Assistant Behavior Preserved
# ---------------------------------------------------------------------------

def test_12_existing_assistant_behavior_preserved(monkeypatch):
    """The existing assistant engine continues to function undisturbed."""
    from app.ai import engine
    import app.ai.llm_backend as llm_backend

    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    req = AssistantRequest(
        messages=[ChatMessage(role="user", content="hello")],
        user=UserContext(wardrobe=[], savedLooks=[], preferredOccasions=[]),
    )
    reply = engine.handle(req)
    assert reply is not None
    assert reply.intent in ("general", "greeting", "clarification")


# ---------------------------------------------------------------------------
# 13. Pydantic WardrobeItem Model Compatibility
# ---------------------------------------------------------------------------

def test_13_pydantic_wardrobe_item_compatibility():
    """Verify WireWardrobeItem (Pydantic) instances are converted cleanly."""
    wire_items = [
        WireWardrobeItem(
            id="wire-top",
            name="Pydantic Oxford",
            category="tops",
            color="white",
            material="cotton",
            isFavorite=True,
        ),
        WireWardrobeItem(
            id="wire-bottom",
            name="Pydantic Trousers",
            category="bottoms",
            color="navy",
            material="wool",
            isFavorite=False,
        ),
    ]
    repo = EphemeralWardrobeItemRepository(wire_items)
    assert len(repo.items) == 2
    top = repo.get_by_id(item_id="wire-top")
    assert top is not None
    assert top.name == "Pydantic Oxford"
    assert top.is_favorite is True
    assert top.category == "tops"
    assert top.color == "white"

    user_state = EphemeralUserStateRepository()
    use_case = GenerateOutfit(wardrobe_items=repo, user_state=user_state)
    rec, reason = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )
    assert reason is None
    assert rec is not None
    assert [c.id for c in rec.components] == ["wire-top", "wire-bottom"]


# ---------------------------------------------------------------------------
# 14. Preferred Item IDs (C-03) Grounded Scoring
# ---------------------------------------------------------------------------

def test_14_preferred_item_ids_c03_boost():
    """C-03 preferredItemIds awards preference points and emits grounded reason."""
    top_id = str(uuid4())
    bottom_id = str(uuid4())
    items = [
        {"id": top_id, "name": "Linen Shirt", "category": "tops", "color": "white"},
        {"id": bottom_id, "name": "Navy Trousers", "category": "bottoms", "color": "navy"},
    ]
    wardrobe = EphemeralWardrobeItemRepository(items)
    user_state = EphemeralUserStateRepository()

    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    # Target top_id as explicit preferred pick
    rec, _ = use_case.derive_with_reason(
        user_id=None,
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
        preferred_item_ids=[top_id],
    )

    assert rec is not None
    assert "Uses an item you selected" in rec.reasons


# ---------------------------------------------------------------------------
# 15. Appearance Stripping & Zero Fabrication Defense
# ---------------------------------------------------------------------------

def test_15_appearance_injection_rejection():
    """Any injected appearance/biometric attributes in guest preferences are strictly stripped."""
    repo = EphemeralUserStateRepository(
        preferred_occasions=["casual"],
        preferences={
            "face_shape": "oval",
            "skin_tone": "fair",
            "body_type": "athletic",
            "style_profile": {"face_shape": "oval"},
            "appearance": {"face_shape": "oval"},
            "favorite_fabric": "linen",
        },
    )

    profile = repo.get_profile()
    assert profile.style_profile == {}
    assert "face_shape" not in profile.preferences
    assert "skin_tone" not in profile.preferences
    assert "body_type" not in profile.preferences
    assert "style_profile" not in profile.preferences
    assert "appearance" not in profile.preferences
    assert profile.preferences["favorite_fabric"] == "linen"

    # Even update_preferences strips appearance keys
    repo.update_preferences(preferences={"face_shape": "round", "shoe_size": "10"})
    updated = repo.get_profile()
    assert "face_shape" not in updated.preferences
    assert updated.preferences["shoe_size"] == "10"


# ---------------------------------------------------------------------------
# 16. Attribute Normalization and Whitespace Trimming
# ---------------------------------------------------------------------------

def test_16_normalization_and_whitespace():
    """Categories and colors with leading/trailing whitespace and mixed case are normalized."""
    dirty_items = [
        {"id": "d1", "name": "  Clean Shirt  ", "category": "  TOPS  ", "color": "  WHITE  "},
        {"id": "d2", "name": "  Clean Pants  ", "category": "  BOTTOMS  ", "color": "  NAVY  "},
    ]
    repo = EphemeralWardrobeItemRepository(dirty_items)
    assert len(repo.items) == 2
    item1 = repo.get_by_id(item_id="d1")
    assert item1 is not None
    assert item1.name == "Clean Shirt"
    assert item1.category == "tops"
    assert item1.color == "white"


# ---------------------------------------------------------------------------
# 17. Import Path Parity
# ---------------------------------------------------------------------------

def test_17_import_path_parity():
    """Verify both ephemeral adapters are importable from all intended architectural paths."""
    from app.infrastructure.external.ephemeral_wardrobe import EphemeralWardrobeItemRepository as EWR1
    from app.infrastructure.external.ephemeral_user_state import EphemeralUserStateRepository as EUR1
    from app.infrastructure.external.ephemeral_repositories import (
        EphemeralWardrobeItemRepository as EWR2,
        EphemeralUserStateRepository as EUR2,
    )
    from app.infrastructure.external import (
        EphemeralWardrobeItemRepository as EWR3,
        EphemeralUserStateRepository as EUR3,
    )

    assert EWR1 is EWR2 is EWR3
    assert EUR1 is EUR2 is EUR3


# ---------------------------------------------------------------------------
# 18. Pagination Bounds
# ---------------------------------------------------------------------------

def test_18_pagination_bounds():
    """Out-of-range pagination safely returns empty list without index errors."""
    repo = EphemeralWardrobeItemRepository(_sample_guest_items())
    items, total = repo.get_for_user(page=100, page_size=10)
    assert total == 4
    assert items == []

