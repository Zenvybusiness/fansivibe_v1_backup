# STAGE 2 P1-3: PHASE 3 BACKEND ORCHESTRATION & WEATHER-AWARE DAILY LOOK API IMPLEMENTATION REPORT
## Backend Application Orchestration & Weather-Aware Daily Look API

**Feature:** P1-3 — Weather-Aware Location Seeding for Daily Looks (FEAT-14 Extension)  
**Phase:** Phase 3 — Backend Application Orchestration & Weather-Aware Daily Look API  
**Date:** 2026-11-02  
**Status:** COMPLETE (100% Verified)  
**Safety Invariants:** Zero database migrations created or executed, shared databases `fansivibe` and `fansivibe_test` untouched at revision `0032`, zero Flutter files created or modified, zero duplicate recommendation pipelines, zero secondary scoring engines, fail-open weather resilience (DEC-017-G), OW-1 owner-scoping preserved, ephemeral guest isolation (D10 Option A) preserved. All pre-existing 87 modified and untracked repository files strictly preserved.

---

## 1. Executive Summary

Phase 3 connects the Phase 1 `WeatherProvider` port and Phase 2 canonical 12-term weather-aware scoring engine to Fansivibe's existing daily outfit recommendation application flow (`GetTodayLook`, `RegenerateTodayLook`, `_derive_today_look`) and the public HTTP endpoints (`GET /v1/looks/today`, `POST /v1/looks/today`).

### Key Accomplishments & Architectural Invariants Upheld:
1. **Single Recommendation Pipeline Preserved:** Daily outfit derivation continues to use the existing `_derive_today_look` pipeline. No second recommendation pipeline or duplicate weather endpoint was created.
2. **Singular Canonical 12-Term Scoring Engine:** Outfit candidates generated from the user's owned wardrobe are scored exclusively using `app.domain.services.analysis_rules.score_outfit_candidate` with optional `weather_context`. All 12 baseline terms, occasion matching, pinned item behaviors, and category rules remain untouched.
3. **Four-Level Location Resolution Priority:**
   - Priority 1: Explicit query parameters (`city`, `lat`/`latitude`, `lon`/`longitude`) in the current request.
   - Priority 2: Authenticated user's saved location preference from `UserProfileRecord.settings["weather_location"]`.
   - Priority 3: Guest user's ephemeral location preference in ephemeral user state.
   - Priority 4: `weather_context=None` when no location is available, cleanly falling back to baseline derivation.
4. **Provider Seam & Resilient Orchestration:** Application orchestration depends strictly on the `WeatherProvider` protocol port via `get_weather_provider`. Direct imports of the Open-Meteo adapter in application code are strictly forbidden and avoided. Fail-open resilience (DEC-017-G) guarantees that weather outages, timeouts, upstream 5xx errors, malformed responses, or unexpected exceptions never cause the daily look endpoints to return 500 or 503; they gracefully fall back to baseline scoring without weather.
5. **Privacy by Architecture:**
   - Coarse coordinates only: coordinates are rounded to 2 decimal places (~1.1 km resolution).
   - Zero coordinate exposure: neither raw nor truncated coordinates are ever serialized into API responses or logged in stdout/stderr.
   - Curated city centroids: 20 major city centroid coordinates are embedded in `MAJOR_CITIES` to allow city-only lookups without external geocoding calls or GPS tracking.
6. **API Response Backward Compatibility:**
   - `TodayLookWeather` schema added to `TodayLook` response DTO.
   - `response_model_exclude_none=True` on `GET /v1/looks/today` and `POST /v1/looks/today` ensures that when weather context is omitted or unavailable, the `"weather"` key is completely omitted from the wire JSON, maintaining 100% backward compatibility with existing mobile clients.
   - Missing meteorological fields (such as precipitation probability or wind speed) are represented honestly as `None`, never fabricated.
7. **Strict Scope Discipline:** Zero Flutter changes, zero database migrations, zero external network calls in automated tests, and Phase 4 has NOT started.

---

## 2. Existing Daily-Look Architecture

