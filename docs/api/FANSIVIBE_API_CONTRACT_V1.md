# Fansivibe — API Contract V1 (Single Source of Truth)

> **STEP 6 — FINAL API CONTRACT REVIEW.** Consolidates the complete HTTP
> contract between the Fansivibe Flutter client and the FastAPI backend into
> **one authoritative reference**, cross-checked against every STEP 6 contract
> document, the STEP 2–5 accepted designs, the real Flutter project, and the
> live FastAPI backend. This document is the **single source of truth**; where
> a sibling document is ambiguous or diverges, the resolution recorded here
> (¶7) is canonical.
>
> **Status: contract design only. Nothing is implemented.** No endpoints are
> created, no Flutter/routing/UI is modified, no database migrations or
> repositories are written, no services are implemented, no dependencies are
> added, and no existing endpoints are removed. The live contract
> (`GET /health`, `POST /v1/assistant/chat`) is **preserved unchanged**.
>
> **Verdict: the contract is internally consistent.** Cross-checking the 18
> STEP 6 API documents, the STEP 2–5 reference docs, the live backend
> (`backend/app/main.py`, `backend/app/models/schemas.py`), and the real
> Flutter client (`newproject/flutter_application_1/`) produced **one
> field-level wire discrepancy** (¶7.I-1, `AnalysisRun.input_media`) and a set
> of minor, non-blocking doc-level notes (¶7.I-2…I-7). All are resolved
> here. **STEP 6 COMPLETE — READY FOR IMPLEMENTATION.**

---

## 1. Purpose and scope

This document answers, once, for every operation the product performs (the 32
STEP 2 actions clustered into the 33 application use cases):

- **What is the endpoint** (method, `/v1/...` path, auth requirement)?
- **What does the client send** (request DTO, headers, multipart for images)?
- **What does the client receive** (response DTO, envelope or not, status)?
- **What can go wrong** (typed error `code`, HTTP status, safe `details`)?
- **Is it sync or async**, and **does it need idempotency**?

It is the **single source of truth** because it:

1. Locks the **canonical endpoint set** (48 endpoints, ¶4) derived from
   `API_INVENTORY.md` and verified 1:1 against `API_CONTRACT_RULES.md` §12 and
   every module contract.
2. Locks the **cross-cutting conventions** (envelopes, errors, pagination,
   idempotency, versioning, security) already accepted in STEP 5/6.
3. Records the **findings register** (¶7) — every discrepancy found during the
   final cross-check and its **resolution**, so implementation never re-opens a
   settled question.

It does **not**: implement routers/DTOs, write SQL, modify Flutter, change
routing, redesign UI, add dependencies, or duplicate the exhaustive field
detail already in `TABLE_DEFINITIONS.md` / `FANSIVIBE_DOMAIN_MODEL_V1.md` /
the module contracts. The P0 DTO sketches are reproduced (¶6) because they are
the parts that must not drift.

### 1.1 Documents under review

| Doc | Role in the contract |
| --- | --- |
| `API_CONTRACT_RULES.md` | **Master**: 16 binding principles (C-1…C-16), headers, auth, methods, URI map, response/error/async shapes, pagination, idempotency, §12 full endpoint catalog, §13 P0 DTO sketches. |
| `API_INVENTORY.md` | Master endpoint inventory (48) with phase and status flags; the source that §12 of the rules and every module doc must match. |
| `API_RESPONSE_CONVENTIONS.md` | Envelope decision (bare DTO / list / error / async-accept), success/error/pagination/async format, identifiers, timestamps, nullable/version fields, request IDs. |
| `API_ERROR_CONTRACT.md` | The public error contract: wire shape, 12-category taxonomy, field errors, request-id correlation, leak-prevention allow-list. |
| `API_VERSIONING.md` | Two-part version model (path major + optional minor pin), breaking-change policy, deprecation/sunset, mobile backward compatibility. |
| `PAGINATION_FILTERING.md` | Offset vs cursor strategy per collection, default/max limits, server-validated filters/sorts, cursor metadata names. |
| `API_SECURITY_REVIEW.md` | Per-endpoint security matrix + findings register (F-1…F-9) for the 48 endpoints and the additive/gated surfaces. |
| Module contracts | `AUTH_API.md`, `PROFILE_ONBOARDING_API.md`, `WARDROBE_API.md`, `ASSISTANT_API.md`, `APPEARANCE_API.md`, `SCAN_API.md`, `HAIRSTYLE_RECOMMENDATION_API.md`, `RECOMMENDATION_API.md`, `DAILY_OUTFIT_EVENTS_API.md`, `FEEDBACK_LEARNING_API.md`, `SUBSCRIPTION_API.md` — per-module field-level endpoint contracts. |

> **Note:** the task list includes `OUTFIT_API.md`; that document does not
> exist. The outfit surface is fully defined by `RECOMMENDATION_API.md` §4.3
> (`OutfitRecommendation`, shared by `POST /v1/outfits/generate` and
> `POST /v1/events/{event_id}/outfit`), `API_CONTRACT_RULES.md` §12.12, and
> `PAGINATION_FILTERING.md` §9.2. No contract content is missing — only the
> filename differs from the task's naming. Resolved (¶7.I-7).

### 1.2 Grounding facts (re-verified against source)

- The backend today has exactly **two routes**: `GET /health` (plain
  `{"status":"ok"}`, versionless, envelope-free) and `POST /v1/assistant/chat`
  (typed `AssistantReply`, no envelope, **no auth**) — `backend/app/main.py`.
- The assistant DTOs are mirrored 1:1 between `schemas.py` and
  `lib/features/assistant/data/models.dart` and are **frozen** (F-13).
