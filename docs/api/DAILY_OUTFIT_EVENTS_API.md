# Fansivibe — API Contract: Daily Outfit & Events

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> the daily-outfit and events surfaces**: get today's look, regenerate it,
> create/list/get/update/delete events, and generate an event-specific outfit
> recommendation — with **weather/context data** handled where the domain
> actually supports it. It is the focused companion to
> `API_CONTRACT_RULES.md` (§12.7 events, §12.8 today's look, §8.2 list
> envelope, §10 pagination, §13 DTO sketches) and `API_INVENTORY.md`
> (endpoints 26–30 events, 31–33 today's look, 21 occasions vocabulary), and
> it sits beside the sibling contracts `RECOMMENDATION_API.md` (the daily look
> and event outfit are **ensemble/derived-look families** of the one common
> `Recommendation` envelope), `WARDROBE_API.md` (the wardrobe items a daily/
> event outfit consumes), `PROFILE_ONBOARDING_API.md` (preferred occasions),
> and `AUTH_API.md` (identity/ownership).
>
> **Status: contract design only. The daily-outfit and events APIs are NOT
> implemented.** No code, no `deps.py`, no routers, no SQL migrations, no
> dependencies, no Flutter changes. The live contract (`GET /health`,
> `POST /v1/assistant/chat`) is preserved unchanged. Both surfaces are **P1**
> (M8 events, M9 daily outfit) and stay **unmounted** until the auth seam
> (D-AUTH-1) lands (API-12) — no fake 200 before then.
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> the real features (`event_list_screen.dart`, `add_event_screen.dart`,
> `event_details_screen.dart`, `daily_outfit_screen.dart`,
> `event_mock_data.dart`, `daily_outfit_mock_data.dart`,
> `home_mock_data.dart`), STEP 3 `FANSIVIBE_DOMAIN_MODEL_V1.md` (E3
> `UserEvent`, today's look as value object), STEP 4 `TABLE_DEFINITIONS.md`
> (`user_events`, `today_look_records`* P1, `event_types`/`occasions` vocab) +
> `TRANSACTION_BOUNDARIES.md` (TRX-7) + `BUSINESS_CONSTRAINTS.md` (BC-13/
> BC-56/BC-57) + `VALUE_OBJECTS.md` (Date Range), STEP 5
> `APPLICATION_USE_CASES.md` (UC-16…UC-21) + `DECISION_ENGINE_ARCHITECTURE.md`
> + `BACKEND_ARCHITECTURE_RULES.md` (BA-6 WeatherProvider port), STEP 6
> `API_CONTRACT_RULES.md` (§12.7/§12.8/§8.2/§10/§13) + `API_INVENTORY.md`
> (endpoints 26–33/21).

---

## 1. Purpose and scope

This document defines, for every **required operation** on these two surfaces,
the contract attributes the STEP 6 design task asks for — **method, path,
request schema, response schema, validation, authorization, errors** (plus
security considerations, side effects, and domain entities, following the same
convention as the sibling contracts). The task's coverage list is mapped
operation by operation (§3, §5):

- **daily outfit: get today's outfit** — §5.1 (D-1)
- **daily outfit: regenerate today's outfit** — §5.2 (D-2, **supported** —
  `POST /v1/looks/today`, action 13)
- **daily outfit: save today's look** — §5.3 (D-3, referenced — the daily
  surface's save path, owned by M7)
- **events: create event** — §5.4 (E-1)
- **events: list events** — §5.5 (E-2)
- **events: get a single event** — §5.6 (E-3, **additive** — not in the
  inventory)
- **events: update event** — §5.7 (E-4)
- **events: delete event** — §5.8 (E-5)
- **events: generate event outfit recommendation** — §5.9 (E-6)
- **weather / context data** — §4.2 (daily look) + §4.3 (event context)

**The three binding design rules of this document:**

1. **Both surfaces are owner-scoped user state + derived value objects.**
   Every event is owner-scoped (OW-1, BC-19-style composition); a foreign or
   non-existent `event_id` → **404-not-403** (API-10). The **today's look and
   the event outfit are derived value objects** — regenerable, never persisted
   as truth (TRX-2/TRX-7); only an explicit save freezes a snapshot (§4.8,
   `RECOMMENDATION_API.md` §4.8).
2. **Weather is a hint, never authoritative.** The daily look may be seeded
   with a weather hint through the `WeatherProvider` port (BA-6); the wire
   carries the derived `weather` display string only, and the client never
   sends weather. Events carry **user-provided context** (event type, date,
   time, location, notes) that seeds occasion-aware outfit generation
   (R35) — not weather. No invented weather/subscription API exists (§4.2).
3. **Events are user current-state rows; the event outfit is a separate,
   regenerable recommendation.** `user_events` is a normalized P1 row
   (BC-13, TRX-7 single insert); creating/updating an event **also feeds**
   `preferred_occasions` (R36). `POST /v1/events/{event_id}/outfit` (E-6)
   reuses the outfit generation engine pre-seeded with the event's occasion —
   it returns the **same `OutfitRecommendation` DTO** as the builder
   (ensemble family, §4.4) and is **not** a stored child of the event.

**What it does not do:** implement anything, mount endpoints, change the
frozen assistant DTOs, add a weather/subscription provider API, or re-own the
saved-look/wardrobe/knowledge surfaces (those are referenced, not
re-defined). The events + today's-look endpoints are owned by this doc; the
save path (endpoint 33) and the occasions vocabulary (endpoint 21) are
referenced and kept identical to their contracts.

### 1.1 Grounding facts (re-verified)

- **The daily outfit and events are real, local-only features today.**
  `DailyOutfitScreen` (home) renders a **regenerated mock** `DailyOutfitData`
  and "Save Look" writes `LearningService.addSavedLook` (action 12);
  "Generate Another Look" re-derives the same mock (action 13). Events are
  **widget state lost on restart**: `AddEventScreen` writes only a local
  `_events` list + the `occasion_preferred` learning signal; `EventDetailsScreen`
  shows `hasOutfitRecommendation` as a local flag and "Generate Outfit"
  navigates to the builder (`buildOutfit` route) — **no outfit is fetched for
  the event today** (action 11 `future-required`,
  `ACTION_API_INVENTORY.md`). The contract defines the server surface.
- **`user_events` is a normalized P1 row** (PR-1): `id uuid`, `user_id`,
  `title [1,200]`, `event_type_id FK event_types` (**mandatory**, RESTRICT,
  R34), `event_date` (`date` value object, not a timestamp), `location?`,
  `notes?`, `created_at`, `updated_at` (`TABLE_DEFINITIONS.md` §4.1). The
  event date is validated **not in the past** (UC-18). Creating/updating an
  event also records the occasion preference (R36, TRX-7).
- **Event types are a controlled vocabulary, not client hardcodes** (K9.1,
  API-14): the mock's `EventType.mockTypes` (casual/formal/business/date/
  party/travel/workout/other) are the renderings of `event_types.code`; the
  add-event screen picks a type and the wire carries the **code**, never a
  free string. `GET /v1/knowledge/occasions` (endpoint 21) is the public
  occasions vocabulary read (referenced, M5).
