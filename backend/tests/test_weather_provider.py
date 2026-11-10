"""Exhaustive tests for Weather Provider Port, Domain Value Objects, and Open-Meteo Adapter.

Validates Stage 2 P1-3 Phase 1 requirements:
- Value object range validation, unit normalization, timestamps, immutability, privacy.
- Open-Meteo response parsing, WMO code mapping, fallback behaviors.
- Error handling: timeouts, connection errors, HTTP 4xx/5xx, malformed JSON, missing fields.
- Zero leakage of httpx/transport exceptions into domain code.
- In-memory caching, TTL expiry, coarse coordinate quantization.
- Dependency injection, settings configuration, and clean HTTP client lifecycle.
- Zero live network requests (all HTTP mocked via httpx.MockTransport).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Any, Optional

import httpx
import pytest
from pydantic import ValidationError

from app.api.deps import get_weather_provider
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.external import (
    WeatherError,
    WeatherLocationError,
    WeatherProvider,
    WeatherResponseError,
    WeatherTransientError,
)
from app.domain.value_objects import WeatherContext, WeatherLocation
from app.infrastructure.external.weather import (
    OpenMeteoWeatherAdapter,
    WMO_CODE_MAP,
    create_weather_provider,
    get_default_weather_provider,
    reset_default_weather_provider,
    resolve_wmo_code,
)


# ==============================================================================
# 1. Domain Value Object Tests
# ==============================================================================


class TestWeatherLocationValueObject:
    """Validate WeatherLocation privacy invariants, range limits, and immutability."""

    def test_valid_location_creation_and_coarse_rounding(self):
        # Precise coordinate 47.606211, -122.332071 must be rounded to 2 decimal places
        loc = WeatherLocation(
            latitude=47.606211,
            longitude=-122.332071,
            city="Seattle",
            country="US",
        )
        assert loc.latitude == 47.61
        assert loc.longitude == -122.33
        assert loc.city == "Seattle"
        assert loc.country == "US"

    def test_optional_city_and_country_defaults(self):
        loc = WeatherLocation(latitude=10.0, longitude=20.0)
        assert loc.city is None
        assert loc.country is None

    def test_whitespace_stripped_for_city_and_country(self):
        loc = WeatherLocation(
            latitude=10.0, longitude=20.0, city="  Paris  ", country="  FR  "
        )
        assert loc.city == "Paris"
        assert loc.country == "FR"

    def test_empty_string_city_country_normalized_to_none(self):
        loc = WeatherLocation(
            latitude=10.0, longitude=20.0, city="   ", country=""
        )
        assert loc.city is None
        assert loc.country is None

    def test_latitude_out_of_bounds_raises(self):
        with pytest.raises(ValueError, match="Latitude must be between -90.0 and 90.0"):
            WeatherLocation(latitude=90.1, longitude=0.0)

        with pytest.raises(ValueError, match="Latitude must be between -90.0 and 90.0"):
            WeatherLocation(latitude=-90.01, longitude=0.0)

    def test_longitude_out_of_bounds_raises(self):
        with pytest.raises(ValueError, match="Longitude must be between -180.0 and 180.0"):
            WeatherLocation(latitude=0.0, longitude=180.05)

        with pytest.raises(ValueError, match="Longitude must be between -180.0 and 180.0"):
            WeatherLocation(latitude=0.0, longitude=-180.05)

    def test_non_numeric_coordinates_raise(self):
        with pytest.raises(ValueError, match="Latitude must be a number"):
            WeatherLocation(latitude="invalid", longitude=0.0)  # type: ignore

        with pytest.raises(ValueError, match="Longitude must be a number"):
            WeatherLocation(latitude=0.0, longitude=True)  # type: ignore

    def test_immutability_enforced(self):
        loc = WeatherLocation(latitude=51.5, longitude=-0.12)
        with pytest.raises(AttributeError):
            loc.latitude = 52.0  # type: ignore


class TestWeatherContextValueObject:
    """Validate WeatherContext numeric validation, unit conversion, and properties."""

    @pytest.fixture
    def valid_timestamps(self):
        now = datetime.now(timezone.utc)
        return now, now

    def test_valid_weather_context_creation(self, valid_timestamps):
        ts, ret = valid_timestamps
        loc = WeatherLocation(latitude=40.71, longitude=-74.01, city="New York")
        ctx = WeatherContext(
            temperature_c=18.5,
            apparent_temperature_c=17.8,
            weather_code=2,
            condition_code="partly_cloudy",
            condition_text="Partly cloudy",
            forecast_timestamp=ts,
            retrieved_at=ret,
            precipitation_probability=20.0,
            precipitation_mm=0.0,
            relative_humidity_pct=65.0,
            wind_speed_kmh=12.5,
            is_day=True,
            location=loc,
        )
        assert ctx.temperature_c == 18.5
        assert ctx.apparent_temperature_c == 17.8
        assert ctx.temperature_f == 65.3
        assert ctx.apparent_temperature_f == 64.0
        assert ctx.weather_code == 2
        assert ctx.condition_code == "partly_cloudy"
        assert ctx.is_raining is False
        assert ctx.is_day is True
        assert ctx.location == loc

    def test_missing_optional_fields_explicitly_none(self, valid_timestamps):
        ts, ret = valid_timestamps
        ctx = WeatherContext(
            temperature_c=22.0,
            apparent_temperature_c=22.0,
            weather_code=0,
            condition_code="clear",
            condition_text="Clear sky",
            forecast_timestamp=ts,
            retrieved_at=ret,
        )
        assert ctx.precipitation_probability is None
        assert ctx.precipitation_mm is None
        assert ctx.relative_humidity_pct is None
        assert ctx.wind_speed_kmh is None
        assert ctx.is_day is None
        assert ctx.location is None

    def test_is_raining_property_logic(self, valid_timestamps):
        ts, ret = valid_timestamps
        # Rain code 61
        ctx_rain_code = WeatherContext(
            temperature_c=10.0,
            apparent_temperature_c=8.0,
            weather_code=61,
            condition_code="rain",
            condition_text="Slight rain",
            forecast_timestamp=ts,
            retrieved_at=ret,
        )
        assert ctx_rain_code.is_raining is True

        # Non-rain code but precipitation mm > 0.1
        ctx_precip_mm = WeatherContext(
            temperature_c=12.0,
            apparent_temperature_c=11.0,
            weather_code=3,
            condition_code="overcast",
            condition_text="Overcast",
            precipitation_mm=0.5,
            forecast_timestamp=ts,
            retrieved_at=ret,
        )
        assert ctx_precip_mm.is_raining is True

        # Non-rain code but high probability (>= 50%)
        ctx_precip_prob = WeatherContext(
            temperature_c=12.0,
            apparent_temperature_c=11.0,
            weather_code=3,
            condition_code="overcast",
            condition_text="Overcast",
            precipitation_probability=60.0,
            forecast_timestamp=ts,
            retrieved_at=ret,
        )
        assert ctx_precip_prob.is_raining is True

        # Dry conditions
        ctx_dry = WeatherContext(
            temperature_c=25.0,
            apparent_temperature_c=25.0,
            weather_code=0,
            condition_code="clear",
            condition_text="Clear sky",
            precipitation_probability=10.0,
            precipitation_mm=0.0,
            forecast_timestamp=ts,
            retrieved_at=ret,
        )
        assert ctx_dry.is_raining is False

    def test_temperature_out_of_bounds_raises(self, valid_timestamps):
        ts, ret = valid_timestamps
        with pytest.raises(ValueError, match="temperature_c outside reasonable"):
            WeatherContext(
                temperature_c=-95.0,
                apparent_temperature_c=-95.0,
                weather_code=0,
                condition_code="clear",
                condition_text="Clear sky",
                forecast_timestamp=ts,
                retrieved_at=ret,
            )

        with pytest.raises(ValueError, match="temperature_c outside reasonable"):
            WeatherContext(
                temperature_c=75.0,
                apparent_temperature_c=75.0,
                weather_code=0,
                condition_code="clear",
                condition_text="Clear sky",
                forecast_timestamp=ts,
                retrieved_at=ret,
            )

    def test_weather_code_out_of_bounds_raises(self, valid_timestamps):
        ts, ret = valid_timestamps
        with pytest.raises(ValueError, match="weather_code must be in WMO range 0-99"):
            WeatherContext(
                temperature_c=20.0,
                apparent_temperature_c=20.0,
                weather_code=100,
                condition_code="unknown",
                condition_text="Unknown",
                forecast_timestamp=ts,
                retrieved_at=ret,
            )

    def test_invalid_precipitation_probability_raises(self, valid_timestamps):
        ts, ret = valid_timestamps
        with pytest.raises(ValueError, match="precipitation_probability must be between 0.0 and 100.0"):
            WeatherContext(
                temperature_c=20.0,
                apparent_temperature_c=20.0,
                weather_code=0,
                condition_code="clear",
                condition_text="Clear sky",
                forecast_timestamp=ts,
                retrieved_at=ret,
                precipitation_probability=105.0,
            )

    def test_negative_precipitation_mm_raises(self, valid_timestamps):
        ts, ret = valid_timestamps
        with pytest.raises(ValueError, match="precipitation_mm cannot be negative"):
            WeatherContext(
                temperature_c=20.0,
                apparent_temperature_c=20.0,
                weather_code=0,
                condition_code="clear",
                condition_text="Clear sky",
                forecast_timestamp=ts,
                retrieved_at=ret,
                precipitation_mm=-1.0,
            )

    def test_immutability_enforced(self, valid_timestamps):
        ts, ret = valid_timestamps
        ctx = WeatherContext(
            temperature_c=20.0,
            apparent_temperature_c=20.0,
            weather_code=0,
            condition_code="clear",
            condition_text="Clear sky",
            forecast_timestamp=ts,
            retrieved_at=ret,
        )
        with pytest.raises(AttributeError):
            ctx.temperature_c = 25.0  # type: ignore


# ==============================================================================
# 2. WMO Code Mapping Tests
# ==============================================================================


class TestWMOCodeMapping:
    """Validate authoritative WMO weather interpretation code resolutions."""

    @pytest.mark.parametrize(
        "code,expected_cat,expected_text_contains",
        [
            (0, "clear", "Clear"),
            (1, "mainly_clear", "clear"),
            (2, "partly_cloudy", "cloudy"),
            (3, "overcast", "Overcast"),
            (45, "fog", "Fog"),
            (51, "drizzle", "drizzle"),
            (61, "rain", "rain"),
            (65, "rain", "Heavy rain"),
            (71, "snow", "snow"),
            (80, "rain_showers", "showers"),
            (85, "snow_showers", "snow showers"),
            (95, "thunderstorm", "Thunderstorm"),
            (99, "thunderstorm_hail", "hail"),
        ],
    )
    def test_known_wmo_codes_resolve_accurately(
        self, code: int, expected_cat: str, expected_text_contains: str
    ):
        cat, text = resolve_wmo_code(code)
        assert cat == expected_cat
        assert expected_text_contains.lower() in text.lower()

    def test_unknown_wmo_code_falls_back_cleanly(self):
        cat, text = resolve_wmo_code(42)
        assert cat == "unknown"
        assert "42" in text


# ==============================================================================
# 3. Open-Meteo Adapter Tests (Mocked Transport)
# ==============================================================================


def create_mock_transport(handler) -> httpx.AsyncClient:
    """Helper creating an httpx.AsyncClient backed by an in-memory mock handler."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="https://api.open-meteo.com")