Prior to Phase 3, Fansivibe's daily look recommendation flow operated as follows:
- **Routers:** [backend/app/api/routers/looks.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/looks.py) exposed `GET /v1/looks/today` (`get_today_look`) and `POST /v1/looks/today` (`regenerate_today_look`).
- **Application Service:** [backend/app/application/today.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/today.py) orchestrated derivation via `GetTodayLook` and `RegenerateTodayLook`, delegating to `_derive_today_look`.
- **Database Model:** Derivation was READ/DERIVE only (TRX-2, DEC-017-A). No `today_look_records` table exists.
- **Candidate Pipeline:**
  1. `_load_owner_wardrobe(...)` loads owner-scoped items in pages of 100 via `WardrobeItemRepository.get_for_user(user_id=user_id)`.
  2. Nearest upcoming event resolved from `UserEventRepository.list_for_user(...)` with `event_date >= utc_today`.
  3. Occasions constructed: `[event_code] + preferred_occasions`.
  4. Candidate generation: `generate_outfit_candidates(adapted)`.
  5. Scoring: `score_outfit_candidate(candidate, items_by_id, frozenset(), occasions)`.
  6. Ranking: `rank_outfit_candidates(...)`.
  7. Deterministic selection: winner chosen via `select_best_outfit_candidate` (or hash index if `key` provided).
  8. Mapping to wire DTO: `TodayLookRecommendation` mapped to `TodayLook` via `_today_to_schema`.

---

## 3. Weather Location Resolution

Location resolution is implemented in `resolve_weather_location` in [backend/app/application/today.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/today.py).

### 3.1 Four-Level Priority Order
1. **Request Query Parameters:** If `latitude` and `longitude` (or `lat`/`lon`) are provided in the HTTP request, they are parsed, checked against valid ranges ($-90 \le \text{lat} \le 90$, $-180 \le \text{lon} \le 180$), and rounded to 2 decimal places. Optional `city` parameter is sanitized and attached.
   If only `city` is provided, `resolve_weather_location` looks up the city in `MAJOR_CITIES`.
2. **Authenticated User Settings:** If request parameters are absent, the user's profile is loaded via `user_state.get_profile(user_id=user_id)`. Settings JSONB is inspected for `weather_location` (or aliases `weatherLocation`, `location`). Both structured objects `{"lat": 47.61, "lon": -122.33, "city": "Seattle"}` and flat keys `{"latitude": 47.61, "longitude": -122.33}` are supported.
3. **Guest Ephemeral User State:** For guest users, the ephemeral user state repository (`EphemeralUserStateRepository`) stores settings in-memory. If the guest supplies a location in their session, it resolves through the same protocol seam without touching PostgreSQL.
4. **Fallback to Absent Context:** If neither explicit params nor user settings provide valid coordinates or a known major city, `resolve_weather_location` returns `None`.

### 3.2 Curated Major City Centroids
To allow manual city selection without requiring GPS or external geocoding services, `MAJOR_CITIES` includes 20 pre-computed coarse centroids:
- London, Paris, New York, Tokyo, Seattle, San Francisco, Los Angeles, Chicago, Berlin, Sydney, Toronto, Milan, Rome, Oslo, Stockholm, Amsterdam, Madrid, Barcelona, Singapore, Seoul.

---

## 4. Authenticated & Guest Behavior

### 4.1 Authenticated Users
- Ownership Scoping (OW-1): Derivation strictly scopes wardrobe items, events, and settings to the authenticated `user_id`. Cross-user data access is impossible by design.
- Persistence: Stored user settings in PostgreSQL `users.settings` JSONB column persist `weather_location`.
- Update Validation: `UpdatePreferences` in [backend/app/application/users.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/users.py) validates `weather_location`:
  - Enforces coarse coordinate rounding: `round(float(val), 2)`.
  - Rejects invalid latitudes ($<-90$ or $>90$) and longitudes ($<-180$ or $>180$) with 422 `VALIDATION_ERROR`.
  - Rejects non-string city names or cities longer than 100 characters with 422 `VALIDATION_ERROR`.
  - Preserves all other unrelated user settings (e.g., `dark_mode`, notifications).

### 4.2 Guest Users
- Ephemeral Isolation (D10 Option A):
  - Guest requests use `EphemeralUserStateRepository` and `EphemeralWardrobeItemRepository`.
  - No database writes, no `users` rows, no session cookies in PostgreSQL.
  - No guest UUID generation in PostgreSQL.
  - Ephemeral user settings support `weather_location` for in-memory recommendation derivation.

---

## 5. Weather Provider Orchestration & Fail-Open Resilience

### 5.1 Seam Isolation
Application orchestration imports only `WeatherProvider` and domain errors from `app.domain.ports.external`. The Open-Meteo adapter implementation remains isolated behind the dependency injection seam `get_weather_provider` in [backend/app/api/deps.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/deps.py).

