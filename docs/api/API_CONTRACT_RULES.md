# Fansivibe — HTTP API Contract Rules V1

> **STEP 6 — API CONTRACT DESIGN.** Defines the complete HTTP API contract
> between the Flutter application and the production FastAPI backend: the
> canonical endpoint set, the wire shapes (request/response DTOs, list
> envelopes, async run objects), the error contract, and the cross-cutting
> rules every endpoint follows.
>
> **Status: contract design only. Nothing is implemented.** No endpoints are
> created, no Flutter/routing/UI is modified, no database migrations or
> repositories are written, no services are implemented, no dependencies are
> added, and no existing endpoints are removed. The live contract
> (`GET /health`, `POST /v1/assistant/chat`) is **preserved unchanged**.
>
> **Source of truth:** the real Fansivibe repository (`backend/`,
> `newproject/flutter_application_1/`) and the accepted design docs:
> STEP 2 `ACTION_API_INVENTORY.md` (32 actions + Part 3 errors),
> STEP 3 `FANSIVIBE_DOMAIN_MODEL_V1.md` (E1–E10 + value objects),
> STEP 4 `TABLE_DEFINITIONS.md` / `TRANSACTION_BOUNDARIES.md` /
> `SECURITY_PRIVACY_DESIGN.md`, and STEP 5 `FASTAPI_ARCHITECTURE_V1.md` and
> its companions (`API_LAYER_ARCHITECTURE.md`, `ERROR_HANDLING.md`,
> `AUTH_AUTHORIZATION_ARCHITECTURE.md`, `APPLICATION_USE_CASES.md`,
> `KNOWLEDGE_ARCHITECTURE.md`, `BACKGROUND_JOB_ARCHITECTURE.md`,
> `MEDIA_UPLOAD_ARCHITECTURE.md`). The separate reference project is
> **not** merged and its APIs are **not** adopted.

---

## 1. Purpose and scope

This document is the **single source of truth for the HTTP wire contract**
between the Fansivibe Flutter client and the FastAPI backend. It answers, for
every operation the product performs (the 32 STEP 2 actions, clustered into
the 33 application use cases):

- **What is the endpoint** (method, `/v1/...` path, auth requirement)?
- **What does the client send** (request DTO, headers, multipart for images)?
- **What does the client receive** (response DTO, envelope or not, status)?
- **What can go wrong** (typed error `code`, HTTP status, safe `details`)?
- **Is it sync or async**, and **does it need idempotency**?

It also fixes the **cross-cutting rules** (API-1…API-44 from
`API_LAYER_ARCHITECTURE.md`, the 12-category error taxonomy from
`ERROR_HANDLING.md`, and the ownership invariants from
`AUTH_AUTHORIZATION_ARCHITECTURE.md`), so every future endpoint is built the
same way.

It does **not**: implement routers/DTOs, write SQL, modify Flutter, change
routing, redesign UI, or add dependencies. It also does **not** freeze every
field of every DTO exhaustively — the canonical field names and types come
from `TABLE_DEFINITIONS.md` (entities) and `FANSIVIBE_DOMAIN_MODEL_V1.md`
(value objects); this document fixes the **contract shapes and rules** those
DTOs must follow, with field-level sketches for the P0 slice.

**Grounding facts (BAR-0), re-verified against source:**
- The backend today has exactly **two routes**: `GET /health` (plain
  `{"status":"ok"}`, versionless, envelope-free) and
  `POST /v1/assistant/chat` (typed `AssistantReply`, no envelope, **no auth**)
  (`backend/app/main.py`).
- All 32 user actions are **future-required auth**; there is **no auth
  today** (ACTION_API Part 4 rule 1).
- Errors today are untyped FastAPI defaults; the target is the typed error
  contract (A3.3/E13.1, migration M2).
- The assistant DTOs are mirrored 1:1 between `schemas.py` and
  `lib/features/assistant/data/models.dart` and are **frozen** (A3.1, F-13).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app/main.py` + `backend/app/models/schemas.py` | The live contract: `GET /health`, `POST /v1/assistant/chat`, frozen DTOs. |
| `docs/architecture/ACTION_API_INVENTORY.md` | The 32 user actions → future endpoints + Part 3 error summary (primary shape driver). |
| `docs/architecture/FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities E1–E10 + value objects; the DTO content source. |
| `docs/database/TABLE_DEFINITIONS.md` | Canonical field names/types/nullability for entity DTOs. |
| `docs/database/TRANSACTION_BOUNDARIES.md` | TRX-1…8: which writes need idempotency/transaction semantics. |
| `docs/database/SECURITY_PRIVACY_DESIGN.md` | user_id scoping, MS10.3 media gate, erasure. |
| `docs/backend/API_LAYER_ARCHITECTURE.md` | API-1…API-44 — the cross-cutting wire conventions. |
| `docs/backend/ERROR_HANDLING.md` | The 12-category error taxonomy + `{error:{code,message,details}}`. |
| `docs/backend/AUTH_AUTHORIZATION_ARCHITECTURE.md` | Bearer auth, OW-1 ownership, 404-not-403. |
| `docs/backend/APPLICATION_USE_CASES.md` | UC-1…UC-33 — the operations each endpoint invokes (DR-1). |
| `docs/backend/BACKEND_MODULE_MAP.md` | M1–M16 module → router mapping (endpoint grouping). |
| `docs/backend/KNOWLEDGE_ARCHITECTURE.md` | `GET /knowledge/*` public catalog; knowledge_version. |
| `docs/backend/BACKGROUND_JOB_ARCHITECTURE.md` | SYNC vs ASYNC classification → 202+run_id pattern. |
| `docs/backend/MEDIA_UPLOAD_ARCHITECTURE.md` | Media upload flow (sealed M16, signed PUT, MediaRef). |
| `docs/backend/FASTAPI_ARCHITECTURE_V1.md` | The consolidated STEP 5 architecture (no contradiction). |

