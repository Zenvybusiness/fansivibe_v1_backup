# Fansivibe — Error Handling System

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines the **consistent
> error-handling system** for the production Fansivibe backend — one typed
> error taxonomy, one wire shape, one mapping rule from exception to HTTP, and
> one logging policy.
>
> **Status: architecture design only. Nothing is implemented.** No code,
> files, or directories are created; the live assistant contract
> (`POST /v1/assistant/chat`) is unchanged.
>
> **Grounding facts (BAR-0, safety):** errors today are untyped FastAPI
> defaults. The target is the typed error contract (A3.3/E13.1) defined in
> `BACKEND_ARCHITECTURE_RULES.md` §9 M2 and `API_LAYER_ARCHITECTURE.md`
> §11 (API-28…31). **Sensitive implementation details (stack traces,
> internals, paths, provider names, tokens) must never reach Flutter** — the
> client sees only a stable `code` + a safe `message`.

---

## 1. Purpose and scope

This document defines:

1. **The error taxonomy** — 12 stable error categories, each with its
   internal exception, domain error, application error, API response, HTTP
   status, safe client message, and internal logging.
2. **The propagation model** — how an exception raised in the domain travels
   up through the application to `api/errors.py` and becomes a response,
   without leaking internals.
3. **The wire contract** — the single JSON error shape and its rules.
4. **The logging policy** — what is logged internally at each level, and what
   is **never** logged.

It does **not** implement handlers, DTOs, or logging config.

**Grounding rules from accepted docs:**
- **A3.3 / E13.1:** typed error contract — errors are typed, structured, and
  mapped once (`BACKEND_ARCHITECTURE_RULES.md` §9 M2).
- **API-28…31 (`API_LAYER_ARCHITECTURE.md`):** one error shape
  `{error:{code,message,details}}`; routers raise only typed exceptions;
  `errors.py` maps them; unhandled → `500 INTERNAL_ERROR` with a correlation
  id (`X-Request-Id`).
- **DR-1:** routers call exactly one use case; error mapping lives in the API
  layer, not the domain.
- **F-3:** the domain raises domain exceptions, never HTTP exceptions.
- **SAFETY rules (AGENTS.md):** never log tokens, secrets, private user
  images, or auth internals; never hide errors to fake success.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `BACKEND_ARCHITECTURE_RULES.md` | A3.3/E13.1 typed errors, §9 M2 (typed error contract migration). |
| `API_LAYER_ARCHITECTURE.md` | §11 errors (API-28…31), §12 status codes (API-32), `errors.py`. |
| `APPLICATION_USE_CASES.md` | §3.3 error vocabulary (401/404/409/413/422/429/503/402/424/502) used by UC-1…33. |
| `ACTION_API_INVENTORY.md` | Part 3 cross-action error summary — the source of the taxonomy's coverage. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1…8 — where failures happen (media, AI, DB) and what a rollback leaves. |
| `AI_INTEGRATION_ARCHITECTURE.md` | AI failure/retry/degrade behavior → `AI_FAILURE` category. |
| `DEPENDENCY_RULES.md` | F-3 (domain never raises HTTP), DR-1 (one use case per router). |
| `SECURITY_PRIVACY_DESIGN.md` | user scoping, erasure, MS10.3 — what must never leak. |

---

## 3. The propagation model

```
  domain/           raises DomainError subtypes (F-3, pure Python, no HTTP)
    │
    ▼
  application/      catches/lets domain errors propagate; may add application
    │               context (which use case, which resource) as ApplicationError
    ▼
  api/errors.py     the ONLY place domain/application errors become HTTP
    │               (maps code → status, builds safe message, logs)
    ▼
  Flutter           sees ONLY {error:{code, message, details}}
```

Rules:

1. **Domain raises, never catches to fake success** (F-3). Domain errors are
   typed (`DomainError` subclasses) and carry a **stable code** + an
   **internal message** only.
2. **Application may wrap** with resource context (e.g. "wardrobe item") but
   never replaces the code or adds internals.
3. **`api/errors.py` is the single mapper.** It maps each `DomainError` (and
   known framework errors: validation, auth) to HTTP status + safe client
   message + logging. Nothing else in the codebase builds an HTTP error body.
4. **Unknown/unexpected exceptions** are caught once at the FastAPI exception
   handler → `500 INTERNAL_ERROR` + correlation id, with full internals only
   in server logs.

---

## 4. The wire contract (API-28)

