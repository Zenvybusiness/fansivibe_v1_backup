# Fansivibe — API Response Conventions

> **STEP 6 — API CONTRACT DESIGN.** Defines the **common API response
> conventions** for Fansivibe in one focused reference: success format, error
> format, pagination format, async operation format, resource identifiers,
> timestamps, nullable fields, version fields, and request IDs — and settles
> the **envelope decision** (direct resource responses vs standard envelopes)
> with a single consistent approach. It is the companion to
> `API_CONTRACT_RULES.md` (§8 response shapes, §9 errors, §10 pagination, §11
> idempotency), `API_LAYER_ARCHITECTURE.md` (API-1…44), `ERROR_HANDLING.md`
> (the frozen 12-category taxonomy + wire shape), `OBSERVABILITY.md` (§4.1
> request-id correlation), and the sibling contract docs
> (`ASSISTANT_API.md`, `SUBSCRIPTION_API.md`, `PROFILE_ONBOARDING_API.md`, …),
> all of which already apply these conventions endpoint-by-endpoint.
>
> **Status: contract design only. Nothing is implemented.** No code, no
> routers, no `deps.py`, no SQL migrations, no dependencies, no Flutter changes.
> This document **codifies what the accepted STEP 5/6 docs already decided**
> (C-4/C-5, API-17…31) into one response-conventions reference; it introduces
> **no new wire shape** and changes **no live contract** (`GET /health`,
> `POST /v1/assistant/chat` stay untouched).
>
> **Source of truth:** the accepted backend/API docs — `API_CONTRACT_RULES.md`
> (§4 headers/field-naming/timestamps/identifiers, §8 response shapes, §9
> errors, §10 pagination, §11 idempotency), `API_LAYER_ARCHITECTURE.md`
> (§3 versioning, §7 envelopes, §8–10 pagination/filtering/sorting, §11–13
> errors/status/idempotency, §15 async), `ERROR_HANDLING.md` (§4 wire
> contract, §5 taxonomy, §6 allow-list), `OBSERVABILITY.md` (§3 log fields,
> §4.1 request-id), `FASTAPI_ARCHITECTURE_V1.md` (M-module mounting),
> `TABLE_DEFINITIONS.md` (canonical field names/types/nullability for entity
> DTOs), `APPLICATION_USE_CASES.md` (§3.3 error vocabulary), and the live repo
> (`backend/app/` — `GET /health` + `POST /v1/assistant/chat` only).

---

## 1. Purpose and scope

This document answers the STEP 6 response-conventions task with **one
consistent approach**:

- **The envelope decision (§3).** The API uses **direct resource responses**,
  not a standard envelope. A single resource returns its DTO **bare**; only
  list endpoints add a minimal, uniform envelope for pagination metadata; the
  error body and the async-accept body are their own fixed shapes. There is
  **no** `{data: ...}` / `{meta: ...}` global wrapper.
- **Nine conventions (§4–§12).** Success format, error format, pagination
  format, async format, resource identifiers, timestamps, nullable fields,
  version fields, and request IDs — each stated once, with the rule, the
  wire example, and the accepted-rule references.
- **A validation reference (§13)** tracing every convention to its accepted
  source, and **open decisions (§14)**.

The task's determination list is mapped explicitly:

- **Success response format** — §4 (200/201/204, bare DTO, list envelope, empty)
- **Error response format** — §5 (the frozen `{error:{code,message,details}}`)
- **Pagination format** — §6 (offset + cursor; envelope fields)
- **Async operation format** — §7 (202 + `{run_id}`, poll-to-terminal)
- **Resource identifiers** — §8 (UUIDs for user-owned, stable codes for knowledge)
- **Timestamps** — §9 (ISO-8601 UTC; `YYYY-MM-DD` for date-only)
- **Nullable fields** — §10 (optional values omitted; `null` only where the
  frozen DTO requires it)
- **Version fields** — §11 (path `/v1` + additive-only; `version`/`engine_version`
  resource fields; `X-Knowledge-Version`)
- **Request IDs** — §12 (`X-Request-Id`, echo + error-body `request_id`)

**The three binding design rules of this document:**

1. **One response shape per response kind, everywhere (C-4).** Single →
   bare DTO; list → `{items,page,page_size,total}`; error →
   `{error:{code,message,details}}`; async-accept → `{run_id}`. No module
   may invent its own envelope, wrapper, or naming (API-17/18).
