# Fansivibe — Public HTTP Error Contract

> **STEP 6 — API CONTRACT DESIGN.** Defines the **public HTTP error contract**
> for Fansivibe in one focused reference: for every application error category
> it fixes the **HTTP status**, the stable machine-readable **`error.code`**,
> the safe client **`message`**, the optional **field errors**, and the
> **`request_id`** correlation, plus the leak-prevention boundary that keeps
> stack traces, SQL, provider secrets, and internal implementation details off
> the wire. It is the focused companion to `ERROR_HANDLING.md` (§4 wire
> contract, §5 taxonomy, §6 ER-0/ER-1/ER-2/ER-3 leak prevention, §7 logging),
> `API_CONTRACT_RULES.md` (§9 the frozen error contract C-5, §4.2 request-id),
> `API_LAYER_ARCHITECTURE.md` (§11 errors API-28…31, §12 status codes API-32),
> and `API_RESPONSE_CONVENTIONS.md` (§5 error format, §12 request IDs) — all of
> which already apply this contract endpoint-by-endpoint.
>
> **Status: contract design only. Nothing is implemented.** No code, no
> `api/errors.py`, no exception classes, no handlers, no Flutter changes. The
> taxonomy remains the accepted **frozen 12-category** set (`ERROR_HANDLING.md`
> §5, `API_CONTRACT_RULES.md` §9.1); this document does **not** rename, remove,
> or add a category — it makes the public contract explicit (status, code, safe
> message, field errors, request ID) and maps the task's requested categories
> onto that frozen set.
>
> **Source of truth:** `ERROR_HANDLING.md` (§4 wire, §5 taxonomy, §6 leak
> prevention, §7 logging), `API_CONTRACT_RULES.md` (§9 C-5, §4.2 request-id),
> `API_LAYER_ARCHITECTURE.md` (§11 API-28…31, §12 API-32), `API_RESPONSE_CONVENTIONS.md`
> (§5 error format, §12 request IDs), `OBSERVABILITY.md` (§4.1 request-id),
> `APPLICATION_USE_CASES.md` (§3.3 error vocabulary), `AUTH_AUTHORIZATION_ARCHITECTURE.md`
> (OW-1, 404-not-403), and the live repo (`backend/app/` — `GET /health` +
> `POST /v1/assistant/chat` only; no typed error exists yet).

---

## 1. Purpose and scope

This document defines the **one public error contract** every Fansivibe
endpoint shares. For each application error category it states, exactly:

1. **HTTP status** — the 4xx/5xx code on the wire.
2. **`error.code`** — the stable machine-readable value clients switch on
   (API-32), drawn only from the frozen 12-category taxonomy.
3. **Safe `message`** — the leak-free client string (ER-2), built only in
   `api/errors.py`.
4. **Optional field errors** — the allow-listed per-field `details` shape
   (`{field, error, allowed?}`), primarily for `422 VALIDATION_ERROR`.
5. **`request_id`** — the correlation id echoed in `details` (mandatory on
   `5xx`, `API-31`), plus the `X-Request-Id` header on every response.

It also fixes **what never appears on the wire** (§9) and the **logging
levels** per category (§10).

**The task's categories are mapped, not renamed (§4).** The task names
`UNAUTHORIZED` / `FORBIDDEN` / `INTERNAL_ERROR`; the frozen taxonomy uses
`AUTHENTICATION_ERROR` / `AUTHORIZATION_ERROR` / `DATABASE_FAILURE` (with
`INTERNAL_ERROR` as the unhandled-`500` catch-all wire code, API-31). The
canonical `error.code` set is unchanged; §4 is the translation table.

**What it does not do:** implement anything, mount endpoints, change a live
contract, rename/retype an `error.code`, extend the 12-category taxonomy, or
invent new `details` keys beyond the allow-list.

### 1.1 Grounding facts (re-verified)

- **One error body, everywhere (C-5, API-28).** Every non-`2xx` response is
  `{ "error": { "code", "message", "details?" } }`. No module invents its own
  shape (`ERROR_HANDLING.md` §4; `API_RESPONSE_CONVENTIONS.md` §5).