class TestOpenMeteoAdapterResponses:
    """Validate Open-Meteo API response parsing across all variations."""

    @pytest.mark.anyio
    async def test_successful_full_response_parsing(self):
        payload = {
            "latitude": 47.6,
            "longitude": -122.33,
            "generationtime_ms": 0.05,
            "utc_offset_seconds": 0,
            "timezone": "UTC",
            "current": {
                "time": "2026-11-02T12:00",
                "interval": 900,
                "temperature_2m": 14.2,
                "apparent_temperature": 13.5,
                "precipitation_probability": 35.0,
                "precipitation": 0.2,
                "relative_humidity_2m": 78.0,
                "wind_speed_10m": 15.4,
                "weather_code": 61,
                "is_day": 1,
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/forecast"
            assert "latitude=47.60" in request.url.query.decode()
            assert "longitude=-122.33" in request.url.query.decode()
            assert "timezone=UTC" in request.url.query.decode()
            assert "current=" in request.url.query.decode()
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        weather = await adapter.get_weather(
            latitude=47.601, longitude=-122.331, city="Seattle", country="US"
        )
        assert weather is not None
        assert weather.temperature_c == 14.2
        assert weather.apparent_temperature_c == 13.5
        assert weather.temperature_f == 57.6
        assert weather.apparent_temperature_f == 56.3
        assert weather.precipitation_probability == 35.0
        assert weather.precipitation_mm == 0.2
        assert weather.relative_humidity_pct == 78.0
        assert weather.wind_speed_kmh == 15.4
        assert weather.weather_code == 61
        assert weather.condition_code == "rain"
        assert weather.condition_text == "Slight rain"
        assert weather.is_day is True
        assert weather.is_raining is True
        assert weather.location is not None
        assert weather.location.latitude == 47.6
        assert weather.location.longitude == -122.33
        assert weather.location.city == "Seattle"
        assert weather.location.country == "US"
        assert weather.forecast_timestamp == datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        assert weather.forecast_timestamp.tzinfo == timezone.utc

        await adapter.close()

    @pytest.mark.anyio
    async def test_non_zero_offset_local_timestamp_normalized_to_utc(self):
        """F-02 / F-04: Non-zero-offset fixture (Seattle, PST UTC-8) correctly normalizes to UTC instant."""
        payload = {
            "latitude": 47.6,
            "longitude": -122.33,
            "utc_offset_seconds": -28800,  # PST: -8 hours
            "timezone": "America/Los_Angeles",
            "current": {
                "time": "2026-11-02T04:00",  # 4:00 AM local PST -> 12:00 PM UTC
                "temperature_2m": 12.0,
                "apparent_temperature": 11.5,
                "weather_code": 3,
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        weather = await adapter.get_weather(
            latitude=47.60, longitude=-122.33, city="Seattle", country="US"
        )
        assert weather is not None
        expected_utc = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        assert weather.forecast_timestamp == expected_utc
        # Verify exact instant match
        assert weather.forecast_timestamp.timestamp() == expected_utc.timestamp()
        assert weather.forecast_timestamp.tzinfo == timezone.utc

        await adapter.close()

    @pytest.mark.anyio
    async def test_aware_timestamp_with_offset_no_double_offset_conversion(self):
        """F-02: Aware ISO timestamps must not apply utc_offset_seconds twice."""
        payload = {
            "latitude": 47.6,
            "longitude": -122.33,
            "utc_offset_seconds": -28800,  # -8 hours in root metadata
            "timezone": "America/Los_Angeles",
            "current": {
                # Already carries -08:00 offset in ISO string
                "time": "2026-11-02T04:00:00-08:00",
                "temperature_2m": 12.0,
                "apparent_temperature": 11.5,
                "weather_code": 0,
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        weather = await adapter.get_weather(latitude=47.6, longitude=-122.33)
        assert weather is not None
        expected_utc = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        assert weather.forecast_timestamp == expected_utc
        assert weather.forecast_timestamp.timestamp() == expected_utc.timestamp()
        assert weather.forecast_timestamp.tzinfo == timezone.utc

        await adapter.close()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "invalid_time",
        [None, "", "   ", "malformed-timestamp", "2026-99-99T99:99", 12345],
    )
    async def test_missing_or_malformed_timestamp_safely_falls_back_to_utc_now(
        self, invalid_time
    ):
        """Phase 6C: Missing or invalid time field raises WeatherResponseError and is not cached."""
        payload = {
            "current": {
                "time": invalid_time,
                "temperature_2m": 18.0,
                "apparent_temperature": 18.0,
                "weather_code": 1,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherResponseError) as exc_info:
            await adapter.get_weather(latitude=40.71, longitude=-74.01)

        err_msg = str(exc_info.value)
        assert "Missing or invalid forecast timestamp in weather response" in err_msg
        assert "40.71" not in err_msg
        assert "-74.01" not in err_msg
        assert "40.7" not in err_msg
        assert "-74.0" not in err_msg
        if invalid_time is not None and str(invalid_time).strip():
            assert str(invalid_time) not in err_msg

        # Prohibit caching an invalid response
        assert adapter.cache_size == 0

        await adapter.close()

    @pytest.mark.anyio
    async def test_invalid_timestamp_not_cached_and_subsequent_valid_request_succeeds(self):
        """Phase 6C: Invalid timestamp is not cached and does not poison subsequent requests."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First request returns invalid timestamp
                return httpx.Response(
                    200,
                    json={
                        "current": {
                            "time": "not-a-timestamp",
                            "temperature_2m": 18.0,
                            "apparent_temperature": 18.0,
                            "weather_code": 1,
                        }
                    },
                )
            # Second request returns valid timestamp
            return httpx.Response(
                200,
                json={
                    "timezone": "UTC",
                    "utc_offset_seconds": 0,
                    "current": {
                        "time": "2026-11-02T12:00",
                        "temperature_2m": 20.0,
                        "apparent_temperature": 20.0,
                        "weather_code": 0,
                    },
                },
            )

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        # First call fails and is not cached
        with pytest.raises(WeatherResponseError) as exc_info:
            await adapter.get_weather(latitude=40.71, longitude=-74.01)
        assert "Missing or invalid forecast timestamp in weather response" in str(exc_info.value)
        assert adapter.cache_size == 0
        assert call_count == 1

        # Second call to same coordinates succeeds and populates cache
        weather = await adapter.get_weather(latitude=40.71, longitude=-74.01)
        assert weather is not None
        assert weather.temperature_c == 20.0
        assert weather.forecast_timestamp == datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        assert adapter.cache_size == 1
        assert call_count == 2

        # Third call served from cache (handler not invoked)
        cached_weather = await adapter.get_weather(latitude=40.71, longitude=-74.01)
        assert cached_weather is not None
        assert cached_weather.temperature_c == 20.0
        assert call_count == 2

        await adapter.close()

    @pytest.mark.anyio
    async def test_missing_optional_fields_handled_gracefully(self):
        # Open-Meteo returns minimal fields without precipitation or wind
        payload = {
            "current": {
                "time": "2026-11-02T14:30",
                "temperature_2m": 21.0,
                "apparent_temperature": 21.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        weather = await adapter.get_weather(latitude=34.05, longitude=-118.24)
        assert weather is not None
        assert weather.temperature_c == 21.0
        assert weather.apparent_temperature_c == 21.0
        assert weather.weather_code == 0
        assert weather.condition_code == "clear"
        assert weather.precipitation_probability is None
        assert weather.precipitation_mm is None
        assert weather.relative_humidity_pct is None
        assert weather.wind_speed_kmh is None
        assert weather.is_day is None
        assert weather.is_raining is False

        await adapter.close()

    @pytest.mark.anyio
    async def test_missing_required_temperature_raises_response_error(self):
        payload = {
            "current": {
                "apparent_temperature": 15.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherResponseError, match="Missing required field 'temperature_2m'"):
            await adapter.get_weather(latitude=10.0, longitude=20.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_missing_current_block_raises_response_error(self):
        payload = {"daily": {}}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherResponseError, match="Missing or invalid 'current' block"):
            await adapter.get_weather(latitude=10.0, longitude=20.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_malformed_json_raises_response_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>Bad Gateway</html>", headers={"Content-Type": "text/html"})

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherResponseError, match="Malformed JSON response"):
            await adapter.get_weather(latitude=10.0, longitude=20.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_open_meteo_error_payload_raises_response_error(self):
        payload = {"error": True, "reason": "Latitude must be in range of -90 to 90°"}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherLocationError, match="Weather service rejected coordinates"):
            await adapter.get_weather(latitude=89.99, longitude=0.0)

        await adapter.close()


class TestOpenMeteoAdapterTransportErrors:
    """Validate HTTP and transport failure mapping to domain WeatherError hierarchy."""

    @pytest.mark.anyio
    async def test_http_400_maps_to_location_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="Invalid coordinate parameter")

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherLocationError, match="rejected coordinates"):
            await adapter.get_weather(latitude=45.0, longitude=90.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_http_500_maps_to_transient_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherTransientError, match="upstream server error HTTP 500"):
            await adapter.get_weather(latitude=45.0, longitude=90.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_http_503_maps_to_transient_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherTransientError, match="upstream server error HTTP 503"):
            await adapter.get_weather(latitude=45.0, longitude=90.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_timeout_maps_to_transient_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Request timed out", request=request)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client, timeout_s=1.5)

        with pytest.raises(WeatherTransientError, match="timed out after 1.5s"):
            await adapter.get_weather(latitude=45.0, longitude=90.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_connection_failure_maps_to_transient_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Failed to establish a new connection", request=request)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherTransientError, match="Weather connection failure"):
            await adapter.get_weather(latitude=45.0, longitude=90.0)

        await adapter.close()

    @pytest.mark.anyio
    async def test_coordinate_input_out_of_bounds_raises_location_error(self):
        adapter = OpenMeteoWeatherAdapter()

        with pytest.raises(WeatherLocationError, match="Latitude out of range"):
            await adapter.get_weather(latitude=91.0, longitude=0.0)

        with pytest.raises(WeatherLocationError, match="Longitude out of range"):
            await adapter.get_weather(latitude=0.0, longitude=-185.0)

        with pytest.raises(WeatherLocationError, match="Latitude must be numeric"):
            await adapter.get_weather(latitude="north", longitude=0.0)  # type: ignore

        await adapter.close()

    @pytest.mark.anyio
    async def test_coordinate_sanitization_in_location_error(self):
        """F-03: Neither raw nor coarse coordinates appear in WeatherLocationError message on HTTP 400."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="Latitude must be in range of -90 to 90°")

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        with pytest.raises(WeatherLocationError) as exc_info:
            await adapter.get_weather(latitude=47.61, longitude=-122.33)

        msg = str(exc_info.value)
        # Operational info preserved
        assert "Weather service rejected coordinates" in msg
        assert "HTTP 400" in msg
        # Privacy: coarse and raw coordinates stripped
        assert "47.6" not in msg
        assert "122.3" not in msg

        await adapter.close()

    @pytest.mark.anyio
    async def test_out_of_bounds_coordinate_error_message_sanitized(self):
        """F-03: Out-of-bounds coordinate checks do not leak coordinate values in error messages."""
        adapter = OpenMeteoWeatherAdapter()

        with pytest.raises(WeatherLocationError) as exc_info_lat:
            await adapter.get_weather(latitude=95.5, longitude=0.0)
        assert "95" not in str(exc_info_lat.value)
        assert "Latitude out of range [-90.0, 90.0]" in str(exc_info_lat.value)

        with pytest.raises(WeatherLocationError) as exc_info_lon:
            await adapter.get_weather(latitude=0.0, longitude=195.5)
        assert "195" not in str(exc_info_lon.value)
        assert "Longitude out of range [-180.0, 180.0]" in str(exc_info_lon.value)

        await adapter.close()


# ==============================================================================
# 4. In-Memory Caching & Privacy Tests
# ==============================================================================


class TestWeatherAdapterCachingAndPrivacy:
    """Validate in-memory LRU/TTL caching, coordinate quantization, and privacy boundaries."""

    @pytest.mark.anyio
    async def test_cache_hit_prevents_duplicate_network_call(self):
        call_count = 0
        payload = {
            "current": {
                "time": "2026-11-02T12:00",
                "temperature_2m": 15.0,
                "apparent_temperature": 15.0,
                "weather_code": 1,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client, cache_ttl_s=1800)

        # First call -> cache miss -> network call
        w1 = await adapter.get_weather(latitude=47.606, longitude=-122.332, city="Seattle")
        assert call_count == 1
        assert w1 is not None
        assert adapter.cache_size == 1

        # Second call to slightly different coordinates that round to the same coarse point (47.61, -122.33)
        w2 = await adapter.get_weather(latitude=47.609, longitude=-122.334, city="Seattle")
        assert call_count == 1  # Network call was NOT made
        assert w2 is not None
        assert w2.temperature_c == 15.0

        # Third call with updated city name preserves cached data with updated city
        w3 = await adapter.get_weather(latitude=47.61, longitude=-122.33, city="Downtown Seattle")
        assert call_count == 1
        assert w3 is not None
        assert w3.location is not None
        assert w3.location.city == "Downtown Seattle"

        await adapter.close()

    @pytest.mark.anyio
    async def test_cache_ttl_expiry_triggers_fresh_call(self, monkeypatch):
        call_count = 0
        payload = {
            "current": {
                "time": "2026-11-02T12:00",
                "temperature_2m": 15.0,
                "apparent_temperature": 15.0,
                "weather_code": 1,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        # 1-second TTL for testing
        adapter = OpenMeteoWeatherAdapter(client=client, cache_ttl_s=1)

        w1 = await adapter.get_weather(latitude=40.0, longitude=50.0)
        assert call_count == 1

        # Advance time by 2 seconds
        current_time = asyncio.get_event_loop().time()
        monkeypatch.setattr(asyncio.get_event_loop(), "time", lambda: current_time + 2.0)

        # Calling after TTL must trigger fresh fetch
        w2 = await adapter.get_weather(latitude=40.0, longitude=50.0)
        assert call_count == 2

        await adapter.close()

    @pytest.mark.anyio
    async def test_manual_clear_cache(self):
        payload = {
            "current": {
                "time": "2026-11-02T12:00",
                "temperature_2m": 10.0,
                "apparent_temperature": 10.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        adapter = OpenMeteoWeatherAdapter(client=client)

        await adapter.get_weather(latitude=10.0, longitude=20.0)
        assert adapter.cache_size == 1

        adapter.clear_cache()
        assert adapter.cache_size == 0

        await adapter.close()

    @pytest.mark.anyio
    async def test_bounded_cache_capacity_eviction(self):
        payload = {
            "current": {
                "time": "2026-11-02T12:00",
                "temperature_2m": 10.0,
                "apparent_temperature": 10.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        # Max capacity 3
        adapter = OpenMeteoWeatherAdapter(client=client, max_cache_entries=3)

        await adapter.get_weather(latitude=10.0, longitude=10.0)
        await adapter.get_weather(latitude=20.0, longitude=20.0)
        await adapter.get_weather(latitude=30.0, longitude=30.0)
        assert adapter.cache_size == 3

        # Adding 4th must evict oldest
        await adapter.get_weather(latitude=40.0, longitude=40.0)
        assert adapter.cache_size == 3
        assert (10.0, 10.0) not in adapter._cache
        assert (40.0, 40.0) in adapter._cache

        await adapter.close()


# ==============================================================================
# 5. Dependency Injection, Settings & Architecture Tests
# ==============================================================================


class TestWeatherArchitectureAndDI:
    """Validate protocol compliance, DI resolution, lifecycle, and settings."""

    def test_open_meteo_adapter_conforms_to_weather_provider_protocol(self):
        adapter = OpenMeteoWeatherAdapter()
        # Protocol check
        assert isinstance(adapter, WeatherProvider)

    def test_settings_weather_configuration_defaults(self):
        settings = Settings()
        assert settings.weather_provider == "open_meteo"
        assert settings.weather_api_base_url == "https://api.open-meteo.com"
        assert settings.weather_timeout_s == 1.5
        assert settings.weather_cache_ttl_s == 1800

    def test_settings_weather_provider_validation(self):
        with pytest.raises(ValidationError, match="WEATHER_PROVIDER must be 'open_meteo' or 'off'"):
            Settings(weather_provider="invalid_provider")

        with pytest.raises(ValidationError, match="WEATHER_TIMEOUT_S must be greater than 0"):
            Settings(weather_timeout_s=0.0)

        with pytest.raises(ValidationError, match="WEATHER_CACHE_TTL_S must be non-negative"):
            Settings(weather_cache_ttl_s=-10)

    def test_weather_provider_off_returns_none_cleanly(self):
        """F-01: WEATHER_PROVIDER=off disables weather cleanly without raising exception."""
        clear_settings_cache()
        reset_default_weather_provider()

        settings = Settings(weather_provider="off")
        created = create_weather_provider(settings)
        assert created is None

        default_provider = get_default_weather_provider(settings)
        assert default_provider is None

        # Verify idempotence on singleton getter
        assert get_default_weather_provider(settings) is None

        reset_default_weather_provider()
        clear_settings_cache()

    def test_weather_provider_open_meteo_initialization(self):
        """Verify open_meteo continues to initialize correctly."""
        settings = Settings(weather_provider="open_meteo")
        provider = create_weather_provider(settings)
        assert isinstance(provider, OpenMeteoWeatherAdapter)

    def test_unsupported_weather_provider_raises_value_error(self):
        """Unsupported provider raises descriptive ValueError."""
        # Using model_construct to bypass Pydantic validation and test factory error handling
        settings = Settings.model_construct(
            weather_provider="unsupported_vendor",
            weather_api_base_url="https://api.open-meteo.com",
            weather_timeout_s=1.5,
            weather_cache_ttl_s=1800,
        )
        with pytest.raises(ValueError, match="Unsupported weather provider: 'unsupported_vendor'"):
            create_weather_provider(settings)

    def test_di_resolves_weather_provider_singleton(self):
        clear_settings_cache()
        reset_default_weather_provider()

        settings = Settings()
        p1 = get_default_weather_provider(settings)
        p2 = get_default_weather_provider(settings)

        assert p1 is p2
        assert isinstance(p1, OpenMeteoWeatherAdapter)

        # FastAPI dependency function returns the singleton
        dep_provider = get_weather_provider()
        assert dep_provider is p1

        reset_default_weather_provider()
        clear_settings_cache()

    @pytest.mark.anyio
    async def test_async_context_manager_lifecycle(self):
        payload = {
            "current": {
                "time": "2026-11-02T12:00",
                "temperature_2m": 15.0,
                "apparent_temperature": 15.0,
                "weather_code": 0,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_transport(handler)
        async with OpenMeteoWeatherAdapter(client=client) as adapter:
            res = await adapter.get_weather(latitude=12.0, longitude=34.0)
            assert res is not None

        # Verify clean exit without error
