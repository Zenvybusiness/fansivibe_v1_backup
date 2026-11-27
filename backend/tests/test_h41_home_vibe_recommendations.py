"""H4.1 tests — Home recommendation source transparency & vibe-to-attribute matching."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.api.routers.looks import _today_to_schema
from app.application.today import GetTodayLook, RegenerateTodayLook
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


def _wardrobe_item(
    *,
    item_id: UUID | None = None,
    name: str,
    category: str,
    color: str,
    material: str = "cotton",
    fit: str | None = None,
    fit_confidence: float | None = None,
    image_url: str | None = None,
):
    return SimpleNamespace(
        id=item_id or uuid4(),
        name=name,
        category=category,
        color=color,
        material=material,
        fit=fit,
        fit_confidence=fit_confidence,
        is_favorite=False,
        image_url=image_url,
    )


@pytest.mark.parametrize(
    "raw_vibe,expected_id,expected_palette,expected_fit",
    [
        ("minimalist", "minimalist", "monochrome", "slim"),
        ("Minimal", "minimalist", "monochrome", "slim"),
        ("classic", "classic", "cool", "slim"),
        ("bold", "bold", "warm", "relaxed"),
        ("trendy", "trendy", "monochrome", "relaxed"),
        ("Street Style", "streetwear", "monochrome", "relaxed"),
        ("streetwear", "streetwear", "monochrome", "relaxed"),
        ("natural", "natural", "warm", "relaxed"),
        ("bohemian", "bohemian", "warm", "relaxed"),
        ("edgy", "edgy", "monochrome", "slim"),
        ("athleisure", "athleisure", "cool", "relaxed"),
        ("sporty", "athleisure", "cool", "relaxed"),
    ],
)
def test_supported_vibes_map_to_canonical_attributes(
    raw_vibe, expected_id, expected_palette, expected_fit
):
    attrs = resolve_vibe_attributes(raw_vibe)
    assert attrs is not None
    assert attrs.canonical_id == expected_id
    assert attrs.preferred_palette == expected_palette
    assert attrs.preferred_fit == expected_fit


def test_unknown_or_empty_vibe_returns_none():
    assert resolve_vibe_attributes(None) is None
    assert resolve_vibe_attributes("") is None
    assert resolve_vibe_attributes("   ") is None
    assert resolve_vibe_attributes("nonexistent_vibe_xyz") is None


def test_selected_vibe_influences_today_look_ranking_and_provenance():
    user_id = UUID("00000000-0000-0000-0000-000000000010")
    mono_top = _wardrobe_item(
        item_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Black Slim Tee",
        category="tops",
        color="black",
        fit="slim",
        fit_confidence=0.9,
        image_url="https://cdn.example.com/black-tee.jpg",
    )
    warm_top = _wardrobe_item(
        item_id=UUID("00000000-0000-0000-0000-000000000002"),
        name="Olive Relaxed Shirt",
        category="tops",
        color="olive",
        fit="relaxed",
        fit_confidence=0.9,
        image_url="https://cdn.example.com/olive-shirt.jpg",
    )
    shared_bottom = _wardrobe_item(
        item_id=UUID("00000000-0000-0000-0000-000000000003"),
        name="Charcoal Trousers",
        category="bottoms",
        color="charcoal",
    )
    wardrobe = [mono_top, warm_top, shared_bottom]

    minimal_look = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo(wardrobe),
            user_state=_FakeUserStateRepo(style_type="minimalist"),
        )(user_id=user_id)
    )
    assert minimal_look is not None
    assert minimal_look.selected_vibe == "minimalist"
    assert minimal_look.source_type == "wardrobe_derived"
    assert minimal_look.is_personalized is True
    assert minimal_look.recommendation_id.startswith("today-")
    assert str(mono_top.id) in minimal_look.selected_item_ids
    assert str(shared_bottom.id) in minimal_look.selected_item_ids
    assert minimal_look.image_url == "https://cdn.example.com/black-tee.jpg"
    assert any("Minimalist vibe" in r for r in minimal_look.reasons)

    # Bold vibe prefers relaxed fit -> warm_top outscores mono_top unambiguously
    bold_look = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo(wardrobe),
            user_state=_FakeUserStateRepo(style_type="bold"),
        )(user_id=user_id)
    )
    assert bold_look is not None
    assert bold_look.selected_vibe == "bold"
    assert bold_look.source_type == "wardrobe_derived"
    assert bold_look.is_personalized is True
    assert str(warm_top.id) in bold_look.selected_item_ids
    assert str(shared_bottom.id) in bold_look.selected_item_ids
    assert bold_look.image_url == "https://cdn.example.com/olive-shirt.jpg"
    assert any("Bold vibe" in r for r in bold_look.reasons)
    assert bold_look.selected_item_ids != minimal_look.selected_item_ids


def test_empty_wardrobe_returns_none_never_fabricates_recommendation():
    user_id = uuid4()
    look = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo([]),
            user_state=_FakeUserStateRepo(style_type="minimalist"),
        )(user_id=user_id)
    )
    assert look is None


def test_missing_vibe_and_missing_image_stay_null_in_schema():
    user_id = uuid4()
    top = _wardrobe_item(name="White Tee", category="tops", color="white")
    bottom = _wardrobe_item(name="Black Jeans", category="bottoms", color="black")
    rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo([top, bottom]),
            user_state=_FakeUserStateRepo(style_type=None),
        )(user_id=user_id)
    )
    assert rec is not None
    assert rec.selected_vibe is None
    assert rec.image_url is None
    schema = _today_to_schema(rec)
    assert schema.recommendationId == rec.recommendation_id
    assert schema.sourceType == "wardrobe_derived"
    assert schema.selectedVibe is None
    assert schema.isPersonalized is True
    assert schema.imageUrl is None


def test_explicit_vibe_overrides_profile_and_works_on_regenerate():
    user_id = uuid4()
    top = _wardrobe_item(name="Navy Oxford", category="tops", color="navy")
    bottom = _wardrobe_item(name="Black Trousers", category="bottoms", color="black")
    rec = asyncio.run(
        RegenerateTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo([top, bottom]),
            user_state=_FakeUserStateRepo(style_type="minimalist"),
        )(user_id=user_id, vibe="classic")
    )
    assert rec is not None
    assert rec.selected_vibe == "classic"
    assert any("Classic vibe" in r for r in rec.reasons)


def test_today_look_fetches_user_profile_once_per_request():
    user_id = UUID("00000000-0000-0000-0000-000000000020")
    top = _wardrobe_item(
        item_id=UUID("00000000-0000-0000-0000-000000000021"),
        name="White Tee",
        category="tops",
        color="white",
    )
    bottom = _wardrobe_item(
        item_id=UUID("00000000-0000-0000-0000-000000000022"),
        name="Black Jeans",
        category="bottoms",
        color="black",
    )

    class _CountingUserStateRepo(_FakeUserStateRepo):
        def __init__(self):
            super().__init__(style_type="minimalist", preferred_occasions=["office"])
            self.calls = 0

        def get_profile(self, *, user_id):
            self.calls += 1
            return super().get_profile(user_id=user_id)

    repo = _CountingUserStateRepo()
    rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo(),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=_FakeWardrobeRepo([top, bottom]),
            user_state=repo,
        )(user_id=user_id)
    )
    assert rec is not None
    assert repo.calls == 1


def test_resolve_component_image_url_logs_safe_warning_on_storage_error(caplog):
    import logging
    from app.application.today import _resolve_component_image_url
    from app.domain.ports.storage import StorageError

    owner_id = UUID("00000000-0000-0000-0000-000000000030")
    secret_key = f"users/{owner_id}/wardrobe/private-secret-key.jpg"
    record = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000031"),
        user_id=owner_id,
        image_ref={"objectKey": secret_key},
    )

    class _FailingStorage:
        async def generate_presigned_get_url(self, *, key: str, expires_in_s: int = 900) -> str:
            raise StorageError(f"presign failed for {key} with secret=tok_123")

    with caplog.at_level(logging.WARNING, logger="app.application.today"):
        url = asyncio.run(_resolve_component_image_url(record, _FailingStorage()))

    assert url is None
    assert any("StorageError" in rec.message for rec in caplog.records)
    joined = "\n".join(rec.message for rec in caplog.records)
    assert secret_key not in joined
    assert str(owner_id) not in joined
    assert "tok_123" not in joined