- The Flutter client reaches the backend only via
  `lib/features/assistant/data/assistant_client.dart` (`baseUrl` from
  `--dart-define=ASSISTANT_BASE_URL`, `POST $baseUrl/v1/assistant/chat`).
  All 32 STEP 2 actions are otherwise client-local (mocks,
  SharedPreferences) or stubs; **no auth exists** in the app or backend.
- App version `fansivibe 1.0.0+1` → targets API **v1**, default minor
  (`pubspec.yaml`).
- The `analysis_runs` table has an `input_media jsonb` column
  (`TABLE_DEFINITIONS.md:466`) — the basis for the ¶7.I-1 resolution.

---

## 2. The binding principles (C-1…C-16)

Adopted verbatim from `API_CONTRACT_RULES.md` §3. Every endpoint obeys them.

| # | Principle | Meaning on the wire |
| --- | --- | --- |
| C-1 | **Version APIs** | Path `/v1`; additive-only within a version; optional `Accept: application/json; version=1.0` pin; breaking changes → new version + deprecation window. |
| C-2 | **Resource-oriented naming** | Nouns, plural, kebab-case leaf params; verb tails only for genuine actions (`/sync`, `/generate`, `/outfit`, `/chat`). |
| C-3 | **Consistent HTTP methods** | GET=read, POST=create/action, PUT=replace, PATCH=partial, DELETE=delete; 204 for no-content. |
| C-4 | **Consistent response structures** | Single resource → DTO directly (frozen `AssistantReply` stays bare); list → `{items,page,page_size,total}`; camelCase keys. |
| C-5 | **Consistent error structures** | Every error is `{error:{code,message,details}}`; stable `code` from the frozen 12-category taxonomy; safe `message`; allow-listed `details`. |
| C-6 | **Validate all inputs** | Every body/query is a typed Pydantic DTO; vocab validated server-side (422); 404 ≠ 422; media size/type checked (413/422). |
| C-7 | **Never expose DB details** | DTOs are the only shape; no table/column names, SQL, ORM types in any response, error, or header. |
| C-8 | **Never expose AI/provider details** | No provider/vendor/model names, prompts, or raw output in responses; degraded path flagged as `details.degraded=true` only. |
| C-9 | **Enforce authenticated ownership** | `user_id` from the token, never client input; another user's resource → 404 (never 403). |
| C-10 | **Sync vs async** | Sync by default; slow image analysis → `202 + {run_id}` then poll `GET /analysis/runs/{run_id}` (pending→completed|failed, write-once). |
| C-11 | **Pagination** | Offset `?page=&page_size=` (default 20, max 100) where a stable collection grows; cursor for the discover feed; `total` from the same query. |
| C-12 | **Idempotency** | `Idempotency-Key` on saves/sync/create-account/webhook; repeats return the original result. |
| C-13 | **Stable identifiers** | Server-generated UUIDs for user-owned entities; stable text `code` for knowledge/vocabularies; never client-supplied ids. |
| C-14 | **Backward compatibility** | Within `/v1` responses only gain optional fields; `AssistantReply` (F-13) never reordered/renamed; `GET /health` versionless. |
| C-15 | **Auth is not in the domain** | Routers resolve `user_id` via `deps.py`; application/domain receive only `user_id`; no endpoint trusts client identity. |
| C-16 | **AI output is never a source of truth** | Recommendation/analysis endpoints return regenerable results; only explicit *save* endpoints create durable rows. |

---

## 3. Cross-cutting conventions (frozen)

### 3.1 Response shapes (the envelope decision)

| Response kind | Wire shape | Reference |
| --- | --- | --- |
| Single resource (GET one, create, update, action result) | **Bare DTO** — no `data`/`meta` wrapper | C-4, API-17 |
| List | `{ "items": [...], "page": 1, "page_size": 20, "total": 137 }` | C-4, API-18 |
| Error | `{ "error": { "code", "message", "details?" } }` | C-5, API-28 |
| Async accepted | `{ "run_id": "7a2b..." }` | C-10, API-41 |
| No-content (delete/logout/ack) | `204` (empty) | §8.4 |
| Health | `{"status":"ok"}` — versionless, envelope-free | API-4 |
| Feed (discover) | `{ "items": [...], "next_cursor": "...", "has_more": true }` — **no `total`** | API-21; PAGINATION §5.2 |

JSON keys are **camelCase**; timestamps are **ISO-8601 UTC**; date-only fields
are `YYYY-MM-DD`. Optional response values are **omitted**, never `null`/empty
strings (the frozen `AssistantReply` nullable members are the single exception).

### 3.2 The 12-category error taxonomy (frozen)

| `error.code` | HTTP | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | 422 | Invalid input/vocab/date; `details.field_errors` `[{field,error,allowed?}]`. |
| `AUTHENTICATION_ERROR` | 401 | Missing/expired/revoked token (+ `WWW-Authenticate: Bearer`). |
| `AUTHORIZATION_ERROR` | 403 | Authenticated but disallowed (admin path). |
| `NOT_FOUND` | 404 | Resource missing **or not-yours** (no existence leak). |
| `CONFLICT` | 409 | Duplicate, version, sync conflict; `details.kind`. |
| `RATE_LIMITED` | 429 | Throttling (+ `Retry-After`). |
| `AI_FAILURE` | 503 (or none if degraded) | Provider timeout/malformed output; `details.degraded`. |
| `MEDIA_FAILURE` | 413 / 422 / 503 | Image too large/unsupported / blob failure; `details.kind`. |
| `DATABASE_FAILURE` | 500 / 503 | Internal; `details.request_id` only. |
| `EXTERNAL_SERVICE_FAILURE` | 502 / 503 / 402 / 424 | Identity (502), weather/knowledge/billing (503), payment (402/424). |
| `PROCESSING_FAILURE` | 500 (sync) / `status=failed` (poll) | Analysis/generation pipeline; `details.run_id`. |
| `INSUFFICIENT_USER_DATA` | 200+`needs_data` / 422 | Decision needs more user data; `details.missing`. |

