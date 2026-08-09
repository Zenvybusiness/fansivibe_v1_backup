# Fansivibe — HTTP API Layer Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines the **HTTP API layer**
> conventions for the production Fansivibe backend — the `app/api` slice from
> `BACKEND_FOLDER_STRUCTURE.md` (routers, `deps.py`, `errors.py`, `v1/`,
> `schemas/`).
>
> These are the **cross-cutting wire contracts** every endpoint follows:
> versioning, authentication, authorization, request validation, response
> envelopes, pagination, filtering, sorting, errors, status codes, idempotency,
> file uploads, and asynchronous processing.
>
> **Status: architecture design only. No endpoint implementations are written,
> no Flutter is modified.** The live contract `POST /v1/assistant/chat` is
> unchanged.
>
> **Source of truth:** the real Fansivibe repository — the accepted STEP 5
> docs, the STEP 2 `ACTION_API_INVENTORY.md` (32 actions + Part 3 error
> summary), the STEP 4 `TRANSACTION_BOUNDARIES.md`, and the current
> `backend/app/main.py` (the only live endpoint today).

---

## 1. Purpose and scope

This document answers, for every Fansivibe endpoint (future, per
`APPLICATION_USE_CASES.md` UC-1…UC-33):

- **How is the path and version written?** (versioning)
- **How is a caller identified?** (authentication)
- **What may a caller do?** (authorization)
- **What happens to bad input?** (request validation)
- **What does a response look like?** (response envelopes)
- **How are lists shaped?** (pagination, filtering, sorting)
- **How do failures look?** (errors, status codes)
- **Which operations are safe to repeat?** (idempotency)
- **How are binaries sent?** (file uploads)
- **How do long jobs work?** (asynchronous processing)

It does **not** write endpoint implementations, define every DTO, or touch
Flutter.

**Grounding facts (BAR-0):**
- Today the backend has exactly **two** routes: `GET /health` (plain dict) and
  `POST /v1/assistant/chat` (typed `AssistantReply`, no envelope, no auth).
  This doc defines the conventions future endpoints follow **without breaking
  the live assistant contract** (A3.1, F-13).
- All 32 user actions are **future-required auth** (ACTION_API Part 4 rule 1);
  there is **no auth today**.
- Errors today are untyped FastAPI defaults; the target is the typed error
  contract (A3.3/E13.1, migration M2).
- The API layer is a **thin projection**: routers parse input, call exactly
  one application use case (DR-1), and map the result to a DTO. It owns no
  business logic and imports no infrastructure (DR-1, F-6).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `ACTION_API_INVENTORY.md` | The 32 future endpoints + per-action errors + Part 3 cross-action error summary (the primary shape driver). |
| `APPLICATION_USE_CASES.md` | The 33 use cases the routers call; their inputs/outputs/errors define DTO needs. |
| `BACKEND_ARCHITECTURE_RULES.md` | §4.1 API target shape (`deps.py`, `errors.py`, `v1/*`), A3.3/E13.1 typed errors, BA-8 user scoping. |
| `BACKEND_FOLDER_STRUCTURE.md` | `app/api/` layout: `deps.py`, `errors.py`, `schemas/`, `v1/router.py` + per-module routers. |
| `DEPENDENCY_RULES.md` | DR-1 (routers call one use case), F-6 (DB models never become API contracts), F-13 (assistant DTOs frozen). |
| `TRANSACTION_BOUNDARIES.md` | TRX-5 write-once completion → async analysis pattern; §5 non-transactional external calls. |
| `SECURITY_PRIVACY_DESIGN.md` | user_id scoping, token/session, privacy of appearance/image data, MS10.3 media gate. |
| `AI_INTEGRATION_ARCHITECTURE.md` | Capability timeouts/retries → async handling of slow analysis. |

---

## 3. Versioning

- **Path-based versioning (API-1):** every endpoint lives under `/v{N}`, the
  current version is **v1** (`/v1/...`). The router root mounts all `v1`
  routers (`app/api/v1/router.py`).
- **Additive changes only (API-2):** within a version, responses only gain
  fields (new keys never break old clients); field **removal, rename, or
  retype requires a new version** (`/v2`) and a deprecation window. The
  assistant DTOs are **frozen outright** (F-13) — no additive change may
  reorder/remove their fields.