- **Today's look is a derived, sync value object** (UC-16/17, M9):
  `GET|POST /v1/looks/today` derive it from StyleProfile + wardrobe +
  optional nearest event + a **weather hint** (`WeatherProvider` port, BA-6 —
  never authoritative). Score is the **0–100 int** scale of the derived-look
  family (§4.4). `today_look_records` history is **conditional** — INSERT
  only if the P1 decision lands (`TABLE_DEFINITIONS.md` §4.6); until then the
  look is a regenerable computation (TRX-2).
- **The event outfit reuses the ensemble family.** `POST
  /v1/events/{event_id}/outfit` (UC-21, endpoint 30) returns the **bare
  `OutfitRecommendation` value object** — identical to `POST
  /v1/outfits/generate` (endpoint 41), only the seeding occasion differs
  (`RECOMMENDATION_API.md` §3.1/§4.3). Regenerable (TRX-7); only a save
  persists it. **No separate event-outfit DTO exists.**
- **The task's operations map 1:1 to the accepted inventory:** `GET
  /v1/looks/today` (31, UC-17), `POST /v1/looks/today` (32, UC-16), `POST
  /v1/looks/today/save` (33, referenced), `POST /v1/events` (26, UC-18),
  `GET /v1/events` (27), `PUT /v1/events/{event_id}` (28, UC-19), `DELETE
  /v1/events/{event_id}` (29, UC-20), `POST /v1/events/{event_id}/outfit`
  (30, UC-21). All **auth + owner** (OW-1). **No `GET /v1/events/{event_id}`
  exists in the inventory** — §5.6 defines it as additive (today the details
  screen is served from the tapped `UserEvent` in the list).
- **No archive for events; delete IS supported.** `user_events` has no
  archive/status column (current state only, BC-13); there is no archive
  endpoint. Delete (UC-20) removes the row; **history is untouched** — the
  `occasion_preferred` and `look_saved` signals have no FK to the event
  (BC-41 pattern). The derived event outfit is regenerable and is **not** a
  stored child, so deleting an event never deletes a recommendation.
- **Idempotency:** `POST /v1/looks/today/save` **requires** `Idempotency-Key`
  (TRX-3); `POST /v1/looks/today` (regenerate) and `POST
  /v1/events/{event_id}/outfit` (generation) are **never idempotent** — each
  call derives a new value (like analysis submission, §11); `PUT`/`DELETE`
  and reads are naturally idempotent. `POST /v1/events` (create) is **not**
  in the inventory's keyed list (§8.4 records the choice).
- **Path-collision guard:** `/v1/looks/today`, `/v1/looks/today/save`,
  `/v1/looks/saved`… must be registered **before** `/v1/looks` and
  `/v1/looks/{look_id}` (`API_CONTRACT_RULES.md` §7).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `event_mock_data.dart` | The real event shape (`UserEvent`: id/name/date/time/eventType/hasOutfitRecommendation) + `EventType.mockTypes` (8 codes) — the client renderings of the wire DTO + vocabulary. |
| `event_list_screen.dart` / `add_event_screen.dart` / `event_details_screen.dart` | The real UX: list (local `_events`), add-event form (type grid, date, time, location/notes), details (date/time display, `hasOutfitRecommendation` badge, "Generate Outfit" → builder route) — grounding the CRUD + event-outfit flows. |
| `daily_outfit_mock_data.dart` | `DailyOutfitData` — title/occasion/weather/description/matchScore(0-100)/styleScore/components[]/reasons[]/styleDna/wardrobeContext/aiSelectionReason?/confidenceBoost?/aiInsights[]/alternatives[]/dailyStyleTip? — the client rendering of the `TodayLook` wire DTO. |
| `daily_outfit_screen.dart` | The real UX: occasion + weather chips, "Save Look" (`addSavedLook`, action 12), "Generate Another Look" (action 13) — grounding D-1/D-2/D-3. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | E3 `UserEvent`; today's look as a value object; `VALUE_OBJECTS.md` Date Range (`UserEvent.date`/`time`). |
| `TABLE_DEFINITIONS.md` | `user_events` (columns/constraints), `event_types`/`occasions` vocab, `today_look_records`* (P1, conditional); PR-1/PR-2/PR-3. |
| `BUSINESS_CONSTRAINTS.md` | BC-13 (title bound), BC-56 (outfit membership validated by domain), BC-57 (event-type/occasion validity). |
| `TRANSACTION_BOUNDARIES.md` | TRX-7 (single INSERT; event outfit derived, not stored), TRX-2 (today's look = computation), TRX-3 (save = snapshot + signal). |
| `APPLICATION_USE_CASES.md` | UC-16 `GenerateDailyOutfit`, UC-17 `GetTodayLook`, UC-18 `CreateEvent`, UC-19 `UpdateEvent`, UC-20 `DeleteEvent`, UC-21 `GenerateEventOutfit`. |
| `BACKEND_ARCHITECTURE_RULES.md` / `DECISION_ENGINE_ARCHITECTURE.md` | BA-6 (external systems via ports), the `WeatherProvider` port (hint only); decision-engine stages (occasion × wardrobe scoring). |
| `API_CONTRACT_RULES.md` | Catalog §12.7/§12.8, list envelope §8.2, pagination §10, DTO sketches §13, errors §9, idempotency §11, URI map §7. |
| `API_INVENTORY.md` | Endpoints 26–30 (events), 31–33 (today's look), 21 (occasions vocab); related domain entities per endpoint. |
| Sibling contracts | `RECOMMENDATION_API.md` (derived-look `TodayLook` + ensemble `OutfitRecommendation` families, §4.3), `WARDROBE_API.md` (wardrobe items the looks consume), `PROFILE_ONBOARDING_API.md` (R-1 preferred occasions), `AUTH_API.md` (Bearer, OW-1). |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), CONFLICT (409), EXTERNAL_SERVICE_FAILURE (503), RATE_LIMITED (429). |

---

## 3. Operation selection (define only the required operations)

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| D-1 | **Get today's outfit** | **Required** — `GET /v1/looks/today` | UC-17, endpoint 31, action 13 read. Home Daily Outfit card. §5.1. |
| D-2 | **Regenerate today's outfit** | **Required — supported** — `POST /v1/looks/today` | UC-16, endpoint 32, action 13. Derives a fresh look (per `?seed=`). §5.2. |
| D-3 | **Save today's look** | **Required (referenced)** — `POST /v1/looks/today/save` | Endpoint 33, action 12. Snapshot + `look_saved` signal, TRX-3. Owned by M7 — referenced, not re-defined. §5.3. |
| E-1 | **Create event** | **Required** — `POST /v1/events` | UC-18, endpoint 26, action 9. Validated create + occasion preference (R36, TRX-7). §5.4. |
| E-2 | **List events** | **Required** — `GET /v1/events` | Endpoint 27, action 9 read. Upcoming events, paginated/sorted by `event_date`. §5.5. |
| E-3 | **Get a single event** | **Defined; additive** — `GET /v1/events/{event_id}` | The task requires the coverage; the resource already exists in the URI map (PUT/DELETE). **Not in the current 48-endpoint inventory** — today the details screen is served from the tapped `UserEvent` in the list; documented fully, stays unmounted until accepted (API-2). §5.6. |
| E-4 | **Update event** | **Required** — `PUT /v1/events/{event_id}` | UC-19, endpoint 28, action 10. Full-object PUT (the inventory's method). §5.7. |
| E-5 | **Delete event** | **Required** — `DELETE /v1/events/{event_id}`; **archive NOT supported** | UC-20, endpoint 29, action 10. Hard delete; history untouched (BC-41). No archive column exists. §5.8. |
| E-6 | **Generate event outfit recommendation** | **Required** — `POST /v1/events/{event_id}/outfit` | UC-21, endpoint 30, action 11. Occasion-seeded generation → `OutfitRecommendation` (ensemble family); regenerable, not stored (TRX-7). §5.9. |
| — | **Save an event outfit** | **NOT defined here** | An event outfit is saved through the type-agnostic save (`POST /v1/looks/saved`, endpoint 23 / `POST /v1/outfits/saved`, endpoint 42 — referenced, `RECOMMENDATION_API.md` §4.8). No per-event save endpoint. |
| — | **Weather / forecast endpoint, weather preferences** | **NOT defined** | Weather is a backend hint via the `WeatherProvider` port (BA-6), never a client input or a user-facing API resource (§4.2). |
| — | **Bulk event operations, reordering, event recurrence** | **NOT defined** | No product action or UC supports them; no invented endpoints. |

### 3.1 What these surfaces are (and are not)

The daily-outfit and events surfaces are **owner-scoped user current state
(events) + derived, regenerable value objects (looks)**, with vocabulary and
saved-look persistence referenced from their own surfaces:

```
daily:  GET  /v1/looks/today                    →  TodayLook   (D-1; derived, sync)
        POST /v1/looks/today?seed=              →  TodayLook   (D-2; regenerate — supported)
        POST /v1/looks/today/save               →  SavedLook   (D-3; referenced, TRX-3)