Unhandled exceptions → `500 INTERNAL_ERROR`, generic message +
`details.request_id` (API-31). `details` is **allow-list only** (ER-1):
`request_id`, `run_id`, caller-owned resource ids, `field_errors`, `kind`,
`missing`, `retry_after`. Never SQL, prompts, stack traces, tokens,
provider/model names, or user content.

### 3.3 Headers

| Header | Where | Meaning |
| --- | --- | --- |
| `Authorization: Bearer <token>` | every protected endpoint | resolved to `user_id` by `deps.py`; missing/invalid → 401. |
| `Idempotency-Key` | saves/sync/register/subscribe/webhook | API-33; opaque, hashed server-side (API-35). |
| `Accept: application/json; version=1.0` | optional | API-3; unsupported → 422. |
| `X-Request-Id` | every response (echo) | correlation id; in `details.request_id` on 5xx. |
| `Retry-After` | 429 | rate-limit hint. |
| `WWW-Authenticate` | 401 | `Bearer`. |
| `X-Knowledge-Version` | `GET /knowledge/*` | content version (KN-1). |
| `X-Conversation-Id` | request side, `POST /v1/assistant/chat` (additive, gated) | associates chat turns; server creates conversation on first use. |

### 3.4 Authentication and authorization

- **Bearer tokens (API-5)** issued by `POST /v1/auth/*` (UC-1…3), revoked by
  logout (UC-4). Backend never stores passwords or refresh secrets; provider
  is an open seam (D-AUTH-1).
- **Public endpoints (API-7):** `POST /v1/auth/register|social|login`,
  `GET /v1/knowledge/*`, `GET /health`, and `POST /v1/assistant/chat`
  (public **today**; may gain additive auth later without changing its wire
  shape — F-5). Everything else is auth-required.
- **Ownership (OW-1, API-10):** 401 = unauthenticated; 403 = authenticated
  but disallowed (admin only); **404** = missing **or not-yours**. No
  existence leak.
- **Gating (API-12):** sealed/gated modules are **not mounted** and return no
  fake 200: M11 `feedback` (until the feedback UI ships), M16 `media` (until
  MS10.3), M12 analysis (until D-AUTH-1 + MS10.3 + a real analysis pipeline),
  conversation family A-3/A-4/A-5 (until retention decision G6/G7).

### 3.5 Pagination, filtering, sorting

| Collection | Endpoint | Strategy | Default / Max | Filters | Sort keys |
| --- | --- | --- | --- | --- | --- |
| Wardrobe | `GET /v1/wardrobe/items` | offset | 20 / 100 | `category`, `color` | `createdAt`(desc)·`updatedAt`(desc)·`name`(asc) |
| Saved looks (incl. outfits) | `GET /v1/looks/saved` | offset | 20 / 100 | — (`sourceContext` additive) | `createdAt`(desc) |
| Events | `GET /v1/events` | offset | 20 / 100 | `from` | `eventDate`(asc) |
| Conversations (gated) | `GET /v1/assistant/conversations` | offset | 20 / 100 | — | `updatedAt`(desc) |
| Analysis runs | `GET /v1/analysis/runs` | offset | 20 / 100 | `runType` | `createdAt`(desc) |
| Knowledge looks | `GET /v1/knowledge/looks` | offset | 20 / 100 | `occasion`, `style` | catalog `sortOrder` |
| Discover feed | `GET /v1/looks` | **cursor** | 20 / 50 | `occasion`, `style`, `fit` | engine-ranked (no `sort`) |

Rules: `page` 1-based default 1; `page_size` default 20 bound `[1,100]` →
422 outside; cursor opaque + `limit` bound `[1,50]`; empty list → `200`
`items:[]` (never an error); filters/sorts server-validated vocab → 422 with
allowed values; **never re-sort engine output** (API-27).

### 3.6 Idempotency (C-12)

| Applies | Endpoints |
| --- | --- |
| **Requires `Idempotency-Key`** | `POST /v1/auth/register`, `POST /v1/users/me/sync`, `POST /v1/looks/saved`, `POST /v1/looks/today/save`, `POST /v1/outfits/saved`, `POST /v1/feedback` (when live), `POST /v1/subscriptions` |
| **Naturally idempotent (no key)** | `PATCH`/`DELETE`, logout, reads, analysis **submission** |
| **Never idempotent** | `POST /v1/assistant/chat`, `POST /v1/analysis/*` |

Not keyed (accepted trade-off, F-8): `POST /v1/wardrobe/items`,
`POST /v1/events`. Not keyed (F-7): `POST /v1/assistant/feedback`.

---

## 4. The canonical endpoint set (48 endpoints)

Method, path, auth, use case, phase, sync/async, idempotency, and the error
codes each can return. Auth: **public** / **auth** (Bearer → `user_id`).
"Key" = `Idempotency-Key` required. This table is the merged, verified form of
`API_INVENTORY.md` §4 and `API_CONTRACT_RULES.md` §12; where a module doc or
the inventory abbreviated an error set, the fuller set below is canonical.

### 4.1 P0 — the live slice