### 5.2 Fail-Open Containment (DEC-017-G)
In `_derive_today_look`:
```python
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
```
Weather is strictly advisory. An upstream provider outage, network timeout, rate limit, or invalid response results in `weather_context = None`, allowing outfit recommendation to complete normally with baseline scoring. The endpoint never returns 500 or 503 due to weather unavailability.

---

## 6. Canonical Scoring Integration

In `_derive_today_look`:
```python
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
```
- When `weather_context is None`, `score_outfit_candidate` produces identical scores to pre-weather baselines across all 12 canonical terms.
- When `weather_context` is provided, `_weather_points` calculates a soft advisory adjustment $[-10.0, +10.0]$:
  - Cold weather ($<10^\circ\text{C}$): Rewards thermal insulation, wool, layering, and coats.
  - Hot weather ($>25^\circ\text{C}$): Demotes heavy outerwear, rewards linen, cotton, and breathable garments.
  - Rain/Snow: Rewards waterproof/water-resistant outerwear shells, demotes water-vulnerable fabrics (suede, silk).
- The composite candidate score is clamped to $[0.0, 100.0]$.
- Candidate ranking, winner selection, and runner-up alternative selection use the unified canonical scores without secondary sorting pipelines.

---

## 7. Daily-Look API Contract & Response Compatibility

### 7.1 Schema Additions
In [backend/app/api/schemas/today.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/schemas/today.py):
```python
class TodayLookWeather(BaseModel):
    """Normalized weather context exposed in TodayLook (Stage 2 P1-3)."""
    applied: bool = True
    condition: str
    conditionCode: Optional[str] = None
    temperatureC: float
    temperatureF: float
    apparentTemperatureC: Optional[float] = None
    apparentTemperatureF: Optional[float] = None
    precipitationProbability: Optional[float] = None
    precipitationMm: Optional[float] = None
    windSpeedKmh: Optional[float] = None
    isRaining: Optional[bool] = None
    forecastTimestamp: Optional[datetime] = None
    city: Optional[str] = None
    summary: str
    fallback: bool = False
```
`TodayLook` includes:
```python
class TodayLook(BaseModel):
    title: str
    occasion: Optional[str] = None
    weather: Optional[TodayLookWeather] = None
    description: str
    matchScore: int = Field(ge=0, le=100)
    styleScore: int = Field(ge=0, le=100)
    ...
```

### 7.2 Summary String Generation
`_build_weather_payload` generates a concise, user-friendly summary string suitable for Flutter display:
- With city: `"{temp}°C • {condition} in {city}"` (e.g., `"14°C • Moderate rain in Seattle"`).
- Without city: `"{temp}°C • {condition}"` (e.g., `"22°C • Clear sky"`).

### 7.3 Backward Compatibility Invariants
- `response_model_exclude_none=True` on `GET /v1/looks/today` and `POST /v1/looks/today` ensures that when `weather is None`, the `"weather"` field is omitted from wire JSON. Existing clients that don't send location parameters continue to receive byte-compatible responses without breaking changes.
- Existing clients that ignore the new `"weather"` object can safely ignore it without deserialization errors.

---

## 8. Privacy & Security Safeguards

1. **Coarse Resolution Only:** Coordinates are truncated to 2 decimal places ($\approx 1.1\,\text{km}$). High-precision GPS coordinates are never stored or forwarded to upstream weather providers.
2. **Zero Coordinate Wire Leakage:** Neither latitude nor longitude is ever returned in `TodayLookWeather` or any response payload.
3. **Zero Exception Leakage:** Provider error messages, stack traces, and internal URLs are logged internally at `WARNING` or `ERROR` level and never returned in API responses.
4. **OW-1 Owner Scoping:** Wardrobe items, saved looks, and user preferences are strictly validated against `current_user_id`.
5. **No Ephemeral Guest Persistence:** Guest sessions remain ephemeral in memory; no database rows are created.

---

## 9. Test Execution & Verification

### 9.1 Focused Phase 3 Orchestration Suite
A dedicated test suite [backend/tests/test_weather_orchestration.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_weather_orchestration.py) was implemented with 42 comprehensive tests organized into 7 suites:

