"""H4.4 tests — Home and AI Stylist recommendation context parity."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.ai import engine
from app.ai.tools import derive_canonical_outfit_recommendation
from app.api.deps import get_current_user_id, get_weather_provider
from app.application.today import GetTodayLook
from app.domain.ports.repositories import (
    UserEventRecord,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.domain.ports.storage import ObjectStoragePort
from app.domain.value_objects import WeatherContext, WeatherLocation
from app.infrastructure.db.session import get_db
from app.models.schemas import AssistantRequest, ChatMessage


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _make_item(
    *,
    user_id: UUID,
    item_id: UUID | None = None,
    name: str,
    category: str,
    color: str,
    material: str = "cotton",
    fit: str | None = None,
    fit_confidence: float | None = None,
    image_ref: dict | None = None,
) -> WardrobeItemRecord:
    now = datetime.now(timezone.utc)
    return WardrobeItemRecord(
        id=item_id or uuid4(),
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


def _make_event(
    *,
    user_id: UUID,
    event_type: str,
    event_date: date,
    title: str = "Test Event",
) -> UserEventRecord:
    now = datetime.now(timezone.utc)
    return UserEventRecord(
        id=uuid4(),
        user_id=user_id,
        title=title,
        event_type=event_type,
        event_date=event_date,
        event_time=None,
        location=None,
        notes=None,
        created_at=now,
        updated_at=now,
    )


def _make_rain_weather(city: str = "Seattle") -> WeatherContext:
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    return WeatherContext(
        temperature_c=6.0,
        apparent_temperature_c=4.0,
        weather_code=63,
        condition_code="rain",
        condition_text="Moderate rain",
        forecast_timestamp=now,
        retrieved_at=now,
        precipitation_probability=90.0,
        precipitation_mm=6.0,
        relative_humidity_pct=92.0,
        wind_speed_kmh=22.0,
        is_day=True,
        location=WeatherLocation(latitude=47.61, longitude=-122.33, city=city, country="US"),
    )


class _FakeEventsRepo:
    def __init__(self, events: list[UserEventRecord] | None = None, fail: bool = False):
        self._events = list(events or [])
        self._fail = fail

    def list_for_user(self, *, user_id, from_date=None, order="asc", page=1, page_size=1):
        if self._fail:
            raise RuntimeError("events db unavailable")
        filtered = [
            e
            for e in self._events
            if e.user_id == user_id and (from_date is None or e.event_date >= from_date)
        ]
        filtered.sort(key=lambda e: (e.event_date, str(e.id)), reverse=(order == "desc"))
        return (filtered[:page_size], len(filtered))


class _UnfilteringPastEventsRepo:
    """Simulates a buggy/unfiltered repo returning a past event to verify defensive guard."""

    def __init__(self, past_event: UserEventRecord):
        self._past_event = past_event

    def list_for_user(self, *, user_id, from_date=None, order="asc", page=1, page_size=1):
        return ([self._past_event], 1)


class _FakeEventTypesRepo:
    def get_by_code(self, *, code: str):
        return SimpleNamespace(code=code, label=code.title())


class _FakeWardrobeRepo:
    def __init__(self, items: list[WardrobeItemRecord]):
        self._items = list(items)

    def get_for_user(self, *, user_id, page=1, page_size=100, **_kwargs):
        owned = [i for i in self._items if i.user_id == user_id]
        if page > 1:
            return ([], len(owned))
        return (owned, len(owned))


class _FakeUserStateRepo:
    def __init__(
        self,
        *,
        style_type: str | None = None,
        preferred_occasions: list[str] | None = None,
        settings: dict | None = None,
        return_none: bool = False,
    ):
        self._style_type = style_type
        self._preferred_occasions = preferred_occasions
        self._settings = settings
        self._return_none = return_none

    def get_profile(self, *, user_id):
        if self._return_none:
            return None
        style_profile = {"style_type": self._style_type} if self._style_type is not None else {}
        preferences = (
            {"preferred_occasions": self._preferred_occasions}
            if self._preferred_occasions is not None
            else {}
        )
        return UserProfileRecord(
            user_id=user_id,
            display_name="Test User",
            style_profile=style_profile,
            preferences=preferences,
            settings=dict(self._settings or {}),
            flags={},
            version=1,
        )


class _FakeWeatherProvider:
    def __init__(self, ctx: WeatherContext | None = None, fail: bool = False):
        self._ctx = ctx
        self._fail = fail

    async def get_weather(self, *, latitude, longitude, city=None, country=None):
        if self._fail:
            raise RuntimeError("weather service down")
        return self._ctx

    async def close(self):
        return None


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


def test_1_same_inputs_produce_consistent_ranking_across_home_and_ai_stylist():
    user_id = uuid4()
    formal_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Silk Dress Shirt",
        category="tops",
        color="white",
        material="silk",
        fit="slim",
        fit_confidence=0.9,
    )
    casual_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000002"),
        name="Cotton Hoodie",
        category="tops",
        color="olive",
        material="cotton",
        fit="relaxed",
        fit_confidence=0.9,
    )
    trousers = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000003"),
        name="Black Wool Trousers",
        category="bottoms",
        color="black",
        material="wool",
        fit="slim",
        fit_confidence=0.9,
    )
    rain_shell = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000004"),
        name="Nylon Trench",
        category="outerwear",
        color="charcoal",
        material="nylon",
        fit="slim",
        fit_confidence=0.9,
    )
    wardrobe = _FakeWardrobeRepo([formal_top, casual_top, trousers, rain_shell])
    events = _FakeEventsRepo([_make_event(user_id=user_id, event_type="formal", event_date=_utc_today())])
    user_state = _FakeUserStateRepo(
        style_type="classic",
        preferred_occasions=["casual"],
        settings={"city": "Seattle"},
    )
    weather_ctx = _make_rain_weather()

    home_rec = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=_FakeWeatherProvider(weather_ctx),
        )(user_id=user_id)
    )
    assert home_rec is not None

    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=events,
        weather_context=weather_ctx,
    )
    assert cards[0].kind == "outfit"
    assert oi.occasion == home_rec.occasion == "formal"
    assert set(home_rec.selected_item_ids) == set(oi.selectedItemIds)
    assert home_rec.match_score == oi.matchScore


def test_2_upcoming_event_changes_occasion_suitability():
    user_id = uuid4()
    silk_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000011"),
        name="White Silk Shirt",
        category="tops",
        color="white",
        material="silk",
    )
    linen_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000012"),
        name="Beige Linen Tee",
        category="tops",
        color="beige",
        material="linen",
    )
    bottom = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000013"),
        name="Navy Trousers",
        category="bottoms",
        color="navy",
        material="cotton",
    )
    wardrobe = _FakeWardrobeRepo([silk_top, linen_top, bottom])
    user_state = _FakeUserStateRepo(style_type="classic", preferred_occasions=["casual"])

    no_event_cards, no_event_oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=_FakeEventsRepo([]),
    )
    assert no_event_oi.occasion == "casual"
    assert no_event_cards[0].kind == "outfit"

    formal_events = _FakeEventsRepo(
        [_make_event(user_id=user_id, event_type="formal", event_date=_utc_today() + timedelta(days=1))]
    )
    event_cards, event_oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=formal_events,
    )
    assert event_oi.occasion == "formal"
    assert str(silk_top.id) in event_oi.selectedItemIds
    assert event_cards[0].kind == "outfit"

    # Also verify via engine.handle("What should I wear today?")
    reply = engine.handle(
        AssistantRequest(
            messages=[ChatMessage(role="user", content="What should I wear today?")],
        ),
        user_id=user_id,
        preferred_occasions=["casual"],
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=formal_events,
    )
    assert reply.outfitIntelligence is not None
    assert reply.outfitIntelligence.occasion == "formal"
    assert str(silk_top.id) in reply.outfitIntelligence.selectedItemIds


def test_3_past_events_are_ignored():
    user_id = uuid4()
    top = _make_item(user_id=user_id, name="Casual Tee", category="tops", color="black")
    bottom = _make_item(user_id=user_id, name="Denim Jeans", category="bottoms", color="navy")
    wardrobe = _FakeWardrobeRepo([top, bottom])
    user_state = _FakeUserStateRepo(preferred_occasions=["casual"])
    past_event = _make_event(
        user_id=user_id,
        event_type="formal",
        event_date=_utc_today() - timedelta(days=2),
    )

    # Filtered repo ignores past event
    _, oi_filtered = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=_FakeEventsRepo([past_event]),
    )
    assert oi_filtered.occasion == "casual"

    # Defensive guard also ignores past event even if a repo fails to filter from_date
    _, oi_defensive = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=_UnfilteringPastEventsRepo(past_event),
    )
    assert oi_defensive.occasion == "casual"


def test_4_no_event_users_and_unavailable_events_receive_safe_default():
    user_id = uuid4()
    top = _make_item(user_id=user_id, name="Black Tee", category="tops", color="black")
    bottom = _make_item(user_id=user_id, name="Gray Pants", category="bottoms", color="gray")
    wardrobe = _FakeWardrobeRepo([top, bottom])
    user_state = _FakeUserStateRepo()

    home_rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo([]),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=user_state,
        )(user_id=user_id)
    )
    assert home_rec is not None
    assert home_rec.occasion is None

    _, oi_none = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=None,
    )
    assert oi_none.status == "success"
    assert oi_none.occasion == ""
    assert oi_none.matchScore == home_rec.match_score
    assert oi_none.confidence == round(home_rec.match_score / 100, 2)
    assert set(oi_none.selectedItemIds) == set(home_rec.selected_item_ids)

    _, oi_failed = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=_FakeEventsRepo(fail=True),
    )
    assert oi_failed.status == "success"
    assert oi_failed.occasion == ""
    assert oi_failed.matchScore == home_rec.match_score


def test_5_rain_weather_context_affects_scoring_across_both_paths():
    user_id = uuid4()
    top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000021"),
        name="Cotton Tee",
        category="tops",
        color="white",
        material="cotton",
    )
    bottom = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000022"),
        name="Dark Trousers",
        category="bottoms",
        color="black",
        material="cotton",
    )
    suede_jacket = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000023"),
        name="Suede Jacket",
        category="outerwear",
        color="navy",
        material="suede",
    )
    rain_jacket = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000024"),
        name="Waterproof Polyester Parka",
        category="outerwear",
        color="navy",
        material="polyester",
    )
    shoes = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000025"),
        name="Canvas Sneakers",
        category="footwear",
        color="black",
        material="cotton",
    )
    wardrobe = _FakeWardrobeRepo([top, bottom, suede_jacket, rain_jacket, shoes])
    user_state = _FakeUserStateRepo(preferred_occasions=["casual"], settings={"city": "Seattle"})
    rain_ctx = _make_rain_weather()

    home_baseline = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo([]),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=None,
        )(user_id=user_id)
    )
    home_rain = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo([]),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=_FakeWeatherProvider(rain_ctx),
        )(user_id=user_id)
    )
    assert home_baseline is not None
    assert home_rain is not None
    assert str(rain_jacket.id) in home_rain.selected_item_ids
    assert home_rain.match_score != home_baseline.match_score

    stylist_baseline_cards, stylist_baseline_oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=_FakeEventsRepo([]),
        weather_context=None,
    )
    stylist_cards, stylist_oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=_FakeEventsRepo([]),
        weather_context=rain_ctx,
    )
    assert stylist_oi.status == "success"
    assert stylist_baseline_oi.status == "success"
    assert str(rain_jacket.id) in stylist_oi.selectedItemIds
    assert stylist_oi.matchScore != stylist_baseline_oi.matchScore
    assert set(home_rain.selected_item_ids) == set(stylist_oi.selectedItemIds)
    assert home_rain.match_score == stylist_oi.matchScore
    assert "Weather:" in stylist_cards[0].subtitle
    assert "Weather:" not in stylist_baseline_cards[0].subtitle


def test_6_missing_or_failing_weather_does_not_break_recommendations(monkeypatch):
    user_id = uuid4()
    top = _make_item(user_id=user_id, name="Black Tee", category="tops", color="black")
    bottom = _make_item(user_id=user_id, name="Navy Chinos", category="bottoms", color="navy")
    wardrobe_items = [top, bottom]

    # Direct tool call without weather
    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=_FakeWardrobeRepo(wardrobe_items),
        user_state=_FakeUserStateRepo(),
        events=_FakeEventsRepo([]),
        weather_context=None,
    )
    assert oi.status == "success"
    assert len(cards) == 1

    # Full /v1/assistant/chat endpoint with failing weather provider
    monkeypatch.setattr(main_module, "WardrobeItemRepositorySQL", lambda db: _FakeWardrobeRepo(wardrobe_items))
    monkeypatch.setattr(main_module, "SavedLookRepositorySQL", lambda db: SimpleNamespace(list_for_user=lambda **kw: ([], 0)))
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db: _FakeUserStateRepo(settings={"city": "Seattle"}))
    monkeypatch.setattr(main_module, "UserEventRepositorySQL", lambda db: _FakeEventsRepo([]))
    monkeypatch.setattr(main_module, "get_current_user_id", lambda auth=None, db=None: user_id)

    dummy_session = type("DummySession", (), {"execute": lambda self, *a, **k: None})()
    main_module.app.dependency_overrides[get_db] = lambda: dummy_session
    main_module.app.dependency_overrides[get_weather_provider] = lambda: _FakeWeatherProvider(fail=True)
    try:
        client = TestClient(main_module.app)
        resp = client.post(
            "/v1/assistant/chat",
            headers={"Authorization": "Bearer valid-token"},
            json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "outfit"
        assert body["outfitIntelligence"]["status"] == "success"
    finally:
        main_module.app.dependency_overrides.clear()


def test_7_missing_or_incomplete_profile_preferences_do_not_fail():
    user_id = uuid4()
    top = _make_item(user_id=user_id, name="White Shirt", category="tops", color="white")
    bottom = _make_item(user_id=user_id, name="Black Jeans", category="bottoms", color="black")
    wardrobe = _FakeWardrobeRepo([top, bottom])
    empty_state = _FakeUserStateRepo(return_none=True)

    home_rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo([]),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=empty_state,
        )(user_id=user_id)
    )
    assert home_rec is not None

    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=empty_state,
        events=_FakeEventsRepo([]),
    )
    assert oi.status == "success"
    assert set(home_rec.selected_item_ids) == set(oi.selectedItemIds)
    assert cards[0].kind == "outfit"


def test_8_image_ownership_and_provenance_protections_remain_intact():
    user_id = uuid4()
    other_user_id = uuid4()
    owned_key = f"users/{user_id}/wardrobe/owned.jpg"
    foreign_key = f"users/{other_user_id}/wardrobe/foreign.jpg"

    owned_top = _make_item(
        user_id=user_id,
        name="Owned Shirt",
        category="tops",
        color="white",
        image_ref={"objectKey": owned_key},
    )
    foreign_key_bottom = _make_item(
        user_id=user_id,
        name="Trousers",
        category="bottoms",
        color="black",
        image_ref={"objectKey": foreign_key},
    )
    other_owner_item = _make_item(
        user_id=other_user_id,
        name="Foreign User Jacket",
        category="outerwear",
        color="navy",
        image_ref={"objectKey": foreign_key},
    )
    wardrobe = _FakeWardrobeRepo([owned_top, foreign_key_bottom, other_owner_item])

    home_rec = asyncio.run(
        GetTodayLook(
            events=_FakeEventsRepo([]),
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=_FakeUserStateRepo(style_type="minimalist"),
            storage=_FakeStorageAdapter(),
        )(user_id=user_id)
    )
    assert home_rec is not None
    assert home_rec.is_personalized is True
    assert home_rec.source_type == "wardrobe_derived"
    assert home_rec.selected_vibe == "minimalist"
    by_id = {c.id: c for c in home_rec.components}
    assert by_id[str(owned_top.id)].image_url == f"https://storage.example.com/get/{owned_key}?exp=900"
    assert by_id[str(foreign_key_bottom.id)].image_url is None
    assert str(other_owner_item.id) not in home_rec.selected_item_ids

    _, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=_FakeUserStateRepo(style_type="minimalist"),
        events=_FakeEventsRepo([]),
    )
    assert str(other_owner_item.id) not in oi.selectedItemIds


def test_9_default_occasion_parity_across_preference_and_event_combinations():
    """H4.4.1: Home and AI Stylist produce identical ranking scores and occasion resolution
    across:
      1. No style type and no preferred occasions (neutral 0 occasion pts, no +5 casual inflation)
      2. Style type present, no preferred occasions (vibe default occasion)
      3. Preferred occasions present, no upcoming event
      4. Explicit user-selected occasion preserves precedence over upcoming event
      5. Upcoming event with a different occasion overrides preferred/vibe defaults
      6. No upcoming event + weather present vs unavailable
    """
    user_id = uuid4()
    shirt = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000101"),
        name="White Cotton Shirt",
        category="tops",
        color="white",
        material="cotton",
    )
    trousers = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000102"),
        name="Black Wool Trousers",
        category="bottoms",
        color="black",
        material="wool",
    )
    jacket = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000103"),
        name="Polyester Rain Jacket",
        category="outerwear",
        color="black",
        material="polyester",
    )
    wardrobe = _FakeWardrobeRepo([shirt, trousers, jacket])
    rain_ctx = _make_rain_weather()

    def _run_both(
        *,
        user_state: _FakeUserStateRepo,
        events: _FakeEventsRepo,
        weather: WeatherContext | None = None,
        stylist_occasion: str | None = "today",
    ):
        home_rec = asyncio.run(
            GetTodayLook(
                events=events,
                event_types=_FakeEventTypesRepo(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=_FakeWeatherProvider(weather) if weather is not None else None,
            )(user_id=user_id)
        )
        cards, oi = derive_canonical_outfit_recommendation(
            occasion=stylist_occasion,
            user=None,
            user_id=user_id,
            wardrobe_items=wardrobe,
            user_state=user_state,
            events=events,
            weather_context=weather,
        )
        assert home_rec is not None
        assert oi.status == "success"
        assert cards[0].kind == "outfit"
        return home_rec, cards[0], oi

    # 1. No style type, no preferred occasions, no upcoming event -> no +5 casual boost
    home_none, card_none, oi_none = _run_both(
        user_state=_FakeUserStateRepo(style_type=None, preferred_occasions=None),
        events=_FakeEventsRepo([]),
    )
    assert home_none.occasion is None
    assert oi_none.occasion == ""
    assert set(home_none.selected_item_ids) == set(oi_none.selectedItemIds)
    assert home_none.match_score == card_none.score == oi_none.matchScore
    assert oi_none.confidence == round(home_none.match_score / 100, 2)

    # 2. Style type present ("minimalist" -> "office"), no preferred occasions -> +5 office boost
    home_vibe, card_vibe, oi_vibe = _run_both(
        user_state=_FakeUserStateRepo(style_type="minimalist", preferred_occasions=None),
        events=_FakeEventsRepo([]),
    )
    assert home_vibe.occasion == oi_vibe.occasion == "office"
    assert set(home_vibe.selected_item_ids) == set(oi_vibe.selectedItemIds)
    assert home_vibe.match_score == card_vibe.score
    assert home_vibe.match_score > home_none.match_score  # confirms +5 occasion points vs 0

    # 3. Preferred occasions present (["date"]), no upcoming event
    home_pref, card_pref, oi_pref = _run_both(
        user_state=_FakeUserStateRepo(style_type="minimalist", preferred_occasions=["date"]),
        events=_FakeEventsRepo([]),
    )
    assert home_pref.occasion == oi_pref.occasion == "date"
    assert set(home_pref.selected_item_ids) == set(oi_pref.selectedItemIds)
    assert home_pref.match_score == card_pref.score

    # 4. Upcoming event ("formal") overrides preferred_occasions (["casual"]) and vibe default ("office")
    formal_events = _FakeEventsRepo(
        [_make_event(user_id=user_id, event_type="formal", event_date=_utc_today())]
    )
    home_ev, card_ev, oi_ev = _run_both(
        user_state=_FakeUserStateRepo(style_type="minimalist", preferred_occasions=["casual"]),
        events=formal_events,
    )
    assert home_ev.occasion == oi_ev.occasion == "formal"
    assert set(home_ev.selected_item_ids) == set(oi_ev.selectedItemIds)
    assert home_ev.match_score == card_ev.score

    # 5. Explicit user-selected occasion ("party") in AI Stylist is preserved over upcoming event ("formal")
    _, _, oi_explicit = _run_both(
        user_state=_FakeUserStateRepo(style_type="minimalist", preferred_occasions=["casual"]),
        events=formal_events,
        stylist_occasion="party",
    )
    assert oi_explicit.occasion == "party"

    # 6. Weather present vs unavailable produces identical parity
    home_w, card_w, oi_w = _run_both(
        user_state=_FakeUserStateRepo(style_type=None, preferred_occasions=None, settings={"city": "Seattle"}),
        events=_FakeEventsRepo([]),
        weather=rain_ctx,
    )
    assert home_w.occasion is None
    assert oi_w.occasion == ""
    assert set(home_w.selected_item_ids) == set(oi_w.selectedItemIds)
    assert home_w.weather is not None and home_w.weather["applied"] is True
    assert "Weather:" in card_w.subtitle
    assert home_w.match_score == card_w.score == oi_w.matchScore


def test_h442_no_style_type_and_no_preferred_occasions_passes_none_scoring_inputs(monkeypatch):
    """H4.4.2: No style_type and no preferred_occasions -> None fit/palette/occasions, no spurious bonuses, M13 422 preserved."""
    import app.application.outfits as outfits_mod
    import app.application.today as today_mod
    from app.api.errors import ApiError
    from app.application.outfits import GenerateOutfit
    from app.domain.services import analysis_rules

    user_id = uuid4()
    items = [
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000201"),
            name="White Tee",
            category="tops",
            color="white",
            fit="slim",
            fit_confidence=0.95,
        ),
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000202"),
            name="Black Jeans",
            category="bottoms",
            color="black",
            fit="slim",
            fit_confidence=0.95,
        ),
    ]
    wardrobe = _FakeWardrobeRepo(items)
    user_state = _FakeUserStateRepo(style_type=None, preferred_occasions=None)
    events = _FakeEventsRepo([])

    captured_home: list[dict] = []
    captured_stylist: list[dict] = []

    def _spy_home(*args, **kwargs):
        captured_home.append({
            "occasions": list(args[3]) if len(args) > 3 else kwargs.get("preferred_occasions"),
            "palette": kwargs.get("preferred_palette"),
            "fit": kwargs.get("preferred_fit"),
            "weather": kwargs.get("weather_context"),
        })
        return analysis_rules.score_outfit_candidate(*args, **kwargs)

    def _spy_stylist(*args, **kwargs):
        captured_stylist.append({
            "occasions": list(args[3]) if len(args) > 3 else kwargs.get("preferred_occasions"),
            "palette": kwargs.get("preferred_palette"),
            "fit": kwargs.get("preferred_fit"),
            "weather": kwargs.get("weather_context"),
        })
        return analysis_rules.score_outfit_candidate(*args, **kwargs)

    monkeypatch.setattr(today_mod, "score_outfit_candidate", _spy_home)
    monkeypatch.setattr(outfits_mod, "score_outfit_candidate", _spy_stylist)

    home_rec = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=user_state,
        )(user_id=user_id)
    )
    cards, oi = derive_canonical_outfit_recommendation(
        None,
        None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=events,
    )

    assert captured_home and captured_stylist
    assert captured_home[0] == {
        "occasions": [],
        "palette": None,
        "fit": None,
        "weather": None,
    }
    assert captured_stylist[0] == captured_home[0]
    assert home_rec is not None
    assert home_rec.match_score == cards[0].score == oi.matchScore
    assert "Matches your preferred palette" not in oi.explanation
    assert "Matches your preferred fit" not in oi.explanation

    # M13 validation behavior is preserved when allow_empty_preferences=False (default)
    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=user_state)
    with pytest.raises(ApiError) as exc_fit:
        use_case.derive_with_reason(
            user_id=user_id,
            occasion="casual",
            mood="classic",
            fit=None,
            color_palette="monochrome",
        )
    assert exc_fit.value.status_code == 422

    with pytest.raises(ApiError) as exc_palette:
        use_case.derive_with_reason(
            user_id=user_id,
            occasion="casual",
            mood="classic",
            fit="slim",
            color_palette=None,
        )
    assert exc_palette.value.status_code == 422


def test_h442_style_type_present_resolves_fit_and_palette_for_both():
    """H4.4.2: When style_type is present, both Home and AI Stylist resolve and apply fit/palette bonuses."""
    user_id = uuid4()
    items = [
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000211"),
            name="White Shirt",
            category="tops",
            color="white",
            fit="slim",
            fit_confidence=0.9,
        ),
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000212"),
            name="Charcoal Trousers",
            category="bottoms",
            color="charcoal",
            fit="slim",
            fit_confidence=0.9,
        ),
    ]
    wardrobe = _FakeWardrobeRepo(items)
    events = _FakeEventsRepo([])

    home_none = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=_FakeUserStateRepo(style_type=None),
        )(user_id=user_id)
    )
    home_min = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=_FakeUserStateRepo(style_type="minimalist"),
        )(user_id=user_id)
    )
    cards_min, oi_min = derive_canonical_outfit_recommendation(
        None,
        None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=_FakeUserStateRepo(style_type="minimalist"),
        events=events,
    )

    assert home_none is not None and home_min is not None
    assert home_min.match_score == cards_min[0].score == oi_min.matchScore
    assert home_min.match_score > home_none.match_score
    assert set(home_min.selected_item_ids) == set(oi_min.selectedItemIds)


def test_h442_explicit_fit_and_palette_preferences_award_bonus():
    """H4.4.2: Explicit fit and palette preferences override vibe defaults and score accurately."""
    user_id = uuid4()
    items = [
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000221"),
            name="Beige Linen Shirt",
            category="tops",
            color="beige",
            fit="relaxed",
            fit_confidence=0.9,
        ),
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000222"),
            name="Olive Chinos",
            category="bottoms",
            color="olive",
            fit="relaxed",
            fit_confidence=0.9,
        ),
    ]
    wardrobe = _FakeWardrobeRepo(items)
    user_state = _FakeUserStateRepo(style_type="minimalist", preferred_occasions=["casual"])
    events = _FakeEventsRepo([])

    _, oi_vibe_only = derive_canonical_outfit_recommendation(
        "casual",
        None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=events,
    )
    _, oi_explicit = derive_canonical_outfit_recommendation(
        "casual",
        None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=events,
        fit="relaxed",
        color_palette="warm",
    )

    assert oi_explicit.matchScore is not None and oi_vibe_only.matchScore is not None
    # +5 fit +5 palette = +10 points over mismatched minimalist vibe
    assert oi_explicit.matchScore - oi_vibe_only.matchScore == 10


def test_h442_fit_confidence_below_and_above_threshold_scoring_parity():
    """H4.4.2: Fit confidence < 0.6 gives 0 fit points; >= 0.6 gives +5 fit points identically in Home & AI Stylist."""
    user_id = uuid4()
    events = _FakeEventsRepo([])
    user_state = _FakeUserStateRepo(style_type="minimalist")

    def _run_with_confidence(conf: float):
        items = [
            _make_item(
                user_id=user_id,
                item_id=UUID("00000000-0000-0000-0000-000000000231"),
                name="White Shirt",
                category="tops",
                color="white",
                fit="slim",
                fit_confidence=conf,
            ),
            _make_item(
                user_id=user_id,
                item_id=UUID("00000000-0000-0000-0000-000000000232"),
                name="Black Trousers",
                category="bottoms",
                color="black",
                fit="slim",
                fit_confidence=conf,
            ),
        ]
        wardrobe = _FakeWardrobeRepo(items)
        home_rec = asyncio.run(
            GetTodayLook(
                events=events,
                event_types=_FakeEventTypesRepo(),
                wardrobe_items=wardrobe,
                user_state=user_state,
            )(user_id=user_id)
        )
        cards, oi = derive_canonical_outfit_recommendation(
            None,
            None,
            user_id=user_id,
            wardrobe_items=wardrobe,
            user_state=user_state,
            events=events,
        )
        return home_rec, cards[0], oi

    home_low, card_low, oi_low = _run_with_confidence(0.59)
    home_high, card_high, oi_high = _run_with_confidence(0.60)

    assert home_low is not None and home_high is not None
    assert home_low.match_score == card_low.score == oi_low.matchScore
    assert home_high.match_score == card_high.score == oi_high.matchScore
    assert home_high.match_score - home_low.match_score == 5


def test_h442_equivalent_home_and_ai_stylist_scoring_inputs(monkeypatch):
    """H4.4.2: Home and AI Stylist pass identical scoring inputs for equivalent profile, wardrobe, event, occasion, and weather."""
    import app.application.outfits as outfits_mod
    import app.application.today as today_mod
    from app.domain.services import analysis_rules

    user_id = uuid4()
    items = [
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000241"),
            name="Navy Blazer",
            category="outerwear",
            color="navy",
            material="wool",
        ),
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000242"),
            name="White Shirt",
            category="tops",
            color="white",
            fit="slim",
            fit_confidence=0.85,
        ),
        _make_item(
            user_id=user_id,
            item_id=UUID("00000000-0000-0000-0000-000000000243"),
            name="Charcoal Trousers",
            category="bottoms",
            color="charcoal",
            fit="slim",
            fit_confidence=0.85,
        ),
    ]
    wardrobe = _FakeWardrobeRepo(items)
    events = _FakeEventsRepo(
        [_make_event(user_id=user_id, event_type="formal", event_date=_utc_today())]
    )
    weather_ctx = _make_rain_weather("Seattle")
    user_state = _FakeUserStateRepo(
        style_type="classic",
        preferred_occasions=["office", "date"],
        settings={"city": "Seattle"},
    )

    class _FakeWeatherProvider:
        async def get_weather(self, **_kwargs):
            return weather_ctx

    captured_home: list[dict] = []
    captured_stylist: list[dict] = []

    def _capture(target: list[dict]):
        def _inner(*args, **kwargs):
            target.append({
                "preferred_item_ids": args[2] if len(args) > 2 else kwargs.get("preferred_item_ids"),
                "preferred_occasions": list(args[3]) if len(args) > 3 else kwargs.get("preferred_occasions"),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
            })
            return analysis_rules.score_outfit_candidate(*args, **kwargs)
        return _inner

    monkeypatch.setattr(today_mod, "score_outfit_candidate", _capture(captured_home))
    monkeypatch.setattr(outfits_mod, "score_outfit_candidate", _capture(captured_stylist))

    home_rec = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=_FakeWeatherProvider(),
        )(user_id=user_id)
    )
    cards, oi = derive_canonical_outfit_recommendation(
        "today",
        None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=user_state,
        events=events,
        weather_context=weather_ctx,
    )

    assert len(captured_home) == len(captured_stylist) > 0
    assert captured_home[0] == captured_stylist[0]
    assert captured_home[0] == {
        "preferred_item_ids": frozenset(),
        "preferred_occasions": ["formal", "office", "date"],
        "preferred_palette": "cool",
        "preferred_fit": "slim",
        "weather_context": weather_ctx,
    }
    assert home_rec is not None
    assert home_rec.match_score == cards[0].score == oi.matchScore
    assert set(home_rec.selected_item_ids) == set(oi.selectedItemIds)


def test_10_h442_no_style_type_or_preferences_passes_none_not_regular_or_neutral(monkeypatch):
    """H4.4.2: When user has no resolved style preference, Home and AI Stylist both pass
    preferred_fit=None and preferred_palette=None (never 'regular'/'neutral') and award
    no fit/palette/occasion bonus.
    """
    import app.application.outfits as outfits_mod
    import app.application.today as today_mod
    from app.application.outfits import GenerateOutfit
    from app.api.errors import ApiError

    user_id = uuid4()
    slim_black_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000201"),
        name="Black Slim Shirt",
        category="tops",
        color="black",
        material="cotton",
        fit="slim",
        fit_confidence=0.95,
    )
    white_bottom = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000202"),
        name="White Slim Trousers",
        category="bottoms",
        color="white",
        material="cotton",
        fit="slim",
        fit_confidence=0.95,
    )
    wardrobe = _FakeWardrobeRepo([slim_black_top, white_bottom])
    empty_state = _FakeUserStateRepo(style_type=None, preferred_occasions=None)
    empty_events = _FakeEventsRepo([])

    home_calls: list[dict] = []
    stylist_calls: list[dict] = []
    real_score = today_mod.score_outfit_candidate

    def _spy_home_score(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        home_calls.append(
            {
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
            }
        )
        return real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)

    def _spy_stylist_score(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        stylist_calls.append(
            {
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
            }
        )
        return real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)

    monkeypatch.setattr(today_mod, "score_outfit_candidate", _spy_home_score)
    monkeypatch.setattr(outfits_mod, "score_outfit_candidate", _spy_stylist_score)

    home_rec = asyncio.run(
        GetTodayLook(
            events=empty_events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=empty_state,
        )(user_id=user_id)
    )
    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=empty_state,
        events=empty_events,
    )

    assert home_rec is not None
    assert oi.status == "success"
    assert len(home_calls) == len(stylist_calls) >= 1
    assert home_calls[0] == stylist_calls[0] == {
        "preferred_occasions": [],
        "preferred_palette": None,
        "preferred_fit": None,
        "weather_context": None,
    }
    assert home_rec.match_score == cards[0].score == oi.matchScore
    assert "neutral palette" not in oi.compatibilityRationale.lower()
    assert "regular fit" not in oi.compatibilityRationale.lower()

    # M13 validation remains fail-closed when allow_empty_preferences is False (default)
    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=empty_state)
    with pytest.raises(ApiError) as exc_fit:
        use_case.derive_with_reason(
            user_id=user_id,
            occasion="casual",
            mood="classic",
            fit=None,
            color_palette="monochrome",
        )
    assert exc_fit.value.status_code == 422

    with pytest.raises(ApiError) as exc_palette:
        use_case.derive_with_reason(
            user_id=user_id,
            occasion="casual",
            mood="classic",
            fit="slim",
            color_palette=None,
        )
    assert exc_palette.value.status_code == 422


def test_11_h442_style_type_explicit_prefs_and_fit_confidence_threshold(monkeypatch):
    """H4.4.2: Verify style_type resolution, explicit fit/palette overrides,
    garment fit_confidence threshold (< 0.6 vs >= 0.6), and identical scoring inputs
    between Home and AI Stylist.
    """
    import app.application.outfits as outfits_mod
    import app.application.today as today_mod

    user_id = uuid4()
    low_conf_slim_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000301"),
        name="Low-Conf Slim White Shirt",
        category="tops",
        color="white",
        material="cotton",
        fit="slim",
        fit_confidence=0.59,
    )
    high_conf_slim_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000302"),
        name="High-Conf Slim Black Shirt",
        category="tops",
        color="black",
        material="cotton",
        fit="slim",
        fit_confidence=0.60,
    )
    relaxed_warm_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000303"),
        name="Relaxed Olive Tee",
        category="tops",
        color="olive",
        material="cotton",
        fit="relaxed",
        fit_confidence=0.90,
    )
    bottom = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000304"),
        name="Grey Cotton Trousers",
        category="bottoms",
        color="grey",
        material="cotton",
        fit="slim",
        fit_confidence=0.90,
    )
    # 1) Fit confidence threshold (< 0.6 vs >= 0.6) with style_type="minimalist"
    threshold_wardrobe = _FakeWardrobeRepo([low_conf_slim_top, high_conf_slim_top, bottom])
    minimalist_state = _FakeUserStateRepo(
        style_type="minimalist",
        preferred_occasions=None,
        settings={"city": "Seattle"},
    )
    rain_ctx = _make_rain_weather()
    events = _FakeEventsRepo([_make_event(user_id=user_id, event_type="office", event_date=_utc_today())])

    home_captured: list[dict] = []
    stylist_captured: list[dict] = []
    real_score = today_mod.score_outfit_candidate

    def _capture_home(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        res = real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)
        home_captured.append(
            {
                "top_ids": tuple(candidate.top_ids),
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
                "score": res.score,
            }
        )
        return res

    def _capture_stylist(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        res = real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)
        stylist_captured.append(
            {
                "top_ids": tuple(candidate.top_ids),
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
                "score": res.score,
            }
        )
        return res

    monkeypatch.setattr(today_mod, "score_outfit_candidate", _capture_home)
    monkeypatch.setattr(outfits_mod, "score_outfit_candidate", _capture_stylist)

    home_rec = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=threshold_wardrobe,
            user_state=minimalist_state,
            weather_provider=_FakeWeatherProvider(rain_ctx),
        )(user_id=user_id)
    )
    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=threshold_wardrobe,
        user_state=minimalist_state,
        events=events,
        weather_context=rain_ctx,
    )

    assert home_rec is not None
    assert oi.status == "success"
    assert home_captured == stylist_captured
    by_top = {c["top_ids"][0]: c for c in home_captured}
    # 0.60 gets +5 fit bonus over 0.59
    assert by_top[str(high_conf_slim_top.id)]["score"] == by_top[str(low_conf_slim_top.id)]["score"] + 5.0
    assert str(high_conf_slim_top.id) in home_rec.selected_item_ids
    assert set(home_rec.selected_item_ids) == set(oi.selectedItemIds)
    assert home_rec.match_score == cards[0].score == oi.matchScore

    # 2) Explicit fit and color_palette preferences in AI Stylist override no-style-type None
    monkeypatch.undo()
    explicit_wardrobe = _FakeWardrobeRepo([high_conf_slim_top, relaxed_warm_top, bottom])
    empty_state = _FakeUserStateRepo(style_type=None, preferred_occasions=None)

    _, oi_none = derive_canonical_outfit_recommendation(
        occasion="casual",
        user=None,
        user_id=user_id,
        wardrobe_items=explicit_wardrobe,
        user_state=empty_state,
        events=_FakeEventsRepo([]),
    )
    _, oi_explicit = derive_canonical_outfit_recommendation(
        occasion="casual",
        user=None,
        user_id=user_id,
        wardrobe_items=explicit_wardrobe,
        user_state=empty_state,
        events=_FakeEventsRepo([]),
        fit="relaxed",
        color_palette="warm",
    )
    assert str(high_conf_slim_top.id) in oi_none.selectedItemIds
    assert str(relaxed_warm_top.id) in oi_explicit.selectedItemIds
    assert "warm palette" in oi_explicit.compatibilityRationale.lower()


def test_10_h442_no_style_type_or_preferences_passes_none_not_regular_or_neutral(monkeypatch):
    """H4.4.2: When user has no resolved style preference, Home and AI Stylist both pass
    preferred_fit=None and preferred_palette=None (never 'regular'/'neutral') and award
    no fit/palette/occasion bonus.
    """
    import app.application.outfits as outfits_mod
    import app.application.today as today_mod
    from app.application.outfits import GenerateOutfit
    from app.api.errors import ApiError

    user_id = uuid4()
    slim_black_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000201"),
        name="Black Slim Shirt",
        category="tops",
        color="black",
        material="cotton",
        fit="slim",
        fit_confidence=0.95,
    )
    white_bottom = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000202"),
        name="White Slim Trousers",
        category="bottoms",
        color="white",
        material="cotton",
        fit="slim",
        fit_confidence=0.95,
    )
    wardrobe = _FakeWardrobeRepo([slim_black_top, white_bottom])
    empty_state = _FakeUserStateRepo(style_type=None, preferred_occasions=None)
    empty_events = _FakeEventsRepo([])

    home_calls: list[dict] = []
    stylist_calls: list[dict] = []
    real_score = today_mod.score_outfit_candidate

    def _spy_home_score(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        home_calls.append(
            {
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
            }
        )
        return real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)

    def _spy_stylist_score(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        stylist_calls.append(
            {
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
            }
        )
        return real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)

    monkeypatch.setattr(today_mod, "score_outfit_candidate", _spy_home_score)
    monkeypatch.setattr(outfits_mod, "score_outfit_candidate", _spy_stylist_score)

    home_rec = asyncio.run(
        GetTodayLook(
            events=empty_events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=wardrobe,
            user_state=empty_state,
        )(user_id=user_id)
    )
    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=wardrobe,
        user_state=empty_state,
        events=empty_events,
    )

    assert home_rec is not None
    assert oi.status == "success"
    assert len(home_calls) == len(stylist_calls) >= 1
    assert home_calls[0] == stylist_calls[0] == {
        "preferred_occasions": [],
        "preferred_palette": None,
        "preferred_fit": None,
        "weather_context": None,
    }
    assert home_rec.match_score == cards[0].score == oi.matchScore
    assert "neutral palette" not in oi.compatibilityRationale.lower()
    assert "regular fit" not in oi.compatibilityRationale.lower()

    # M13 validation remains fail-closed when allow_empty_preferences is False (default)
    use_case = GenerateOutfit(wardrobe_items=wardrobe, user_state=empty_state)
    with pytest.raises(ApiError) as exc_fit:
        use_case.derive_with_reason(
            user_id=user_id,
            occasion="casual",
            mood="classic",
            fit=None,
            color_palette="monochrome",
        )
    assert exc_fit.value.status_code == 422

    with pytest.raises(ApiError) as exc_palette:
        use_case.derive_with_reason(
            user_id=user_id,
            occasion="casual",
            mood="classic",
            fit="slim",
            color_palette=None,
        )
    assert exc_palette.value.status_code == 422


def test_11_h442_style_type_explicit_prefs_and_fit_confidence_threshold(monkeypatch):
    """H4.4.2: Verify style_type resolution, explicit fit/palette overrides,
    garment fit_confidence threshold (< 0.6 vs >= 0.6), and identical scoring inputs
    between Home and AI Stylist.
    """
    import app.application.outfits as outfits_mod
    import app.application.today as today_mod

    user_id = uuid4()
    low_conf_slim_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000301"),
        name="Low-Conf Slim White Shirt",
        category="tops",
        color="white",
        material="cotton",
        fit="slim",
        fit_confidence=0.59,
    )
    high_conf_slim_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000302"),
        name="High-Conf Slim Black Shirt",
        category="tops",
        color="black",
        material="cotton",
        fit="slim",
        fit_confidence=0.60,
    )
    relaxed_warm_top = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000303"),
        name="Relaxed Olive Tee",
        category="tops",
        color="olive",
        material="cotton",
        fit="relaxed",
        fit_confidence=0.90,
    )
    bottom = _make_item(
        user_id=user_id,
        item_id=UUID("00000000-0000-0000-0000-000000000304"),
        name="Grey Cotton Trousers",
        category="bottoms",
        color="grey",
        material="cotton",
        fit=None,
        fit_confidence=None,
    )
    # 1) Fit confidence threshold (< 0.6 vs >= 0.6) with style_type="minimalist"
    threshold_wardrobe = _FakeWardrobeRepo([low_conf_slim_top, high_conf_slim_top, bottom])
    minimalist_state = _FakeUserStateRepo(
        style_type="minimalist",
        preferred_occasions=None,
        settings={"city": "Seattle"},
    )
    rain_ctx = _make_rain_weather()
    events = _FakeEventsRepo([_make_event(user_id=user_id, event_type="office", event_date=_utc_today())])

    home_captured: list[dict] = []
    stylist_captured: list[dict] = []
    real_score = today_mod.score_outfit_candidate

    def _capture_home(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        res = real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)
        home_captured.append(
            {
                "top_ids": tuple(candidate.top_ids),
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
                "score": res.score,
            }
        )
        return res

    def _capture_stylist(candidate, items_by_id=None, preferred_item_ids=None, preferred_occasions=None, **kwargs):
        res = real_score(candidate, items_by_id, preferred_item_ids, preferred_occasions, **kwargs)
        stylist_captured.append(
            {
                "top_ids": tuple(candidate.top_ids),
                "preferred_occasions": list(preferred_occasions or []),
                "preferred_palette": kwargs.get("preferred_palette"),
                "preferred_fit": kwargs.get("preferred_fit"),
                "weather_context": kwargs.get("weather_context"),
                "score": res.score,
            }
        )
        return res

    monkeypatch.setattr(today_mod, "score_outfit_candidate", _capture_home)
    monkeypatch.setattr(outfits_mod, "score_outfit_candidate", _capture_stylist)

    home_rec = asyncio.run(
        GetTodayLook(
            events=events,
            event_types=_FakeEventTypesRepo(),
            wardrobe_items=threshold_wardrobe,
            user_state=minimalist_state,
            weather_provider=_FakeWeatherProvider(rain_ctx),
        )(user_id=user_id)
    )
    cards, oi = derive_canonical_outfit_recommendation(
        occasion="today",
        user=None,
        user_id=user_id,
        wardrobe_items=threshold_wardrobe,
        user_state=minimalist_state,
        events=events,
        weather_context=rain_ctx,
    )

    assert home_rec is not None
    assert oi.status == "success"
    assert home_captured == stylist_captured
    by_top = {c["top_ids"][0]: c for c in home_captured}
    # 0.60 gets +5 fit bonus over 0.59
    assert by_top[str(high_conf_slim_top.id)]["score"] == by_top[str(low_conf_slim_top.id)]["score"] + 5.0
    assert str(high_conf_slim_top.id) in home_rec.selected_item_ids
    assert set(home_rec.selected_item_ids) == set(oi.selectedItemIds)
    assert home_rec.match_score == cards[0].score == oi.matchScore

    # 2) Explicit fit and color_palette preferences in AI Stylist override no-style-type None
    monkeypatch.undo()
    explicit_wardrobe = _FakeWardrobeRepo([high_conf_slim_top, relaxed_warm_top, bottom])
    empty_state = _FakeUserStateRepo(style_type=None, preferred_occasions=None)

    _, oi_none = derive_canonical_outfit_recommendation(
        occasion="casual",
        user=None,
        user_id=user_id,
        wardrobe_items=explicit_wardrobe,
        user_state=empty_state,
        events=_FakeEventsRepo([]),
    )
    _, oi_explicit = derive_canonical_outfit_recommendation(
        occasion="casual",
        user=None,
        user_id=user_id,
        wardrobe_items=explicit_wardrobe,
        user_state=empty_state,
        events=_FakeEventsRepo([]),
        fit="relaxed",
        color_palette="warm",
    )
    assert str(high_conf_slim_top.id) in oi_none.selectedItemIds
    assert str(relaxed_warm_top.id) in oi_explicit.selectedItemIds
    assert "warm palette" in oi_explicit.compatibilityRationale.lower()
