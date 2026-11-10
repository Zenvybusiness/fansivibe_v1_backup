"""Open-Meteo weather provider adapter (Stage 2 P1-3 / FEAT-14).

Implements the application-owned ``WeatherProvider`` port using the Open-Meteo
forecast REST API. Isolates the Fansivibe decision engine from external weather
vendors, handles WMO code mapping, normalizes units, enforces strict timeout
and in-memory caching guarantees, and guarantees privacy compliance.

Privacy & Geolocation Invariants (Phase 0 Audit §6):
- Operates on coarse geographic resolution (~1.1 km / 2 decimal places max).
- Meter-level GPS coordinates are never accepted, transmitted, or logged.
- Never accesses device hardware or location services directly.
- All location context is caller-provided.

Resilience & Fallback Invariants (DEC-017-G):
- Strict 1.5s timeout on outbound HTTP calls.
- Bounded 30-minute in-memory LRU/TTL cache by coarse coordinates.
- All network, timeout, HTTP, and parsing errors are translated into
  domain ``WeatherError`` subclasses (never leaking ``httpx`` exceptions).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional

import httpx

from app.config.settings import Settings
from app.domain.ports.external import (
    WeatherError,
    WeatherLocationError,
    WeatherProvider,
    WeatherResponseError,
    WeatherTransientError,
)
from app.domain.value_objects import WeatherContext, WeatherLocation

logger = logging.getLogger(__name__)

# --- WMO Weather Interpretation Codes (WW) ---
# Authoritative mapping from numeric WMO weather interpretation code to
# (condition_code, condition_text).
WMO_CODE_MAP: dict[int, tuple[str, str]] = {
    0: ("clear", "Clear sky"),
    1: ("mainly_clear", "Mainly clear"),
    2: ("partly_cloudy", "Partly cloudy"),
    3: ("overcast", "Overcast"),
    45: ("fog", "Fog"),
    48: ("fog", "Depositing rime fog"),
    51: ("drizzle", "Light drizzle"),
    53: ("drizzle", "Moderate drizzle"),
    55: ("drizzle", "Dense drizzle"),
    56: ("freezing_drizzle", "Light freezing drizzle"),
    57: ("freezing_drizzle", "Dense freezing drizzle"),
    61: ("rain", "Slight rain"),
    63: ("rain", "Moderate rain"),
    65: ("rain", "Heavy rain"),
    66: ("freezing_rain", "Light freezing rain"),
    67: ("freezing_rain", "Heavy freezing rain"),
    71: ("snow", "Slight snow fall"),
    73: ("snow", "Moderate snow fall"),
    75: ("snow", "Heavy snow fall"),
    77: ("snow", "Snow grains"),
    80: ("rain_showers", "Slight rain showers"),
    81: ("rain_showers", "Moderate rain showers"),
    82: ("rain_showers", "Violent rain showers"),
    85: ("snow_showers", "Slight snow showers"),
    86: ("snow_showers", "Heavy snow showers"),
    95: ("thunderstorm", "Thunderstorm"),
    96: ("thunderstorm_hail", "Thunderstorm with slight hail"),
    99: ("thunderstorm_hail", "Thunderstorm with heavy hail"),
}


def resolve_wmo_code(code: int) -> tuple[str, str]:
    """Map numeric WMO code to semantic condition_code and condition_text."""
    if code in WMO_CODE_MAP:
        return WMO_CODE_MAP[code]
    return "unknown", f"Weather condition {code}"


@dataclass
class _WeatherCacheEntry:
    """Internal cache entry holding timestamp and normalized WeatherContext."""

    cached_at: float
    context: WeatherContext


class OpenMeteoWeatherAdapter:
    """Concrete Open-Meteo external weather adapter conforming to ``WeatherProvider``."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.open-meteo.com",
        timeout_s: float = 1.5,
        cache_ttl_s: int = 1800,
        max_cache_entries: int = 500,
        client: Optional[httpx.AsyncClient] = None,
        user_agent: str = "Fansivibe/1.0 (weather-client; privacy-first)",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._cache_ttl_s = cache_ttl_s
        self._max_cache_entries = max_cache_entries
        self._user_agent = user_agent

        self._client: Optional[httpx.AsyncClient] = client
        self._owns_client = client is None
        self._cache: dict[tuple[float, float], _WeatherCacheEntry] = {}

    def _get_client(self) -> httpx.AsyncClient:
        """Retrieve existing client or instantiate owned async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    self._timeout_s,
                    connect=min(self._timeout_s, 1.0),
                ),
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "application/json",
                },
            )
            self._owns_client = True
        return self._client

    async def get_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Optional[WeatherContext]:
        """Fetch and normalize current weather for the given coarse coordinates.

        Enforces coordinate validation, coarse rounding (~1.1km), in-memory TTL
        caching, strict timeout, and comprehensive error mapping.
        """
        # Validate coordinate input
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            raise WeatherLocationError(
                f"Latitude must be numeric, got {type(latitude).__name__}"
            )
        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            raise WeatherLocationError(
                f"Longitude must be numeric, got {type(longitude).__name__}"
            )

        lat_val = float(latitude)
        lon_val = float(longitude)

        if not (-90.0 <= lat_val <= 90.0):
            raise WeatherLocationError(
                f"Latitude out of range [-90.0, 90.0]: {lat_val}"
            )
        if not (-180.0 <= lon_val <= 180.0):
            raise WeatherLocationError(
                f"Longitude out of range [-180.0, 180.0]: {lon_val}"
            )

        # Enforce coarse resolution: round to 2 decimal places (~1.1km)
        coarse_lat = round(lat_val, 2)
        coarse_lon = round(lon_val, 2)
        cache_key = (coarse_lat, coarse_lon)

        # Check in-memory cache
        now_mono = asyncio.get_event_loop().time()
        cached = self._cache.get(cache_key)
        if cached is not None:
            if (now_mono - cached.cached_at) < self._cache_ttl_s:
                # Return cached context with updated location metadata if city/country provided
                ctx = cached.context
                if city and (not ctx.location or ctx.location.city != city):
                    updated_loc = WeatherLocation(
                        latitude=coarse_lat,
                        longitude=coarse_lon,
                        city=city,
                        country=country or (ctx.location.country if ctx.location else None),
                    )
                    return WeatherContext(
                        temperature_c=ctx.temperature_c,
                        apparent_temperature_c=ctx.apparent_temperature_c,
                        weather_code=ctx.weather_code,
                        condition_code=ctx.condition_code,
                        condition_text=ctx.condition_text,
                        forecast_timestamp=ctx.forecast_timestamp,
                        retrieved_at=ctx.retrieved_at,
                        precipitation_probability=ctx.precipitation_probability,
                        precipitation_mm=ctx.precipitation_mm,
                        relative_humidity_pct=ctx.relative_humidity_pct,
                        wind_speed_kmh=ctx.wind_speed_kmh,
                        is_day=ctx.is_day,
                        location=updated_loc,
                    )
                return ctx
            else:
                self._cache.pop(cache_key, None)

        # Minimum required variables per Phase 0 audit §5
        params = {
            "latitude": f"{coarse_lat:.2f}",
            "longitude": f"{coarse_lon:.2f}",
            "current": (
                "temperature_2m,"
                "apparent_temperature,"
                "precipitation_probability,"
                "precipitation,"
                "relative_humidity_2m,"
                "wind_speed_10m,"
                "weather_code,"
                "is_day"
            ),
            "timezone": "auto",
        }

        client = self._get_client()
        try:
            response = await client.get("/v1/forecast", params=params)
        except httpx.TimeoutException as exc:
            raise WeatherTransientError(
                f"Weather request timed out after {self._timeout_s}s",
                cause=exc,
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise WeatherTransientError(
                f"Weather connection failure: {exc}",
                cause=exc,
            ) from exc
        except httpx.RequestError as exc:
            raise WeatherTransientError(
                f"Weather transport error: {exc}",
                cause=exc,
            ) from exc

        # Handle HTTP status codes
        if response.status_code == 400:
            raise WeatherLocationError(
                f"Weather service rejected coordinates ({coarse_lat}, {coarse_lon}): {response.text[:200]}"
            )
        elif response.status_code >= 500:
            raise WeatherTransientError(
                f"Weather upstream server error HTTP {response.status_code}"
            )
        elif response.is_error:
            raise WeatherResponseError(
                f"Weather service returned HTTP {response.status_code}"
            )

        # Parse JSON payload
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise WeatherResponseError(
                "Malformed JSON response received from weather service",
                cause=exc,
            ) from exc

        if not isinstance(data, dict):
            raise WeatherResponseError(
                "Unexpected response format: root payload is not a JSON object"
            )

        if data.get("error"):
            reason = data.get("reason", "unknown error")
            raise WeatherResponseError(f"Weather service returned error: {reason}")

        current = data.get("current")
        if not isinstance(current, dict):
            raise WeatherResponseError(
                "Missing or invalid 'current' block in weather response"
            )

        # Extract required measurements
        temp_raw = current.get("temperature_2m")
        app_temp_raw = current.get("apparent_temperature")
        weather_code_raw = current.get("weather_code")

        if temp_raw is None:
            raise WeatherResponseError(
                "Missing required field 'temperature_2m' in current weather block"
            )
        if app_temp_raw is None:
            raise WeatherResponseError(
                "Missing required field 'apparent_temperature' in current weather block"
            )
        if weather_code_raw is None:
            raise WeatherResponseError(
                "Missing required field 'weather_code' in current weather block"
            )

        try:
            temperature_c = float(temp_raw)
            apparent_temperature_c = float(app_temp_raw)
            weather_code = int(weather_code_raw)
        except (ValueError, TypeError) as exc:
            raise WeatherResponseError(
                f"Invalid numeric data in current weather block: {exc}",
                cause=exc,
            ) from exc

        # Extract optional measurements
        precip_prob_raw = current.get("precipitation_probability")
        precipitation_probability: Optional[float] = None
        if precip_prob_raw is not None:
            try:
                precipitation_probability = float(precip_prob_raw)
            except (ValueError, TypeError):
                precipitation_probability = None

        precip_mm_raw = current.get("precipitation")
        precipitation_mm: Optional[float] = None
        if precip_mm_raw is not None:
            try:
                precipitation_mm = float(precip_mm_raw)
            except (ValueError, TypeError):
                precipitation_mm = None

        humidity_raw = current.get("relative_humidity_2m")
        relative_humidity_pct: Optional[float] = None
        if humidity_raw is not None:
            try:
                relative_humidity_pct = float(humidity_raw)
            except (ValueError, TypeError):
                relative_humidity_pct = None

        wind_raw = current.get("wind_speed_10m")
        wind_speed_kmh: Optional[float] = None
        if wind_raw is not None:
            try:
                wind_speed_kmh = float(wind_raw)
            except (ValueError, TypeError):
                wind_speed_kmh = None

        is_day_raw = current.get("is_day")
        is_day: Optional[bool] = None
        if is_day_raw is not None:
            if isinstance(is_day_raw, bool):
                is_day = is_day_raw
            elif isinstance(is_day_raw, (int, float)):
                is_day = bool(int(is_day_raw) == 1)

        # Parse forecast timestamp
        time_raw = current.get("time")
        now_utc = datetime.now(timezone.utc)
        forecast_ts: datetime
        if isinstance(time_raw, str) and time_raw.strip():
            try:
                parsed_dt = datetime.fromisoformat(time_raw.strip())
                if parsed_dt.tzinfo is None:
                    forecast_ts = parsed_dt.replace(tzinfo=timezone.utc)
                else:
                    forecast_ts = parsed_dt.astimezone(timezone.utc)
            except ValueError:
                forecast_ts = now_utc
        else:
            forecast_ts = now_utc

        condition_code, condition_text = resolve_wmo_code(weather_code)

        loc = WeatherLocation(
            latitude=coarse_lat,
            longitude=coarse_lon,
            city=city,
            country=country,
        )

        try:
            weather_ctx = WeatherContext(
                temperature_c=temperature_c,
                apparent_temperature_c=apparent_temperature_c,
                weather_code=weather_code,
                condition_code=condition_code,
                condition_text=condition_text,
                forecast_timestamp=forecast_ts,
                retrieved_at=now_utc,
                precipitation_probability=precipitation_probability,
                precipitation_mm=precipitation_mm,
                relative_humidity_pct=relative_humidity_pct,
                wind_speed_kmh=wind_speed_kmh,
                is_day=is_day,
                location=loc,
            )
        except ValueError as exc:
            raise WeatherResponseError(
                f"Normalized weather validation failed: {exc}",
                cause=exc,
            ) from exc

        # Cache valid response (with LRU eviction if at capacity)
        if len(self._cache) >= self._max_cache_entries:
            # Evict oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k].cached_at)
            self._cache.pop(oldest_key, None)

        self._cache[cache_key] = _WeatherCacheEntry(
            cached_at=now_mono,
            context=weather_ctx,
        )

        return weather_ctx

    async def close(self) -> None:
        """Release owned HTTP client resources."""
        if self._owns_client and self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> OpenMeteoWeatherAdapter:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def clear_cache(self) -> None:
        """Clear the in-memory weather cache."""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Number of currently cached location weather contexts."""
        return len(self._cache)