---

## 3. Contract principles (the 16 binding rules)

Each principle is grounded in an accepted rule (API-*, ER-*, OW-*, TRX-*)
and is binding on every endpoint.

| # | Principle | Rule(s) | Meaning on the wire |
| --- | --- | --- | --- |
| C-1 | **Version APIs** | API-1…4 | Path version `/v1`; additive-only within a version; `Accept: application/json; version=1.0` optional pin; breaking changes need a new version + deprecation window. |
| C-2 | **Resource-oriented naming** | §7 | Nouns, plural, kebab-case leaf params: `/wardrobe/items`, `/analysis/runs/{run_id}`. No verb-in-path except actions that are genuinely verbs (`/sync`, `/generate`, `/outfit` on a resource). |
| C-3 | **Consistent HTTP methods** | §6 | GET=read, POST=create/action, PUT=replace, PATCH=partial, DELETE=delete; 204 for no-content deletes/acks. |
| C-4 | **Consistent response structures** | API-17…19 | Single resource → DTO directly (no envelope; the frozen `AssistantReply` stays bare). List → `{items,page,page_size,total}`. camelCase keys. |
| C-5 | **Consistent error structures** | API-28…31, ERROR_HANDLING | Every error is `{error:{code,message,details}}`; stable `code` from the frozen 12-category taxonomy; safe `message`; allow-listed `details`. |
| C-6 | **Validate all inputs** | API-13…16 | Every body/query is a typed Pydantic DTO; controlled-vocabulary values validated server-side (422); not-found vs invalid distinguished (404 vs 422); media size/type checked (413/422). |
| C-7 | **Never expose DB implementation details** | F-6, ER-0 | DTOs are the only shape; no table/column names, SQL, ORM types, or schema internals in any response, error, or header. |
| C-8 | **Never expose internal AI/provider details** | AI-0, ER-0, F-7 | No provider/vendor/model names, prompts, or raw model output in responses; analysis/adapter details stay server-side; a degraded-to-rules response is flagged neutrally (`details.degraded=true`), never with internals. |
| C-9 | **Enforce authenticated user ownership** | OW-1, API-10 | Every user-owned endpoint resolves `user_id` from the token (never client input) and filters all queries/writes by it; another user's resource → 404 (never 403). |
| C-10 | **Distinguish sync vs async** | API-40…44, BJ-0 | Sync by default; slow image analysis → `202 + {run_id}` then `GET /analysis/runs/{run_id}` polling (pending→completed|failed, write-once). |
| C-11 | **Support pagination where needed** | API-20…22 | Offset `?page=&page_size=` (default 20, max 100); cursor for deep feeds (discover); `total` from the same query. |
| C-12 | **Support idempotency where required** | API-33…35 | `Idempotency-Key` header on saves/sync/create-account/webhook; repeats return the original result; reads and naturally-idempotent mutations need no key. |
| C-13 | **Use stable identifiers** | PR-3 | Server-generated `uuid` for user-owned entities; stable text `code` for knowledge/vocabularies. Never client-supplied uuids; never reuse Dart-local ids as keys. |
| C-14 | **Preserve backward compatibility** | API-2…4 | Within `/v1`, responses only gain optional fields; the frozen `AssistantReply` (F-13) must never be reordered/renamed; `GET /health` stays versionless. |
| C-15 | **Auth is not in the domain** | F-3, DR-1 | Routers resolve `user_id` via `deps.py`; application/domain receive only `user_id`. No endpoint trusts client-supplied identity. |
| C-16 | **AI output is never a source of truth** | BAR-0, TRX-7 | Recommendation/analysis endpoints return regenerable results; only explicit user *save* endpoints (with `Idempotency-Key`) create durable rows. |

---

## 4. Global conventions

### 4.1 Base URL and protocol

- HTTPS in production. The Flutter client overrides the base URL with
  `--dart-define=ASSISTANT_BASE_URL` (current `assistant_client.dart:17-20`).
- All endpoints (except `GET /health`) are under `/v1` (API-1).
- JSON bodies use `application/json; charset=UTF-8` (matching the current
  assistant client); image analysis uses `multipart/form-data` (API-36).

### 4.2 Headers

| Header | Where | Meaning |
| --- | --- | --- |
| `Authorization: Bearer <token>` | every protected endpoint | API-5; resolved by `deps.py` to `user_id`. Missing/invalid → 401 + `WWW-Authenticate: Bearer`. |
| `Content-Type` | requests with a body | `application/json` or `multipart/form-data` (analysis/media). |
| `Idempotency-Key` | saves/sync/create/webhook | API-33; opaque client key, hashed server-side (API-35). |
| `Accept: application/json; version=1.0` | optional | API-3; default is latest `/v1`. Unsupported → 422. |
| `X-Request-Id` | every response (echo) | Correlation id; assigned at the API boundary, echoed by the server (OBSERVABILITY §4.1). |
| `Retry-After` | 429 | Rate-limit retry hint (ERROR_HANDLING §5.6). |
| `WWW-Authenticate: Bearer` | 401 | Standard auth challenge (API-7). |
| `X-Knowledge-Version` | `GET /knowledge/*` responses | Content version for cache/validation (KN-1, KNOWLEDGE_ARCHITECTURE §5.1). |

### 4.3 Field naming, timestamps, identifiers

- **camelCase** for all JSON keys (API-19, A3.1 mirror convention).
- **Timestamps:** ISO-8601 UTC (`2026-08-09T12:34:56Z`); date-only fields
  (`event_date`, `day`) are `YYYY-MM-DD`.