events: POST /v1/events                         →  UserEvent   (E-1; + occasion_preferred, TRX-7)
        GET  /v1/events?from=&sort=&page=       →  UserEventList (E-2; envelope)
        GET  /v1/events/{event_id}              →  UserEvent   (E-3; additive)
        PUT  /v1/events/{event_id}              →  UserEvent   (E-4; full replace)
        DELETE /v1/events/{event_id}            →  204         (E-5; archive NOT supported)
        POST /v1/events/{event_id}/outfit       →  OutfitRecommendation (E-6; ensemble family)
vocab:  GET /v1/knowledge/occasions             →  event-type/occasion codes (referenced, M5)
weather: backend hint via WeatherProvider port  →  never a client input or API resource
```

There is **no** archive state for events, **no** weather/forecast endpoint,
**no** per-event outfit save, and **no** stored "current event outfit". All
recommendation delivery follows the common `Recommendation` envelope
(`RECOMMENDATION_API.md` §4): today's look = derived-look family (`TodayLook`),
event outfit = ensemble family (`OutfitRecommendation`).

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19).
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- `Idempotency-Key` **required** on `POST /v1/looks/today/save` (D-3, §11);
  **never** on regenerate (D-2) or event-outfit generation (E-6) — each call
  derives a new value; **naturally idempotent** on `PUT`/`DELETE`/reads.
  `POST /v1/events` (E-1) is not keyed by the inventory (§8.4).
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1). Vocabulary reads
  carry `X-Knowledge-Version` (KN-1).

### 4.2 Weather / context data (where the domain supports it)

- **Daily look — weather is a backend hint, not a client input.** The
  generation derives a `weather` display string (e.g. "68°F • Partly Cloudy",
  `DailyOutfitData.weather`) via the **`WeatherProvider` port** (BA-6), used
  only as a hint in the decision engine — **never authoritative** (UC-16 note;
  `API_CONTRACT_RULES.md` §12.8). The client **never sends** weather, and no
  weather/forecast API exists. The `weather` field travels **only as output**,
  inside `TodayLook` (§4.5), and is absent when the port has no data (the
  field is optional output, not a guaranteed service).
- **Event — context is user-provided occasion data, not weather.** The event
  carries `eventType` (vocab code), `eventDate`, `time?`, `location?`,
  `notes?` (E-1/E-4). This context **seeds** the event-outfit generation
  (R35: the occasion pre-seeds the ensemble engine) and **feeds**
  `preferred_occasions` (R36). The event outfit response embeds the
  `selectedOccasion` it was derived from (§4.4) — that is the only
  "context echo" on the recommendation.
- **Rule:** no invented weather subscription/provider API, no client-authored
  weather, and no occasion on the wire as a free string (K9.1).

### 4.3 Event vocabulary — types and occasions (K9.1)

- `eventType` on the wire is a **stable vocab code** (`event_types.code`,
  PR-2) — e.g. `casual`, `formal`, `business`, `date`, `party`, `travel`,
  `workout`, `other` (`EventType.mockTypes`). The client maps code → label
  from the public occasions vocabulary (`GET /v1/knowledge/occasions`,
  endpoint 21, referenced — owned by M5).
- Server-side **vocab validation on every event write** (API-14, BC-57): an
  unknown `eventType` → `422 VALIDATION_ERROR` with allowed values in
  `details`. No free strings.
- `eventDate` is a **date value object** (`VALUE_OBJECTS.md` §3.1), carried as
  ISO-8601 **date** (`YYYY-MM-DD`) — **not** a timestamp; validated **not in
  the past** (UC-18 → `422`). `time`/`location`/`notes` are optional user
  context (see §8.3 for the `time`/schema note).

### 4.4 The recommendation DTOs (frozen to the common contract)

The looks reuse the **two frozen value-object families** from
`RECOMMENDATION_API.md` §4.3 — no new DTO is invented here:

```
TodayLook            { title*, occasion*, weather?, description*, matchScore*,   // derived-look family
                       styleScore*, components*: DailyOutfitComponent[],         //   0–100 int score
                       reasons*: string[], styleDna*, wardrobeContext*,
                       aiSelectionReason?, confidenceBoost?, aiInsights[],
                       alternatives[], dailyStyleTip? }