# --- Weather Provider Factory & Singleton Seam ---

_weather_provider_instance: Optional[WeatherProvider] = None
_weather_provider_config_fingerprint: Optional[tuple] = None


def create_weather_provider(settings: Settings) -> WeatherProvider:
    """Factory creating the appropriate WeatherProvider based on Settings."""
    provider = (settings.weather_provider or "open_meteo").lower().strip()
    if provider == "open_meteo":
        return OpenMeteoWeatherAdapter(
            base_url=settings.weather_api_base_url,
            timeout_s=settings.weather_timeout_s,
            cache_ttl_s=settings.weather_cache_ttl_s,
        )
    raise ValueError(f"Unsupported weather provider: '{provider}'")


def get_default_weather_provider(settings: Settings) -> WeatherProvider:
    """Retrieve or initialize the process-wide weather provider singleton."""
    global _weather_provider_instance, _weather_provider_config_fingerprint
    fingerprint = (
        settings.weather_provider,
        settings.weather_api_base_url,
        settings.weather_timeout_s,
        settings.weather_cache_ttl_s,
    )
    if (
        _weather_provider_instance is None
        or _weather_provider_config_fingerprint != fingerprint
    ):
        _weather_provider_instance = create_weather_provider(settings)
        _weather_provider_config_fingerprint = fingerprint
    return _weather_provider_instance


def reset_default_weather_provider() -> None:
    """Reset the cached weather provider singleton (used in tests)."""
    global _weather_provider_instance, _weather_provider_config_fingerprint
    _weather_provider_instance = None
    _weather_provider_config_fingerprint = None