- **Identifiers (C-13):** user-owned resources use server-generated UUIDs
  (`users.id`, `wardrobe_items.id`, `saved_looks.id`, `user_events.id`,
  `analysis_runs.id`, `subscriptions.id`); knowledge uses stable text codes
  (`looks.code`, `wardrobe_categories.code`, `colors.code`, `occasions.code`,
  `event_types.code`, `signal_types.code`). Clients store and echo ids, never
  generate them.

### 4.4 Media references

Image bytes never travel through FastAPI RAM (PR-8). DTOs carry **`MediaRef`**
objects (object key / URL + media type + size + hash), never base64 or URLs
that are long-lived. Signed URLs are minted per-request by the owner
(MEDIA_UPLOAD_ARCHITECTURE §4.8). Media endpoints are **sealed (M16) until
MS10.3** — the reference columns (`image_ref`, `input_media`) exist, the
upload endpoints do not.

---

## 5. Authentication and authorization

- **Bearer tokens (API-5):** issued by `POST /v1/auth/*` (UC-1…3); revoked by
  `POST /v1/auth/logout` (UC-4) and logout-all (R51). Backend never stores
  passwords or refresh secrets; the provider is an open seam (D-AUTH-1).
- **Resolution (API-6):** `deps.py` → `user_id` (UUID) threaded through
  application → domain (F-3). No singleton; per-request.
- **Public endpoints (API-7):**
  - `POST /v1/auth/register`, `POST /v1/auth/social`, `POST /v1/auth/login`
  - `GET /v1/knowledge/*` (public catalog)
  - `GET /health`
  - `POST /v1/assistant/chat` (public **today**; may gain auth later without
    changing its wire shape — F-5 note in FASTAPI_ARCHITECTURE_V1)
- **Everything else is auth-required** (ACTION_API Part 4 rule 1).
- **Anonymous mode (API-8):** the "save locally" path (action 4) has no
  token; data reaches the backend only later through `POST /v1/users/me/sync`
  (UC-9) after account creation. **No anonymous write endpoints exist.**
- **Authorization (API-10):** 401 = unauthenticated; 403 = authenticated but
  disallowed (admin path from a user token); **404** = resource not found
  **or** not-yours (no existence leak). Every user-owned query carries
  `WHERE user_id = :uid` (OW-1).
- **Admin (API-11):** knowledge content writes (seed/admin, M5 P2) require a
  separate admin principal (`require_admin`). No user-accessible admin paths
  today; default closed, audited.
- **Feature gates (API-12):** sealed modules (M11 `feedback`, M16 `media`)
  are **not mounted** — their endpoints return no fake 200; the routes do not
  exist until the gate lifts.

---

## 6. HTTP method semantics

| Method | Semantics | Response on success |
| --- | --- | --- |
| `GET` | Read (single or list). Never changes state. | 200; 200 list envelope. |
| `POST` | Create a resource, or a **resource action** (`/sync`, `/generate`, `/outfit`, `/chat`). | 201 (created) / 200 (action result) / 202 (async accepted). |
| `PUT` | Replace a resource (whole object). | 200 (or 204). |
| `PATCH` | Partial update (fields present are changed; favorite toggle). | 200. |
| `DELETE` | Delete a resource. | 204. |

**Create-vs-action rule (C-2/C-3):** a noun path + `POST` creates the noun
(`POST /v1/wardrobe/items`); a verb tail on a resource performs an action on
it (`POST /v1/users/me/sync`, `POST /v1/events/{event_id}/outfit`). Idempotent
`POST` actions accept `Idempotency-Key`; pure `POST` creates that would
double-apply also require it (saves, sync, register, subscribe).

---

## 7. Resource naming and URI map

Resource-oriented, plural nouns, versioned under `/v1`. Static segments must
be declared **before** parameterized ones in routers so literal paths win
(e.g. `/v1/looks/today` before `/v1/looks/{look_id}`).

| Resource | Canonical URI | Module |
| --- | --- | --- |
| Auth | `/v1/auth/register`, `/social`, `/login`, `/logout` | M1 |
| Current user (profile/preferences/settings/sync) | `/v1/users/me`, `/v1/users/me/preferences`, `/v1/users/me/settings`, `/v1/users/me/sync` | M2 |
| Wardrobe items | `/v1/wardrobe/items`, `/v1/wardrobe/items/{item_id}`, `/v1/wardrobe/insight` | M3 |
| Assistant | `/v1/assistant/chat`, `/v1/assistant/feedback` | M4 |
| Knowledge (public catalog) | `/v1/knowledge/looks`, `/categories`, `/colors`, `/occasions`, `/items` | M5 |
| Saved looks | `/v1/looks/saved`, `/v1/looks/saved/{saved_look_id}` | M7 |
| Events | `/v1/events`, `/v1/events/{event_id}`, `/v1/events/{event_id}/outfit` | M8 |
| Today's look | `/v1/looks/today`, `/v1/looks/today/save` | M9 |
| Learning summary | `/v1/learning/summary` | M10 |
| Feedback | `/v1/feedback` (gated) | M11 |
| Analysis runs | `/v1/analysis/outfit`, `/hairstyle`, `/grooming`, `/v1/analysis/runs`, `/v1/analysis/runs/{run_id}` | M12 |
| Outfits | `/v1/outfits/generate`, `/v1/outfits/saved` | M13 |
| Discover feed | `/v1/looks`, `/v1/looks/{look_id}` | M14 |
| Subscriptions | `/v1/subscriptions/me`, `/v1/subscriptions` (+ provider webhook, server-to-server) | M15 |
| Media | `/v1/media/uploads`, `/v1/media/uploads/{upload_id}/complete` (sealed) | M16 |