OutfitRecommendation { title*, matchScore*, components*: OutfitComponent[],      // ensemble family
                       reasons*: string[], colorHarmony*, bodyFit*,              //   0..1 float score
                       occasionMatch*, styleScoreImpact*, improvementSuggestion*,
                       selectedOccasion*, selectedMood*, selectedColorPalette* }
```

Both **satisfy the `Recommendation` envelope** (§4.1 of `RECOMMENDATION_API.md`);
field names/types are identical to `daily_outfit_mock_data.dart` /
`outfit_builder_mock_data.dart` and the accepted §13 sketches. `confidence` /
`tradeOffs` / `expiresAt` are **absent today** (AI-0) — never fabricated. The
event outfit (`OutfitRecommendation`) embeds `selectedOccasion` (= the event's
occasion) as the derivation context echo.

### 4.5 Event DTO (normalized P1 row)

```
UserEvent      { id*, title*, eventType*, eventDate*, time?, location?, notes?,
                 createdAt*, updatedAt* }
EventCreate    { title*, eventType*, eventDate*, time?, location?, notes? }
EventUpdate    { title*, eventType*, eventDate*, time?, location?, notes? }   // full replace
EventSummary   { id*, title*, eventType*, eventDate*, time? }                 // list card, §4.6
```

- `id` is **DB-owned** (PR-3): server UUID, never the client's local id.
- `title` non-empty `[1,200]` (BC-13); `eventType` required vocab code
  (BC-57); `eventDate` required, not in the past (UC-18).
- The client's `hasOutfitRecommendation` flag (`event_mock_data.dart`) is a
  **local presentation state** — the server stores no such column; the
  details screen derives "Ready/Pending" from its local state today (§8.5).

### 4.6 Filters, sorting, pagination (shared for E-2)

- **Filtering (API-23/24/25):** `?from=<date>` (events on/after the given
  date, `YYYY-MM-DD`) — the inventory's accepted filter. `eventType` /
  date-range filters are **additive-only** (not in the inventory). No free-form
  `?filter=json`.
- **Sorting (API-26):** `?sort=event_date` (default; the inventory's key),
  `order=asc|desc`. Unknown key/order → `422`. The API never re-sorts derived
  engine output (none here for events — this is user state).
- **Pagination (API-20):** `?page=1&page_size=20` (1-based; `page` default 1,
  `page_size` default 20, max 100); `total` from the same query. Out-of-bounds
  `page_size` → `422`. Response is the `ListEnvelope`
  `{ items: EventSummary[], page, page_size, total }` (§8.2).

### 4.7 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
`event_id`/`looks` id (own resource only), `request_id` (500). **Never**
another user's data, provider internals, or generated-look internals (C-7/C-8,
ER-0/ER-2).

### 4.8 Auth, ownership, privacy

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | all of `/v1/looks/today*` (get/regenerate/save), `/v1/events*` (create/list/get/update/delete), `/v1/events/{event_id}/outfit`. |
| **Public** | `GET /v1/knowledge/occasions` (no user data, KN-1). |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): every
event is scoped to the caller's `user_id`; another user's (or a non-existent)
`event_id` → `404` — no existence leak. The daily look and event outfit are
derived **per user** (StyleProfile × own wardrobe × own events), never from
another user's data. Events are not image-bearing (no media/privacy surface);
saved looks are private snapshots via M7 (referenced).

---

## 5. Operation contracts

### 5.1 D-1 — Get today's look (`GetTodayLook`, UC-17, endpoint 31)

- **Method / path:** `GET /v1/looks/today`
- **Request schema:** query param `variant?` (optional; a stable seed/variant
  id for the same-day look — the inventory's accepted param).
- **Response schema:** `200 OK` — `TodayLook` (bare value object, §4.4).
  **`404`** when none can be derived (e.g. no wardrobe/context to derive from
  — "none found" is the inventory's empty case, not an invented error).
- **Validation:** `variant` bounded/validated → `422` if malformed.
- **Authorization:** **auth** (Bearer); **owner** — always derived for the
  caller.
- **Errors:** `200`; `401`; `404 NOT_FOUND` (none found); `422 VALIDATION_ERROR`;
  `429 RATE_LIMITED`.
- **Security considerations:** derived from the caller's own StyleProfile,
  wardrobe, and (optional) nearest event; no internals, no provider names; the
  `weather` field is a hint, never asserted as truth (BA-6).
- **Side effects:** none — a derived computation (TRX-2); no rows written
  (`today_look_records` INSERT only if the P1 decision lands, §8.2).
- **Domain entities involved:** today's look (value object); E1.1 `UserState`
  (StyleProfile/preferences), E2 `WardrobeItem`, E3 `UserEvent` (optional
  nearest), E5 `Look` catalog; `WeatherProvider` port (BA-6).

### 5.2 D-2 — Regenerate today's look (`GenerateDailyOutfit`, UC-16, endpoint 32)

- **Method / path:** `POST /v1/looks/today`
- **Request schema:** query param `seed?` (optional; produces a **different**
  result per seed — the "Generate Another Look" flow, action 13).
- **Response schema:** `200 OK` — `TodayLook` (a fresh derivation).
- **Validation:** `seed` bounded/validated → `422` if malformed.
- **Authorization:** **auth** (Bearer); **owner**.
- **Errors:** `200`; `401`; `422 VALIDATION_ERROR`; `503 EXTERNAL_SERVICE_FAILURE`
  (generation/weather-port failure — C-8: no provider internals); `429`.
- **Security considerations:** derived per user; no internals; weather is a
  hint only.
- **Side effects:** none persistent — a regenerable computation (TRX-2). **Not
  idempotent**: each call derives a new value (like analysis submission, §11).
- **Domain entities involved:** as D-1; `seed` selects the derivation variant.

### 5.3 D-3 — Save today's look (`SaveTodayLook`, endpoint 33 — referenced, owned by M7)

- **Method / path:** `POST /v1/looks/today/save`
- **Status:** **referenced** — owned by M7 (`RECOMMENDATION_API.md` §4.8); the
  daily surface's save path, consolidated with `POST /v1/looks/saved`
  (endpoint 23). Defined here only for the daily flow's completeness.
- **Request schema:** the today-look reference/snapshot (`SaveLookRequest`
  with `snapshot` = the `TodayLook` value object, `sourceContext: "daily"`) +
  **`Idempotency-Key` required** (TRX-3).
- **Response schema:** `201 Created` — `SavedLook` (frozen snapshot + title).
- **Validation:** snapshot structural validity + title `[1,200]` (BC-11) →
  `422`.
- **Authorization:** **auth** (Bearer); **owner** (OW-1).
- **Errors:** `201`; `401`; `404`; `409 CONFLICT` (duplicate); `422`;
  `429 RATE_LIMITED`.
- **Side effects:** **one true transaction** (TRX-3): `INSERT saved_looks` +
  `INSERT learning_signals(look_saved)`. Immutable once written (R31).
- **Domain entities involved:** E4 `SavedLook`; E7 `LearningSignal`.

### 5.4 E-1 — Create event (`CreateEvent`, UC-18, endpoint 26)

- **Method / path:** `POST /v1/events`
- **Request schema** (`EventCreate`):

```
{
  "title": "Company Gala",        // required, [1,200] (BC-13)
  "eventType": "formal",          // required — event_types code (K9.1, BC-57)
  "eventDate": "2026-08-15",      // required — ISO date, NOT in the past (UC-18)
  "time": "19:00",                // optional — HH:mm (see §8.3)
  "location": "Grand Ballroom",   // optional — free text, bounded
  "notes": "Black tie",           // optional — free text, bounded
}
```

- **Response schema:** `201 Created` — `UserEvent` (server-assigned `id`,
  `createdAt`, `updatedAt`).
- **Validation:** `title` non-empty `[1,200]`; `eventType` **required** valid
  vocab code (BC-57) → `422` with allowed values; `eventDate` required, valid
  date, **not in the past** → `422` (UC-18); `time` format/`location`/`notes`
  bounded.
- **Authorization:** **auth** (Bearer); **owner** (OW-1).
- **Errors:** `201`; `401`; `404` (account gone); `422 VALIDATION_ERROR`
  (past date/type/bounds); `409 CONFLICT` (duplicate/limit); `429 RATE_LIMITED`.
- **Security considerations:** vocab is knowledge-controlled (no free-string
  types, API-14); the occasion preference is derived server-side (R36), never
  client-echoed as an independent write.
- **Side effects:** **`INSERT user_events`** (TRX-7, tier 1 single insert) +
  records the occasion preference in `user_state.preferences.preferred_occasions`
  (R36, same transaction). `updated_at = created_at` on insert.
- **Domain entities involved:** E3 `UserEvent`; E1.1 `UserState` (preferred
  occasions); vocab `event_types`.

### 5.5 E-2 — List events (`ListEvents`, endpoint 27)

- **Method / path:** `GET /v1/events`
- **Request schema:** query params — `from?` (ISO date), `sort?`
  (`event_date`, default), `order?` (`asc|desc`), `page?`, `page_size?`
  (§4.6).
- **Response schema:** `200 OK` — `ListEnvelope { items: EventSummary[],
  page, page_size, total }` (§8.2), upcoming events, soonest-first by default.
  Empty result is an empty `items` list with `total=0` — **never an error**.
- **Validation:** `from`/`sort`/`order`/pagination validated → `422`.
- **Authorization:** **auth** (Bearer); **owner** — always scoped to the
  caller.
- **Errors:** `200`; `401`; `422 VALIDATION_ERROR` (filters/sort/pagination);
  `429 RATE_LIMITED`.
- **Security considerations:** only the caller's own events.
- **Side effects:** none — a pure read.
- **Domain entities involved:** E3 `UserEvent`.

### 5.6 E-3 — Get a single event (`GetEvent` — additive, not in the inventory)

- **Method / path:** `GET /v1/events/{event_id}` (`event_id` UUID).
- **Status:** **additive** — defined fully because the task requires the
  coverage; **not in the current 48-endpoint inventory** (API_INVENTORY §4 has
  no single-event read). Today the details screen is served **from the list**
  (the tapped `UserEvent` travels with the route). This GET is the natural
  read on the already-resourced `/v1/events/{event_id}` (§7 URI map) and is
  additive under API-2 when the inventory accepts it.
- **Request schema:** none (`event_id` UUID in path).
- **Response schema:** `200 OK` — `UserEvent` (bare, §4.5).
- **Validation:** `event_id` must be a valid UUID → `422`.
- **Authorization:** **auth** (Bearer); **owner** — another user's or
  non-existent `event_id` → `404` (404-not-403).
- **Errors:** `200`; `401`; `404 NOT_FOUND`; `422 VALIDATION_ERROR`.
- **Security considerations:** owner-only; no internals.
- **Side effects:** none.
- **Domain entities involved:** E3 `UserEvent`.

### 5.7 E-4 — Update event (`UpdateEvent`, UC-19, endpoint 28)

- **Method / path:** `PUT /v1/events/{event_id}`
- **Request schema** (`EventUpdate` — **full replace**, the inventory's
  method; all mutable fields sent, same shape as `EventCreate`):
  `title*`, `eventType*`, `eventDate*`, `time?`, `location?`, `notes?`.
- **Response schema:** `200 OK` — the updated `UserEvent` (server-bumped
  `updatedAt`).
- **Validation:** same as E-1 (`title` `[1,200]`; `eventType` valid code;
  `eventDate` not in the past → `422`); the event must exist + be owned →
  `404`.
- **Authorization:** **auth** (Bearer); **owner** (OW-1; 404-not-403).
- **Errors:** `200`; `401`; `404 NOT_FOUND`; `422 VALIDATION_ERROR`;
  `429 RATE_LIMITED`.
- **Security considerations:** owner-only; vocab-validated; occasion
  preference refreshed server-side (R36) when the type/date changes.
- **Side effects:** **`UPDATE user_events`** (single-row, tier 1); refreshes
  `preferred_occasions` (R36). Naturally idempotent (full replace).
- **Domain entities involved:** E3 `UserEvent`; E1.1 (preferred occasions);
  vocab `event_types`.

### 5.8 E-5 — Delete event (`DeleteEvent`, UC-20, endpoint 29)

- **Method / path:** `DELETE /v1/events/{event_id}`
- **Request schema:** none.
- **Response schema:** `204 No Content`.
- **Validation:** `event_id` UUID → `422`; existence + ownership → `404`.
- **Authorization:** **auth** (Bearer); **owner** (OW-1; 404-not-403).
- **Errors:** `204`; `401`; `404 NOT_FOUND`; `422 VALIDATION_ERROR`.
- **Security considerations:** owner-only. **Archive is NOT supported** — no
  archive column/status exists (`user_events` is current state); delete is the
  only removal.
- **Side effects:** **`DELETE user_events`** (tier 1). **History untouched**
  (BC-41): the `occasion_preferred` / `look_saved` signals have no FK to the
  event; any previously saved look snapshot survives. The derived event outfit
  is regenerable and **not** a stored child — nothing to cascade. Naturally
  idempotent (a repeat returns `404`).
- **Domain entities involved:** E3 `UserEvent`.

### 5.9 E-6 — Generate event outfit recommendation (`GenerateEventOutfit`, UC-21, endpoint 30)

- **Method / path:** `POST /v1/events/{event_id}/outfit`
- **Request schema:** none — the event id + its **occasion seed** the
  generation (R35). No body.
- **Response schema:** `200 OK` — `OutfitRecommendation` (bare ensemble-family
  value object, §4.4 — identical DTO to `POST /v1/outfits/generate`; only the
  seeding occasion differs). **`404`** when the event is not found/owned.
- **Validation:** `event_id` UUID → `422`; the event must exist + be owned →
  `404`.
- **Authorization:** **auth** (Bearer); **owner** (OW-1; 404-not-403 on event).
- **Errors:** `200`; `401`; `404 NOT_FOUND` (event); `422 VALIDATION_ERROR`;
  `503 EXTERNAL_SERVICE_FAILURE` (generation — C-8: no provider internals);
  `429 RATE_LIMITED`.
- **Security considerations:** derived from the caller's own event + wardrobe +
  StyleProfile; no internals; `selectedOccasion` echoes the derivation context.
- **Side effects:** none persistent — **regenerable** (TRX-7); **not
  idempotent** (each call derives a new value). Only an explicit save
  (`POST /v1/looks/saved` / `/v1/outfits/saved`, referenced) persists it
  (TRX-3).
- **Domain entities involved:** E3 `UserEvent` (occasion seed); E2
  `WardrobeItem`; E1.1 `StyleProfile`; E5 `Look` catalog; outfit generation
  engine (`ai_engine` M6 — never a provider directly, BA-8).

### 5.10 The daily-outfit + events flow (a sequence of the accepted endpoints — no new endpoint)

```
daily:   GET /v1/looks/today                    → TodayLook        (D-1)
         POST /v1/looks/today?seed=             → TodayLook        (D-2; regenerate)
         POST /v1/looks/today/save              → SavedLook        (D-3; TRX-3, Idempotency-Key)