- **The taxonomy is frozen (ER-3).** 12 categories, additive-only once shipped
  (F-13-style stability). The client contracts on `error.code`, never on HTTP
  alone (API-32).
- **`api/errors.py` is the single mapper (ER-2/ER-3, DR-1).** Routers raise
  typed exceptions; the domain raises `DomainError` subtypes (F-3, never HTTP);
  only `errors.py` builds the body, the safe message, and the status
  (`ERROR_HANDLING.md` §3).
- **Unhandled exceptions → `500 INTERNAL_ERROR` (API-31).** Generic message +
  `details.request_id` (the `X-Request-Id` echo); full internals only in server
  logs.
- **Leak prevention is structural (ER-0/ER-1).** `details` is allow-list-only;
  stack traces, SQL, provider/model names, prompts, tokens, and user content
  are **never** serialized (§9).
- **Ownership leaks nothing (API-10/15, OW-1).** A foreign or non-existent
  resource → `404 NOT_FOUND`, never `403`; `403 AUTHORIZATION_ERROR` is
  reserved for authenticated-but-disallowed admin paths.
- **Live contract today:** `GET /health` and `POST /v1/assistant/chat` exist
  with **no typed error body** — this contract is the target, not the current
  wire. Nothing is implemented (API-12).

---

## 2. Source of truth and inputs

| Concern | Source |
| --- | --- |
| Wire shape `{error:{code,message,details}}` | `ERROR_HANDLING.md` §4; `API_CONTRACT_RULES.md` §9 (C-5); `API_LAYER_ARCHITECTURE.md` §11 (API-28) |
| The 12-category taxonomy | `ERROR_HANDLING.md` §5; `API_CONTRACT_RULES.md` §9.1; `API_RESPONSE_CONVENTIONS.md` §5.1 |
| Status-code principle | `API_LAYER_ARCHITECTURE.md` §12 (API-32); `ERROR_HANDLING.md` §8 |
| Unhandled → `500 INTERNAL_ERROR` + correlation | `API_LAYER_ARCHITECTURE.md` §11 (API-31); `OBSERVABILITY.md` §4.1 |
| Field-level validation errors | `API_LAYER_ARCHITECTURE.md` §11 (API-30); `ERROR_HANDLING.md` §5.1 |
| Allow-list `details` / never-leak list | `ERROR_HANDLING.md` §6 (ER-0/ER-1); `API_CONTRACT_RULES.md` §14 |
| Safe `message` built in one place | `ERROR_HANDLING.md` §6 (ER-2), §3 |
| Logging policy | `ERROR_HANDLING.md` §7; `OBSERVABILITY.md` §3/§4 |
| Error vocabulary / statuses per use case | `APPLICATION_USE_CASES.md` §3.3; `API_CONTRACT_RULES.md` §12 |
| Ownership (404-not-403) | `AUTH_AUTHORIZATION_ARCHITECTURE.md` (OW-1); `API_LAYER_ARCHITECTURE.md` §5 |
| Live contract (frozen) | `backend/app/main.py`, `backend/app/models/schemas.py` |

---

## 3. The public wire contract

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
| `code` | Stable machine-readable string from the frozen 12-category taxonomy (§5). Clients switch on this, never on HTTP alone (API-32). |
| `message` | Safe client message, human-readable, no internals, no stack traces, no provider names, no paths (ER-2). Built **only** in `api/errors.py`. |
| `details` | Optional, **allow-list only** (ER-1): `request_id`, `run_id`, caller-owned resource ids, field errors `[{field,error,allowed?}]`, `kind`, `missing`, neutral `retry_after`. Never SQL, prompts, stack traces, tokens, provider/model names, or user content (ER-0). |

**Status-code principle (API-32):** `4xx` = caller errors, `5xx` = our/external
failures. The body `code` is stable and primary; HTTP is a second signal. The
HTTP status is **always** consistent with the `code` (no `200` with an error
body except the two documented `INSUFFICIENT_USER_DATA` cases, §5.12).