> **Path-collision guard:** `/v1/looks` is shared by M9 (`today`,
> `today/save`), M7 (`saved`), and M14 (`{look_id}`). Router registration
> order must be: `/v1/looks/today`, `/v1/looks/today/save`, `/v1/looks/saved`,
> `/v1/looks/saved/{saved_look_id}`, then `/v1/looks` (discover list) and
> `/v1/looks/{look_id}`. The discover list is `GET /v1/looks`; the public
> catalog is `GET /v1/knowledge/looks` — two different read surfaces (see §12).

---

## 8. Response structures

### 8.1 Single resource (no envelope — API-17)

A single object returns the **DTO directly**:

```json
{ "id": "3f1c...", "name": "Navy Blazer", "category": "blazer", "color": "navy", "isFavorite": false }
```

The frozen `AssistantReply` is returned bare (unchanged; F-13). **No**
`{data: ...}` wrapper anywhere — it would break the live contract.

### 8.2 List envelope (API-18)

Only list endpoints wrap items:

```json
{
  "items": [ /* DTOs */ ],
  "page": 1,
  "page_size": 20,
  "total": 137
}
```

`page_size` bound `[1,100]` (API-22). `total` comes from the same query.

### 8.3 Async run object (API-41/42)

An accepted async operation returns `202`:

```json
{ "run_id": "7a2b..." }
```

Polling `GET /v1/analysis/runs/{run_id}` returns the run DTO:

```json
{
  "run_id": "7a2b...",
  "run_type": "outfit",
  "status": "pending",
  "created_at": "2026-08-09T12:00:00Z"
}
```

`status` ∈ `pending | completed | failed` (TRX-5). On `failed`, the DTO
carries the typed error in `error` (API-42). Completed runs include the
immutable `result` snapshot + `engine_version` (PR-6). The run row is
write-once; only the guarded completion flips `pending → completed|failed`.

### 8.4 Empty / no-content

- Deletes, logout, card-feedback ack → `204` (no body).
- Empty *derived* results that are not errors (e.g. empty wardrobe insight,
  no matching looks) → `200` with `needs_data: true` **or** `204` per use
  case (ERROR_HANDLING §5.12; UC-14 → 204/empty, UC-28 → 204/empty). Empty
  is not an error.

---

## 9. Errors (the frozen contract — C-5)