events:  GET /v1/knowledge/occasions            → type/occasion codes (public, versioned)
         POST /v1/events                        → UserEvent (+ occasion_preferred, TRX-7)
         GET  /v1/events?from=&sort=&page=      → UserEventList    (E-2)
         GET  /v1/events/{event_id}             → UserEvent        (E-3; additive)
         PUT  /v1/events/{event_id}             → UserEvent        (E-4; full replace)
         DELETE /v1/events/{event_id}           → 204              (E-5)
         POST /v1/events/{event_id}/outfit      → OutfitRecommendation (E-6; regenerable)
         save any recommendation                → POST /v1/looks/saved | /v1/outfits/saved (referenced)
```

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `event_id` | UUID; owned (404-not-403) | path param, OW-1 |
| `title` | non-empty, `[1,200]` | BC-13 / §4.5 |
| `eventType` | required valid `event_types.code` → 422 + allowed values | BC-57, K9.1 |
| `eventDate` | required ISO date, **not in the past** → 422 | UC-18, VALUE_OBJECTS §3.1 |
| `time` | optional `HH:mm` (or 12h label per client); see §8.3 | mock `UserEvent.time` |
| `location` / `notes` | optional free text, bounded | §4.5 |
| `from` (filter) | ISO date → 422 | API-24/25 |
| `sort` / `order` | `event_date` × `asc|desc` → 422 | API-26 |
| `page` / `page_size` | 1-based; `page_size` `[1,100]` → 422 | API-20 |
| `variant` / `seed` | optional, bounded → 422 | API-24 |
| `TodayLook` / `OutfitRecommendation` fields | derived, never client-authored; family-frozen shapes (§4.4) | RECOMMENDATION_API §4 |
| `snapshot` (D-3 save) | the type DTO verbatim; structural validity at save time | R31, BC-11 |

All validation is **server-side** (Flutter never enforces security) and
returns the **safe client message**, never internals (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | bad `title`/`eventType`/`eventDate` (past)/`time`/filters/sort/pagination/`event_id`/`variant`/`seed` | field errors + allowed values in `details` |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | event not owned / never existed; today's look none found; account gone | 404-not-403, no existence leak |
| `CONFLICT` | 409 | duplicate save (D-3) | `details.kind` |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | generation / weather-port failure (D-2, E-6) | C-8: no provider internals |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the P1 events +
   daily-outfit surfaces (endpoints stay unmounted until the seam lands,
   API-12).
2. **`Today'sLookRecord` (P1)** — `today_look_records` history is conditional;
   if it ships it adds a read + changes D-1 to "derive or read snapshot"
   (UC-17); no wire change to `TodayLook`.