Every error response is exactly:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The item was not found.",
    "details": { }
  }
}
```

| Field | Rule |
| --- | --- |
| `code` | Stable machine-readable string (the taxonomy below). Clients switch on this, never on HTTP code alone (API-32). |
| `message` | **Safe client message** — human-readable, no internals, no stack traces, no provider names, no paths. |
| `details` | Optional. Only non-sensitive structured info: field-level validation errors, allowed values, resource id (own id only), correlation id. **Never** SQL, prompts, stack, tokens, or user content. |

`details` carries a `request_id` (echo of `X-Request-Id`) on `500` so users
can report an incident without exposing internals.

---

## 5. Error taxonomy (the 12 categories)

For each: **internal exception**, **domain error**, **application error**,
**API response**, **HTTP status**, **safe client message**, **internal
logging**.

### 5.1 `VALIDATION_ERROR`

- **Internal exception:** `pydantic.ValidationError`, `ValueError` from schema
  checks, custom vocabulary checks.
- **Domain error:** `InvalidInputError` (raised by domain rules / validation
  services).
- **Application error:** `ValidationApplicationError` (wraps field errors).
- **API response:** `details` carries `[{field, error, allowed?}]`.
- **HTTP status:** `422`.
- **Safe client message:** "Some of the provided values are not valid. Please
  check your input."
- **Internal logging:** WARN: `code`, resource, field names, violating value
  (value is user-provided, not sensitive). No full request body beyond fields.

### 5.2 `AUTHENTICATION_ERROR`

- **Internal exception:** unknown token, expired session, revoked session.
- **Domain error:** `UnauthenticatedError`.
- **Application error:** `AuthApplicationError` (adds whether token was
  missing/expired).
- **API response:** plus `WWW-Authenticate: Bearer` header (401).
- **HTTP status:** `401`.
- **Safe client message:** "Your session has expired or is invalid. Please
  sign in again."
- **Internal logging:** INFO: `code`, user scope (if resolvable), token id
  hash — **never the token itself**. Never log credentials.

### 5.3 `AUTHORIZATION_ERROR`

- **Internal exception:** authenticated user lacks the required role/scope.
- **Domain error:** `ForbiddenError`.
- **Application error:** `AuthorizationApplicationError` (role required).
- **API response:** no existence hints; generic.
- **HTTP status:** `403`.
- **Safe client message:** "You do not have permission to perform this
  action."
- **Internal logging:** WARN: `code`, user_id, required role. Note: resource
  *scoping* (not-yours id) is `NOT_FOUND`, not this — no existence leak
  (API-10).

### 5.4 `NOT_FOUND`

- **Internal exception:** missing row / missing id.
- **Domain error:** `NotFoundError`.
- **Application error:** `NotFoundApplicationError` (resource type).
- **API response:** generic message; no distinction between "not yours" and
  "doesn't exist" (API-10/15).
- **HTTP status:** `404`.
- **Safe client message:** "The requested item was not found."
- **Internal logging:** INFO: `code`, resource type, id. Id is the caller's
  own id (safe).

### 5.5 `CONFLICT`

- **Internal exception:** duplicate email/item/save, optimistic-concurrency
  version mismatch, sync timestamp conflict.
- **Domain error:** `ConflictError`.
- **Application error:** `ConflictApplicationError` (kind: duplicate |
  version | sync).
- **API response:** `details.kind` + optional conflicting field.
- **HTTP status:** `409`.
- **Safe client message:** "This action conflicts with the current state.
  Refresh and try again."
- **Internal logging:** INFO: `code`, kind, resource type. No user content.

### 5.6 `RATE_LIMITED`

- **Internal exception:** rate-limit exceeded (register/login/feedback).
- **Domain error:** `RateLimitError`.
- **Application error:** `RateLimitApplicationError` (retry-after).
- **API response:** plus `Retry-After` header.
- **HTTP status:** `429`.
- **Safe client message:** "Too many attempts. Please wait a moment and try
  again."
- **Internal logging:** INFO: `code`, scope (user/anonymous), endpoint. No
  content.

### 5.7 `AI_FAILURE`

- **Internal exception:** provider timeout/5xx, malformed structured output,
  capability error (from `AI_INTEGRATION_ARCHITECTURE.md`).
- **Domain error:** `ExternalServiceError` (source=ai) or a specific
  `AiProviderError`.
- **Application error:** `AiFailureApplicationError` (capability, degraded?
  status).
- **API response:** note in `details` whether the **rules fallback** was used
  (AI is additive; the request still succeeded if it degraded — see below).
- **HTTP status:** `503` (or no error if gracefully degraded to rules).
- **Safe client message:** "The style service is temporarily unavailable.
  Please try again shortly."
- **Internal logging:** WARN/ERROR: `code`, capability, provider (internal
  log only), model version, duration. **Never** prompt text, model output, or
  user context.

### 5.8 `MEDIA_FAILURE`

- **Internal exception:** invalid image, unsupported type, too large, blob
  upload/delete failure.
- **Domain error:** `MediaValidationError` (413/422) or `MediaStorageError`
  (503).
- **Application error:** `MediaFailureApplicationError` (kind: invalid |
  storage).
- **API response:** `details.kind`.
- **HTTP status:** `413` / `422` / `503` per kind.
- **Safe client message:** "The image could not be processed." / "The image
  is too large or not a supported format."
- **Internal logging:** WARN: `code`, kind, size/type metadata (not bytes).
  **Image bytes and image content are never logged** (SAFETY, MS10.3).

### 5.9 `DATABASE_FAILURE`

- **Internal exception:** connection error, constraint violation,
  transaction rollback, migration state mismatch.
- **Domain error:** `DatabaseError` (raised by infrastructure; surfaced as a
  typed error, never raw SQLAlchemy text).
- **Application error:** `DatabaseApplicationError` (operation).
- **API response:** generic; `details` carries `request_id` only.
- **HTTP status:** `500` (or `503` when the DB is down and the service cannot
  serve).
- **Safe client message:** "Something went wrong on our side. Please try
  again later."
- **Internal logging:** ERROR: `code`, operation, constraint (if known),
  `request_id`, full traceback (server-side only). **Never** query text with
  user data, connection strings, or credentials.

### 5.10 `EXTERNAL_SERVICE_FAILURE`

- **Internal exception:** identity provider unavailable (502), billing
  provider failure (503), weather/knowledge source unavailable.
- **Domain error:** `ExternalServiceError` (source: identity | billing |
  weather | knowledge).
- **Application error:** `ExternalServiceApplicationError` (source).
- **API response:** `details.source` (internal-only value, stripped for
  clients — see §6).
- **HTTP status:** `502` (identity upstream) / `503` (other) / `402`/`424`
  (payment outcome).
- **Safe client message:** "This service is temporarily unavailable. Please
  try again later."
- **Internal logging:** ERROR: `code`, source, provider (log only), duration,
  `request_id`. No tokens, no payment details.

### 5.11 `PROCESSING_FAILURE`

- **Internal exception:** analysis/generation pipeline failure (rule engine
  invariant broken, stage crash, timed-out long job), async run failure.
- **Domain error:** `ProcessingError` (e.g. a run transitions to `failed`).
- **Application error:** `ProcessingApplicationError` (run_id).
- **API response:** `details.run_id`; async polls see `status=failed` +
  `error.code` (API-42).
- **HTTP status:** `500` (sync) or `200/202` with `status=failed` on poll.
- **Safe client message:** "We couldn't finish this request. Please try
  again."
- **Internal logging:** ERROR: `code`, run_id, stage, traceback (server).
  No user content, no image bytes.

### 5.12 `INSUFFICIENT_USER_DATA`

- **Internal exception:** a decision cannot be made with the available user
  data (empty wardrobe, no face profile, missing preferences) — distinct
  from an empty *result* (which is a 200/204).
- **Domain error:** `InsufficientUserDataError`.
- **Application error:** `InsufficientDataApplicationError` (what's missing:
  wardrobe | face | preferences).
- **API response:** `details.missing`; may carry suggested next action
  (e.g. "add wardrobe items").
- **HTTP status:** `200` with a `needs_data` indicator **or** `422` for
  hard-gated flows (decision: per use case — e.g. outfit generation with an
  empty wardrobe is `200` + `needs_data`; UC-28 204/empty per ACTION_API).
- **Safe client message:** "We need a bit more from your profile to do this.
  Add a few items and try again."
- **Internal logging:** INFO: `code`, missing field(s). No content.

---

## 6. Leak prevention (the safety contract)

**ER-0 (never leaks):** the Flutter client receives **only** `code`,
`message`, and non-sensitive `details`. The following are **never** included
in any API response:

- stack traces, file paths, line numbers
- SQL, query text, schema/table names
- provider/vendor names, model names, prompts, raw AI output
- tokens, credentials, session ids (full), API keys
- internal exception messages or class names
- user content (messages, image bytes, face data, wardrobe snapshots)
- internal `details.source` values from EXTERNAL_SERVICE_FAILURE (mapped to a
  neutral value before response)

**ER-1 (details allow-list):** `details` may only contain values from an
explicit allow-list: `request_id`, `run_id`, resource ids (caller-owned),
field names, allowed values, `missing` fields, `kind`, and a neutral
`retry_after`. Anything else is stripped by `errors.py`.

**ER-2 (double-build):** the safe `message` is built in `errors.py` only; the
domain and application never build client-facing strings (they carry only the
code + internal context).

**ER-3 (one mapper):** no router, use case, or repository builds an error
body or safe message. If a new error category is needed, it is added to the
taxonomy and mapped once in `errors.py` (F-13 style stability — the taxonomy
is frozen once shipped).

---

## 7. Logging policy

| Level | What | Never |
| --- | --- | --- |
| DEBUG | successful typed outcomes; capability durations (AI doc) | message content, image bytes |
| INFO | auth events (login/logout/register), NOT_FOUND, CONFLICT, RATE_LIMITED, degraded-AI, `request_id` correlation | tokens, credentials |
| WARN | VALIDATION_ERROR, AUTHORIZATION_ERROR, AI_FAILURE (degraded), MEDIA_FAILURE | user content, raw AI output |
| ERROR | DATABASE_FAILURE, EXTERNAL_SERVICE_FAILURE, PROCESSING_FAILURE, unhandled → `500` | query text w/ user data, connection strings, secrets |
| CRITICAL | security-relevant (auth provider compromise signals) | — |

Every log line includes `request_id` and the stable `code` for
correlation. **No log line ever contains:** tokens, passwords, session ids in
full, private image references, face data, or assistant/user message text
(SAFETY; `AI_INTEGRATION_ARCHITECTURE.md` §8; `SECURITY_PRIVACY_DESIGN.md`).

---

## 8. Mapping summary

| Category | HTTP | `error.code` | Log level |
| --- | --- | --- | --- |
| VALIDATION_ERROR | 422 | `VALIDATION_ERROR` | WARN |
| AUTHENTICATION_ERROR | 401 | `AUTHENTICATION_ERROR` | INFO |
| AUTHORIZATION_ERROR | 403 | `AUTHORIZATION_ERROR` | WARN |
| NOT_FOUND | 404 | `NOT_FOUND` | INFO |
| CONFLICT | 409 | `CONFLICT` | INFO |
| RATE_LIMITED | 429 | `RATE_LIMITED` | INFO |
| AI_FAILURE | 503 (or none if degraded) | `AI_FAILURE` | WARN/ERROR |
| MEDIA_FAILURE | 413/422/503 | `MEDIA_FAILURE` | WARN |
| DATABASE_FAILURE | 500/503 | `DATABASE_FAILURE` | ERROR |
| EXTERNAL_SERVICE_FAILURE | 502/503/402/424 | `EXTERNAL_SERVICE_FAILURE` | ERROR |
| PROCESSING_FAILURE | 500 / run `failed` | `PROCESSING_FAILURE` | ERROR |
| INSUFFICIENT_USER_DATA | 200+needs_data / 422 | `INSUFFICIENT_USER_DATA` | INFO |

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `ERROR_HANDLING.md` — the consistent
error-handling system (taxonomy, propagation model, wire contract, leak
prevention, logging policy). No implementation.

**Skills used:** repository analysis (accepted A3.3/E13.1 + API-28…31,
use-case error vocabulary, action-inventory Part 3, transaction boundaries,
AI integration, security/privacy) — architecture documentation only.

**Files changed:** `docs/backend/ERROR_HANDLING.md` (new).

**Validation run:**
- Every category maps to a real failure source: ACTION_API Part 3 (401/404/
  409/413/422/429/402/424/502/503), TRX-1/5 (media, run completion), AI
  integration (AI_FAILURE + degrade), use-case vocabulary (UC-1…33).
- Consistent with accepted docs: A3.3/E13.1 (typed), API-28…31 (shape,
  single mapper, correlation id), DR-1 (mapping in API only), F-3 (domain
  raises typed errors), API-10 (not-yours → 404).
- The 12 requested category names are used exactly as given (with
  `error.code` values identical to the category names).
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Implemented at migration M2 (typed error contract): `errors.py` mapper,
  exception base classes, taxonomy registry, allow-listed `details`, logging
  config — guided by this document and §9 M2 of the rules doc.
- The two `INSUFFICIENT_USER_DATA` HTTP choices (200+needs_data vs 422) are
  set per use case at implementation; the taxonomy itself is fixed.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation only); open items remain in `BACKEND_ARCHITECTURE_RULES.md`
  §8/§10.

**Assumptions recorded:**
- "Internal exception" = the exception class raised at the source;
  "domain error" = the typed `DomainError` the domain raises (F-3);
  "application error" = the typed wrapper carrying resource context;
  "API response" = the `{error:{...}}` body; "safe client message" = the
  leak-free string Flutter renders; "internal logging" = server-side log line.
- The taxonomy is **frozen once shipped** (additive-only), mirroring the
  F-13 stability principle — clients switch on stable `code` values.
- Flutter is never sent internals; the only client-visible fields are
  `code`, `message`, and allow-listed `details` (ER-0/ER-1).

**Constraints honored:** A3.3/E13.1 (typed error contract), API-28…31
(single mapper, correlation id), DR-1/F-3 (mapping in API, typed domain
errors), the SAFETY rules (no tokens/images/user text in logs or responses),
the UI Change Safety Rule (no Flutter modified), and the Scope rule (this
document only).