**Empty is not an error (`ERROR_HANDLING.md` §5.12):** deletes/logout/ack →
`204` no body; empty *derived* results → `200` + `needs_data: true` **or**
`204` per use case. These are not error responses and carry no `error` body.

---

## 4. Task categories → frozen taxonomy (the mapping table)

The task requests 11 categories. The frozen taxonomy keeps 12 codes; three
task names are the familiar HTTP-semantics synonyms of frozen codes, and
`INTERNAL_ERROR` is the unhandled-`500` catch-all wire code that coexists with
the specific `DATABASE_FAILURE` category. **No code is renamed; this table is
the translation.**

| Task category | `error.code` (canonical, frozen) | HTTP | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | `VALIDATION_ERROR` | 422 | same name (API-30) |
| `UNAUTHORIZED` | `AUTHENTICATION_ERROR` | 401 | + `WWW-Authenticate: Bearer` |
| `FORBIDDEN` | `AUTHORIZATION_ERROR` | 403 | authenticated-but-disallowed; never for not-yours (404) |
| `NOT_FOUND` | `NOT_FOUND` | 404 | missing **or** not-yours (OW-1) |
| `CONFLICT` | `CONFLICT` | 409 | `details.kind` |
| `RATE_LIMITED` | `RATE_LIMITED` | 429 | + `Retry-After` |
| `AI_FAILURE` | `AI_FAILURE` | 503 (or none if degraded) | `details.degraded` |
| `MEDIA_FAILURE` | `MEDIA_FAILURE` | 413 / 422 / 503 | `details.kind` |
| `PROCESSING_FAILURE` | `PROCESSING_FAILURE` | 500 (sync) / `status=failed` (poll) | `details.run_id` |
| `EXTERNAL_SERVICE_FAILURE` | `EXTERNAL_SERVICE_FAILURE` | 502 / 503 / 402 / 424 | identity / service / payment |
| `INTERNAL_ERROR` | `DATABASE_FAILURE` (specific) **and** `INTERNAL_ERROR` (unhandled catch-all, API-31) | 500 / 503 | §5.9; `details.request_id` only |

The frozen set also contains a 12th category not in the task's list, kept
because the domain already requires it:

| Task category | `error.code` (canonical, frozen) | HTTP |
| --- | --- | --- |
| (not requested) | `INSUFFICIENT_USER_DATA` | `200`+`needs_data` **or** 422 (§5.12) |

---

## 5. The category contract

For each category: HTTP status, `error.code`, safe message, optional details
(field errors where applicable), request ID, and a wire example. Logging
levels are consolidated in §10.

### 5.1 `VALIDATION_ERROR`

| Attribute | Value |
| --- | --- |
| HTTP status | `422 Unprocessable Entity` |
| `error.code` | `VALIDATION_ERROR` |
| Safe `message` | "Some of the provided values are not valid. Please check your input." |
| Field errors | `details.field_errors` — array of `{field, error, allowed?}` (API-30, §6) |
| `request_id` | header echo; optional in body on 4xx |
| Triggers | malformed body, unknown vocabulary code, past date, `page_size` outside `[1,100]`, unknown sort key, bad UUID, unbounded input (ASSISTANT_API §5) |

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Some of the provided values are not valid. Please check your input.",
    "details": {
      "field_errors": [
        { "field": "color", "error": "unknown value", "allowed": ["black", "navy", "white"] },
        { "field": "event_date", "error": "must not be in the past" }
      ]
    }
  }
}
```

### 5.2 `AUTHENTICATION_ERROR` (task: `UNAUTHORIZED`)

| Attribute | Value |
| --- | --- |
| HTTP status | `401 Unauthorized` |
| `error.code` | `AUTHENTICATION_ERROR` |
| Safe `message` | "Your session has expired or is invalid. Please sign in again." |
| Field errors | none |
| `request_id` | header echo; optional in body on 4xx |
| Headers | `WWW-Authenticate: Bearer` (API-7) |
| Triggers | missing/invalid/expired/revoked token |

```json
{
  "error": {
    "code": "AUTHENTICATION_ERROR",
    "message": "Your session has expired or is invalid. Please sign in again."
  }
}
```

### 5.3 `AUTHORIZATION_ERROR` (task: `FORBIDDEN`)

| Attribute | Value |
| --- | --- |
| HTTP status | `403 Forbidden` |
| `error.code` | `AUTHORIZATION_ERROR` |
| Safe `message` | "You do not have permission to perform this action." |
| Field errors | none |
| `request_id` | header echo; optional in body on 4xx |
| Triggers | authenticated but lacks the required role/scope (admin path). **Not** for foreign resource ids — those are `404` (OW-1, API-10) |

```json
{
  "error": {
    "code": "AUTHORIZATION_ERROR",
    "message": "You do not have permission to perform this action."
  }
}
```

### 5.4 `NOT_FOUND`

| Attribute | Value |
| --- | --- |
| HTTP status | `404 Not Found` |
| `error.code` | `NOT_FOUND` |
| Safe `message` | "The requested item was not found." |
| Field errors | none |
| `request_id` | header echo; optional in body on 4xx |
| Triggers | resource missing **or not-yours** — no existence leak (API-10/15, OW-1); foreign `run_id`/`wardrobe_items.id`/`event_id`/conversation id |

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The requested item was not found."
  }
}
```