| # | Method + path | Auth | UC | Notes / Errors |
| --- | --- | --- | --- | --- |
| 01 | GET `/health` | public | — | `{"status":"ok"}` versionless, envelope-free. |
| 02 | POST `/v1/auth/register` | public | UC-1 | 201; 409(email), 422, 429; **Key**. |
| 03 | POST `/v1/auth/social` | public | UC-2 | 200/201; 401, 409, 422, 429, 502. |
| 04 | POST `/v1/auth/login` | public | UC-3 | 200; 401 (uniform), 422, 429. |
| 05 | POST `/v1/auth/logout` | auth | UC-4 | 204; 401 (idempotent). |
| 06 | GET `/v1/users/me` | auth | UC-6 | 200 `ProfileView`; 404. |
| 07 | PATCH `/v1/users/me` | auth | UC-7 | 200; 404, 422, 409(version, If-Match). |
| 08 | PUT `/v1/users/me/preferences` | auth | UC-8 | 200; 422 (vocab). |
| 09 | PUT `/v1/users/me/settings` | auth | (28) | 200; 422. |
| 10 | POST `/v1/users/me/sync` | auth | UC-9/UC-5 | 200; 409(sync), 413, 422; **Key**. |
| 11 | GET `/v1/wardrobe/items` | auth | (5,6,7) | 200 list; 422 (filters/pagination). |
| 12 | POST `/v1/wardrobe/items` | auth | UC-10 | 201; 422, 409. Not keyed (F-8). |
| 13 | PATCH `/v1/wardrobe/items/{item_id}` | auth | UC-11/12 | 200; 404, 409, 422. |
| 14 | DELETE `/v1/wardrobe/items/{item_id}` | auth | UC-13 | 204; 404, 409 (FK refs). |
| 15 | GET `/v1/wardrobe/insight` | auth | UC-14 | 200; 204/empty. |
| 16 | POST `/v1/assistant/chat` | **public today** | UC-22 | 200 bare `AssistantReply` (F-13); 422; **never idempotent**. |
| 17 | POST `/v1/assistant/feedback` | auth | UC-23 | 204; 401, 422, 429. Not keyed (F-7). |
| 18 | GET `/v1/knowledge/looks` | public | (K9.1) | 200 list; 422; `X-Knowledge-Version`. |
| 19 | GET `/v1/knowledge/categories` | public | — | 200 bare `VocabularyItem[]`. |
| 20 | GET `/v1/knowledge/colors` | public | — | 200 bare `VocabularyItem[]`. |
| 21 | GET `/v1/knowledge/occasions` | public | — | 200 bare `VocabularyItem[]`. |
| 22 | GET `/v1/knowledge/items` | public | — | 200 bare `ItemReference[]`. |

### 4.2 P1

| # | Method + path | Auth | UC | Notes / Errors |
| --- | --- | --- | --- | --- |
| 23 | POST `/v1/looks/saved` | auth | UC-15 | 201; 404, 409; **Key** (TRX-3). |
| 24 | GET `/v1/looks/saved` | auth | (14,17) | 200 list (summary rows); 422. |
| 25 | DELETE `/v1/looks/saved/{saved_look_id}` | auth | (7) | 204; 404. |
| 26 | POST `/v1/events` | auth | UC-18 | 201; 422 (past date/type), 409. Not keyed (F-8). |
| 27 | GET `/v1/events` | auth | (9) | 200 list `EventSummary[]`; 422. |
| 28 | PUT `/v1/events/{event_id}` | auth | UC-19 | 200; 404, 422. |
| 29 | DELETE `/v1/events/{event_id}` | auth | UC-20 | 204; 404. |
| 30 | POST `/v1/events/{event_id}/outfit` | auth | UC-21 | 200 `OutfitRecommendation`; 404, 503. Never idempotent. |
| 31 | GET `/v1/looks/today` | auth | UC-17 | 200 `TodayLook`; 404 (none found). |
| 32 | POST `/v1/looks/today` | auth | UC-16 | 200 `TodayLook`; 503. Never idempotent (`?seed=`). |
| 33 | POST `/v1/looks/today/save` | auth | (12) | 201; **Key**. |
| 34 | GET `/v1/learning/summary` | auth | (8,28) | 200 `LearningSummary`. |
| 35 | POST `/v1/feedback` | auth | UC-32 | 201/204; 422, 429. **Gated (NOT mounted)**; **Key** when live. |

### 4.3 P2

| # | Method + path | Auth | UC | Notes / Errors |
| --- | --- | --- | --- | --- |
| 36 | POST `/v1/analysis/outfit` | auth | UC-24 | multipart → `202 {run_id}`; 413/422, 422 (no clothing), 503. **Async; never idempotent.** |
| 37 | POST `/v1/analysis/hairstyle` | auth | UC-25/26 | multipart (`image` for image pass; empty body for profile-only pass — no reference field; `style_profile` by `user_id`, Phase 28) → `202 {run_id}`; 413/422, 422, 503. **Async; never idempotent.** |
| 38 | POST `/v1/analysis/grooming` | auth | UC-27 | empty JSON `{}` (no reference field; `style_profile` by `user_id`, Phase 28) → `202 {run_id}`; 422, 503. **Async; never idempotent.** |
| 39 | GET `/v1/analysis/runs/{run_id}` | auth | (16/21/23) | 200 `AnalysisRun`; 404 (or 422 malformed id). |
| 40 | GET `/v1/analysis/runs` | auth | — | 200 list (summary rows, **no `result`**); 422. |
| 41 | POST `/v1/outfits/generate` | auth | UC-28/29 | 200 `OutfitRecommendation`; 422, 503, 204 (empty wardrobe). Never idempotent. |
| 42 | POST `/v1/outfits/saved` | auth | UC-30 | 201; 409; **Key**. |
| 43 | GET `/v1/looks` | auth | UC-31 | 200 cursor feed; 422 (filters). |
| 44 | GET `/v1/looks/{look_id}` | auth | (14) | 200 `LookDetail` (incl. `isOwned`); 404. |
| 45 | GET `/v1/subscriptions/me` | auth | (30) | 200 `Subscription`; 404 (never subscribed). |
| 46 | POST `/v1/subscriptions` | auth | UC-33 | 200/201; 402/424, 404, 503; **Key**. Not mounted until M15. |
| 47 | POST `/v1/media/uploads` | auth | (M16) | 201 `{upload_id, signedPutUrl, expiresAt}`; 413/422. **Sealed (NOT mounted).** |
| 48 | POST `/v1/media/uploads/{upload_id}/complete` | auth | — | 200 `MediaRef`; 404, 413/422, 503. **Sealed (NOT mounted).** |