- **Version header (API-3):** a client may pin the exact contract with
  `Accept: application/json; version=1.0`; the default is the latest of `/v1`.
  Unsupported versions → `422` with a clear message.
- **Breaking change process (API-4):** new version + old version kept running
  for a transition window (non-breaking migration, §9 M-series);
  `GET /health` stays versionless and envelope-free.

---

## 4. Authentication

- **Bearer token (API-5):** authenticated requests carry
  `Authorization: Bearer <token>`. Tokens are issued by `auth` (UC-1…3) and
  revoked by `SignOut` (UC-4) and logout-all (R51).
- **Stateless validation (API-6):** the `deps.py` auth dependency parses the
  bearer token, resolves it to a `user_id`, and injects `user_id` into the
  use case. The router never validates credentials itself (DR-1).
- **Public endpoints (API-7):** `POST /auth/register`, `POST /auth/social`,
  `POST /auth/login`, and `GET /knowledge/*` (public catalog) are
  unauthenticated; everything else is **auth-required** (ACTION_API Part 4
  rule 1). A missing/invalid token → `401` (`WWW-Authenticate: Bearer`).
- **Anonymous mode (API-8):** the "save locally" path (action 4) has no
  token; its data reaches the backend only later through `SyncLocalData`
  (UC-9) **after** account creation. No anonymous write endpoints exist.
- **Privacy (API-9):** tokens never appear in logs, URLs, or response bodies;
  image/appearance payloads require auth (MS10.3-gated flows are always
  private).

---

## 5. Authorization

- **Resource scoping (API-10):** every user-data endpoint is scoped to the
  authenticated `user_id`; a resource id that does not belong to the caller
  is treated as **404**, never `403` (no existence leak).
- **Role-based admin (API-11):** knowledge content writes (seed/admin, M5 P2)
  require an admin role checked in `deps.py`; regular users never reach
  them. Admin-only routes are documented and minimal.
- **Feature gates (API-12):** feature-gated modules (M11 `feedback`,
  M16 `media`/MS10.3) either return `404`/`501` while sealed or are not
  mounted at all — never a fake 200. Decision: sealed modules are **not
  mounted** until their gate lifts (no endpoint exists for a FUTURE
  capability — AI-0 honesty applies to APIs too).

---

## 6. Request validation

- **Typed models (API-13):** every request body and query string is a
  Pydantic model in `api/schemas/`; validation happens **before** the use
  case call (BA-3 keeps validation out of the domain).