### 5.5 `CONFLICT`

| Attribute | Value |
| --- | --- |
| HTTP status | `409 Conflict` |
| `error.code` | `CONFLICT` |
| Safe `message` | "This action conflicts with the current state. Refresh and try again." |
| Field errors | none |
| `request_id` | header echo; optional in body on 4xx |
| `details` | `kind` ∈ `duplicate` \| `version` \| `sync` (ER-1); optional conflicting field name |
| Triggers | duplicate email/item/save, `user_state.version` optimistic-concurrency mismatch, sync conflict, `Idempotency-Key` replay with conflicting payload (API-33…35), account-erasure cancel-first (`AUTH_API.md:388`) |

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "This action conflicts with the current state. Refresh and try again.",
    "details": {
      "kind": "version"
    }
  }
}
```

### 5.6 `RATE_LIMITED`

| Attribute | Value |
| --- | --- |
| HTTP status | `429 Too Many Requests` |
| `error.code` | `RATE_LIMITED` |
| Safe `message` | "Too many attempts. Please wait a moment and try again." |
| Field errors | none |
| `request_id` | header echo; optional in body on 4xx |
| Headers / details | `Retry-After` header + neutral `details.retry_after` (ER-1) |
| Triggers | register/login/feedback throttling (`APPLICATION_USE_CASES.md` §3.3); public chat is a prime target (`ASSISTANT_API.md` §7) |

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many attempts. Please wait a moment and try again.",
    "details": {
      "retry_after": 30
    }
  }
}
```

### 5.7 `AI_FAILURE`

| Attribute | Value |
| --- | --- |
| HTTP status | `503 Service Unavailable` (or **none** if gracefully degraded) |
| `error.code` | `AI_FAILURE` |
| Safe `message` | "The style service is temporarily unavailable. Please try again shortly." |
| Field errors | none |
| `request_id` | `details.request_id` (5xx) |
| `details` | `degraded: true` if the rules fallback served the request (AI is additive; the call may still succeed, `ERROR_HANDLING.md` §5.7) |
| Triggers | provider timeout/`5xx`, malformed structured output, capability error (`AI_INTEGRATION_ARCHITECTURE.md`) |

```json
{
  "error": {
    "code": "AI_FAILURE",
    "message": "The style service is temporarily unavailable. Please try again shortly.",
    "details": {
      "degraded": false
    }
  }
}
```

### 5.8 `MEDIA_FAILURE`