### 4.4 Additive / gated (defined, **not mounted** — no fake 200)

| Endpoint | Module | Status |
| --- | --- | --- |
| GET `/v1/assistant/conversations` (A-3) | M4 | additive + gated on G6/G7; summaries `messageCount` only. |
| GET `/v1/assistant/conversations/{conversation_id}` (A-4) | M4 | additive + gated; owner-only transcript. |
| DELETE `/v1/assistant/conversations/{conversation_id}` (A-5) | M4 | additive + gated; whole-conversation delete. |
| GET `/v1/wardrobe/items/{item_id}` (W-2) | M3 | additive; served from the list today. |
| GET `/v1/events/{event_id}` (E-3) | M8 | additive; served from the list today. |

### 4.5 Non-client-facing (system/admin)

| Path | Principal | Notes |
| --- | --- | --- |
| Subscription billing webhook | system | idempotent; never in a DB transaction; updates status/renewsAt/external_ref only. |
| Knowledge seed/write (M5 P2) | admin (`require_admin`) | no user-accessible admin path. |
| Account erasure | server-side | full CASCADE + blob cleanup + external cancel; cancel-first 409 for active subscription. |

---

## 5. Async analysis pattern (C-10, API-40…44)

- **Accept:** `POST /v1/analysis/{outfit|hairstyle|grooming}` → `202` +
  `{ "run_id": "..." }`. Submission is a new run each time (**never
  idempotent**).
- **Poll:** `GET /v1/analysis/runs/{run_id}` → the run DTO, `status ∈
  {pending, completed, failed}`. Write-once (TRX-5): only the guarded
  completion flips `pending → completed|failed`.
- **Completed:** the DTO carries the immutable `result` snapshot +
  `engine_version` (PR-6). `result` = `{ context?, recommendations: { top,
  alternatives } }` for hairstyle/grooming; `{ title, sections, detectedItems,
  confidence? }` for outfit.
- **Failed:** the DTO embeds the same `{error:{code,message,details}}` shape
  with `code = PROCESSING_FAILURE` (or `AI_FAILURE`/`MEDIA_FAILURE`).
- **Run history:** `GET /v1/analysis/runs` returns summary rows **without**
  `result`; the full immutable result is only in the owned detail read.
- **No background jobs in the API layer** (API-43): deferred work lives in
  `infrastructure/jobs.py` + the events dispatcher.

---

## 6. Canonical DTO shapes (P0, frozen)

Field names follow `TABLE_DEFINITIONS.md`; JSON keys are camelCase (API-19).
`*` = required. These are the shapes implementation must not drift from.

### 6.1 Auth (M1)

```
AuthResponse    { accessToken*, tokenType*="bearer", expiresIn*, profile: ProfileView }
RegisterRequest { email*, password*, displayName? }
LoginRequest    { email*, password* }
SocialSignIn    { provider* (google|apple), providerToken* }
```

### 6.2 Profile / preferences (M2)

```
ProfileView {
  displayName*, styleProfile: StyleProfile,
  preferences: Preferences, settings: Settings, flags: Flags, version*
}
StyleProfile { faceShape?, skinTone?, bodyType?, styleType?, sourceRunId? }
Preferences  { preferredOccasions?: string[] /* vocab codes */, ... }   // sparse JSONB
Settings     { /* sparse, controlled keys */ }
SyncRequest  { wardrobe: WardrobeItem[], savedLooks: SavedLookRef[], events?: UserEvent[],
               preferences, styleProfile, flags, clientTimestamp }
SyncReceipt  { mergedProfile: ProfileView, conflicts: Conflict[], syncedAt }
Conflict     { resource: string, kind: "latest-wins"|"append"|"needs-review" }
```

> **PATCH vs entity naming (resolved ¶7.I-2):** the **request** wire field for
> a profile write is `styleDna` (PATCH `/v1/users/me`); the **entity/read**
> field is `styleProfile`. `SyncRequest` uses `styleProfile`. Both carry the
> same `StyleProfile` value shape.

### 6.3 Wardrobe (M3)

```
WardrobeItem     { id*, name*, category*, color*, material?, isFavorite, imageRef?: MediaRef,
                   createdAt*, updatedAt* }
WardrobeItemCreate { name*, category*, color*, material?, imageRef? }
WardrobeItemPatch  { name?, category?, color?, material?, isFavorite? }
WardrobeInsight    { title*, insight*, action?, route? }
MediaRef           { objectKey, mediaType, width?, height?, sizeBytes, contentHash,
                     isGenerated, uploadedAt }
```

### 6.4 Assistant (M4 — **frozen, verbatim** from `schemas.py`, F-13)

```
AssistantRequest { messages: ChatMessage[], user?: UserContext }
ChatMessage      { role*, content* }
UserContext      { wardrobe: WardrobeItem[], face?: FaceData, savedLooks: string[],
                   preferredOccasions: string[] }
AssistantReply   { intent*, text*, cards: SuggestionCard[], clarifications: ClarificationOption[],
                   navigation?: NavigationRequest }
SuggestionCard   { kind, title, subtitle, score?, items: string[], action? }
ClarificationOption { label, value }
NavigationRequest   { route, label }
```