3. **`time` on events** — the mock `UserEvent.time` is a real field and
   `EventCreate` carries `time?`, but the P1 `user_events` schema has no
   dedicated `time` column (only `event_date date`). Whether `time` merges
   into `event_date` at implementation or stays a request-only field is open —
   the wire keeps `time?` (API-2, never silently dropped).
4. **Idempotency-Key on event create** — the inventory does not key E-1
   (duplicates surface as duplicate rows). Additive if the product wants
   duplicate suppression.
5. **`hasOutfitRecommendation`** — a client-local presentation flag today; the
   server stores no such column. If event-outfit **status** should be
   server-known, that is an additive schema + read decision (§4.5).
6. **E-3 single-event GET** — defined but **additive**: not in the current
   48-endpoint inventory; the details screen is served from the list today.
   Accepted (API-2) when the inventory adds the read.
7. **Archive for events** — **deliberately not defined** (no archive
   column/state/UC). If a soft-delete/archive ships, it adds a
   `status`/`archived_at` column + a controlled key — a product + schema
   decision first (§5.8).
8. **Weather as a user-facing feature** — currently a backend hint via the
   `WeatherProvider` port (BA-6), never a client input or API resource; a
   forecast/preference surface would be a new product decision.
9. All other open decisions from `API_CONTRACT_RULES.md` §16,
   `WARDROBE_API.md` §8, `PROFILE_ONBOARDING_API.md` §8,
   `RECOMMENDATION_API.md` §8, `SCAN_API.md` §8, and `APPEARANCE_API.md` §8
   remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/DAILY_OUTFIT_EVENTS_API.md` —
the field-level API contract for the daily-outfit and events surfaces. It
defines every task operation — **get today's look** (D-1), **regenerate
today's look** (D-2, supported), **save today's look** (D-3, referenced),
**create/list/get/update/delete events** (E-1…E-5), and **generate event
outfit recommendation** (E-6) — each with method/path/request/response/
validation/authorization/errors plus security/side-effects/entities,
consistent with the sibling contracts, and it handles **weather/context data**
honestly (§4.2: weather is a backend hint, never a client input or API
resource; events carry user-provided occasion context that seeds generation).
Nothing is implemented.

**Skills used:** repository + documentation analysis (the real events +
daily-outfit screens and mock data — `event_mock_data.dart`,
`event_list_screen.dart`, `add_event_screen.dart`, `event_details_screen.dart`,
`daily_outfit_mock_data.dart`, `daily_outfit_screen.dart`; `user_events` +
`event_types`/`occasions` + conditional `today_look_records` tables; TRX-7/
TRX-2/TRX-3; BC-13/BC-56/BC-57; UC-16…21; BA-6 WeatherProvider port;
API_CONTRACT_RULES §12.7/§12.8/§8.2/§10/§13; API_INVENTORY endpoints 26–33/21;
RECOMMENDATION_API derived-look/ensemble families §4.3; ERROR_HANDLING
taxonomy) — documentation only.

**Files changed:** `docs/api/DAILY_OUTFIT_EVENTS_API.md` (new);
`CURRENT_STATE.md` (status).

**Validation run:**
- **Every required operation traces 1:1 to the accepted inventory** — D-1→31/
  UC-17, D-2→32/UC-16, D-3→33, E-1→26/UC-18, E-2→27, E-4→28/UC-19,
  E-5→29/UC-20, E-6→30/UC-21; E-3 (single GET) **explicitly flagged additive**
  (not in the inventory; the details screen is served from the list today);
  occasions vocab→21. Paths/methods/auth/UC/errors identical to
  `API_CONTRACT_RULES.md` §12.7/§12.8 and `API_INVENTORY.md` §5.8/§5.9. No
  invented endpoints (archive, weather API, per-event save, event-outfit
  status explicitly excluded).
- **Wire shapes match the accepted sketches AND the real product** — `UserEvent`/
  `EventCreate`/`EventUpdate` field names from `user_events` columns and
  `event_mock_data.dart`; `eventType` carries vocab codes (K9.1) never free
  strings; `TodayLook`/`OutfitRecommendation` identical to the two frozen
  families (`RECOMMENDATION_API.md` §4.3) and to `daily_outfit_mock_data.dart`/
  `outfit_builder_mock_data.dart`; score scales family-frozen (0–100 int
  derived-look vs 0..1 float ensemble); `confidence`/`tradeOffs`/`expiresAt`
  honestly absent (AI-0).
- **Weather/context handled where the domain supports it** — weather is a
  backend hint via the `WeatherProvider` port (BA-6), output-only inside
  `TodayLook`, never a client input or a forecast API; event context
  (type/date/time/location/notes) is user-provided and seeds occasion-aware
  generation (R35) + feeds `preferred_occasions` (R36). No invented weather
  surface.
- **Auth/authorization/errors consistent** — all endpoints auth + owner-only
  (OW-1, 404-not-403); frozen 12-category errors; `POST /v1/looks/today/save`
  keyed (TRX-3), regenerate/event-outfit never idempotent (each call derives a
  new value), `PUT`/`DELETE`/reads naturally idempotent (§11).
- **`git status --short`:** `docs/api/` now holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md,
  SCAN_API.md, HAIRSTYLE_RECOMMENDATION_API.md, RECOMMENDATION_API.md,
  WARDROBE_API.md, DAILY_OUTFIT_EVENTS_API.md (untracked) + `CURRENT_STATE.md`;
  no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The P1 events + daily-outfit endpoints are **not mounted** until D-AUTH-1
  (API-12 — no fake 200).
- Additive/open: E-3 single-event GET, `time` persistence on events,
  event-create idempotency, `hasOutfitRecommendation` server status, event
  archive, `Today'sLookRecord` history (P1).