| Attribute | Value |
| --- | --- |
| HTTP status | `413 Payload Too Large` / `422` / `503` per kind (API-38) |
| `error.code` | `MEDIA_FAILURE` |
| Safe `message` | "The image is too large or not a supported format." (`413`/`422`) or "The image could not be processed." (`503`) |
| Field errors | `details.field` for the offending part where applicable |
| `request_id` | `details.request_id` on the `503` (5xx) |
| `details` | `kind` ∈ `invalid` \| `too_large` \| `storage` (ER-1) |
| Triggers | unsupported type, dimension/size limits, blob upload/delete failure (API-16, API-38) |

```json
{
  "error": {
    "code": "MEDIA_FAILURE",
    "message": "The image is too large or not a supported format.",
    "details": {
      "kind": "too_large"
    }
  }
}
```

### 5.9 `DATABASE_FAILURE` + the `INTERNAL_ERROR` catch-all (task: `INTERNAL_ERROR`)

| Attribute | `DATABASE_FAILURE` (specific) | `INTERNAL_ERROR` (unhandled catch-all, API-31) |
| --- | --- | --- |
| HTTP status | `500` (or `503` when the DB is down and the service cannot serve) | `500` |
| `error.code` | `DATABASE_FAILURE` | `INTERNAL_ERROR` |
| Safe `message` | "Something went wrong on our side. Please try again later." | same generic family |
| Field errors | none | none |
| `request_id` | **`details.request_id` required (5xx, API-31)** | **`details.request_id` required (API-31)** |
| `details` | `request_id` only (ER-1) | `request_id` only (ER-1) |
| Triggers | connection error, constraint violation, transaction rollback, migration mismatch | any exception not mapped to a typed category |