Every error response is exactly (API-28, ERROR_HANDLING §4):

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The requested item was not found.",
    "details": { }
  }
}
```

- **`code`** is a stable machine-readable string from the frozen 12-category
  taxonomy (below). Clients switch on `code`, never on HTTP alone (API-32).
- **`message`** is the safe client message built only in `api/errors.py`
  (ER-2) — no internals.
- **`details`** is optional and **allow-list only** (ER-1): `request_id`,
  `run_id`, caller-owned resource ids, field names, allowed values, `missing`
  fields, `kind`, neutral `retry_after`. Never SQL, prompts, stack traces,
  tokens, provider/model names, or user content (ER-0).

### 9.1 The 12-category taxonomy (frozen)

| `error.code` | HTTP | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | 422 | Invalid input, vocabulary, dates; `details` carries field errors `[{field,error,allowed?}]`. |
| `AUTHENTICATION_ERROR` | 401 | Missing/expired/revoked token (+ `WWW-Authenticate`). |
| `AUTHORIZATION_ERROR` | 403 | Authenticated but disallowed (admin path). |
| `NOT_FOUND` | 404 | Resource missing **or not-yours** (API-10/15). |
| `CONFLICT` | 409 | Duplicate email/item/save, version conflict, sync conflict; `details.kind`. |
| `RATE_LIMITED` | 429 | Register/login/feedback throttling (+ `Retry-After`). |
| `AI_FAILURE` | 503 (or none if degraded) | Provider timeout/malformed output; `details.degraded=true` if rules fallback served. |
| `MEDIA_FAILURE` | 413 / 422 / 503 | Image too large/unsupported (413/422) or blob storage failure (503); `details.kind`. |
| `DATABASE_FAILURE` | 500 / 503 | Internal; `details.request_id` only. |
| `EXTERNAL_SERVICE_FAILURE` | 502 / 503 / 402 / 424 | Identity provider (502), weather/knowledge/billing (503), payment outcome (402/424). |
| `PROCESSING_FAILURE` | 500 (sync) / `status=failed` (poll) | Analysis/generation pipeline failure; `details.run_id`. |
| `INSUFFICIENT_USER_DATA` | 200+`needs_data` / 422 | Decision needs more user data (empty wardrobe, no face profile); `details.missing`. |

### 9.2 Status-code principle (API-32)

4xx = caller errors; 5xx = our/external failures. The body `code` is stable
and is what clients switch on. Unhandled exceptions → `500 INTERNAL_ERROR`
with a generic message + `X-Request-Id` (API-31, ER-0).

---

## 10. Pagination, filtering, sorting

- **Pagination (API-20):** `?page=1&page_size=20` (1-based, default 20, max
  100); `total` from the same query. `page_size` outside bounds → 422.
- **Cursor (API-21):** discover feed and long history lists may use
  `?cursor=<opaque>&limit=20`; cursor is server-generated, opaque, encodes the
  last key; feed ordering stable (secondary key = id).
- **Filtering (API-23/24/25):** filters are explicit typed query params
  (`?occasion=casual&color=navy`), validated against the controlled
  vocabulary server-side → 422 on invalid values. No free-form
  `?filter=json`. Server-side only; clients never download-and-filter.
- **Sorting (API-26/27):** `?sort=<key>&order=asc|desc` with documented keys
  per endpoint (`created_at`, `event_date`, `score`, ...); unknown key → 422.
  Personalized ordering (discover match, hair/grooming score) is produced by
  the Decision Engine and returned as-is — the API never re-sorts engine
  output (API-27).

---

## 11. Idempotency (C-12, API-33…35)

| Applies | Endpoints |
| --- | --- |
| **Requires `Idempotency-Key`** | `POST /v1/auth/register`, `POST /v1/users/me/sync`, `POST /v1/looks/saved`, `POST /v1/looks/today/save`, `POST /v1/outfits/saved`, `POST /v1/feedback` (when live), `POST /v1/subscriptions` |
| **Naturally idempotent (no key)** | `PATCH`/`DELETE`, logout, reads, analysis **submission** (each call is a new run) |
| **Never idempotent** | `POST /v1/assistant/chat` (a new exchange each call), `POST /v1/analysis/*` (each call creates a new run) |

- Repeats with the same key + `user_id` return the **original result** (not a
  re-run); conflicting payloads → 409 `CONFLICT`.
- The key is hashed and stored server-side with the first response; repeats
  never re-run the transaction (TRX-3/TRX-5 never double-write — API-35).
- Enforcement lives in the application layer; the router only passes the
  header through.

---

## 12. Endpoint catalog (the complete contract)

Each endpoint: method, path, auth, use case, sync/async, idempotency,
request → response, and the error codes it can return. DTO field names follow
`TABLE_DEFINITIONS.md` and `FANSIVIBE_DOMAIN_MODEL_V1.md`; the P0 DTOs are
sketched field-by-field in §13. Auth column: **public** / **auth** (Bearer →
`user_id`).

### 12.1 Auth — M1 (P0)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/auth/register` | public | UC-1 | `RegisterRequest` (email, password, displayName?) → `AuthResponse` (accessToken, tokenType, expiresIn, profile) | 201; 409 (email taken), 422, 429 |
| POST | `/v1/auth/social` | public | UC-2 | `SocialSignInRequest` (provider, providerToken) → `AuthResponse` | 200 (existing) / 201 (new); 502, 401, 409 |
| POST | `/v1/auth/login` | public | UC-3 | `LoginRequest` (email, password) → `AuthResponse` (+ last stored profile snapshot) | 200; 401, 404, 429 |
| POST | `/v1/auth/logout` | auth | UC-4 | — → 204 | 204; 401 (idempotent) |

`Idempotency-Key` on register (C-12). Tokens never appear in bodies besides
`accessToken` on issue; never in logs/URLs (API-9).

### 12.2 Users — M2 (P0)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/users/me` | auth | UC-6 | — → `ProfileView` (displayName, styleProfile, preferences, settings, flags, version) | 200; 404 |
| PATCH | `/v1/users/me` | auth | UC-7 | `ProfileUpdateRequest` (displayName?, avatarMediaRef?, styleDna?) → `ProfileView` | 200; 422, 409 (version) |
| PUT | `/v1/users/me/preferences` | auth | UC-8 | `Preferences` (sparse key/values, vocab-validated) → `Preferences` | 200; 422 |
| PUT | `/v1/users/me/settings` | auth | (28) | `Settings` → `Settings` | 200; 422 |
| POST | `/v1/users/me/sync` | auth | UC-9 | `SyncRequest` (full `UserModel` blob) → `SyncReceipt` (mergedProfile, conflicts[], syncedAt) | 200; 409 (conflict), 413 (too large) |

`POST /v1/users/me/sync` is the P7.1 blob split: relational rows
(wardrobe/events/saved-looks) + `user_state` JSONB projection, in one
transaction (TRX-3/TRX-6 style). `Idempotency-Key` required.

### 12.3 Wardrobe — M3 (P0)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/wardrobe/items` | auth | (5,6,7 reads) | `?category=&color=&sort=&page=&page_size=` → `WardrobeItemList` (envelope) | 200; 422 (filters/pagination) |
| POST | `/v1/wardrobe/items` | auth | UC-10 | `WardrobeItemCreate` (name, category, color, material?, imageRef?) → `WardrobeItem` | 201; 422 (vocab), 409 (dup/limit) |
| PATCH | `/v1/wardrobe/items/{item_id}` | auth | UC-11/12 | `WardrobeItemPatch` (name?, category?, color?, material?, isFavorite?) → `WardrobeItem` | 200; 404, 422, 409 |
| DELETE | `/v1/wardrobe/items/{item_id}` | auth | UC-13 | — → 204 | 204; 404, 409 (FK refs) |
| GET | `/v1/wardrobe/insight` | auth | UC-14 | — → `WardrobeInsight` (title, insight, action?, route?) | 200; 204 (empty) |

Category/color/material validated against knowledge (K9.1) → 422 with allowed
values in `details` (API-14). Blob upload, when M16 lifts, happens before the
INSERT (TRX-1; upload-then-insert).

### 12.4 Assistant — M4 (P0, live contract)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/assistant/chat` | public today | UC-22 | `AssistantRequest` (messages, user context) → `AssistantReply` (intent, text, cards, clarifications, navigation) | 200; 422 (invalid context); client offline fallback on network failure (not an error to the user) |
| POST | `/v1/assistant/feedback` | auth | UC-23 | `AssistantCardFeedback` (cardTitle/cardId, interactionType) → 204 | 204; 401 |

**Frozen (F-13):** `AssistantRequest` / `AssistantReply` field names, order,
and types must never change; the DTOs move verbatim to
`api/schemas/assistant.py` at M1. No envelope, no `data` wrapper. The endpoint
is **unauthenticated today** and must not gain auth retroactively without a
contract decision (F-5).

### 12.5 Knowledge — M5 (P0, public)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/knowledge/looks` | public | (K9.1) | `?occasion=&style=&page=` → `LookList` (envelope) | 200; 422 (filters) |
| GET | `/v1/knowledge/categories` | public | — | → `VocabularyItem[]` (code, label, sortOrder) | 200 |
| GET | `/v1/knowledge/colors` | public | — | → `VocabularyItem[]` | 200 |
| GET | `/v1/knowledge/occasions` | public | — | → `VocabularyItem[]` | 200 |
| GET | `/v1/knowledge/items` | public | — | → `ItemReference[]` | 200 |

Responses carry `X-Knowledge-Version` (KN-1). Read-mostly; no user data; no
auth (API-7). Admin/seed writes are M5 P2, admin-only, and not part of the
Flutter contract.

### 12.6 Saved Looks — M7 (P1)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/looks/saved` | auth | UC-15 | `SaveLookRequest` (lookId?, title, sourceContext?, snapshot) → `SavedLook` | 201; 404 (look), 409 (dup); `Idempotency-Key` |
| GET | `/v1/looks/saved` | auth | (14,17 reads) | `?sort=created_at&page=` → `SavedLookList` (envelope) | 200 |
| DELETE | `/v1/looks/saved/{saved_look_id}` | auth | (7) | — → 204 | 204; 404 |

`SaveRecommendation` (UC-15) consolidates the four save paths
(12/14/17/22/24). Saves freeze an immutable snapshot (TRX-3: `saved_looks`
INSERT + `look_saved` signal in one transaction).

### 12.7 Events — M8 (P1)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/events` | auth | UC-18 | `EventCreate` (title, eventType, eventDate, time?, location?, notes?) → `UserEvent` | 201; 422 (past date/type) |
| GET | `/v1/events` | auth | (9) | `?from=&sort=event_date&page=` → `UserEventList` (envelope) | 200 |
| PUT | `/v1/events/{event_id}` | auth | UC-19 | `EventUpdate` (full replace) → `UserEvent` | 200; 404, 422 |
| DELETE | `/v1/events/{event_id}` | auth | UC-20 | — → 204 | 204; 404 |
| POST | `/v1/events/{event_id}/outfit` | auth | UC-21 | — → `OutfitRecommendation` | 200; 404, 503 |

`POST /v1/events/{event_id}/outfit` fixes the current event-context loss
(action 11): the occasion seeds generation. The recommendation is regenerable
(non-transactional, TRX-7) — only an explicit save persists it.

### 12.8 Today's Look — M9 (P1)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/looks/today` | auth | UC-17 | `?variant=` → `TodayLook` | 200; 404 (none found) |
| POST | `/v1/looks/today` | auth | UC-16 | `?seed=` → `TodayLook` | 200; 503 (generation) |
| POST | `/v1/looks/today/save` | auth | (12) | → `SavedLook` | 201; `Idempotency-Key` |

Today's look is derived (SYNC, BJ-0); weather is only a hint via the
`WeatherProvider` port, never authoritative. `today_look_records` history
INSERT only if the P1 decision lands.

### 12.9 Learning — M10 (P1)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/learning/summary` | auth | (8,28 profile) | → `LearningSummary` (styleScore, breakdown, streak, recentSignals) | 200 |

Signals are written **by the backend** (from other use cases), never by the
client directly (M10 is the sole writer, PR-7). No public signal-submit
endpoint exists — the assistant card feedback endpoint is the only
client-facing signal input.

### 12.10 Feedback — M11 (P1, feature-gated — NOT mounted)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/feedback` | auth | UC-32 | `FeedbackCreate` (rating, reason?, targetLookId?, targetSavedLookId?) → 201/204 | 201/204; 422, 429 |

**Not mounted** until the Flutter feedback UI is accepted (API-12, M11
sealed). `Idempotency-Key` when it ships.

### 12.11 Analysis — M12 (P2, async)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/analysis/outfit` | auth | UC-24 | multipart (`image` + typed fields) → `202 {run_id}` | 202; 413/422 (media), 422 (no clothing), 503 |
| POST | `/v1/analysis/hairstyle` | auth | UC-25/26 | multipart (`image` or profile) → `202 {run_id}` | 202; 422, 503 |
| POST | `/v1/analysis/grooming` | auth | UC-27 | `GroomingAnalysisRequest` (options) → `202 {run_id}` | 202; 422, 503 |
| GET | `/v1/analysis/runs/{run_id}` | auth | (16/21/23 poll) | — → `AnalysisRun` (status, result when completed, error when failed) | 200; 404 |
| GET | `/v1/analysis/runs` | auth | — | `?run_type=&sort=created_at&page=` → `AnalysisRunList` (envelope) | 200 |

Async pattern (API-41/42): `POST` returns `202 + run_id`; the client polls
`GET /v1/analysis/runs/{run_id}` until `completed|failed`. Run completion is
write-once (TRX-5). Face/outfit image analysis is ASYNC; grooming is
option-based and could be sync but stays on the run model for uniformity
(BJ-0, TRX-5). Run results are immutable snapshots with `engine_version`
provenance (PR-6).

### 12.12 Outfits — M13 (P2)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/outfits/generate` | auth | UC-28/29 | `OutfitGenerateRequest` (occasion, mood, fit, colorPalette, seed?) → `OutfitRecommendation` | 200; 422, 503, 204 (no matching wardrobe) |
| POST | `/v1/outfits/saved` | auth | UC-30 | `SaveOutfitRequest` (recommendation snapshot) → `SavedLook` | 201; 409; `Idempotency-Key` |

Generation is **SYNC** (rules-based, BJ-0) and non-transactional — the outfit
is a value object, never persisted as truth (TRX-2). `seed` yields a
different result for Regenerate (UC-29).

### 12.13 Discover — M14 (P2)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/looks` | auth | UC-31 | `?occasion=&style=&fit=&cursor=&limit=` → `LookFeed` (envelope, engine-ranked) | 200; 422 (filters) |
| GET | `/v1/looks/{look_id}` | auth | (14) | — → `LookDetail` (ensemble, scores, `isOwned` personalization) | 200; 404 |

Personalized ordering comes from the Decision Engine (API-27). Read-only
presentation of `knowledge` + `learning` (BAR-0).

### 12.14 Subscriptions — M15 (P2)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/subscriptions/me` | auth | (30 read) | — → `Subscription` (planCode, status, startedAt, renewsAt) | 200 |
| POST | `/v1/subscriptions` | auth | UC-33 | `SubscribeRequest` (planCode) → `Subscription` | 200/201; 402/424, 404, 503; `Idempotency-Key` |

Provider webhook is **server-to-server** (system principal), idempotent,
never in a DB transaction (R51). Payment details never stored; the backend
keeps only entitlement state.

### 12.15 Media — M16 (P2, sealed)

| Method | Path | Auth | UC | Request → Response | Status / Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/media/uploads` | auth | (M16) | `UploadRequest` (purpose, filename, size, contentType) → `201 {upload_id, signedPutUrl, expiresAt}` | 201; 413/422 (media validation) |
| POST | `/v1/media/uploads/{upload_id}/complete` | auth | — | → `MediaRef` | 200; 404, 413/422, 503 |

**Sealed until MS10.3** (API-12). Flow: Flutter PUTs bytes directly to object
storage (zero FastAPI RAM — PR-8), then `/complete` verifies via HEAD/size/
hash and inserts the `MediaRef` (TRX-1). Signed URLs are short-lived,
owner-scoped, never persisted. Private by default (MS10.3).

### 12.16 Health (versionless)

| Method | Path | Auth | Response |
| --- | --- | --- | --- |
| GET | `/health` | public | `{"status":"ok"}` — unchanged, no envelope, no version (API-4). |

---

## 13. P0 DTO sketches (canonical field names)

Field names follow `TABLE_DEFINITIONS.md`; JSON keys are camelCase (API-19).
`*` = required. P1/P2 DTOs use the same rules with the table columns as the
source of field names.

### 13.1 Auth

```
AuthResponse   { accessToken*, tokenType*="bearer", expiresIn*, profile: ProfileView }
RegisterRequest{ email*, password*, displayName? }
LoginRequest   { email*, password* }
SocialSignIn   { provider* (google|apple), providerToken* }
```

### 13.2 Profile / preferences (M2; `users` + `user_state`)

```
ProfileView {
  displayName*, styleProfile: StyleProfile,
  preferences: Preferences, settings: Settings, flags: Flags, version*
}
StyleProfile { faceShape?, skinTone?, bodyType?, styleType?, sourceRunId? }
Preferences  { preferredOccasions?: string[] /* vocab codes */, ... }   // sparse JSONB
Settings     { /* sparse, controlled keys */ }
SyncRequest  { wardrobe: WardrobeItem[], savedLooks: SavedLookRef[], events?: UserEvent[],
               preferences, styleProfile, flags, clientTimestamp }      // full UserModel blob