Field names, order, and types must **never** change; the DTOs move verbatim to
`api/schemas/assistant.py` at M1. No envelope, no `data` wrapper.

### 6.5 Knowledge (M5)

```
VocabularyItem { code*, label*, sortOrder*, active }
LookCard       { code*, title*, imageRef?: MediaRef, payload: { ensemble, occasion, style } }
```

### 6.6 Analysis run (M12)

```
AnalysisRun {
  run_id*, run_type* ("outfit"|"hairstyle"|"grooming"; "face" reserved, no endpoint),
  status* ("pending"|"completed"|"failed"), created_at*,
  completed_at?, engine_version?,
  input_media?: MediaRef,     // canonical — see ¶7.I-1
  result?,                    // immutable snapshot when completed
  error?                      // typed error when failed
}
```

### 6.7 Recommendation value objects (M13/M14/M9/M8)

```
OutfitRecommendation { title*, matchScore*, components*: OutfitComponent[],
                       reasons*: string[], colorHarmony*, bodyFit*, occasionMatch*,
                       styleScoreImpact*, improvementSuggestion*, selectedOccasion*,
                       selectedMood*, selectedColorPalette* }
OutfitComponent { id, name, category, color, colorHex, material?, reason }
TodayLook { title*, occasion*, weather?, description*, matchScore*, styleScore*,
            components*: DailyOutfitComponent[], reasons*: string[], styleDna*,
            wardrobeContext*, aiSelectionReason?, confidenceBoost?, aiInsights[],
            alternatives[], dailyStyleTip? }
LearningSummary { styleScore*, breakdown*, streak*, recentSignals* }
SavedLook { id*, lookId?, title*, snapshot*, sourceRunId?, createdAt* }
Subscription { planCode*, status*, startedAt, renewsAt }   // no external_ref on the wire
FeedbackCreate { rating*, reason?, targetLookId?, targetSavedLookId? }   // rating vocab pending
```

> **Naming (resolved ¶7.I-3):** the discover feed row DTO is `LookSummary`
> (list) / `LookDetail` (detail read); the catalog read row is `LookCard`/
> `LookSummary`. Same shape family; the detail DTO carries the full ensemble +
> scores + `isOwned`.

---

## 7. Findings register (cross-check results)

Every discrepancy found in the final review, and its **canonical resolution**.
Severity: **WIRE** = affects a wire DTO/field; **DOC** = doc-level only.