2. **Clients switch on stable machine-readable values, never on HTTP alone
   (API-32).** `error.code` (12-category taxonomy) and DTO field names are the
   stable contract; HTTP status codes are a second signal, never the primary
   switch. The frozen `AssistantReply` (F-13) and `GET /health` are preserved
   verbatim — no response convention may reshape them.
3. **Response fields are DTO-only projections of the domain (C-7, F-6).**
   ORM rows, table/column names, and SQL are never serialized; `details` is
   allow-list-only (ER-0/ER-1); safe client messages are built in one place
   (`api/errors.py`, ER-2).

**What it does not do:** implement anything, mount endpoints, change any live
contract, introduce a global envelope, add a new error category, or invent
response fields beyond the accepted DTOs.

### 1.1 Grounding facts (re-verified)

- **The response conventions are already accepted and applied per-endpoint.**
   `API_CONTRACT_RULES.md` C-4 (consistent response structures, API-17…19),
   C-5 (consistent error structures, API-28…31), C-11 (pagination API-20…22),
   C-10 (async API-40…44); `API_LAYER_ARCHITECTURE.md` §7–15 restate them as
   the API-layer rules. This document consolidates, it does not redesign.
- **The live contract is exactly two endpoints, both envelope-free.** `GET
   /health` → `{"status":"ok"}` (versionless, no envelope, API-4) and `POST
   /v1/assistant/chat` → bare `AssistantReply` (F-13, API-17). Both are
   preserved through every migration step.
- **Single resources return the DTO directly (API-17).** No `{data: ...}`
   wrapper anywhere — it would break the frozen contract. The list envelope is
   the **only** wrapper, and only for list endpoints (API-18).
- **The list envelope is minimal and uniform:** `{ items, page, page_size,
   total }`, `page` 1-based, `page_size ∈ [1,100]` (default 20), `total` from
   the same query (API-18/20/22).
- **Errors are one typed shape (API-28, A3.3/E13.1):** `{error:{code,message,
   details?}}` with `code` from the frozen **12-category taxonomy**
   (`ERROR_HANDLING.md` §5), `message` a safe client string (ER-2), `details`
   allow-listed (ER-1) — `request_id`, `run_id`, caller-owned resource ids,
   field errors `[{field,error,allowed?}]`, `kind`, `missing`, `retry_after`.
   Never SQL, prompts, stack traces, tokens, provider/model names, or user
   content (ER-0).
- **Async is reserved for slow analysis (API-40/41).** Sync by default; image
   analysis (UC-24…27) returns `202 + {run_id}` (`analysis_runs` row in
   `pending`), the client polls `GET /v1/analysis/runs/{run_id}` to a terminal
   `status ∈ {pending, completed, failed}`; `failed` carries the typed error in
   the DTO's `error` (API-42). Write-once guard (TRX-5). No background jobs in
   the API layer (API-43).
- **Identifiers follow C-13.** User-owned resources use **server-generated
   UUIDs** (`users.id`, `wardrobe_items.id`, `saved_looks.id`, `user_events.id`,
   `analysis_runs.id`, `subscriptions.id`); knowledge uses **stable text codes**
   (`looks.code`, `wardrobe_categories.code`, `colors.code`, `occasions.code`,
   `event_types.code`, `signal_types.code`). Clients store and echo ids, never
   generate them (`API_CONTRACT_RULES.md` §4.3).
- **Timestamps are ISO-8601 UTC** (`2026-08-09T12:34:56Z`); date-only fields
   (`event_date`, `day`) are `YYYY-MM-DD` (API-19 field-naming convention).
- **Versioning is path-based `/v1` + additive-only (API-1/2).** Responses only
   gain optional fields within a version; removal/rename/retype requires a new
   version + deprecation window (API-4). A client may pin with
   `Accept: application/json; version=1.0` (API-3). Resource-level version
   fields (`user_state.version` optimistic-concurrency counter, `engine_version`
   on immutable results PR-6, `content_version` on knowledge) are separate from
   API versioning.