- Other open decisions unchanged: auth provider (D-AUTH-1), User fields,
  RecommendationHistory (P3), conversation retention, K9.1 knowledge shape,
  media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- "Regenerate today's outfit" is **supported** (UC-16/endpoint 32, action 13)
  — the daily look is a regenerable value object (TRX-2), not a stored record
  until the P1 decision lands.
- The event details screen is served from the list today; E-3 is defined for
  completeness and accepted additively — it changes nothing until mounted.
- `eventType` is a vocab code resolved client-side via the public occasions
  catalog (K9.1); the client never sends free strings.
- The event outfit reuses the ensemble-family `OutfitRecommendation` DTO —
  there is no separate event-outfit shape, and it is never a stored child of
  the event (TRX-7).
- Weather is output-only and optional (a hint); the client never sends weather
  and no weather API exists.
- Delete is the only event removal today; archive is a future product + schema
  decision, not an invented endpoint.

**Constraints honored:** no implementation, the live assistant contract
untouched (F-5), no invented APIs (weather/archive/per-event-save excluded
honestly, E-3 flagged additive), look/event/DTO shapes kept identical to the
accepted contract and sibling docs, the no-internals rule enforced, the UI
Change Safety Rule (no UI touched), and the Scope rule (this document +
`CURRENT_STATE.md` only).