| ID | Severity | Surface | Finding | Resolution (canonical) |
| --- | --- | --- | --- | --- |
| I-1 | WIRE | `AnalysisRun` DTO | `input_media` appears in SCAN_API §4.3, HAIRSTYLE §4.2, RECOMMENDATION §4.7, but is **omitted** from APPEARANCE_API §4.3 (and its response example), even though SCAN claims its DTO is "referenced and kept identical". | **Include `input_media?: MediaRef`** in the canonical `AnalysisRun` DTO (¶6.6). It is a real `analysis_runs.input_media jsonb` column (`TABLE_DEFINITIONS.md:466`) and never a submission request field (submissions use multipart `image`). APPEARANCE_API §4.3 should be corrected at implementation to match. |
| I-2 | DOC | profile write | `styleDna` (PATCH request) vs `styleProfile` (entity/read) — catalog/inventory name the PATCH field `styleDna`; the read entity is `styleProfile`. | Accepted and documented (PROFILE_ONBOARDING_API §1.1/§8.2). Canonical: request = `styleDna`, read/sync = `styleProfile`, same value shape (¶6.2). No change needed. |
| I-3 | DOC | endpoint 17 | `POST /v1/assistant/feedback` error set: inventory says "401 (only)" (`API_INVENTORY.md:502`); ASSISTANT_API and FEEDBACK_LEARNING_API add 422 + 429. FEEDBACK doc self-contradicts ("401 only, per the inventory" then lists 422/429). | Canonical: **204; 401; 422; 429** (¶4.1 #17). The inventory entry is an abbreviation; the fuller set is the target. `AssistantCardFeedback.cardId` is the canonical field name. |
| I-4 | DOC | endpoint 35 | `POST /v1/feedback` auth: inventory hedges "auth (or public with rate limits — future decision)"; FEEDBACK_LEARNING_API requires auth firmly. | Canonical: **auth** (OW-1). Feedback targets user-owned content and requires owner scoping; the gated module mounts as auth when the feedback UI ships (¶4.2 #35). |
| I-5 | DOC | `run_type` vocab | APPEARANCE §4.3 inline run-DTO vocab lists `face`; SCAN §4.3 comment lists only `outfit/hairstyle/grooming` with `face` reserved. | Same intent. Canonical: `{outfit, face, hairstyle, grooming}`; `face` is **reserved, no endpoint** — face analysis mounts on `hairstyle` (¶6.6). No change needed. |
| I-6 | DOC | list-envelope DTO names | `ListEnvelope` vs `WardrobeItemList`/`UserEventList`/`LookFeed`/`EventSummary[]` — same `{items,page,page_size,total}` shape, different type names across docs. | Cosmetic. Canonical: the generic `ListEnvelope` shape (¶3.1); per-resource aliases are the same shape and do not change the wire. No change needed. |
| I-7 | DOC | `OUTFIT_API.md` | The task lists a 19th doc, `OUTFIT_API.md`, which does not exist in `docs/api/` (18 files). | The outfit surface is fully defined in `RECOMMENDATION_API.md` §4.3 + `API_CONTRACT_RULES.md` §12.12 + `DAILY_OUTFIT_EVENTS_API.md` §4.4 + `PAGINATION_FILTERING.md` §9.2. No contract content is missing; only the expected filename differs. Resolved: no new file needed. |
| I-8 | DOC | endpoint 16 | Chat error set: inventory lists "422 only"; ASSISTANT_API target adds 401/429 (auth + rate limit as additive future behavior). | Not a conflict — additive behavior when auth lands (F-5). Canonical target: **200; 422** today; 401/429 become valid only if/when the endpoint gains auth without changing its wire shape (¶4.1 #16). |

### 7.1 Verified consistent (no finding)

- **Endpoint set:** the 48 endpoints in `API_INVENTORY.md` match
  `API_CONTRACT_RULES.md` §12 1:1 (paths, methods, auth, UC, phases), and every
  module contract references them without a conflicting method/path.
- **Error taxonomy:** the 12-category set is identical across
  `API_CONTRACT_RULES.md` §9.1, `API_ERROR_CONTRACT.md` §5,
  `API_RESPONSE_CONVENTIONS.md` §5.1, and `ERROR_HANDLING.md` §5.
- **Envelopes:** bare DTO for single resources; list envelope
  `{items,page,page_size,total}`; `{error:{code,message,details}}`; `{run_id}`;
  cursor `{items,next_cursor,has_more}` — consistent everywhere.
- **Pagination:** offset default 20/max 100, cursor for discover (default
  20/max 50), server-validated filters/sorts → 422 — consistent.
- **Idempotency:** keyed list (register, sync, saved, today-save,
  outfits-saved, feedback-when-live, subscriptions) and never-list (chat,
  analysis) match `API_CONTRACT_RULES.md` §11 and `API_INVENTORY.md` §6.5;
  wardrobe/event create and assistant feedback intentionally not keyed.
- **Async:** analysis submissions are the only async operations (`202 +
  run_id`, poll to terminal, write-once); generation/today's look are sync —
  consistent with `BACKGROUND_JOB_ARCHITECTURE.md` BJ-0.
- **Security posture:** OW-1 + 404-not-403 everywhere; UUID identifiers;
  typed/vocab validation; ER-0/1 leak prevention; MediaRef-only + private
  media + short-lived signed URLs; AI internals never on the wire; summary-only
  lists; erasure CASCADE — all verified strong by `API_SECURITY_REVIEW.md`
  (F-1…F-9 are implementation-milestone controls, none a contract change).
- **Live contract:** `GET /health` and `POST /v1/assistant/chat` unchanged,
  envelope-free, frozen DTOs (F-13); `GET /health` versionless; assistant
  `UserContext.face` travels frozen inside the frozen contract
  (`APPEARANCE_API.md`).
- **Domain/database grounding:** every DTO traces to `FANSIVIBE_DOMAIN_MODEL_V1.md`
  (E1–E10) and `TABLE_DEFINITIONS.md`; `analysis_runs` columns match the run
  DTO; `saved_looks.snapshot`, `user_state.style_profile`, `subscriptions`
  (4 fields, no payment details) all consistent. No endpoint demands data the
  domain model cannot provide; no endpoint exposes a table/column name.
- **32 actions / 33 use cases:** every STEP 2 action maps to ≥1 endpoint and
  every UC-1…UC-33 maps to an endpoint (verified in `API_CONTRACT_RULES.md`
  §17 and the module docs).

---

## 8. Versioning and compatibility (summary)

Adopted from `API_VERSIONING.md` (canonical):

- **Two-part model:** path major `/vN` (authoritative, API-1) + optional minor
  pin `Accept: application/json; version=N.M` (API-3). Default = latest minor
  of the current major (a superset of every older shape, API-2).
- **Within `/v1`:** additive responses only; frozen assistant DTOs (F-13) with
  no reorder/rename/retype; stable status codes and the frozen 12-category
  taxonomy; stable path/method/ownership semantics.
- **Breaking change** (removal/rename/retype/reorder/semantic/status-mapping/
  error-shape/auth-change) → new path major `/v2`, deprecation window,
  side-by-side routing via pure prefix split (rollback-free).
- **Deprecation:** `Deprecation: true` + `Sunset` (RFC 8594) headers;
  sunset unmounts the old major → `410 Gone` (never `404`).
- **Mobile policy:** at least two majors mounted; supported server surface
  covers every API version used by supported-range app builds; retirement =
  ≥90 days AND no supported-range build calls it. Clients tolerate unknown
  fields/vocab; `410`/`422`-unsupported → update-required flow.
- **Gated modules mount additively** (API-12) — M11/M16/M12/conversations are
  new endpoints under `/v1`, never a change to an existing one.

---

## 9. Security (summary)

Adopted from `API_SECURITY_REVIEW.md` (canonical posture):

- **Auth:** Bearer → `user_id` via `deps.py`; tokens issued only by
  `POST /v1/auth/*`; backend never stores passwords/refresh secrets; tokens
  never logged or in URLs.
- **Ownership:** OW-1 + 404-not-403 on every user-owned endpoint; admin/system
  principals closed by default; media namespaced `users/{user_id}/...`.
- **Validation:** typed DTOs + server-validated vocab → 422 with allowed
  values; media MIME allow-list + size checked twice; no free-form
  `?filter=json`.
- **Leak prevention:** `details` allow-list only; never SQL, prompts, stack
  traces, tokens, provider/model names, or user content on the wire; image
  bytes never logged or echoed — only `MediaRef` travels; AI internals never
  on the wire (`details.degraded` boolean only).
- **Findings F-1…F-9** (unquantified rate limits, media deep-inspection,
  snapshot provenance, login enumeration, AI data minimization, accepted
  idempotency trade-offs) land at implementation milestones (M1/M4/M7/M16,
  AI-integration). **None requires a contract change.**

---

## 10. Validation performed (final review)

- **Cross-checked all 18 API docs** in `docs/api/` against each other, the 12
  task cross-check dimensions (missing/duplicate endpoints, request-model
  conflicts, response-model conflicts, domain leakage, database leakage,
  security issues, naming, errors, pagination, unsupported features,
  unimplementable endpoints), the STEP 2–5 reference docs, the live backend,
  and the real Flutter client.
- **Endpoint matrix verified 1:1:** 48 endpoints in `API_INVENTORY.md` §4
  match `API_CONTRACT_RULES.md` §12 and the module contracts; additive/gated
  (A-3/4/5, W-2, E-3) and non-client-facing (webhook, admin seed, erasure)
  surfaces traced to their owning docs.
- **Live contract preserved:** `GET /health` + `POST /v1/assistant/chat`
  verbatim, envelope-free, frozen DTOs (F-13); verified against
  `backend/app/main.py`, `backend/app/models/schemas.py`, and
  `lib/features/assistant/data/models.dart` + `assistant_client.dart`.
- **One wire discrepancy found and resolved** (I-1); all other findings are
  doc-level, cosmetic, or already-accepted (¶7).
- **`git status --short`:** only `docs/api/` (18 untracked API docs +
  `FANSIVIBE_API_CONTRACT_V1.md`) + `CURRENT_STATE.md` (modified). No code,
  directories, or files created; no `pytest` run needed (no code changed).

---

## 11. Open decisions carried forward (unchanged)

These remain open from STEP 5 and **affect the contract only when they land**;
none blocks implementation:

1. **Auth provider (D-AUTH-1)** — determines token/refresh semantics and when
   protected endpoints mount; assistant stays public until then (F-5).
2. **Knowledge shape (K9.1)** — static config vs DB-backed vocab tables;
   endpoint set is fixed either way.
3. **Media privacy (MS10.3)** — lifts the sealed M16 media endpoints.
4. **Feedback design** — shapes `POST /v1/feedback` fields + `rating`
   vocabulary when the UI ships (M11).
5. **Conversation retention (G6/G7)** — gates the A-3/A-4/A-5 conversation
   family.
6. **User fields / profile view contents** — `ProfileView` shape details.
7. **`Today'sLookRecord` (P1)** and **`RecommendationHistory` (P3)** — add
   history reads only if built.
8. **Rate-limit thresholds (F-2)** — quantified per-surface limits at M1.

---

## 12. Report

**What changed (this step):** added `docs/api/FANSIVIBE_API_CONTRACT_V1.md` —
the consolidated single source of truth for the Fansivibe HTTP API contract:
the 16 binding principles (C-1…C-16), frozen cross-cutting conventions
(response/error/pagination/async shapes, headers, auth, idempotency), the
canonical 48-endpoint set + additive/gated + system surfaces, the async
analysis pattern, the frozen P0 DTO sketches, the findings register with
canonical resolutions, and the versioning/security summaries. **No
implementation.**

**Skills used:** repository analysis (live `main.py`, `schemas.py`,
`assistant_client.dart`, `models.dart`, `pubspec.yaml`, `TABLE_DEFINITIONS.md`,
`ERROR_HANDLING.md`, `FANSIVIBE_DOMAIN_MODEL_V1.md`) + design-doc synthesis
(all 18 STEP 6 API docs, `API_LAYER_ARCHITECTURE.md`, `AUTH_AUTHORIZATION_ARCHITECTURE.md`,
`BACKGROUND_JOB_ARCHITECTURE.md`, `MEDIA_UPLOAD_ARCHITECTURE.md`,
`APPLICATION_USE_CASES.md`) — documentation only.

**Files changed:** `docs/api/FANSIVIBE_API_CONTRACT_V1.md` (new);
`CURRENT_STATE.md` (updated).

**Validation run:**
- Every endpoint, DTO, error code, pagination rule, and idempotency rule in
  this document was cross-checked against the accepted sources (¶10).
- One wire-level discrepancy (I-1) resolved canonically; the remaining notes
  are doc-level/cosmetic/accepted (I-2…I-8) with no wire impact.
- Live contract preserved verbatim; `git status --short` shows only `docs/api/`
  + `CURRENT_STATE.md`.
- No `pytest`/`flutter test` run needed: no code changed.

**Remaining issues / follow-ups:**
- At M12 implementation, align `APPEARANCE_API.md` §4.3 with the canonical
  `AnalysisRun` DTO (add `input_media`) — see ¶7.I-1.
- Endpoint 17 error set in `API_INVENTORY.md:502` should be widened to
  `204; 401; 422; 429` when next touched — see ¶7.I-3.
- Open decisions in ¶11 land at their milestones with no contract change.

**Assumptions recorded:** path versioning `/v1` additive-only (API-1/2);
single resources envelope-free (API-17); lists use the envelope (API-18);
Bearer auth introduced with the auth module, `deps.py` a stub until then,
assistant stays unauthenticated (F-5); async is opt-in per endpoint
(analysis runs only), sync-by-default otherwise; endpoint set derived from the
32 actions / 33 use cases and the module map; sealed/gated modules not mounted
(API-12).

**Constraints honored:** BAR-0 (frozen assistant DTOs; thin projection),
DR-1 (one use case per router), F-6 (DTO-only responses), F-13 (assistant
contract unchanged), C-7/C-8 (no DB or AI/provider internals on the wire),
OW-1/API-10 (owner-scoped, 404-not-403), API-28…31 (typed errors), TRX-1/3/5
(upload-then-insert, save + signal transaction, write-once completion), the UI
Change Safety Rule (no Flutter modified), the Scope rule (contract design
only), and no implementation.

**Conclusion:** the Fansivibe HTTP API contract is **internally consistent**
after the resolutions in ¶7. **STEP 6 COMPLETE — READY FOR IMPLEMENTATION.**