- **`X-Request-Id` is assigned at the API boundary and echoed on every
   response** (`OBSERVABILITY.md` §4.1; `API_CONTRACT_RULES.md` §4.2). If the
   client supplies one (bounded format) it is used, else generated; it is
   threaded application→domain and carried in every log line. On `500`, the
   error `details.request_id` carries the same id so users can report an
   incident (API-31).
- **Empty is not an error (§8.4).** Deletes/logout/ack → `204` (no body);
   empty *derived* results that are not errors → `200` with `needs_data: true`
   **or** `204` per use case (`ERROR_HANDLING.md` §5.12; UC-14 → 204/empty,
   UC-28 → 204/empty).
- **Idempotency is a header, not a response shape (API-33…35).**
   `Idempotency-Key` on saves/sync/create/webhook; repeats return the original
   result; conflicting payloads → `409 CONFLICT` with `details.kind`. Reads and
   naturally-idempotent mutations need no key.
- **Ownership leaks nothing (API-10, OW-1):** a foreign or non-existent
   resource id → `404 NOT_FOUND`, never `403` (no existence leak); `403` is
   reserved for authenticated-but-disallowed admin paths.

---

## 2. Source of truth and inputs

| Concern | Source |
| --- | --- |
| Response shapes (bare/list/empty) | `API_CONTRACT_RULES.md` §8 (API-17/18); `API_LAYER_ARCHITECTURE.md` §7 |
| Error wire contract + taxonomy | `ERROR_HANDLING.md` §4/§5; `API_CONTRACT_RULES.md` §9; `API_LAYER_ARCHITECTURE.md` §11–12 |
| Pagination / filtering / sorting | `API_CONTRACT_RULES.md` §10; `API_LAYER_ARCHITECTURE.md` §8–10 |
| Async pattern | `API_LAYER_ARCHITECTURE.md` §15 (API-40…44); `API_CONTRACT_RULES.md` §8.3; `BACKGROUND_JOB_ARCHITECTURE.md` BJ-0 |
| Identifiers / timestamps / field names | `API_CONTRACT_RULES.md` §4.3 (C-13); `TABLE_DEFINITIONS.md` |
| Versioning | `API_LAYER_ARCHITECTURE.md` §3 (API-1…4); `API_CONTRACT_RULES.md` C-1 |
| Request IDs | `OBSERVABILITY.md` §3/§4.1; `API_CONTRACT_RULES.md` §4.2 (API-31) |
| Nullability | `TABLE_DEFINITIONS.md`; `API_CONTRACT_RULES.md` §4.3; `OBSERVABILITY.md` §3 |
| Live contract (frozen) | `backend/app/main.py`, `backend/app/models/schemas.py` |

---

## 3. The envelope decision — direct resource responses (chosen)

### 3.1 Decision

> **Fansivibe uses direct resource responses, not a standard envelope.**
> A single resource returns its DTO **bare** (no `data`/`meta` wrapper). The
> only wrapper in the entire API is the **list envelope** (`{items,page,
> page_size,total}`) on list endpoints, plus the two fixed shapes for errors
> (`{error:{code,message,details}}`) and async-accept (`{run_id}`).

| Response kind | Wire shape | Why |
| --- | --- | --- |
| Single resource (GET one, create, update, action result) | **Bare DTO** | API-17; preserves the frozen `AssistantReply` (F-13); no double-nesting for clients; simplest to deserialize. |
| List | `{ "items": [ ... ], "page": 1, "page_size": 20, "total": 137 }` | API-18; pagination metadata is the *only* thing a wrapper earns; uniform everywhere. |
| Error | `{ "error": { "code", "message", "details?" } }` | API-28; the stable machine-readable `code` is what clients switch on (API-32). |
| Async-accept | `{ "run_id": "7a2b..." }` | API-41; minimal, polled via the run resource. |
| No-content (delete/logout/ack) | `204` (empty body) | §8.4; nothing to return. |
| Health | `{"status":"ok"}` | versionless, envelope-free, frozen (API-4). |

### 3.2 Why this approach (simplicity + project requirements)

- **The frozen contract forces it.** `AssistantReply` is already bare (F-13);
  a global `{data: ...}` wrapper would break the live wire. Consistency starts
  from the one contract that cannot change.
- **One wrapper type beats two philosophies.** "Direct everywhere, except one
  uniform list envelope" is a single, teachable rule (C-4) — vs the common
  `{data, meta, errors, code, message}` super-envelope that duplicates the
  error contract and adds nesting for every single-object read.
