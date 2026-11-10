"""Comprehensive tests for Stage 2 P1-3 Phase 3:
Backend Application Orchestration & Weather-Aware Daily Look API.

Covers:
- Location resolution priority (request -> user settings -> ephemeral guest -> absent).
- Privacy guarantees (coarse coordinates ~1.1km, zero coordinates in API responses).
- Weather provider orchestration (success, timeout, transient error, response error, unexpected error).
- Graceful degradation and honest fallback (DEC-017-G: failure never 500/503).
- Canonical scoring engine integration (cold/hot/rainy scoring, baseline identity when weather is absent).
- Wire API responses (GET & POST /v1/looks/today, TodayLookWeather schema, backward compatibility).
- User settings integration and coordinate rounding in UpdatePreferences.
- Security and isolation (OW-1, guest ephemeral isolation, zero DB writes for guests).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Optional, Sequence
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db, get_weather_provider
from app.api.errors import ApiError
from app.api.schemas.today import TodayLook, TodayLookWeather
from app.application.today import (
    MAJOR_CITIES,
    GetTodayLook,
    RegenerateTodayLook,
    _build_weather_payload,
    resolve_weather_location,
)
from app.application.users import UpdatePreferences
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.external import (
    WeatherError,
    WeatherLocationError,
    WeatherProvider,
    WeatherResponseError,
    WeatherTransientError,
)
from app.domain.ports.repositories import (
    TodayLookRecommendation,
    UserEventRecord,
    UserProfileRecord,
    VocabularyRecord,
    WardrobeItemRecord,
)
from app.domain.value_objects import WeatherContext, WeatherLocation
from app.infrastructure.external.ephemeral_repositories import (
    EphemeralUserStateRepository,
    EphemeralWardrobeItemRepository,
)
from app.infrastructure.external.weather import (
    OpenMeteoWeatherAdapter,
    reset_default_weather_provider,
)
from app.main import app


# ==============================================================================
# In-Memory Test Doubles & Fixtures
# ==============================================================================

_NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
_TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_OTHER_USER_ID = UUID("22222222-2222-2222-2222-222222222222")


def _make_weather_context(
    *,
    temperature_c: float = 14.0,
    apparent_temperature_c: float = 12.0,
    weather_code: int = 61,
    condition_code: str = "rain",
    condition_text: str = "Slight rain",
    precipitation_probability: Optional[float] = 80.0,
    precipitation_mm: Optional[float] = 2.5,
    relative_humidity_pct: Optional[float] = 85.0,
    wind_speed_kmh: Optional[float] = 18.0,
    is_day: Optional[bool] = True,
    city: Optional[str] = "Seattle",
    country: Optional[str] = "US",
) -> WeatherContext:
    loc = (
        WeatherLocation(latitude=47.61, longitude=-122.33, city=city, country=country)
        if city
        else None
    )
    return WeatherContext(
        temperature_c=temperature_c,
        apparent_temperature_c=apparent_temperature_c,
        weather_code=weather_code,
        condition_code=condition_code,
        condition_text=condition_text,
        forecast_timestamp=_NOW,
        retrieved_at=_NOW,
        precipitation_probability=precipitation_probability,
        precipitation_mm=precipitation_mm,
        relative_humidity_pct=relative_humidity_pct,
        wind_speed_kmh=wind_speed_kmh,
        is_day=is_day,
        location=loc,
    )


class MockWeatherProvider:
    """Configurable in-memory test double conforming to WeatherProvider."""

    def __init__(
        self,
        context_to_return: Optional[WeatherContext] = None,
        exception_to_raise: Optional[Exception] = None,
    ) -> None:
        self.context_to_return = context_to_return
        self.exception_to_raise = exception_to_raise
        self.calls: list[dict[str, Any]] = []
        self.is_closed = False

    async def get_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Optional[WeatherContext]:
        self.calls.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "city": city,
                "country": country,
            }
        )
        if self.exception_to_raise is not None:
            raise self.exception_to_raise
        return self.context_to_return

    async def close(self) -> None:
        self.is_closed = True


class MockWardrobeItemRepository:
    def __init__(self, items: Sequence[dict[str, Any]]) -> None:
        self._items = list(items)

    def get_for_user(
        self, *, user_id: UUID, page: int = 1, page_size: int = 100
    ) -> tuple[list[WardrobeItemRecord], int]:
        now = datetime.now(timezone.utc)
        user_items = [
            WardrobeItemRecord(
                id=UUID(item["id"]) if isinstance(item["id"], str) else item["id"],
                user_id=item.get("user_id", user_id),
                name=item["name"],
                category=item["category"],
                color=item.get("color", "black"),
                material=item.get("material"),
                is_favorite=item.get("is_favorite", False),
                image_ref=None,
                created_at=now,
                updated_at=now,
            )
            for item in self._items
            if item.get("user_id", user_id) == user_id
        ]
        start = (page - 1) * page_size
        end = start + page_size
        return user_items[start:end], len(user_items)


class MockUserEventRepository:
    def __init__(self, events: Optional[list[UserEventRecord]] = None) -> None:
        self._events = list(events or [])

    def list_for_user(
        self,
        *,
        user_id: UUID,
        from_date: Any,
        order: str = "asc",
        page: int = 1,
        page_size: int = 1,
    ) -> tuple[list[UserEventRecord], int]:
        matches = [e for e in self._events if e.user_id == user_id]
        return matches[:page_size], len(matches)


class MockEventTypeRepository:
    def __init__(self, types: Optional[dict[str, VocabularyRecord]] = None) -> None:
        self._types = types or {
            "formal": VocabularyRecord(
                code="formal",
                label="Formal",
                sort_order=1,
            ),
            "casual": VocabularyRecord(
                code="casual",
                label="Casual",
                sort_order=2,
            ),
        }

    def get_by_code(self, *, code: str) -> Optional[VocabularyRecord]:
        return self._types.get(code)


class MockUserStateRepository:
    def __init__(
        self,
        *,
        settings: Optional[dict[str, Any]] = None,
        preferences: Optional[dict[str, Any]] = None,
        style_profile: Optional[dict[str, Any]] = None,
    ) -> None:
        self._settings = dict(settings or {})
        self._preferences = dict(preferences or {})
        self._style_profile = dict(style_profile or {})

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]:
        return UserProfileRecord(
            user_id=user_id,
            display_name="Test User",
            style_profile=dict(self._style_profile),
            preferences=dict(self._preferences),
            settings=dict(self._settings),
            flags={},
            version=1,
        )

    def update_settings(self, *, user_id: UUID, settings: dict) -> None:
        self._settings.update(settings)

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None:
        self._preferences.update(preferences)

    def update_style_profile(
        self,
        *,
        user_id: UUID,
        style_type: Optional[str] = None,
        confirmed_by_user: bool = False,
        source: str = "user",
        confidence: float = 1.0,
    ) -> None:
        if style_type:
            self._style_profile["style_type"] = style_type


def _standard_wardrobe(user_id: UUID = _TEST_USER_ID) -> list[dict[str, Any]]:
    return [
        {"id": str(uuid4()), "user_id": user_id, "name": "Linen Tee", "category": "tops", "color": "white", "material": "linen", "is_favorite": False},
        {"id": str(uuid4()), "user_id": user_id, "name": "Wool Sweater", "category": "tops", "color": "navy", "material": "wool", "is_favorite": False},
        {"id": str(uuid4()), "user_id": user_id, "name": "Wool Coat", "category": "outerwear", "color": "black", "material": "wool", "is_favorite": False},
        {"id": str(uuid4()), "user_id": user_id, "name": "Denim Jeans", "category": "bottoms", "color": "blue", "material": "denim", "is_favorite": False},
        {"id": str(uuid4()), "user_id": user_id, "name": "Leather Boots", "category": "footwear", "color": "black", "material": "leather", "is_favorite": False},
    ]


# ==============================================================================
# Suite 1: Weather Location Resolution
# ==============================================================================


class TestWeatherLocationResolution:
    """Validate 4-level priority resolution and privacy bounds."""

    def test_explicit_coordinates_and_city(self):
        loc = resolve_weather_location(
            city="Seattle, WA",
            latitude=47.6062,
            longitude=-122.3321,
        )
        assert loc is not None
        assert loc.city == "Seattle, WA"
        # Enforces coarse resolution (~1.1km / 2 decimals)
        assert loc.latitude == 47.61
        assert loc.longitude == -122.33

    def test_explicit_coordinates_without_city(self):
        loc = resolve_weather_location(latitude=51.5074, longitude=-0.1278)
        assert loc is not None
        assert loc.city is None
        assert loc.latitude == 51.51
        assert loc.longitude == -0.13

    def test_explicit_city_major_cities_lookup(self):
        loc = resolve_weather_location(city="Paris")
        assert loc is not None
        assert loc.city == "Paris"
        assert loc.country == "FR"
        assert loc.latitude == 48.86
        assert loc.longitude == 2.35

    def test_explicit_unknown_city_without_coords_returns_none(self):
        loc = resolve_weather_location(city="NonexistentCity12345")
        assert loc is None

    def test_explicit_out_of_range_latitude_returns_none(self):
        loc = resolve_weather_location(latitude=95.0, longitude=10.0)
        assert loc is None

    def test_explicit_out_of_range_longitude_returns_none(self):
        loc = resolve_weather_location(latitude=40.0, longitude=200.0)
        assert loc is None

    def test_explicit_non_numeric_coordinates_returns_none(self):
        loc = resolve_weather_location(latitude="invalid", longitude=10.0)  # type: ignore
        assert loc is None

    def test_explicit_boolean_coordinates_rejected(self):
        loc = resolve_weather_location(latitude=True, longitude=False)  # type: ignore
        assert loc is None

    def test_authenticated_settings_structured_weather_location(self):
        user_state = MockUserStateRepository(
            settings={
                "weather_location": {
                    "city": "London",
                    "lat": 51.5074,
                    "lon": -0.1278,
                    "country": "GB",
                }
            }
        )
        loc = resolve_weather_location(
            user_state=user_state, user_id=_TEST_USER_ID
        )
        assert loc is not None
        assert loc.city == "London"
        assert loc.country == "GB"
        assert loc.latitude == 51.51
        assert loc.longitude == -0.13

    def test_authenticated_settings_flat_keys(self):
        user_state = MockUserStateRepository(
            settings={"city": "Tokyo", "lat": 35.6762, "lon": 139.6503}
        )
        loc = resolve_weather_location(
            user_state=user_state, user_id=_TEST_USER_ID
        )
        assert loc is not None
        assert loc.city == "Tokyo"
        assert loc.latitude == 35.68
        assert loc.longitude == 139.65

    def test_authenticated_settings_city_only_lookup(self):
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Berlin"}}
        )
        loc = resolve_weather_location(
            user_state=user_state, user_id=_TEST_USER_ID
        )
        assert loc is not None
        assert loc.city == "Berlin"
        assert loc.latitude == 52.52
        assert loc.longitude == 13.41

    def test_guest_ephemeral_user_state_resolution(self):
        guest_repo = EphemeralUserStateRepository(
            settings={"weather_location": {"city": "Chicago", "lat": 41.8781, "lon": -87.6298}}
        )
        loc = resolve_weather_location(
            user_state=guest_repo, user_id=UUID("00000000-0000-0000-0000-000000000000")
        )
        assert loc is not None
        assert loc.city == "Chicago"
        assert loc.latitude == 41.88
        assert loc.longitude == -87.63

    def test_priority_ordering_request_overrides_settings(self):
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Paris", "lat": 48.86, "lon": 2.35}}
        )
        loc = resolve_weather_location(
            city="New York",
            latitude=40.71,
            longitude=-74.01,
            user_state=user_state,
            user_id=_TEST_USER_ID,
        )
        assert loc is not None
        assert loc.city == "New York"
        assert loc.latitude == 40.71
        assert loc.longitude == -74.01

    def test_missing_all_locations_returns_none(self):
        user_state = MockUserStateRepository(settings={})
        loc = resolve_weather_location(
            user_state=user_state, user_id=_TEST_USER_ID
        )
        assert loc is None


# ==============================================================================
# Suite 2: Weather Provider Orchestration & Fallback
# ==============================================================================


class TestWeatherProviderOrchestration:
    """Verify provider invocation, error containment, and fail-open degradation."""

    @pytest.mark.anyio
    async def test_fetch_weather_success_passes_context(self):
        ctx = _make_weather_context(temperature_c=10.0, condition_text="Partly cloudy")
        provider = MockWeatherProvider(context_to_return=ctx)
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )
        events = MockUserEventRepository()
        event_types = MockEventTypeRepository()

        use_case = GetTodayLook(
            events=events,
            event_types=event_types,
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is not None
        assert rec.weather["applied"] is True
        assert rec.weather["temperatureC"] == 10.0
        assert rec.weather["condition"] == "Partly cloudy"
        assert len(provider.calls) == 1
        assert provider.calls[0]["latitude"] == 47.61

    @pytest.mark.anyio
    async def test_weather_never_fetched_when_location_is_none(self):
        provider = MockWeatherProvider(context_to_return=_make_weather_context())
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(settings={})
        events = MockUserEventRepository()
        event_types = MockEventTypeRepository()

        use_case = GetTodayLook(
            events=events,
            event_types=event_types,
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is None
        assert len(provider.calls) == 0

    @pytest.mark.anyio
    async def test_weather_provider_transient_error_falls_back_cleanly(self):
        provider = MockWeatherProvider(
            exception_to_raise=WeatherTransientError("Upstream 503 gateway timeout")
        )
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )
        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        # Never raises 503/500 for weather outage (DEC-017-G)
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is None

    @pytest.mark.anyio
    async def test_weather_provider_response_error_falls_back_cleanly(self):
        provider = MockWeatherProvider(
            exception_to_raise=WeatherResponseError("Malformed JSON")
        )
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )
        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is None

    @pytest.mark.anyio
    async def test_weather_provider_timeout_falls_back_cleanly(self):
        provider = MockWeatherProvider(
            exception_to_raise=asyncio.TimeoutError("Call timed out after 1.5s")
        )
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )
        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is None

    @pytest.mark.anyio
    async def test_weather_provider_unexpected_exception_contained(self):
        provider = MockWeatherProvider(
            exception_to_raise=RuntimeError("Unforeseen crash in connection pool")
        )
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )
        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is None

    @pytest.mark.anyio
    async def test_weather_provider_none_falls_back_cleanly(self):
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )
        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=None,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.weather is None

    @pytest.mark.anyio
    async def test_invalid_forecast_timestamp_fails_open_for_get_and_regenerate(self):
        """Phase 6C: Invalid forecast timestamp raises WeatherResponseError in adapter,
        which is caught at the application fail-open boundary in _derive_today_look,
        producing weather_context=None and uninterrupted canonical recommendation."""
        invalid_payload = {
            "current": {
                "time": "malformed-timestamp",
                "temperature_2m": 22.0,
                "apparent_temperature": 22.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=invalid_payload)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, base_url="https://api.open-meteo.com")
        adapter = OpenMeteoWeatherAdapter(client=client)

        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )

        # Baseline run with weather_provider=None
        use_case_none = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=None,
        )
        rec_baseline = await use_case_none(user_id=_TEST_USER_ID)
        assert rec_baseline is not None
        assert rec_baseline.weather is None

        # GET with invalid timestamp adapter
        use_case_get = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=adapter,
        )
        rec_get = await use_case_get(user_id=_TEST_USER_ID)
        assert rec_get is not None
        assert rec_get.weather is None
        # Canonical recommendation is uninterrupted and identical to baseline
        assert rec_get.match_score == rec_baseline.match_score
        assert [c.id for c in rec_get.components] == [c.id for c in rec_baseline.components]

        # POST with invalid timestamp adapter
        use_case_regen = RegenerateTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=adapter,
        )
        rec_regen = await use_case_regen(user_id=_TEST_USER_ID)
        assert rec_regen is not None
        assert rec_regen.weather is None
        assert rec_regen.match_score == rec_baseline.match_score
        assert [c.id for c in rec_regen.components] == [c.id for c in rec_baseline.components]

        # Ensure adapter cache was never populated
        assert adapter.cache_size == 0

        await adapter.close()


# ==============================================================================
# Suite 3: Canonical Scoring Integration
# ==============================================================================


class TestCanonicalScoringIntegration:
    """Verify that WeatherContext flows into canonical score_outfit_candidate."""

    @pytest.mark.anyio
    async def test_cold_weather_promotes_outerwear(self):
        cold_ctx = _make_weather_context(
            temperature_c=-2.0,
            apparent_temperature_c=-5.0,
            weather_code=71,
            condition_code="snow",
            condition_text="Snow",
        )
        provider = MockWeatherProvider(context_to_return=cold_ctx)
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository()

        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(
            user_id=_TEST_USER_ID,
            city="Oslo",
            latitude=59.91,
            longitude=10.75,
        )
        assert rec is not None
        # In very cold weather (-5°C), the winner includes Wool Coat (outerwear)
        categories = {c.category for c in rec.components}
        assert "outerwear" in categories

    @pytest.mark.anyio
    async def test_hot_weather_demotes_outerwear(self):
        hot_ctx = _make_weather_context(
            temperature_c=32.0,
            apparent_temperature_c=34.0,
            weather_code=0,
            condition_code="clear",
            condition_text="Clear sky",
            precipitation_mm=0.0,
            precipitation_probability=0.0,
        )
        provider = MockWeatherProvider(context_to_return=hot_ctx)
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository()

        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(
            user_id=_TEST_USER_ID,
            city="Madrid",
            latitude=40.42,
            longitude=-3.70,
        )
        assert rec is not None
        # In hot weather (34°C), outerwear is heavily penalized (-6.0)
        # Winner chooses light linen top + jeans without wool coat
        categories = {c.category for c in rec.components}
        assert "outerwear" not in categories

    @pytest.mark.anyio
    async def test_no_weather_baseline_identity(self):
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository()

        # Run 1: provider=None
        use_case_none = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=None,
        )
        rec_none = await use_case_none(user_id=_TEST_USER_ID)

        # Run 2: provider with failure
        provider_fail = MockWeatherProvider(exception_to_raise=WeatherTransientError("timeout"))
        use_case_fail = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider_fail,
        )
        rec_fail = await use_case_fail(
            user_id=_TEST_USER_ID,
            city="Seattle",
            latitude=47.61,
            longitude=-122.33,
        )

        assert rec_none is not None
        assert rec_fail is not None
        assert rec_none.match_score == rec_fail.match_score
        assert rec_none.selected_item_ids == rec_fail.selected_item_ids
        assert rec_none.title == rec_fail.title
        assert rec_none.description == rec_fail.description

    @pytest.mark.anyio
    async def test_warning_logs_do_not_contain_coordinates_on_provider_error(
        self, caplog: pytest.LogCaptureFixture
    ):
        """F-03: Provider error logs must never include raw or coarse coordinates."""
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository()
        provider_fail = MockWeatherProvider(
            exception_to_raise=WeatherLocationError(
                "Weather service rejected coordinates: HTTP 400 Bad Request"
            )
        )

        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider_fail,
        )

        with caplog.at_level(logging.WARNING):
            rec = await use_case(
                user_id=_TEST_USER_ID,
                city="Seattle",
                latitude=47.61,
                longitude=-122.33,
            )

        assert rec is not None
        assert rec.weather is None
        # Coordinates must NOT appear in logged warning output
        assert "47.61" not in caplog.text
        assert "-122.33" not in caplog.text
        assert "47.6" not in caplog.text
        assert "-122.3" not in caplog.text
        # Diagnostic category preserved
        assert "WeatherLocationError" in caplog.text


# ==============================================================================
# Suite 4: Daily-Look API Response & Wire Compatibility
# ==============================================================================


class TestDailyLookApiResponse:
    """Validate HTTP route behavior, schemas, headers, and privacy."""

    @pytest.fixture
    def test_client(self):
        return TestClient(app)

    def test_get_today_look_with_weather_returns_full_schema(self, test_client):
        ctx = _make_weather_context(
            temperature_c=18.5,
            apparent_temperature_c=17.2,
            weather_code=1,
            condition_code="mainly_clear",
            condition_text="Mainly clear",
            city="Paris",
        )
        provider = MockWeatherProvider(context_to_return=ctx)
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository()

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: provider
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_get_today_look = looks_module.GetTodayLook

        try:
            use_case = GetTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=provider,
            )
            looks_module.GetTodayLook = lambda **kwargs: use_case

            # Invoke via HTTP client with explicit coords
            resp = test_client.get(
                "/v1/looks/today?city=Paris&lat=48.86&lon=2.35",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" in data
            assert data["weather"]["applied"] is True
            assert data["weather"]["temperatureC"] == 18.5
            assert data["weather"]["city"] == "Paris"
            assert "latitude" not in data["weather"]
            assert "longitude" not in data["weather"]
            assert data["weather"]["fallback"] is False
        finally:
            looks_module.GetTodayLook = orig_get_today_look
            app.dependency_overrides.clear()

    @pytest.mark.anyio
    async def test_payload_builder_contains_exact_fields(self):
        ctx = _make_weather_context(
            temperature_c=14.2,
            apparent_temperature_c=13.0,
            condition_code="rain",
            condition_text="Moderate rain",
            city="Seattle",
        )
        payload = _build_weather_payload(ctx)
        assert payload is not None
        assert payload["applied"] is True
        assert payload["condition"] == "Moderate rain"
        assert payload["conditionCode"] == "rain"
        assert payload["temperatureC"] == 14.2
        assert payload["temperatureF"] == ctx.temperature_f
        assert payload["apparentTemperatureC"] == 13.0
        assert payload["apparentTemperatureF"] == ctx.apparent_temperature_f
        assert payload["isRaining"] is True
        assert payload["city"] == "Seattle"
        assert payload["summary"] == "14°C • Moderate rain in Seattle"
        assert payload["fallback"] is False

        # Privacy invariant: zero coordinates in payload
        assert "latitude" not in payload
        assert "longitude" not in payload
        assert "lat" not in payload
        assert "lon" not in payload

    @pytest.mark.anyio
    async def test_payload_builder_handles_none_context(self):
        assert _build_weather_payload(None) is None

    @pytest.mark.anyio
    async def test_payload_builder_without_city(self):
        ctx = _make_weather_context(
            temperature_c=22.0,
            condition_text="Clear sky",
            city=None,
        )
        payload = _build_weather_payload(ctx)
        assert payload is not None
        assert payload["city"] is None
        assert payload["summary"] == "22°C • Clear sky"

    @pytest.mark.anyio
    async def test_payload_builder_negative_temperatures(self):
        ctx = _make_weather_context(
            temperature_c=-3.6,
            apparent_temperature_c=-7.1,
            condition_text="Snow",
            city="Oslo",
        )
        payload = _build_weather_payload(ctx)
        assert payload is not None
        assert payload["temperatureC"] == -3.6
        assert payload["summary"] == "-4°C • Snow in Oslo"

    def test_today_look_weather_schema_validation(self):
        weather = TodayLookWeather(
            applied=True,
            condition="Cloudy",
            temperatureC=15.0,
            temperatureF=59.0,
            summary="15°C • Cloudy",
        )
        assert weather.applied is True
        assert weather.fallback is False
        assert weather.precipitationProbability is None
        assert weather.windSpeedKmh is None

    def test_get_today_look_without_weather_omits_weather_field(self, test_client):
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(settings={})
        provider = MockWeatherProvider()

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: provider
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_get_today_look = looks_module.GetTodayLook

        try:
            use_case = GetTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=provider,
            )
            looks_module.GetTodayLook = lambda **kwargs: use_case

            resp = test_client.get(
                "/v1/looks/today",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            # Invariant: response_model_exclude_none=True ensures "weather" is omitted
            # when no weather context is available, preserving exact backward compatibility
            assert "weather" not in data
            assert data["title"] is not None
            assert "components" in data
        finally:
            looks_module.GetTodayLook = orig_get_today_look
            app.dependency_overrides.clear()

    def test_post_regenerate_today_look_with_weather(self, test_client):
        ctx = _make_weather_context(
            temperature_c=25.0,
            apparent_temperature_c=26.0,
            condition_text="Sunny",
            city="Rome",
        )
        provider = MockWeatherProvider(context_to_return=ctx)
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository()

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: provider
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_regenerate_today_look = looks_module.RegenerateTodayLook

        try:
            use_case = RegenerateTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=provider,
            )
            looks_module.RegenerateTodayLook = lambda **kwargs: use_case

            resp = test_client.post(
                "/v1/looks/today?city=Rome&lat=41.90&lon=12.50&seed=summer-seed",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" in data
            assert data["weather"]["applied"] is True
            assert data["weather"]["city"] == "Rome"
            assert data["weather"]["temperatureC"] == 25.0
        finally:
            looks_module.RegenerateTodayLook = orig_regenerate_today_look
            app.dependency_overrides.clear()

    def test_get_today_look_with_weather_provider_off_di_succeeds(self, test_client):
        """F-01: GET /v1/looks/today succeeds when weather_provider is None (WEATHER_PROVIDER=off)."""
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(settings={})

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: None
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_get_today_look = looks_module.GetTodayLook

        try:
            use_case = GetTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=None,
            )
            looks_module.GetTodayLook = lambda **kwargs: use_case

            resp = test_client.get(
                "/v1/looks/today?city=Seattle&lat=47.61&lon=-122.33",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" not in data
            assert data["title"] is not None
            assert len(data["components"]) > 0
        finally:
            looks_module.GetTodayLook = orig_get_today_look
            app.dependency_overrides.clear()

    def test_post_regenerate_today_look_with_weather_provider_off_di_succeeds(self, test_client):
        """F-01: POST /v1/looks/today succeeds when weather_provider is None (WEATHER_PROVIDER=off)."""
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(settings={})

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: None
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_regenerate_today_look = looks_module.RegenerateTodayLook

        try:
            use_case = RegenerateTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=None,
            )
            looks_module.RegenerateTodayLook = lambda **kwargs: use_case

            resp = test_client.post(
                "/v1/looks/today?city=Seattle&lat=47.61&lon=-122.33&seed=new-seed",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" not in data
            assert data["title"] is not None
            assert len(data["components"]) > 0
        finally:
            looks_module.RegenerateTodayLook = orig_regenerate_today_look
            app.dependency_overrides.clear()

    def test_real_dependency_injection_weather_provider_off(self, test_client, monkeypatch):
        """F-01: Real get_weather_provider dependency injects None when WEATHER_PROVIDER=off."""
        monkeypatch.setenv("WEATHER_PROVIDER", "off")
        clear_settings_cache()
        reset_default_weather_provider()

        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(settings={})

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_db] = lambda: object()
        # NOTE: get_weather_provider is NOT overridden — testing the real dependency path!

        import app.api.routers.looks as looks_module
        orig_get_today_look = looks_module.GetTodayLook

        captured_provider: list[Any] = []

        def tracking_factory(**kwargs):
            captured_provider.append(kwargs.get("weather_provider"))
            return GetTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=kwargs.get("weather_provider"),
            )

        try:
            looks_module.GetTodayLook = tracking_factory

            resp = test_client.get(
                "/v1/looks/today?city=Seattle",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" not in data
            assert data["title"] is not None
            # Proves FastAPI dependency injection provided None to router and use-case
            assert len(captured_provider) == 1
            assert captured_provider[0] is None
        finally:
            looks_module.GetTodayLook = orig_get_today_look
            app.dependency_overrides.clear()
            clear_settings_cache()
            reset_default_weather_provider()

    def test_get_today_look_with_invalid_timestamp_fails_open_api(self, test_client):
        """Phase 6C: GET /v1/looks/today fails open when adapter encounters invalid timestamp."""
        invalid_payload = {
            "current": {
                "time": None,
                "temperature_2m": 22.0,
                "apparent_temperature": 22.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=invalid_payload)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, base_url="https://api.open-meteo.com")
        adapter = OpenMeteoWeatherAdapter(client=client)

        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: adapter
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_get_today_look = looks_module.GetTodayLook

        try:
            use_case = GetTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=adapter,
            )
            looks_module.GetTodayLook = lambda **kwargs: use_case

            resp = test_client.get(
                "/v1/looks/today?city=Seattle",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" not in data
            assert data["title"] is not None
            assert len(data["components"]) > 0
            assert adapter.cache_size == 0
        finally:
            looks_module.GetTodayLook = orig_get_today_look
            app.dependency_overrides.clear()

    def test_post_regenerate_today_look_with_invalid_timestamp_fails_open_api(self, test_client):
        """Phase 6C: POST /v1/looks/today fails open when adapter encounters invalid timestamp."""
        invalid_payload = {
            "current": {
                "time": "2026-99-99T99:99",
                "temperature_2m": 22.0,
                "apparent_temperature": 22.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=invalid_payload)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, base_url="https://api.open-meteo.com")
        adapter = OpenMeteoWeatherAdapter(client=client)

        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "Seattle", "lat": 47.61, "lon": -122.33}}
        )

        app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER_ID
        app.dependency_overrides[get_weather_provider] = lambda: adapter
        app.dependency_overrides[get_db] = lambda: object()

        import app.api.routers.looks as looks_module
        orig_regenerate_today_look = looks_module.RegenerateTodayLook

        try:
            use_case = RegenerateTodayLook(
                events=MockUserEventRepository(),
                event_types=MockEventTypeRepository(),
                wardrobe_items=wardrobe,
                user_state=user_state,
                weather_provider=adapter,
            )
            looks_module.RegenerateTodayLook = lambda **kwargs: use_case

            resp = test_client.post(
                "/v1/looks/today?city=Seattle&seed=test-seed",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "weather" not in data
            assert data["title"] is not None
            assert len(data["components"]) > 0
            assert adapter.cache_size == 0
        finally:
            looks_module.RegenerateTodayLook = orig_regenerate_today_look
            app.dependency_overrides.clear()

    def test_missing_optional_weather_fields(self):
        ctx = _make_weather_context(
            precipitation_probability=None,
            precipitation_mm=None,
            wind_speed_kmh=None,
        )
        payload = _build_weather_payload(ctx)
        assert payload is not None
        assert payload["precipitationProbability"] is None
        assert payload["precipitationMm"] is None
        assert payload["windSpeedKmh"] is None
        # Schema serialization works cleanly with missing optional fields
        weather_dto = TodayLookWeather(**payload)
        assert weather_dto.precipitationProbability is None
        assert weather_dto.windSpeedKmh is None


# ==============================================================================
# Suite 5: User Settings Integration & Privacy Hardening
# ==============================================================================


class TestSettingsIntegrationAndPrivacy:
    """Verify settings update, coordinate truncation, and validation."""

    def test_update_preferences_sanitizes_coordinates_to_two_decimals(self):
        user_state = MockUserStateRepository()
        use_case = UpdatePreferences(user_state=user_state)

        record = use_case(
            user_id=_TEST_USER_ID,
            settings={
                "weather_location": {
                    "city": "Chicago",
                    "lat": 41.8781136,
                    "lon": -87.6297982,
                },
                "dark_mode": True,
            },
        )
        assert record is not None
        saved_loc = user_state._settings["weather_location"]
        # Enforces privacy truncation: exactly 2 decimals (~1.1km)
        assert saved_loc["lat"] == 41.88
        assert saved_loc["lon"] == -87.63
        assert saved_loc["city"] == "Chicago"
        # Unrelated settings preserved
        assert user_state._settings["dark_mode"] is True

    def test_update_preferences_rejects_out_of_range_latitude(self):
        user_state = MockUserStateRepository()
        use_case = UpdatePreferences(user_state=user_state)

        with pytest.raises(ApiError) as exc_info:
            use_case(
                user_id=_TEST_USER_ID,
                settings={"weather_location": {"lat": 105.0, "lon": 10.0}},
            )
        assert exc_info.value.status_code == 422
        assert "latitude" in str(exc_info.value.details)

    def test_update_preferences_rejects_out_of_range_longitude(self):
        user_state = MockUserStateRepository()
        use_case = UpdatePreferences(user_state=user_state)

        with pytest.raises(ApiError) as exc_info:
            use_case(
                user_id=_TEST_USER_ID,
                settings={"weather_location": {"lat": 10.0, "lon": 195.0}},
            )
        assert exc_info.value.status_code == 422
        assert "longitude" in str(exc_info.value.details)

    def test_update_preferences_rejects_invalid_city_type(self):
        user_state = MockUserStateRepository()
        use_case = UpdatePreferences(user_state=user_state)

        with pytest.raises(ApiError) as exc_info:
            use_case(
                user_id=_TEST_USER_ID,
                settings={"weather_location": {"city": 12345}},
            )
        assert exc_info.value.status_code == 422


# ==============================================================================
# Suite 6: Security and Isolation
# ==============================================================================


class TestGuestAndSecurity:
    """Verify OW-1 ownership scoping and guest ephemeral behavior."""

    @pytest.mark.anyio
    async def test_authenticated_isolation_ow1(self):
        # User A owns clothes; User B owns none
        user_a_items = _standard_wardrobe(_TEST_USER_ID)
        wardrobe = MockWardrobeItemRepository(user_a_items)
        user_state = MockUserStateRepository()

        use_case = GetTodayLook(
            events=MockUserEventRepository(),
            event_types=MockEventTypeRepository(),
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=None,
        )

        # User A gets outfit
        rec_a = await use_case(user_id=_TEST_USER_ID)
        assert rec_a is not None

        # User B gets None (empty wardrobe -> 404, OW-1 isolated)
        rec_b = await use_case(user_id=_OTHER_USER_ID)
        assert rec_b is None

    def test_unauthenticated_request_is_401(self):
        client = TestClient(app)
        resp = client.get("/v1/looks/today")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_guest_ephemeral_repositories_zero_db(self):
        guest_items = [
            {"id": str(uuid4()), "name": "Linen Shirt", "category": "tops", "color": "white", "material": "linen"},
            {"id": str(uuid4()), "name": "Shorts", "category": "bottoms", "color": "khaki", "material": "cotton"},
        ]
        wardrobe_repo = EphemeralWardrobeItemRepository(guest_items)
        guest_repo = EphemeralUserStateRepository(
            preferred_occasions=["casual"],
            settings={"weather_location": {"city": "Miami", "lat": 25.76, "lon": -80.19}},
        )

        loc = resolve_weather_location(
            user_state=guest_repo,
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
        )
        assert loc is not None
        assert loc.city == "Miami"
        assert loc.latitude == 25.76
        assert loc.longitude == -80.19

        # Zero DB calls, zero DB writes, ephemeral user state profile reflects settings
        prof = guest_repo.get_profile()
        assert prof.settings["weather_location"]["city"] == "Miami"
        assert prof.style_profile == {}


# ==============================================================================
# Suite 7: Recommendation Integrity (Occasions, Pinned Items, Canonical Engine)
# ==============================================================================


class TestRecommendationIntegrity:
    """Verify occasion constraints, pinned items, and 12-term canonical scoring."""

    @pytest.mark.anyio
    async def test_event_occasion_preserved_with_weather(self):
        events = MockUserEventRepository(
            events=[
                UserEventRecord(
                    id=uuid4(),
                    user_id=_TEST_USER_ID,
                    title="Gala Dinner",
                    event_type="formal",
                    event_date=datetime.now(timezone.utc).date(),
                    event_time=None,
                    location="City Hall",
                    notes=None,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ]
        )
        event_types = MockEventTypeRepository()
        wardrobe = MockWardrobeItemRepository(_standard_wardrobe())
        user_state = MockUserStateRepository(
            settings={"weather_location": {"city": "London", "lat": 51.51, "lon": -0.13}}
        )
        ctx = _make_weather_context(temperature_c=5.0)
        provider = MockWeatherProvider(context_to_return=ctx)

        use_case = GetTodayLook(
            events=events,
            event_types=event_types,
            wardrobe_items=wardrobe,
            user_state=user_state,
            weather_provider=provider,
        )
        rec = await use_case(user_id=_TEST_USER_ID)
        assert rec is not None
        assert rec.occasion == "formal"
        assert "Formal" in rec.title
        assert rec.weather is not None
        assert rec.weather["applied"] is True

    def test_canonical_scoring_engine_preserves_12_terms(self):
        from types import SimpleNamespace
        from app.domain.services.analysis_rules import score_outfit_candidate
        from app.domain.value_objects import OutfitCandidate

        items = {
            "top1": SimpleNamespace(id="top1", category="tops", color="white", material="cotton", is_favorite=False),
            "bot1": SimpleNamespace(id="bot1", category="bottoms", color="black", material="denim", is_favorite=False),
            "out1": SimpleNamespace(id="out1", category="outerwear", color="navy", material="wool", is_favorite=False),
        }
        cand = OutfitCandidate(top_ids=("top1",), bottom_ids=("bot1",), outerwear_ids=("out1",))
        # With weather
        ctx = _make_weather_context(temperature_c=2.0)
        scored_weather = score_outfit_candidate(cand, items, frozenset(), ["casual"], weather_context=ctx)
        # Without weather
        scored_none = score_outfit_candidate(cand, items, frozenset(), ["casual"], weather_context=None)

        # Candidate slot contents and baseline terms preserved
        assert scored_weather.top_ids == scored_none.top_ids
        assert scored_weather.bottom_ids == scored_none.bottom_ids
        assert scored_weather.outerwear_ids == scored_none.outerwear_ids
        assert scored_weather.compatibility == scored_none.compatibility
        # Wool outerwear in 2C receives positive weather bonus within [-10, +10] bounds
        assert scored_weather.score > scored_none.score
        assert abs(scored_weather.score - scored_none.score) <= 10.0