SyncReceipt  { mergedProfile: ProfileView, conflicts: Conflict[], syncedAt }
Conflict     { resource: string, kind: "latest-wins"|"append"|"needs-review" }
```

### 13.3 Wardrobe (M3; `wardrobe_items` + vocab codes)

```
WardrobeItem     { id*, name*, category*, color*, material?, isFavorite, imageRef?: MediaRef,
                   createdAt*, updatedAt* }
WardrobeItemCreate { name*, category*, color*, material?, imageRef? }
WardrobeItemPatch  { name?, category?, color?, material?, isFavorite? }   // PATCH partial
WardrobeInsight    { title*, insight*, action?, route? }
MediaRef           { objectKey, mediaType, width?, height?, sizeBytes, contentHash,
                     isGenerated, uploadedAt }
```

### 13.4 Assistant (M4 — **frozen, verbatim** from `schemas.py`)

```
AssistantRequest { messages: ChatMessage[], user?: UserContext }
ChatMessage      { role*, content* }
UserContext      { wardrobe: WardrobeItem[], face?: FaceData, savedLooks: string[],
                   preferredOccasions: string[] }
AssistantReply   { intent*, text*, cards: SuggestionCard[], clarifications: ClarificationOption[],
                   navigation?: NavigationRequest }
SuggestionCard   { kind, title, subtitle, score?, items: string[], action? }
```

These mirror `backend/app/models/schemas.py` exactly (A3.1) and must never
change (F-13).

### 13.5 Knowledge (M5)

```
VocabularyItem { code*, label*, sortOrder*, active }
LookCard       { code*, title*, imageRef?: MediaRef, payload: { ensemble, occasion, style } }
```

### 13.6 Shared types

```
ListEnvelope  { items*: T[], page*, page_size*, total* }
ErrorBody     { error: { code*, message*, details? } }
AsyncAccepted { run_id* }
```

---

## 14. Data privacy and never-expose guarantees

- **C-7 (DB internals):** no response, error, or header exposes table names,
  column names, SQL, ORM types, or schema shapes (F-6, ER-0).
- **C-8 (AI/provider internals):** no provider/vendor/model names, prompts, or
  raw model output in any response (AI-0, F-7). Capability names in responses
  use neutral labels; `details.degraded` is a boolean, never an internal
  fallback path.
- **Appearance/image data** is CRITICAL-sensitivity (SECURITY_PRIVACY_DESIGN
  §3): only the owner may read it; image bytes never in logs, URLs, or
  responses (MS10.3, ER-4). Analysis inputs (`input_media`) are MediaRefs, and
  run results are immutable snapshots never echoed into error `details`.
- **Tokens** never appear in logs, URLs, query strings, or error bodies
  (API-9). Only the `accessToken` on issue.
- **User content** (messages, face data, wardrobe snapshots) is never echoed
  in errors or logs (ER-0/ER-4).
- **Erasure:** account deletion is server-side CASCADE across all user-owned
  rows + async blob cleanup (SECURITY_PRIVACY_DESIGN §5); the API exposes only
  the user's own deletion path (not part of the Flutter contract today).

---

## 15. Backward compatibility

- **Additive-only within `/v1` (API-2):** responses may gain new optional
  fields; never remove, rename, or retype existing fields without `/v2` +
  deprecation window.
- **Frozen assistant DTOs (F-13):** no additive change may reorder/remove
  `AssistantReply` fields.
- **`GET /health`** stays versionless and envelope-free.
- **Migration (M1–M6):** the live `POST /v1/assistant/chat` and `GET /health`
  keep working verbatim through every migration step (19 tests stay green).
- New endpoints are **additive**: nothing existing is removed or changed in
  this contract.

---

## 16. Open decisions carried forward (unchanged)

These remain open from STEP 5 and **affect the contract only when they land**;
none blocks this design:

1. **Auth provider (D-AUTH-1)** — email/password vs social OAuth; determines
   `AuthResponse` claims (not the wire shape).
2. **User fields/auth** — profile view contents.
3. **`Today'sLookRecord` (P1)** — whether `today_look_records` history is
   created (adds a history read endpoint or none).