- **Errors stay first-class.** A global success envelope that also carries
  errors conflicts with HTTP semantics; Fansivibe keeps errors as their own
  typed body (C-5) and reserves `details` for the allow-list.
- **Clients are simple.** The Flutter client deserializes a DTO directly, a
  list envelope only on list calls, and an error body only on non-2xx — no
  unwrap step at every call site.
- **The API is small and resource-oriented** (~48 accepted endpoints, most
  single-object reads). A heavy envelope is machinery the project does not
  need; the list envelope already carries pagination where the work is real.

---

## 4. Success response format

| Case | HTTP | Body |
| --- | --- | --- |
| Read / update / action result | `200` | bare DTO, or list envelope for list endpoints |
| Created | `201` | the created resource as a bare DTO |
| No content (delete, logout, ack) | `204` | empty |
| Async accepted | `202` | `{ "run_id": "..." }` |
| Empty derived result (not an error) | `200`/`204` | `200` with `needs_data: true` **or** `204` per use case (§8.4) |

**Rules:**

- **Bare DTO, always.** A single object returns the DTO directly — no `data`,
  no `result`, no `body` key (API-17):

```json
{ "id": "3f1c...", "name": "Navy Blazer", "category": "blazer", "color": "navy", "isFavorite": false }
```

- **List endpoints only** add the uniform envelope (API-18). `total` is
  computed from the same query, not a separate count call.
- **`camelCase` keys** (API-19), matching the Flutter client (A3.1 mirror
  convention); DTOs are the only serialized shape — domain models and ORM rows
  never serialize directly (F-6).
- **Status codes are 4xx/5xx-mapped, body `code` is stable** (API-32) — see §5.
- **Empty is not an error** — `204` or `200 + needs_data: true` per the
  documented use case; never a fake `500`.

---

## 5. Error response format

