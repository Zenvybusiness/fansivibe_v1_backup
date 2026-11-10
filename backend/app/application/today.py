"""Application use cases — M9 Today's Look derivation (UC-16/UC-17).

`GetTodayLook` (endpoint #31 `GET /v1/looks/today`) and
`RegenerateTodayLook` (endpoint #32 `POST /v1/looks/today`) derive one
`TodayLook` per request from the owner's current UserState + owned
wardrobe + optional nearest event. There is no `today_look_records`
table (DEC-017-A): derivation is READ/DERIVE only — no INSERT/UPDATE/
DELETE anywhere (no save, no signal, no wear row, no preference write,
no event/wardrobe mutation — and no commit call at all).

The canonical generate → score → rank → select pipeline is reused
verbatim (no second engine, no second scoring). The optional nearest
event seeds the scoring occasions as highest priority: candidate set =
owner events with `event_date` >= server-UTC today (today qualifies),
ordered `event_date ASC, event_time ASC NULLS LAST, id ASC` via the
frozen M8 list ordering (DEC-018 §2); the first row or none. Only the
event TYPE CODE is consumed. No event → derive normally (never 404 for
the missing event alone). Scoring occasions are `[event code] +
persisted preferred_occasions`, deduped (DEC-018/M8-C precedent).

Variant/seed only select among the ranked legal candidates (DEC-018
C12): absent → the winner (`select_best_outfit_candidate`); supplied →
a stable hash index into the ranked list (same key + same inputs →
same pick; different keys differ best-effort — a bounded candidate
space can collide, DEC-017-C). Bounds (`1..200`, supplied-empty
rejected) are enforced here so direct callers see identical 422s; the
router declares the same bounds as the wire guard.

Weather integration (Stage 2 P1-3): resolves location based on priority
(request params -> stored user settings -> ephemeral guest settings -> None).
When a valid location exists and WeatherProvider is configured, weather
context is retrieved with provider timeout and caching. Failures or absent
location gracefully fall back to baseline derivation without weather (DEC-017-G).
Canonical 12-term scoring engine evaluates weather as an advisory soft adjustment.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from app.api.errors import ApiError, ai_failure, internal_error
from app.domain.ports.external import WeatherError, WeatherProvider
from app.domain.ports.repositories import (
    EventTypeRepository,
    TodayLookAlternative,
    TodayLookComponent,
    TodayLookRecommendation,
    UserEventRepository,
    UserStateRepository,
    WardrobeItemRepository,
)
from app.domain.services.analysis_rules import (
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
)
from app.domain.value_objects import WeatherContext, WeatherLocation

logger = logging.getLogger(__name__)

# Curated major city centroids (rounded to 2 decimal places, ~1.1km resolution)
# Used when a user or client supplies only a city name without explicit coordinates.
MAJOR_CITIES: dict[str, tuple[float, float, str, str]] = {
    "london": (51.51, -0.13, "London", "GB"),
    "paris": (48.86, 2.35, "Paris", "FR"),
    "new york": (40.71, -74.01, "New York", "US"),
    "tokyo": (35.68, 139.69, "Tokyo", "JP"),
    "seattle": (47.61, -122.33, "Seattle", "US"),
    "san francisco": (37.77, -122.42, "San Francisco", "US"),
    "los angeles": (34.05, -118.24, "Los Angeles", "US"),
    "chicago": (41.88, -87.63, "Chicago", "US"),
    "berlin": (52.52, 13.41, "Berlin", "DE"),
    "sydney": (33.87, 151.21, "Sydney", "AU"),
    "toronto": (43.65, -79.38, "Toronto", "CA"),
    "milan": (45.46, 9.19, "Milan", "IT"),
    "rome": (41.90, 12.50, "Rome", "IT"),
    "oslo": (59.91, 10.75, "Oslo", "NO"),
    "stockholm": (59.33, 18.07, "Stockholm", "SE"),
    "amsterdam": (52.37, 4.90, "Amsterdam", "NL"),
    "madrid": (40.42, -3.70, "Madrid", "ES"),
    "barcelona": (41.39, 2.17, "Barcelona", "ES"),
    "singapore": (1.35, 103.82, "Singapore", "SG"),
    "seoul": (37.57, 126.98, "Seoul", "KR"),
}


def _parse_coordinates(lat_val: Any, lon_val: Any) -> Optional[tuple[float, float]]:
    if lat_val is None or lon_val is None:
        return None
    try:
        if isinstance(lat_val, bool) or isinstance(lon_val, bool):
            return None
        lat = float(lat_val)
        lon = float(lon_val)
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return round(lat, 2), round(lon, 2)
    except (ValueError, TypeError):
        pass
    return None


def resolve_weather_location(
    *,
    city: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    user_state: Optional[UserStateRepository] = None,
    user_id: Optional[UUID] = None,
) -> Optional[WeatherLocation]:
    """Resolve coarse WeatherLocation following the 4-level priority order:
    1. Explicit coordinates / city passed in the current request.
    2. Authenticated user's saved location preference from UserState settings.
    3. Guest user's locally supplied location in ephemeral user state.
    4. Fallback to None (weather omitted cleanly).
    """
    # Priority 1: Explicit request params
    coords = _parse_coordinates(latitude, longitude)
    clean_city = city.strip() if isinstance(city, str) and city.strip() else None
    if coords is not None:
        return WeatherLocation(
            latitude=coords[0],
            longitude=coords[1],
            city=clean_city,
        )
    if clean_city:
        matched = MAJOR_CITIES.get(clean_city.lower())
        if matched is not None:
            return WeatherLocation(
                latitude=matched[0],
                longitude=matched[1],
                city=matched[2],
                country=matched[3],
            )

    # Priority 2 & 3: Stored settings
    if user_state is not None and user_id is not None:
        try:
            profile = user_state.get_profile(user_id=user_id)
        except Exception:
            profile = None
        if profile is not None and isinstance(profile.settings, dict):
            settings = profile.settings
            loc_data = (
                settings.get("weather_location")
                or settings.get("weatherLocation")
                or settings.get("location")
            )
            if isinstance(loc_data, dict):
                s_lat = loc_data.get("lat") or loc_data.get("latitude")
                s_lon = loc_data.get("lon") or loc_data.get("longitude")
                s_city = (
                    loc_data.get("city")
                    or loc_data.get("cityName")
                    or loc_data.get("name")
                )
                s_country = loc_data.get("country")
                s_coords = _parse_coordinates(s_lat, s_lon)
                clean_s_city = (
                    s_city.strip()
                    if isinstance(s_city, str) and s_city.strip()
                    else None
                )
                if s_coords is not None:
                    return WeatherLocation(
                        latitude=s_coords[0],
                        longitude=s_coords[1],
                        city=clean_s_city,
                        country=str(s_country).strip() if s_country else None,
                    )
                if clean_s_city:
                    matched = MAJOR_CITIES.get(clean_s_city.lower())
                    if matched is not None:
                        return WeatherLocation(
                            latitude=matched[0],
                            longitude=matched[1],
                            city=matched[2],
                            country=matched[3],
                        )

            # Check flat settings keys
            flat_lat = settings.get("lat") or settings.get("latitude")
            flat_lon = settings.get("lon") or settings.get("longitude")
            flat_city = settings.get("city")
            flat_coords = _parse_coordinates(flat_lat, flat_lon)
            clean_flat_city = (
                flat_city.strip()
                if isinstance(flat_city, str) and flat_city.strip()
                else None
            )
            if flat_coords is not None:
                return WeatherLocation(
                    latitude=flat_coords[0],
                    longitude=flat_coords[1],
                    city=clean_flat_city,
                )
            if clean_flat_city:
                matched = MAJOR_CITIES.get(clean_flat_city.lower())
                if matched is not None:
                    return WeatherLocation(
                        latitude=matched[0],
                        longitude=matched[1],
                        city=matched[2],
                        country=matched[3],
                    )

    # Priority 4: No valid location
    return None


def _build_weather_payload(
    weather_context: Optional[WeatherContext],
) -> Optional[dict[str, Any]]:
    """Build wire-compatible weather dictionary from domain WeatherContext."""
    if weather_context is None:
        return None
    city = weather_context.location.city if weather_context.location else None
    temp_c = weather_context.temperature_c
    temp_round = int(round(temp_c))
    condition = weather_context.condition_text
    summary = (
        f"{temp_round}°C • {condition} in {city}"
        if city
        else f"{temp_round}°C • {condition}"
    )

    return {
        "applied": True,
        "condition": condition,
        "conditionCode": weather_context.condition_code,
        "temperatureC": temp_c,
        "temperatureF": weather_context.temperature_f,
        "apparentTemperatureC": weather_context.apparent_temperature_c,
        "apparentTemperatureF": weather_context.apparent_temperature_f,
        "precipitationProbability": weather_context.precipitation_probability,
        "precipitationMm": weather_context.precipitation_mm,
        "windSpeedKmh": weather_context.wind_speed_kmh,
        "isRaining": weather_context.is_raining,
        "forecastTimestamp": weather_context.forecast_timestamp,
        "city": city,
        "summary": summary,
        "fallback": False,
    }


# Canonical ensemble slot order for component rendering (tops first —
# same order as the M8-C event outfit adapter).
_OUTFIT_SLOT_ORDER = ("tops", "bottoms", "outerwear", "footwear", "accessories")

_SLOT_ATTRS = {
    "tops": "top_ids",
    "bottoms": "bottom_ids",
    "outerwear": "outerwear_ids",
    "footwear": "footwear_ids",
    "accessories": "accessory_ids",
}

# Selector bound (DEC-018 §3/4: no authoritative maximum; BC-13 family
# ceiling, enforced as 422 — variant/seed never affect determinism
# guarantees, only which ranked candidate is picked).
_SELECTOR_MAX_LENGTH = 200

# Projection of the snake_case `style_profile` store to the camelCase
# `styleDna` wire object (DEC-018 C12: 4-field StyleProfile projection,
# absent subfields omitted — never 404 for profile gaps).
_STYLE_DNA_FIELDS = (
    ("style_type", "styleType"),
    ("body_type", "bodyType"),
    ("skin_tone", "skinTone"),
    ("face_shape", "faceShape"),
)


def _utc_today():
    """Server-UTC calendar date (nearest-event datum, DEC-018 §2)."""
    return datetime.now(timezone.utc).date()


def _field_error(field: str, error: str) -> ApiError:
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": [{"field": field, "error": error}]},
    )


def _validate_selector(field: str, value: object) -> Optional[str]:
    """Validate an opaque variant/seed selector (absent → default pick)."""
    if value is None:
        return None
    if not isinstance(value, str) or not (1 <= len(value) <= _SELECTOR_MAX_LENGTH):
        raise _field_error(
            field,
            f"must be between 1 and {_SELECTOR_MAX_LENGTH} characters",
        )
    return value


def _select_index(count: int, key: Optional[str]) -> int:
    """Deterministic ranked-candidate pick (DEC-018 C12).

    Absent key → rank 0 (the winner). Supplied key → stable SHA-256
    index into the ranked list: identical inputs repeat byte-identically,
    different keys vary best-effort over the bounded candidate space.

    Empty candidate space (`count <= 0`) is a caller error: the derivation
    guards `if not ranked: return None` before selecting, so this raises
    `ValueError` instead of crashing with `ZeroDivisionError` (`% 0`) —
    the Python analog of Dart `Random.nextInt(0)` (`RangeError: max ... was 0`).
    """
    if count <= 0:
        raise ValueError("no candidates to select from")
    if key is None:
        return 0
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % count


def _clamp_score(value: float) -> int:
    """Winner's native 0–100 budget score → wire int (DEC-018 C12)."""
    return max(0, min(100, int(round(value))))