```json
{
  "error": {
    "code": "DATABASE_FAILURE",
    "message": "Something went wrong on our side. Please try again later.",
    "details": {
      "request_id": "9c2f4a1e-7b3d-4c8e-9f5a-2d1b6e7a8c0d"
    }
  }
}
```

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Something went wrong on our side. Please try again later.",
    "details": {
      "request_id": "9c2f4a1e-7b3d-4c8e-9f5a-2d1b6e7a8c0d"
    }
  }
}
```

**Rule:** a typed, known database failure maps to `DATABASE_FAILURE`; anything
the mapper does not know becomes `INTERNAL_ERROR` at the FastAPI exception
handler. Both are `5xx`, both carry `details.request_id`, neither ever
serializes SQL, constraint text, connection strings, or a traceback
(`ERROR_HANDLING.md` §5.9; ER-0).

### 5.10 `EXTERNAL_SERVICE_FAILURE`

| Attribute | Value |
| --- | --- |
| HTTP status | `502` (identity provider upstream) / `503` (weather, knowledge, billing store) / `402`+`424` (payment outcome) |
| `error.code` | `EXTERNAL_SERVICE_FAILURE` |
| Safe `message` | "This service is temporarily unavailable. Please try again later." (payment: per `SUBSCRIPTION_API.md` §7) |
| Field errors | none |
| `request_id` | `details.request_id` (5xx) |
| `details` | internal `source` value **stripped before the response** (ER-0); caller-visible details allow-list only |
| Triggers | identity provider unavailable (UC-2, 502), weather/knowledge/billing unavailable (503), payment outcome (402/424, UC-33) |

```json
{
  "error": {
    "code": "EXTERNAL_SERVICE_FAILURE",
    "message": "This service is temporarily unavailable. Please try again later.",
    "details": {
      "request_id": "9c2f4a1e-7b3d-4c8e-9f5a-2d1b6e7a8c0d"
    }
  }
}
```

### 5.11 `PROCESSING_FAILURE`

| Attribute | Value |
| --- | --- |
| HTTP status | `500` (sync generation) **or** async poll → `status=failed` + embedded `error` (API-42) |
| `error.code` | `PROCESSING_FAILURE` |
| Safe `message` | "We couldn't finish this request. Please try again." |
| Field errors | none |
| `request_id` | `details.request_id` (5xx); async run carries it in the run's `error` |
| `details` | `run_id` (the caller-owned async run id, ER-1) |
| Triggers | analysis/generation pipeline failure: rule-engine invariant broken, stage crash, timed-out long job, run transition to `failed` (TRX-5 write-once) |

```json
{
  "error": {
    "code": "PROCESSING_FAILURE",
    "message": "We couldn't finish this request. Please try again.",
    "details": {
      "run_id": "7a2b3c4d-5e6f-4a1b-9c8d-0e1f2a3b4c5d"
    }
  }
}
```

Async form — the `failed` run DTO embeds the **same** error shape (`SCAN_API.md`
§5.5/5.6, API-42):

```json
{
  "run_id": "7a2b3c4d-5e6f-4a1b-9c8d-0e1f2a3b4c5d",
  "run_type": "outfit",
  "status": "failed",
  "error": {
    "code": "PROCESSING_FAILURE",
    "message": "We couldn't finish this request. Please try again.",
    "details": { "request_id": "9c2f4a1e-7b3d-4c8e-9f5a-2d1b6e7a8c0d" }
  }
}
```

### 5.12 `INSUFFICIENT_USER_DATA`

| Attribute | Value |
| --- | --- |
| HTTP status | `200` + `needs_data: true` **or** `422` (decision per use case; `ERROR_HANDLING.md` §5.12) |
| `error.code` | `INSUFFICIENT_USER_DATA` |
| Safe `message` | "We need a bit more from your profile to do this. Add a few items and try again." |
| Field errors | none |
| `request_id` | header echo |
| `details` | `missing` ∈ `wardrobe` \| `face` \| `preferences` (ER-1); optional suggested next action |
| Triggers | a decision cannot be made with available user data (empty wardrobe, no face profile, missing preferences) — distinct from an empty *result* (which is `200`/`204`, not an error) |

```json
{
  "error": {
    "code": "INSUFFICIENT_USER_DATA",
    "message": "We need a bit more from your profile to do this. Add a few items and try again.",
    "details": {
      "missing": "wardrobe"
    }
  }
}
```

---

## 6. Field errors (the `422` detail shape)

For `VALIDATION_ERROR`, `details` carries an array of per-field errors
(API-30, `ERROR_HANDLING.md` §5.1). Each entry:

| Key | Rule |
| --- | --- |
| `field` | the camelCase DTO field name (never a table/column name, ER-0) |
| `error` | a short, fixed reason string (`unknown value`, `required`, `must not be in the past`, `too long`, …) |
| `allowed` | optional — the controlled-vocabulary values that WOULD be accepted (`null`/omitted when not applicable) |

```json
"details": {
  "field_errors": [
    { "field": "color", "error": "unknown value", "allowed": ["black", "navy", "white"] },
    { "field": "event_date", "error": "must not be in the past" }
  ]
}
```

Rules:

- The field names are **DTO keys only** — never ORM rows or SQL columns (C-7).
- Multiple invalid fields are reported **in one response** (no fail-fast on the
  first error).
- Never echoes user content back beyond the field name and the violating value
  *type* (e.g. "unknown value"); raw user text is not echoed
  (`ASSISTANT_API.md` §7).
- The shorthand `details.field` / `details.allowed` used in sibling endpoint
  notes (`ASSISTANT_API.md:567`, `SUBSCRIPTION_API.md:541`) is the
  single-field form of this array; the array is the canonical multi-field
  shape.

---

## 7. Request ID and correlation

- **`X-Request-Id`** is assigned at the API boundary (middleware) on entry and
  **echoed on every response** — success and error alike
  (`OBSERVABILITY.md` §4.1; `API_CONTRACT_RULES.md` §4.2). A client-supplied
  id (bounded format) is used; otherwise the server generates one. Never
  trusted blindly.
- The id is **threaded explicitly application → domain** (DR-1/F-3) and carried
  in **every log line** (§10).
- **On `5xx`, the error body carries `details.request_id`** — the same echo —
  so a user can report an incident without exposing internals (API-31,
  `ERROR_HANDLING.md` §4).
- On `4xx`, `details.request_id` is **optional** (the header echo suffices);
  the category tables above follow this rule.
- **What it is not:** never a user-data carrier, never an auth token, never a
  rate-limit key.

---

## 8. Headers that ride with errors

| Header | On | Value |
| --- | --- | --- |
| `X-Request-Id` | every response | the correlation id (§7) |
| `WWW-Authenticate` | `401` | `Bearer` (API-7, `AUTHENTICATION_ERROR`) |
| `Retry-After` | `429` | seconds (integer) the client should wait (`RATE_LIMITED`) |
| `Idempotency-Key` | request side, not response | required on save/sync/create/webhook (`API_CONTRACT_RULES.md` §11) — not an error header |

---

## 9. Leak prevention — what never reaches the client (ER-0)

The Flutter client receives **only** `code`, `message`, and allow-listed
`details`. **Never** on the wire:

- stack traces, file paths, line numbers
- SQL, query text, schema/table names, constraint text
- provider/vendor names, model names, prompts, raw AI output
- tokens, credentials, full session ids, API keys, connection strings
- internal exception messages or class names
- user content (messages, image bytes, face data, wardrobe snapshots)
- internal `details.source` values from `EXTERNAL_SERVICE_FAILURE` (mapped to a
  neutral value before the response)

**ER-1 (allow-list):** `details` may only contain `request_id`, `run_id`,
caller-owned resource ids, field errors `[{field,error,allowed?}]`, `kind`,
`missing`, and neutral `retry_after`. Anything else is stripped by
`errors.py`.

**ER-2 (double-build):** the safe `message` is built in `errors.py` only; the
domain and application never build client-facing strings.

**ER-3 (one mapper):** no router, use case, or repository builds an error body
or safe message; the taxonomy is frozen (additive-only).

---

## 10. Logging policy per category

| Level | `error.code` | Server-side only (never on the wire) |
| --- | --- | --- |
| INFO | `AUTHENTICATION_ERROR`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `INSUFFICIENT_USER_DATA`, degraded-AI | token id hash (never the token), resource id, `request_id` |
| WARN | `VALIDATION_ERROR`, `AUTHORIZATION_ERROR`, `AI_FAILURE` (degraded), `MEDIA_FAILURE` | field names, violating value type, kind, size/type metadata (never bytes) |
| ERROR | `DATABASE_FAILURE`, `EXTERNAL_SERVICE_FAILURE`, `PROCESSING_FAILURE`, unhandled → `INTERNAL_ERROR` | operation, constraint (if known), stage, provider (log-only), traceback, `request_id` |
| CRITICAL | security-relevant signals (auth-provider compromise) | — |

Every log line carries `request_id` + the stable `code`. **Never logged:** any
token/credential, full session id, private image reference, face data, or
assistant/user message text (`ERROR_HANDLING.md` §7; `OBSERVABILITY.md` §3/§4;
SAFETY).

---

## 11. Validation reference

- **Taxonomy identical** to `ERROR_HANDLING.md` §5 (12 frozen codes),
  `API_CONTRACT_RULES.md` §9.1, `API_RESPONSE_CONVENTIONS.md` §5.1 — no code
  renamed, removed, or added; the task's `UNAUTHORIZED`/`FORBIDDEN`/
  `INTERNAL_ERROR` are mapped onto `AUTHENTICATION_ERROR`/`AUTHORIZATION_ERROR`/
  `DATABASE_FAILURE`(+`INTERNAL_ERROR` catch-all) per the accepted taxonomy.
- **Wire shape identical** to `API_CONTRACT_RULES.md` §9 (C-5),
  `API_LAYER_ARCHITECTURE.md` §11 (API-28), `ERROR_HANDLING.md` §4.
- **Status mapping identical** to `API_LAYER_ARCHITECTURE.md` §12 (API-32) and
  `ERROR_HANDLING.md` §8; `INTERNAL_ERROR` catch-all per API-31.
- **Field errors** per API-30 (`{field, error, allowed?}`), exactly as
  `AUTH_API.md:416` and `ERROR_HANDLING.md` §5.1.
- **Request ID** per `OBSERVABILITY.md` §4.1 and `API_CONTRACT_RULES.md` §4.2
  (API-31); `details.request_id` required on `5xx`.
- **Leak prevention** per ER-0/ER-1/ER-2/ER-3 (`ERROR_HANDLING.md` §6) and
  `API_CONTRACT_RULES.md` §14; ownership 404-not-403 per OW-1.
- Safe `message` strings match `ERROR_HANDLING.md` §5 verbatim; no new wire
  shape, no code, no routers, no Flutter changes.
- Code fences: 16 balanced (`§3` + 15 in §5/§6).

---

## 12. Open decisions

1. **Auth provider (D-AUTH-1)** — until it lands, no endpoint returns
   `AUTHENTICATION_ERROR`/`AUTHORIZATION_ERROR`; the assistant stays
   anonymous (F-5, API-12).
2. **`details.field_errors` key name** — the array is the canonical multi-field
   shape (§6); the exact key is finalized at M2 implementation alongside
   `errors.py`, keeping the allow-list and the single-mapper rule.
3. **`INSUFFICIENT_USER_DATA` HTTP choice** — `200`+`needs_data` vs `422` is
   set per use case at implementation (UC-14/UC-28 → `200`/`204`); the
   taxonomy is fixed.
4. **`X-Request-Id` client-supplied format bound** — length/regex finalized at
   M1 (`OBSERVABILITY.md` §4.1).
5. **Unchanged project-wide opens** — knowledge shape (K9.1), media privacy
   (MS10.3), feedback design (PR-12), User fields, Today'sLookRecord (P1),
   RecommendationHistory (P3), `subscriptions.status` vocabulary.

---

## 13. Report, assumptions, constraints

**What changed (this step):** added `docs/api/API_ERROR_CONTRACT.md` — the
public HTTP error contract: the one wire shape (§3), the task-categories →
frozen-taxonomy mapping (§4), the per-category contract of HTTP status +
`error.code` + safe `message` + field errors + `request_id` for all 12 frozen
categories plus the `INTERNAL_ERROR` catch-all (§5), the `422` field-errors
detail shape (§6), request-ID correlation (§7), associated headers (§8), the
never-on-the-wire leak-prevention list (§9), and the logging policy (§10).
**No implementation; no taxonomy change; no live contract changed.**

**Skills used:** repository analysis (`ERROR_HANDLING.md`, `API_CONTRACT_RULES.md`
§9/§14, `API_LAYER_ARCHITECTURE.md` §11–12, `API_RESPONSE_CONVENTIONS.md`
§5/§12, `OBSERVABILITY.md` §4.1, `APPLICATION_USE_CASES.md` §3.3,
`AUTH_AUTHORIZATION_ARCHITECTURE.md` OW-1, sibling endpoint error references) +
design-doc synthesis — documentation only.

**Files changed:** `docs/api/API_ERROR_CONTRACT.md` (new).

**Validation run:**
- Every category table traces to an accepted source with identical values —
  HTTP status, `error.code`, safe `message`, and `details` allow-list all match
  `ERROR_HANDLING.md` §5/§6, `API_CONTRACT_RULES.md` §9.1/§9.2, and
  `API_RESPONSE_CONVENTIONS.md` §5.1; `INTERNAL_ERROR` matches API-31;
  field errors match API-30.
- The task's 11 categories are all covered and mapped (§4); no code was
  renamed (user-confirmed approach: keep frozen names + mapping table); the
  12th frozen category (`INSUFFICIENT_USER_DATA`) is retained and documented.
- Leak prevention re-stated verbatim from ER-0/ER-1 (§9) — no stack traces, no
  SQL, no provider secrets, no internal implementation details on the wire.
- 16 code fences balanced; `git status --short`: docs/api/ holds the 14
  untracked API docs (API_ERROR_CONTRACT.md added) + modified
  `CURRENT_STATE.md`; no code, directories, or files created.

**Remaining:** STEP 6 design continues. The remaining feature-module contracts
and the media/outfits surface must apply this error contract (the frozen
`error.code` set, allow-listed `details`, `details.request_id` on `5xx`,
`{field,error,allowed?}` field errors) with no new category or wire shape.
Open decisions in §12.