Every error response is exactly (API-28, `ERROR_HANDLING.md` §4):

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The requested item was not found.",
    "details": { }
  }
}
```

| Field | Rule |
| --- | --- |
| `code` | **Stable machine-readable string** from the frozen 12-category taxonomy (§5.1). Clients switch on this, never on HTTP alone (API-32). |
| `message` | **Safe client message**, human-readable, no internals, no stack traces, no provider names, no paths (ER-2). Built only in `api/errors.py`. |
| `details` | **Optional, allow-list only** (ER-1): `request_id`, `run_id`, caller-owned resource ids, field errors `[{field,error,allowed?}]`, `kind`, `missing`, neutral `retry_after`. **Never** SQL, prompts, stack traces, tokens, provider/model names, or user content (ER-0). |

### 5.1 The frozen 12-category taxonomy

| `error.code` | HTTP | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | 422 | Invalid input, vocabulary, dates; `details` carries `[{field,error,allowed?}]`. |
| `AUTHENTICATION_ERROR` | 401 | Missing/expired/revoked token (+ `WWW-Authenticate: Bearer`). |
| `AUTHORIZATION_ERROR` | 403 | Authenticated but disallowed (admin path). |
| `NOT_FOUND` | 404 | Resource missing **or not-yours** (API-10/15, OW-1). |
| `CONFLICT` | 409 | Duplicate email/item/save, version conflict, sync conflict; `details.kind`. |
| `RATE_LIMITED` | 429 | Register/login/feedback throttling (+ `Retry-After`). |
| `AI_FAILURE` | 503 (or none if degraded) | Provider timeout/malformed output; `details.degraded=true` if the rules fallback served. |
| `MEDIA_FAILURE` | 413 / 422 / 503 | Image too large/unsupported (413/422) or blob storage failure (503); `details.kind`. |
| `DATABASE_FAILURE` | 500 / 503 | Internal; `details.request_id` only. |
| `EXTERNAL_SERVICE_FAILURE` | 502 / 503 / 402 / 424 | Identity provider (502), weather/knowledge/billing (503), payment outcome (402/424). |
| `PROCESSING_FAILURE` | 500 (sync) / `status=failed` (poll) | Analysis/generation pipeline failure; `details.run_id`. |
| `INSUFFICIENT_USER_DATA` | 200+`needs_data` / 422 | Decision needs more user data (empty wardrobe, no face profile); `details.missing`. |

### 5.2 Status-code principle

- 4xx = caller errors; 5xx = our/external failures (API-32).
- Unhandled exceptions → `500 INTERNAL_ERROR` with a **generic message** +
  `X-Request-Id` echoed in `details.request_id` (API-31, ER-0).
- Ownership never leaks: a foreign/non-existent resource → `404`, never `403`
  (API-10).

---

## 6. Pagination format

### 6.1 Offset pagination (default)

`?page=1&page_size=20` — 1-based, default 20, max 100 (API-20/22).

Response envelope:

```json
{
  "items": [ /* DTOs */ ],
  "page": 1,
  "page_size": 20,
  "total": 137
}
```

- `page_size` outside `[1,100]` → `422 VALIDATION_ERROR` (API-22).
- `total` comes from the same query (no separate count call).
- Empty list → `200` with `items: []`, `total: 0` — **not** an error.

### 6.2 Cursor pagination (deep/feed lists)

Deep feeds and long history lists (e.g. discover `GET /v1/looks`, UC-31) may
use `?cursor=<opaque>&limit=20` (API-21):

- `cursor` is **server-generated, opaque**, and encodes the last item key.
- Feed ordering stays **stable** (secondary sort key = id).
- Response keeps the same envelope shape (`items`, plus cursor-aware
  metadata as the endpoint documents).

### 6.3 Filters and sorting

- **Filters:** explicit typed query params (`?occasion=casual&color=navy`),
  validated against the controlled vocabulary server-side → `422` on invalid
  values (API-23/24/25). No free-form `?filter=json`.
- **Sorting:** `?sort=<key>&order=asc|desc` with documented keys per endpoint
  (`created_at`, `event_date`, `score`, ...); unknown key → `422` (API-26).
  Personalized/engine-ranked ordering (discover match, hair/grooming score) is
  returned as produced — the API never re-sorts engine output (API-27).

---

## 7. Async operation format

- **Sync by default** (API-40). Async is reserved for slow image analysis
  (UC-24…27) where a call can take >1s.
- **Accept:** `POST` returns `202` + the run id:

```json
{ "run_id": "7a2b..." }
```

- **Poll:** the client polls `GET /v1/analysis/runs/{run_id}` until a terminal
  state. The run DTO:

```json
{
  "run_id": "7a2b...",
  "run_type": "outfit",
  "status": "pending",
  "created_at": "2026-08-09T12:00:00Z"
}
```

- **Status lifecycle (API-42, TRX-5):** `pending → completed | failed`; the
  run row is **write-once** — only the guarded completion flips the state.
- **`completed`** runs include the **immutable `result` snapshot** +
  `engine_version` (PR-6) so results can be re-derived or audited.
- **`failed`** runs carry the typed error in the DTO's `error` (API-42) —
  same `{error:{code,message,details}}` shape as §5.
- **No background jobs in the API layer (API-43):** deferred work (orphan blob
  cleanup, webhook sync, streak derivation) lives in `infrastructure/jobs.py` +
  the events dispatcher, never in routers.
- **Timeouts (API-44):** synchronous endpoints honor the capability timeouts;
  a degraded AI fallback (rules) keeps the sync path available.

---

## 8. Resource identifiers

- **User-owned resources** use **server-generated UUIDs** (C-13):
  `users.id`, `wardrobe_items.id`, `saved_looks.id`, `user_events.id`,
  `analysis_runs.id`, `subscriptions.id`. Clients store and echo them; clients
  **never generate** them.
- **Knowledge** uses **stable text codes** (C-13): `looks.code`,
  `wardrobe_categories.code`, `colors.code`, `occasions.code`,
  `event_types.code`, `signal_types.code` — human-stable, versionable,
  PR-3.
- **Run ids** (`run_id`) are server-generated UUIDs for async results (§7).
- **JSON keys are `camelCase`** (API-19); the wire id field is always the
  canonical DTO field (`id`, `code`, `run_id`), never a raw table column.
- **Ownership (API-10/15):** a syntactically wrong id → `422`; a well-formed
  id that does not exist or is not the caller's → `404` (never `403`).

---

## 9. Timestamps

- **ISO-8601 UTC** for all timestamps: `2026-08-09T12:34:56Z`
  (`API_CONTRACT_RULES.md` §4.3).
- **Date-only** fields (`event_date`, `day`) are `YYYY-MM-DD`.
- Field names are camelCase (`created_at` → `createdAt`, `updated_at` →
  `updatedAt`, `started_at` → `startedAt`, `renews_at` → `renewsAt`) — JSON
  mirrors the `TABLE_DEFINITIONS.md` column names (A3.1 convention).
- Timezone: always UTC with a trailing `Z`; clients convert to local for
  display.

---

## 10. Nullable fields

- **Optional values are omitted from responses**, never sent as empty strings
  (`OBSERVABILITY.md` §3 — "optional fields are omitted (never empty strings)");
  nullability of entity fields is canonically defined by `TABLE_DEFINITIONS.md`
  (the source of field names/types/nullability for entity DTOs).
- **`null` appears only where the frozen DTO requires it** (e.g. the
  `AssistantReply` DTO's nullable members as shipped today, F-13 — never
  reshaped by this convention). New DTOs omit absent optional fields rather
  than emitting `null` keys.
- **Requests:** optional request fields are accepted as absent **or** `null`
  interchangeably (FastAPI/Pydantic default) — this is a request rule, not a
  response rule; response DTOs omit absent optional values.
- **Reason:** a bare DTO with omitted optionals is smaller, and an absent
  key vs `null` is unambiguous to a JSON client; the frozen contract is the
  single documented exception (F-13).

---

## 11. Version fields

Three distinct version concepts — keep them separate:

| Concept | Field / mechanism | Rule |
| --- | --- | --- |
| **API version** | Path `/v1` (API-1); optional `Accept: application/json; version=1.0` (API-3) | Additive-only within a version (API-2); breaking change → new version + deprecation window (API-4); `GET /health` stays versionless. |
| **Resource optimistic-concurrency** | `version` int on mutable state (e.g. `user_state.version`, echoed on `ProfileView.version`) | `CHECK (version >= 0)`; bumped on writes; a stale write → `409 CONFLICT` (`details.kind`), client refreshes and retries. |
| **Content / engine reproducibility** | `content_version` on knowledge rows; `engine_version` on immutable results (PR-6) | Content version for cache/validation + auditability of references; engine version so past results can be re-derived. |

Additional headers:

- `X-Knowledge-Version` on `GET /knowledge/*` responses — content version for
  cache/validation (KN-1).
- Responses only **gain** optional fields within `/v1` (API-2); removal/
  rename/retype of any existing field is a breaking change.

---

## 12. Request IDs

- **`X-Request-Id`** is assigned at the API boundary (middleware) on entry and
  **echoed on every response** (`OBSERVABILITY.md` §4.1; `API_CONTRACT_RULES.md`
  §4.2). If the client supplies one (bounded format), it is used; otherwise the
  server generates one. Never trusted blindly (length/format enforced).
- The id is **threaded explicitly application → domain** (DR-1/F-3) and carried
  in **every log line** for correlation (§3 of `OBSERVABILITY.md`).
- On `500`, the error body carries `details.request_id` (the same echo) so
  users can report an incident without exposing internals (API-31,
  `ERROR_HANDLING.md` §4).
- **What it is not:** never a user data carrier, never an auth token, never
  used for rate limiting.

---

## 13. Validation reference

- **One shape per response kind** — §3/§4/§5/§7 trace directly to
  `API_CONTRACT_RULES.md` §8 (API-17/18), §9 (API-28), and
  `API_LAYER_ARCHITECTURE.md` §7/§11; the live `GET /health` +
  `POST /v1/assistant/chat` (F-13) are unchanged and envelope-free (API-4/17).
- **Error taxonomy identical** to `ERROR_HANDLING.md` §4/§5 (12 frozen
  categories, allow-list `details`, safe `message` from `api/errors.py`,
  `500 → details.request_id`).
- **Pagination identical** to `API_CONTRACT_RULES.md` §10 and
  `API_LAYER_ARCHITECTURE.md` §8–10 (`{items,page,page_size,total}`,
  `page_size ∈ [1,100]` → 422, cursor for deep/feed lists).
- **Async identical** to `API_LAYER_ARCHITECTURE.md` §15 (`202 + {run_id}`,
  poll `GET /v1/analysis/runs/{run_id}`, `pending→completed|failed` write-once,
  `failed` carries `error`).
- **Identifiers/timestamps/naming** match `API_CONTRACT_RULES.md` §4.3 (C-13,
  ISO-8601 UTC, camelCase) and `TABLE_DEFINITIONS.md`.
- **Versioning** matches `API_LAYER_ARCHITECTURE.md` §3 (API-1…4) and the
  resource-version fields in `TABLE_DEFINITIONS.md` (`user_state.version`,
  `looks.content_version`, `analysis_runs.engine_version`).
- **Request IDs** match `OBSERVABILITY.md` §4.1 and `API_CONTRACT_RULES.md`
  §4.2/API-31.
- No code, routers, migrations, or Flutter changes; `git status --short`
  unchanged except `CURRENT_STATE.md` + the new doc.

---

## 14. Open decisions

1. **Request-optional `null` vs omission** — accepted as interchangeable for
   request DTOs (§10); if the provider/pydantic behavior needs tightening, the
   convention is a single config, not a per-endpoint choice.
2. **Cursor envelope metadata** — the cursor variant (§6.2) keeps `items`
   but the exact cursor metadata field names are finalized with the discover
   feed endpoint (UC-31).
3. **`X-Request-Id` client-supplied format bound** — the bounded format is
   set in `OBSERVABILITY.md` §4.1; final length/regex enforced at M1.
4. **Unchanged project-wide opens** — auth provider (D-AUTH-1), knowledge
   shape (K9.1), media privacy (MS10.3), feedback design (PR-12), User fields,
   Today'sLookRecord (P1), RecommendationHistory (P3), `subscriptions.status`
   vocabulary (billing integration).

---

## 15. Report, assumptions, constraints

**What changed (this step):** added `docs/api/API_RESPONSE_CONVENTIONS.md` —
one consolidated reference for Fansivibe's common response conventions
(success, error, pagination, async, identifiers, timestamps, nullable fields,
version fields, request IDs) and a single **direct resource responses** decision
(bare DTO for single resources; the list envelope `{items,page,page_size,total}`
as the only wrapper; fixed error `{error:{code,message,details}}` and
async-accept `{run_id}` shapes). **No implementation; no new wire shape; no
live contract changed.**

**Skills used:** repository analysis (live `main.py`, `schemas.py` — the frozen
bare contract) + design-doc synthesis (API_CONTRACT_RULES §8/§9/§10/§11,
API_LAYER_ARCHITECTURE §3/§7–15, ERROR_HANDLING §4/§5, OBSERVABILITY §3/§4.1,
TABLE_DEFINITIONS, APPLICATION_USE_CASES §3.3, FASTAPI_ARCHITECTURE M-modules)
— documentation only.

**Files changed:** `docs/api/API_RESPONSE_CONVENTIONS.md` (new).

**Validation run:**
- **Every convention traces to an accepted rule** — API-17/18 (bare/list),
  API-28…31 (errors), API-20…22 (pagination), API-40…44 (async), C-13
  (identifiers), API-19 + §4.3 (timestamps/naming), API-1…4 (versioning),
  OBSERVABILITY §4.1 (request-id) — identical shapes to the source docs.
- **The envelope decision is a codification, not a redesign** — the live
  contract (`GET /health`, `POST /v1/assistant/chat`, F-13) is unchanged and
  envelope-free; the list envelope is already the accepted shape (C-4).
- **`git status --short`:** docs/api/ holds API_CONTRACT_RULES.md +
  API_INVENTORY.md + AUTH_API.md + PROFILE_ONBOARDING_API.md + APPEARANCE_API.md
  + SCAN_API.md + HAIRSTYLE_RECOMMENDATION_API.md + RECOMMENDATION_API.md +
  WARDROBE_API.md + DAILY_OUTFIT_EVENTS_API.md + FEEDBACK_LEARNING_API.md +
  ASSISTANT_API.md + SUBSCRIPTION_API.md + **API_RESPONSE_CONVENTIONS.md**
  (untracked) + CURRENT_STATE.md; no code, directories, or files created.

**Remaining:** STEP 6 design continues. The next response-convention-facing
candidates are the remaining feature module contracts and the media/outfits
surface; all must apply the conventions in this document (§3–§12) with no new
envelope. Open decisions in §14.