class _DerivationFailed(Exception):
    """Unexpected engine failure during candidate derivation."""


async def _derive_today_look(
    *,
    events: UserEventRepository,
    event_types: EventTypeRepository,
    wardrobe_items: WardrobeItemRepository,
    user_state: UserStateRepository,
    user_id: UUID,
    key: Optional[str],
    weather_provider: Optional[WeatherProvider] = None,
    city: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Optional[TodayLookRecommendation]:
    """Shared derivation for GET (variant) and POST (seed).

    Returns the honest `TodayLookRecommendation`, or `None` when the
    owner has no legal candidate (empty wardrobe / tops+bottoms missing)
    — the router maps `None` to 404 ("none found", DEC-017-B).
    """
    wardrobe = _load_owner_wardrobe(wardrobe_items=wardrobe_items, user_id=user_id)
    if not wardrobe:
        return None

    event_code: Optional[str] = None
    nearest = events.list_for_user(
        user_id=user_id, from_date=_utc_today(), order="asc", page=1, page_size=1
    )[0]
    if nearest:
        event_code = nearest[0].event_type

    occasions = [event_code] if event_code is not None else []
    occasions.extend(
        item
        for item in _preferred_occasions(user_state=user_state, user_id=user_id)
        if isinstance(item, str) and item not in occasions
    )

    # Weather location resolution & provider orchestration (Stage 2 P1-3)
    weather_location = resolve_weather_location(
        city=city,
        latitude=latitude,
        longitude=longitude,
        user_state=user_state,
        user_id=user_id,
    )
    weather_context: Optional[WeatherContext] = None
    if weather_provider is not None and weather_location is not None:
        try:
            weather_context = await weather_provider.get_weather(
                latitude=weather_location.latitude,
                longitude=weather_location.longitude,
                city=weather_location.city,
                country=weather_location.country,
            )
        except WeatherError as exc:
            logger.warning(
                "Weather provider returned %s: %s; falling back to normal scoring",
                exc.__class__.__name__,
                exc.message,
            )
            weather_context = None
        except Exception as exc:
            logger.exception(
                "Unexpected error fetching weather (%s); falling back to normal scoring",
                exc.__class__.__name__,
            )
            weather_context = None

    adapted = [
        SimpleNamespace(
            id=str(record.id),
            category=record.category,
            color=record.color,
            material=record.material,
            is_favorite=record.is_favorite,
        )
        for record in wardrobe
    ]
    items_by_id = {item.id: item for item in adapted}
    try:
        ranked = rank_outfit_candidates(
            [
                score_outfit_candidate(
                    candidate,
                    items_by_id,
                    frozenset(),
                    occasions,
                    weather_context=weather_context,
                )
                for candidate in generate_outfit_candidates(adapted)
            ]
        )
    except Exception as exc:
        raise _DerivationFailed from exc
    if not ranked:
        return None
    if key is None:
        winner = select_best_outfit_candidate(ranked)
    else:
        winner = ranked[_select_index(len(ranked), key)]
    if winner is None:  # pragma: no cover — defensive; ranked non-empty.
        return None
    by_record = {str(record.id): record for record in wardrobe}
    return _to_recommendation(
        event_types=event_types,
        event_code=event_code,
        occasions=occasions,
        user_state=user_state,
        user_id=user_id,
        winner=winner,
        ranked=ranked,
        by_record=by_record,
        total_items=len(wardrobe),
        weather_context=weather_context,
    )


def _load_owner_wardrobe(
    *, wardrobe_items: WardrobeItemRepository, user_id: UUID
) -> list:
    """All of the owner's wardrobe items (owner-scoped pages of 100)."""
    items: list = []
    page = 1
    while True:
        batch, total = wardrobe_items.get_for_user(
            user_id=user_id, page=page, page_size=100
        )
        items.extend(batch)
        if len(items) >= total or not batch:
            return items
        page += 1


def _preferred_occasions(*, user_state: UserStateRepository, user_id: UUID) -> list:
    """Persisted occasion codes for scoring context (read-only)."""
    try:
        profile = user_state.get_profile(user_id=user_id)
    except Exception:
        return []
    if profile is None:
        return []
    raw = profile.preferences.get("preferred_occasions")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _style_dna(*, user_state: UserStateRepository, user_id: UUID) -> Optional[dict]:
    """Present-only StyleProfile projection (read-only, gaps tolerated)."""
    try:
        profile = user_state.get_profile(user_id=user_id)
    except Exception:
        return None
    if profile is None:
        return None
    stored = profile.style_profile
    if not isinstance(stored, dict):
        return None
    projected = {
        wire: stored[store]
        for store, wire in _STYLE_DNA_FIELDS
        if isinstance(stored.get(store), str) and stored[store] != ""
    }
    return projected or None


def _candidate_member_ids(candidate) -> list[str]:
    ids: list[str] = []
    for category in _OUTFIT_SLOT_ORDER:
        ids.extend(getattr(candidate, _SLOT_ATTRS[category], ()))
    return [str(item_id) for item_id in ids]


def _to_recommendation(
    *,
    event_types: EventTypeRepository,
    event_code: Optional[str],
    occasions: list,
    user_state: UserStateRepository,
    user_id: UUID,
    winner,
    ranked: list,
    by_record: dict,
    total_items: int,
    weather_context: Optional[WeatherContext] = None,
) -> TodayLookRecommendation:
    if event_code is not None:
        type_row = event_types.get_by_code(code=event_code)
        label: Optional[str] = type_row.label if type_row is not None else event_code
        occasion: Optional[str] = event_code
    else:
        label = occasions[0] if occasions else None
        occasion = occasions[0] if occasions else None
    title = f"{label} Look" if label else "Today's Look"

    selected_item_ids = sorted(set(_candidate_member_ids(winner)))
    components: list[TodayLookComponent] = []
    covered: list[str] = []
    for category in _OUTFIT_SLOT_ORDER:
        for item_id in getattr(winner, _SLOT_ATTRS[category], ()):
            record = by_record.get(str(item_id))
            if record is None:  # pragma: no cover — defensive; IDs are owned.
                continue
            components.append(
                TodayLookComponent(
                    id=str(record.id),
                    name=record.name,
                    category=category,
                    color=record.color,
                    material=record.material,
                )
            )
        if getattr(winner, _SLOT_ATTRS[category], ()):
            covered.append(category)
    count = len(covered)
    description = (
        f"{title} with {len(selected_item_ids)} "
        f"{'piece' if len(selected_item_ids) == 1 else 'pieces'} "
        f"covering {', '.join(covered)}."
    )
    reasons = []
    if label is not None:
        reasons.append(f"Picked for a {label} occasion")
    reasons.append(
        f"Covers {count} categor{'y' if count == 1 else 'ies'}: " + ", ".join(covered)
    )
    for component in components:
        record = by_record.get(component.id)
        if record is not None and record.is_favorite:
            reasons.append(f"Includes your favorite {record.name}")

    score = _clamp_score(winner.score)
    alternatives = [
        TodayLookAlternative(
            id="-".join(sorted(set(_candidate_member_ids(candidate)))),
            match_score=_clamp_score(candidate.score),
        )
        for candidate in ranked[1:3]
    ]
    return TodayLookRecommendation(
        title=title,
        occasion=occasion,
        description=description,
        match_score=score,
        style_score=score,
        components=components,
        reasons=reasons,
        style_dna=_style_dna(user_state=user_state, user_id=user_id),
        total_items=total_items,
        matching_items=len(selected_item_ids),
        alternatives=alternatives,
        selected_item_ids=selected_item_ids,
        weather=_build_weather_payload(weather_context),
    )


class GetTodayLook:
    """Derive today's look (endpoint #31 `GET /v1/looks/today`, UC-17).

    READ/DERIVE only (TRX-2): repeated calls over unchanged inputs are
    byte-identical. `variant` is an opaque ranked-candidate selector —
    no vocabulary is invented for it. No legal candidate → `None`
    (the router answers 404); weather failure gracefully falls back (DEC-017-G).
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
        weather_provider: Optional[WeatherProvider] = None,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state
        self._weather_provider = weather_provider

    async def __call__(
        self,
        *,
        user_id: UUID,
        variant: object = None,
        city: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Optional[TodayLookRecommendation]:
        key = _validate_selector("variant", variant)
        try:
            return await _derive_today_look(
                events=self._events,
                event_types=self._event_types,
                wardrobe_items=self._wardrobe_items,
                user_state=self._user_state,
                user_id=user_id,
                key=key,
                weather_provider=self._weather_provider,
                city=city,
                latitude=latitude,
                longitude=longitude,
            )
        except _DerivationFailed:
            raise internal_error()


class RegenerateTodayLook:
    """Derive a fresh today's look (endpoint #32 `POST /v1/looks/today`, UC-16).

    Same derivation as GET with an independent `seed` selector (no
    variant↔seed equivalence claimed): absent seed → the winner, supplied
    seed → the stable ranked pick. Persists nothing, never keyed. An
    unexpected generation failure surfaces as 503 (C-8, no internals);
    no legal candidate → `None` (the router answers 404).
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
        weather_provider: Optional[WeatherProvider] = None,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state
        self._weather_provider = weather_provider

    async def __call__(
        self,
        *,
        user_id: UUID,
        seed: object = None,
        city: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Optional[TodayLookRecommendation]:
        key = _validate_selector("seed", seed)
        try:
            return await _derive_today_look(
                events=self._events,
                event_types=self._event_types,
                wardrobe_items=self._wardrobe_items,
                user_state=self._user_state,
                user_id=user_id,
                key=key,
                weather_provider=self._weather_provider,
                city=city,
                latitude=latitude,
                longitude=longitude,
            )
        except _DerivationFailed:
            raise ai_failure()