4. **`RecommendationHistory` (P3)** — adds a history endpoint only if built.
5. **Conversation retention** — may add assistant-message history endpoints;
   default transient (no table today).
6. **Knowledge shape (K9.1)** — static config vs DB-backed vocab tables;
   endpoint set is fixed either way.
7. **Media privacy (MS10.3)** — lifts M16 media endpoints.
8. **Feedback design** — shapes `POST /v1/feedback` fields when the UI ships.

---

## 17. Report, assumptions, constraints

**What changed (this step):** added `docs/api/API_CONTRACT_RULES.md` — the
complete HTTP API contract (principles C-1…C-16, global conventions,
auth/authorization, method semantics, URI map, response structures, error
contract with the 12-category taxonomy, pagination/filtering/sorting,
idempotency, the full endpoint catalog grouped by module M1–M16, P0 DTO
sketches, privacy guarantees, backward-compatibility rules). **No
implementation.**

**Skills used:** repository analysis (live `main.py`, `schemas.py`,
`assistant_client.dart`) + design-doc synthesis (ACTION_API 32 actions,
domain model E1–E10, TABLE_DEFINITIONS, API-1…44, ERROR_HANDLING 12
categories, AUTH OW-1, MODULE_MAP M1–M16, BACKGROUND_JOB SYNC/ASYNC,
MEDIA_UPLOAD flow) — documentation only.