- **Controlled-vocabulary validation (API-14):** category/color/occasion/
  type/plan values are validated against knowledge (via the knowledge service
  contract) or the domain's enums — invalid values → `422` with the allowed
  values in the error detail (ACTION_API #5/9/15/18/21/23/28).
- **Not-found vs invalid (API-15):** an id that exists-but-not-yours or
  doesn't exist → `404`; a syntactically wrong id/value → `422`.
- **Media validation (API-16):** image type/size checks → `413`/`422`
  (`MediaValidationError`) before upload (UC-24/25, ACTION_API #16/21).

---

## 7. Response envelopes

- **No envelope for single resources (API-17):** a single object returns the
  DTO directly (e.g. `AssistantReply` today — **unchanged**). Wrapping in
  `{data: …}` would break the live contract (F-13).
- **List envelope (API-18):** list responses use a small, consistent
  envelope for pagination metadata:
  ```
  { "items": [...], "page": 1, "page_size": 20, "total": 137 }
  ```
  Only list endpoints use this; single objects and errors keep their own
  shapes (§11).
- **Consistent field naming (API-19):** JSON keys are camelCase, matching the
  Flutter client (A3.1 mirror convention); DTOs are the only shape — domain
  models and ORM rows never serialize directly (F-6).

---

## 8. Pagination

- **Offset pagination (API-20):** `?page=1&page_size=20` (1-based page,
  default 20, max 100). `total` comes from the same query, not a separate
  count call.
- **Cursor for deep/feed lists (API-21):** `discover` (UC-31) and long
  history lists may use `?cursor=<opaque>&limit=20`; the cursor is
  server-generated, opaque, and encodes the last item key. Feed ordering
  stays stable (secondary sort key ties broken by id).
- **Page-size errors (API-22):** `page_size` outside `[1,100]` → `422`.

---

## 9. Filtering

- **Query-parameter filters (API-23):** filters are explicit query params
  (e.g. `?occasion=casual&color=navy&style=...`), each validated against the
  controlled vocabulary (API-14) → `422` on invalid values
  (ACTION_API #15).
- **Filtering is server-side (API-24):** list endpoints accept filters and
  apply them server-side; clients never download-and-filter (future). The
  filters a module accepts are part of its DTO/spec, not open-ended.
- **No free-form queries (API-25):** no arbitrary `?filter=json` escape
  hatch; every filter is a typed parameter (prevents injection and keeps the
  surface reviewable).

---

## 10. Sorting

- **Typed sort keys (API-26):** `?sort=<key>&order=asc|desc` where `<key>` is
  one of the documented sort keys per endpoint (e.g. `score`, `created_at`,
  `date`). Unknown key → `422`; default order `desc` unless documented.
- **Scoring sorts (API-27):** personalized ordering (discover match score,
  hairstyle/grooming score) is applied by the Decision Engine, not by the API
  — the API passes `sort=score` and the engine's ranked output is returned
  (the API never re-sorts engine output).

---

## 11. Errors

- **Typed error contract (API-28, A3.3/E13.1):** every error is one JSON
  shape:
  ```
  { "error": { "code": "NOT_FOUND", "message": "...", "details": {...} } }
  ```
  `code` is a stable machine-readable string (from the domain exception),
  `message` is human-readable, `details` is optional (e.g. allowed values,
  field errors).
- **Domain exceptions → HTTP (API-29):** `api/errors.py` maps domain
  exceptions to this shape; routers raise/return only typed exceptions
  (they never invent codes).
- **Field-level validation errors (API-30):** for `422`, `details` carries
  per-field errors (`{field: "color", error: "unknown value", allowed: [...]}`).
- **Fallback (API-31):** unhandled exceptions → `500` with
  `INTERNAL_ERROR` and a generic message (no stack traces, no internals); the
  incident is logged server-side with a correlation id echoed as a
  `X-Request-Id` header.

---

## 12. Status codes

| Code | Meaning | Used for |
| --- | --- | --- |
| `200` | success | read/update success |
| `201` | created | UC-1/2/5/10/15/18/24… (creation returns the created resource) |
| `204` | no content | UC-4/13/19/20/23 (delete/signout/ack) |
| `401` | unauthenticated | missing/invalid token (API-7) |
| `404` | not found (incl. not-yours) | all user-resource lookups (API-10/15) |
| `409` | conflict | duplicate email/item/save, version conflict, sync conflict (UC-1/5/7/9/10/15/30) |
| `413` | payload too large | media too large (API-16) |
| `422` | unprocessable | validation errors (vocab, pagination, sort, media invalid, past date) |
| `429` | rate limit | register/login/feedback (ACTION_API Part 3) |
| `402` / `424` | payment | subscription purchase failures (UC-33) |
| `500` | internal | unhandled (API-31) |
| `502` | bad gateway | identity provider unavailable (UC-2) |
| `503` | unavailable | external service/model failure, generation failure (UC-16/21/24…/29/33) |

**Status-code principle (API-32):** 4xx for caller errors, 5xx for our/external
failures; the code in the body (`error.code`) is stable and is what clients
switch on, never the HTTP code alone.

---

## 13. Idempotency

- **Where needed (API-33):** operations that must not double-apply on retry:
  saves (`SaveRecommendation` UC-15, `SaveOutfit` UC-30), create-account
  (UC-1), `SyncLocalData` (UC-9), webhook processing (UC-33). These accept an
  **`Idempotency-Key` header**; a repeat request with the same key + `user_id`
  returns the original result (or `409` for conflicting payloads).
- **Not needed (API-34):** read endpoints and inherently-safe mutations
  (favorite toggle, delete, logout) are naturally idempotent; no key required.
- **Implementation rule (API-35):** the key is hashed and stored server-side
  with the first response; enforcement lives in the application layer (the
  router just passes the header through), and repeats do **not** re-run the
  transaction (TRX-3/TRX-5 never double-write).

---

## 14. File uploads

- **Multipart (API-36):** image uploads use `multipart/form-data` with the
  image part (e.g. `image`) + the typed JSON form fields. Binary is never
  base64'd into JSON.
- **Upload-then-insert (API-37, TRX-1):** the blob is uploaded to object
  storage (M16) **before** the DB write; the response carries the `MediaRef`;
  an upload that succeeds but whose insert fails is cleaned by the async
  orphan sweep (never inside a transaction — §5 `TRANSACTION_BOUNDARIES.md`).
- **Validation before upload (API-38):** type (JPEG/PNG), max size, and
  dimension limits are checked before bytes are accepted (`413`/`422`).
- **Private by default (API-39):** uploads require auth; blobs are
  user-scoped and never returned in logs or public URLs until MS10.3 lifts
  (media module sealed until then — API-12).

---

## 15. Asynchronous processing

- **Synchronous by default (API-40):** most use cases (UC-1…23, UC-28…33)
  return synchronously; the API layer does not add async where the work is
  fast or rules-based.
- **Async for slow analysis (API-41):** image analysis (UC-24/25/26/27, and
  AI-driven generation) can take >1s. Pattern: `POST` returns **`202` +
  `{ "run_id": ... }`** (the `analysis_runs` row in `pending` state,
  TRX-5); the client polls `GET /analysis/runs/{run_id}` until `completed`
  (status field) or receives a completion callback. The write-once guard
  (TRX-5) prevents double-completion.
- **Status transitions (API-42):** `pending → completed | failed`; `failed`
  carries the error code in `error`. `202` responses are only used where the
  async pattern is documented per endpoint.
- **No background jobs in the API layer (API-43):** deferred work (orphan
  blob cleanup, webhook sync, streak derivation) lives in
  `infrastructure/jobs.py` + the events dispatcher, never in routers.
- **Timeouts (API-44):** synchronous endpoints honor the capability timeouts
  (AI doc §8) — a hang upstream never hangs the HTTP request beyond a bounded
  total; the degraded/rules fallback keeps the sync path available.

---

## 16. Report, assumptions, constraints

**What changed (this step):** added `API_LAYER_ARCHITECTURE.md` — the HTTP API
layer conventions (versioning, auth, authorization, validation, envelopes,
pagination, filtering, sorting, errors, status codes, idempotency, uploads,
async). No endpoint implementations.

**Skills used:** repository analysis (current `main.py`, schemas; ACTION/API
inventory, use cases, transaction boundaries, AI integration, folder
structure, dependency rules) — architecture documentation only.

**Files changed:** `docs/backend/API_LAYER_ARCHITECTURE.md` (new).

**Validation run:**
- Every convention traces to an accepted doc: DR-1 (routers call one use
  case), F-6 (DTO-only responses), F-13 (assistant frozen), A3.3/E13.1
  (typed errors), BA-8 (user scoping), TRX-1/5 (upload-then-insert, write-once
  completion), ACTION_API Part 3 (status codes).
- Status-code table matches ACTION_API Part 3 and the use-case error
  vocabulary (UC-1…33).
- The live `POST /v1/assistant/chat` contract is preserved (no envelope,
  unchanged shape, F-13/API-17).
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Envelope/status specifics (exact `details` shapes, cursor encoding) are
  implemented at M2/M4, guided by these conventions.
- The `Idempotency-Key` store and the async polling endpoints are design
  targets; their exact contracts are set with the use-case implementations.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation only); open items remain in `BACKEND_ARCHITECTURE_RULES.md`
  §8/§10.

**Assumptions recorded:**
- Versioning is path-based (`/v1`) with additive-only changes within a
  version (API-1/2).
- List endpoints use the envelope; single resources and the frozen assistant
  reply do not (API-17/18).
- Authentication is bearer-token based (API-5), introduced with the auth
  module (UC-1…4) in M4; `deps.py` is a stub until then.
- Async processing is opt-in per endpoint (analysis runs), not a global
  pattern (API-40/41).

**Constraints honored:** BAR-0 (assistant DTOs frozen A3.1; the API is a thin
projection of the domain model), DR-1 (routers call one use case), F-6 (no
DB/domain models as contracts), F-13 (assistant contract unchanged), BA-8
(user scoping), TRX-1/5 (media upload-then-insert, write-once completion),
the UI Change Safety Rule (no Flutter modified), and the Scope rule (this
document only).