| Test Suite | Test Count | Focus Areas | Result |
|---|---|---|---|
| **Suite 1: Location Resolution** | 14 | Request coords priority, major city fallback, stored settings priority, flat settings, guest ephemeral state, out-of-range coords rejection, boolean rejection, absent locations. | PASSED (14/14) |
| **Suite 2: Provider Orchestration** | 7 | Successful fetch with context, skipping fetch when location is None, transient error fallback, response error fallback, timeout fallback, unexpected error containment, None provider fallback. | PASSED (7/7) |
| **Suite 3: Canonical Scoring** | 3 | Cold weather outerwear promotion, hot weather outerwear demotion, baseline identity when weather is absent. | PASSED (3/3) |
| **Suite 4: API Response & Compatibility** | 8 | Payload builder fields, None context handling, negative temperatures, city omissions, full schema validation, GET /v1/looks/today wire response, POST /v1/looks/today wire response, omission of weather field when absent. | PASSED (8/8) |
| **Suite 5: Settings Integration & Privacy** | 4 | Coordinate sanitization to 2 decimals, latitude range validation, longitude range validation, invalid city type rejection. | PASSED (4/4) |
| **Suite 6: Security & Isolation** | 3 | Authenticated OW-1 isolation, unauthenticated 401 response, guest ephemeral repositories zero-DB invariant. | PASSED (3/3) |
| **Suite 7: Recommendation Integrity** | 2 | Event occasion preserved with weather, canonical scoring engine preserves 12 terms and bounded $[-10, +10]$ weather adjustment. | PASSED (2/2) |
| **TOTAL** | **42** | **Phase 3 Focused Coverage** | **PASSED (42/42)** |

### 9.2 Full Regression Test Suite
Executed the complete relevant test suite across weather, recommendation, preferences, settings, and hydration:
```
backend/tests/test_weather_orchestration.py (42 passed)
backend/tests/test_weather_provider.py (18 passed)
backend/tests/test_weather_scoring.py (70 passed)
backend/tests/test_p1_1_outfit_swap.py (8 passed)
backend/tests/test_saved_look_hydration.py (11 passed)
backend/tests/test_settings.py (15 passed)
backend/tests/test_update_preferences.py (15 passed, 2 skipped DB)
backend/tests/test_preferences_settings_persistence.py (25 passed)
```
**Total:** 204 passed, 2 skipped (DB-only), 0 failed in 1.10s.

### 9.3 Code Quality Checks
- `python -m py_compile` across all backend files: **PASSED (0 errors)**.
- `git diff --check`: **PASSED (0 whitespace errors)**.

---

## 10. Files Created and Modified

### Created Files:
1. `backend/tests/test_weather_orchestration.py` — Comprehensive Phase 3 application orchestration and API response test suite (42 tests).
2. `docs/audits/STAGE2_P1_3_PHASE3_BACKEND_ORCHESTRATION_IMPLEMENTATION.md` — This implementation report.

### Modified Files:
1. `backend/app/domain/ports/repositories.py` — Added `weather: Optional[dict[str, Any]] = None` to `TodayLookRecommendation` dataclass.
2. `backend/app/api/schemas/today.py` — Added `TodayLookWeather` Pydantic model and optional `weather` field to `TodayLook`.
3. `backend/app/application/today.py` — Added `resolve_weather_location`, `_build_weather_payload`, updated `_derive_today_look` to async with weather provider orchestration, updated `GetTodayLook` and `RegenerateTodayLook` use cases to accept `weather_provider` and query parameters.
4. `backend/app/api/routers/looks.py` — Injected `get_weather_provider` and location query parameters (`city`, `lat`/`latitude`, `lon`/`longitude`) into `get_today_look` and `regenerate_today_look`, mapped `record.weather` to `TodayLookWeather` in `_today_to_schema`.
5. `backend/app/application/users.py` — Added validation and coarse coordinate truncation (`round(coord, 2)`) for `weather_location` in `UpdatePreferences`.
6. `CURRENT_STATE.md` — Updated to record completion of Stage 2 P1-3 Phase 3.

---

## 11. Remaining Limitations & Non-Blockers

1. **Flutter Client Implementation Deferred to Phase 4:** The frontend Flutter app does not yet render the `TodayLookWeather` badge, temperature display, or weather-aware summary banner. This is strictly deferred to Phase 4 per the project authorization.
2. **City Geocoding Service:** The backend relies on client-supplied coarse coordinates or the curated 20-city centroids in `MAJOR_CITIES`. A full-featured server-side geocoding API was intentionally omitted to avoid third-party dependencies, rate limits, and network latency.
3. **Database Schema Untouched:** No new tables or migrations were added; `users.settings` JSONB accommodates `weather_location` transparently.

---

## 12. Confirmation of Stop Condition

Phase 3 is complete and 100% verified.  
**Phase 4 (Flutter Integration) has NOT started.** No Flutter files were modified or created. Work has halted awaiting project owner authorization for Phase 4.