**Files changed:** `docs/api/API_CONTRACT_RULES.md` (new).

**Validation run:**
- **Every STEP 2 action maps to ≥1 endpoint** (master table §12 covers
  actions 1–32; action 27 = `navigation` inside `AssistantReply`, action 4 =
  `POST /v1/users/me/sync` precondition).
- **Every UC-1…UC-33 maps to an endpoint** (UC-5 onboarding → sync path;
  UC-17 → `GET /v1/looks/today`; UC-29 → `POST /v1/outfits/generate?seed=`).
- **Consistent with STEP 5:** API-1…44 (versioning, envelopes, errors,
  pagination, idempotency, async), ERROR_HANDLING taxonomy (identical
  `error.code` values), AUTH OW-1 (all user endpoints resolve `user_id`;
  404-not-403), MODULE_MAP routers (paths match), BACKGROUND_JOB
  classification (analysis async, generation sync), MEDIA_UPLOAD flow (M16
  sealed), KNOWLEDGE public catalog, TRX-1…8 (idempotency on saves/sync).
- **Live contract preserved:** `GET /health` and `POST /v1/assistant/chat`
  unchanged, no envelope, frozen DTOs (F-13/API-17).
- **`git status --short`:** only `docs/api/API_CONTRACT_RULES.md` (untracked)
  + `CURRENT_STATE.md` update; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Per-endpoint field-level DTO definitions beyond the P0 sketch are set at
  M2/M4 implementation, guided by §13 rules and TABLE_DEFINITIONS.
- The `Idempotency-Key` store and async polling endpoints are design targets;
  exact contracts set with each use-case implementation.
- `GET /v1/looks` (discover, M14) vs `GET /v1/knowledge/looks` (public
  catalog, M5) coexist as two read surfaces — confirmed against MODULE_MAP.
- No `DECISIONS.md` entry: documentation only; open items remain in §16.

**Assumptions recorded:**
- Path versioning `/v1`, additive-only within a version (API-1/2).
- Single resources (incl. the frozen `AssistantReply`) are envelope-free;
  lists use the envelope (API-17/18).
- Bearer auth introduced with the auth module (M4 slice); `deps.py` is a stub
  until then; assistant stays unauthenticated (F-5).
- Async is opt-in per endpoint (analysis runs only), sync-by-default
  otherwise (API-40/41).
- Endpoint set is derived from the 32 actions / 33 use cases and the module
  map; sealed/gated modules are not mounted (API-12).

**Constraints honored:** BAR-0 (assistant DTOs frozen; the API is a thin
projection of the domain model), DR-1 (one use case per router), F-6 (DTO-only
responses, no DB models), F-13 (assistant contract unchanged), C-7/C-8 (no DB
or AI/provider internals on the wire), OW-1/API-10 (owner-scoped, 404-not-403),
API-28…31 (typed errors), TRX-1/3/5 (upload-then-insert, save + signal
transaction, write-once completion), the UI Change Safety Rule (no Flutter
modified), the Scope rule (contract design only), and no implementation.
