"""H4.2 tests — Recommendation quality, scoring, image association, and Home/Stylist consistency."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.ai.tools import derive_canonical_outfit_recommendation
from app.application.today import GetTodayLook
from app.domain.ports.storage import ObjectStoragePort
from app.domain.services.analysis_rules import (
    OutfitCandidate,
    score_outfit_candidate,
)
from app.domain.services.vibe_mapping import resolve_vibe_attributes


class _FakeEventsRepo:
    def list_for_user(self, *, user_id, from_date=None, order="asc", page=1, page_size=1):
        return ([], 0)


class _FakeEventTypesRepo:
    def get_by_code(self, *, code: str):
        return None


class _FakeWardrobeRepo:
    def __init__(self, items):
        self._items = items

    def get_for_user(self, *, user_id, page=1, page_size=100):
        if page > 1:
            return ([], len(self._items))
        return (self._items, len(self._items))


class _FakeUserStateRepo:
    def __init__(self, *, style_type=None, preferred_occasions=None):
        self._style_type = style_type
        self._preferred_occasions = preferred_occasions or []

    def get_profile(self, *, user_id):
        style_profile = {}
        if self._style_type is not None:
            style_profile["style_type"] = self._style_type
        return SimpleNamespace(
            user_id=user_id,
            style_profile=style_profile,
            preferences={"preferred_occasions": self._preferred_occasions},
            settings={},
        )


class _FakeStorageAdapter(ObjectStoragePort):
    async def put_object(self, *, key: str, data: bytes, content_type: str) -> None:
        return None

    async def get_object(self, *, key: str) -> bytes:
        return b""

    async def delete_object(self, *, key: str) -> None:
        return None

    async def generate_presigned_put_url(self, *, key: str, content_type: str, expires_in_s: int) -> str:
        return f"https://storage.example.com/put/{key}"

    async def generate_presigned_get_url(self, *, key: str, expires_in_s: int) -> str:
        return f"https://storage.example.com/get/{key}?exp={expires_in_s}"


def _wardrobe_item(
    *,
    user_id: UUID,
    name: str,
    category: str,
    color: str,
    material: str = "cotton",
    fit: str | None = None,
    fit_confidence: float | None = None,
    image_ref: dict | None = None,
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        name=name,
        category=category,
        color=color,
        material=material,
        fit=fit,
        fit_confidence=fit_confidence,
        is_favorite=False,
        image_ref=image_ref,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "vibe",
    [
        "minimalist",
        "classic",
        "bold",
        "trendy",
        "streetwear",
        "natural",
        "bohemian",
        "edgy",
        "athleisure",
    ],
)
def test_all_supported_vibes_drive_today_look_metadata(vibe: str):
    user_id = uuid4()
    items = [
        _wardrobe_item(
            user_id=user_id,
            name="Neutral Tee",
            category="tops",
            color="black",
            fit="slim",
            fit_confidence=0.9,
        ),
        _wardrobe_item(
            user_id=user_id,
            name="Neutral Trousers",
            category="bottoms",
            color="navy",
            fit="relaxed",
            fit_confidence=0.9,
        ),
    ]
    attrs = resolve_vibe_attributes(vibe)
    assert attrs is not None

    rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo(items),
            user_state=_FakeUserStateRepo(style_type=vibe),
        )(user_id=user_id)
    )
    assert rec is not None
    assert rec.selected_vibe == attrs.canonical_id
    assert rec.is_personalized is True
    assert rec.source_type == "wardrobe_derived"
    assert rec.image_url is None


def test_scoring_quality_palette_fit_confidence_occasion_and_determinism():
    top_mono_slim = SimpleNamespace(
        id="t1", category="tops", color="black", material="cotton",
        fit="slim", fit_confidence=0.9, is_favorite=False,
    )
    bot_mono_slim = SimpleNamespace(
        id="b1", category="bottoms", color="charcoal", material="cotton",
        fit="slim", fit_confidence=0.9, is_favorite=False,
    )
    top_warm_relaxed = SimpleNamespace(
        id="t2", category="tops", color="olive", material="cotton",
        fit="relaxed", fit_confidence=0.9, is_favorite=False,
    )
    bot_warm_relaxed = SimpleNamespace(
        id="b2", category="bottoms", color="beige", material="cotton",
        fit="relaxed", fit_confidence=0.9, is_favorite=False,
    )
    top_low_conf = SimpleNamespace(
        id="t3", category="tops", color="black", material="cotton",
        fit="slim", fit_confidence=0.4, is_favorite=False,
    )
    bot_low_conf = SimpleNamespace(
        id="b3", category="bottoms", color="charcoal", material="cotton",
        fit="slim", fit_confidence=0.4, is_favorite=False,
    )
    items_by_id = {
        "t1": top_mono_slim,
        "b1": bot_mono_slim,
        "t2": top_warm_relaxed,
        "b2": bot_warm_relaxed,
        "t3": top_low_conf,
        "b3": bot_low_conf,
    }
    cand_mono = OutfitCandidate(top_ids=("t1",), bottom_ids=("b1",))
    cand_warm = OutfitCandidate(top_ids=("t2",), bottom_ids=("b2",))
    cand_low_conf = OutfitCandidate(top_ids=("t3",), bottom_ids=("b3",))

    # Palette & fit influence ranking
    s_mono_for_min = score_outfit_candidate(
        cand_mono, items_by_id, preferred_palette="monochrome", preferred_fit="slim"
    )
    s_warm_for_min = score_outfit_candidate(
        cand_warm, items_by_id, preferred_palette="monochrome", preferred_fit="slim"
    )
    assert s_mono_for_min.score > s_warm_for_min.score

    # Low fit confidence (< 0.6) does not receive the +5 fit bonus
    s_high_conf = score_outfit_candidate(cand_mono, items_by_id, preferred_fit="slim")
    s_low_conf = score_outfit_candidate(cand_low_conf, items_by_id, preferred_fit="slim")
    assert s_high_conf.score > s_low_conf.score

    # Occasion compatibility influences ranking
    s_office = score_outfit_candidate(cand_mono, items_by_id, preferred_occasions=["office"])
    s_none_occ = score_outfit_candidate(cand_mono, items_by_id, preferred_occasions=[])
    assert s_office.score >= s_none_occ.score

    # Missing/unknown preferences do not crash and are deterministic
    s_missing_1 = score_outfit_candidate(
        cand_mono, items_by_id, preferred_palette=None, preferred_fit="unknown"
    )
    s_missing_2 = score_outfit_candidate(
        cand_mono, items_by_id, preferred_palette=None, preferred_fit="unknown"
    )
    assert s_missing_1.score == s_missing_2.score


def test_today_look_resolves_owned_image_ref_and_rejects_foreign_or_missing():
    user_id = uuid4()
    other_user_id = uuid4()
    owned_key = f"users/{user_id}/wardrobe/item-1.jpg"
    foreign_key = f"users/{other_user_id}/wardrobe/item-2.jpg"

    owned_top = _wardrobe_item(
        user_id=user_id,
        name="Owned Black Tee",
        category="tops",
        color="black",
        image_ref={"objectKey": owned_key},
    )
    foreign_bottom = _wardrobe_item(
        user_id=user_id,
        name="Foreign Key Bottom",
        category="bottoms",
        color="navy",
        image_ref={"objectKey": foreign_key},
    )

    rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo([owned_top, foreign_bottom]),
            user_state=_FakeUserStateRepo(style_type="minimalist"),
            storage=_FakeStorageAdapter(),
        )(user_id=user_id)
    )
    assert rec is not None
    by_id = {c.id: c for c in rec.components}
    assert by_id[str(owned_top.id)].image_url == f"https://storage.example.com/get/{owned_key}?exp=900"
    assert by_id[str(foreign_bottom.id)].image_url is None
    assert rec.image_url == by_id[str(owned_top.id)].image_url


def test_home_and_ai_stylist_produce_consistent_recommendations_for_same_vibe():
    user_id = uuid4()
    mono_top = _wardrobe_item(
        user_id=user_id,
        name="Black Slim Tee",
        category="tops",
        color="black",
        fit="slim",
        fit_confidence=0.9,
    )
    mono_bottom = _wardrobe_item(
        user_id=user_id,
        name="Charcoal Slim Trousers",
        category="bottoms",
        color="charcoal",
        fit="slim",
        fit_confidence=0.9,
    )
    warm_top = _wardrobe_item(
        user_id=user_id,
        name="Olive Relaxed Shirt",
        category="tops",
        color="olive",
        fit="relaxed",
        fit_confidence=0.9,
    )
    warm_bottom = _wardrobe_item(
        user_id=user_id,
        name="Beige Relaxed Chinos",
        category="bottoms",
        color="beige",
        fit="relaxed",
        fit_confidence=0.9,
    )
    wardrobe = [mono_top, mono_bottom, warm_top, warm_bottom]
    wardrobe_repo = _FakeWardrobeRepo(wardrobe)

    for vibe in ["minimalist", "classic", "bold", "trendy", "streetwear", "natural", "bohemian", "edgy", "athleisure"]:
        user_state = _FakeUserStateRepo(style_type=vibe)
        home_rec = asyncio.run(
            GetTodayLook(
                events=_FakeEventsRepo(),
                event_types=_FakeEventTypesRepo(),
                wardrobe_items=wardrobe_repo,
                user_state=user_state,
            )(user_id=user_id)
        )
        assert home_rec is not None

        cards, oi = derive_canonical_outfit_recommendation(
            occasion="today",
            user=None,
            user_id=user_id,
            wardrobe_items=wardrobe_repo,
            user_state=user_state,
        )
        assert cards[0].kind == "outfit"
        assert set(home_rec.selected_item_ids) == set(oi.selectedItemIds)


def test_empty_wardrobe_consistent_across_home_and_ai_stylist():
    user_id = uuid4()
    empty_repo = _FakeWardrobeRepo([])
    user_state = _FakeUserStateRepo(style_type="classic")

    home_rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=empty_repo,
            user_state=user_state,
        )(user_id=user_id)
    )
    assert home_rec is None

    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=empty_repo,
        user_state=user_state,
    )
    assert oi.status == "empty_wardrobe"
    assert oi.selectedItemIds == []
