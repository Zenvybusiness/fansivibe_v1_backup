# Fansivibe — API Contract: Authentication & Account Identity

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> authentication and account identity** — the operations that create, prove,
> read, and destroy a Fansivibe account. It is the focused companion to
> `API_CONTRACT_RULES.md` (§12 catalog + §13.1/§13.2 P0 sketches) and
> `API_INVENTORY.md` (§5.2 auth / §5.3 users / §6.4 erasure): it fixes the
> wire shapes, validation, and security posture of the auth surface only.
>
> **Status: contract design only. Authentication is NOT implemented.** No
> auth code, no `deps.py`, no provider adapter, no session store, no
> endpoints, no SQL, no Flutter changes, no dependencies. The live contract
> (`GET /health`, `POST /v1/assistant/chat`) is preserved unchanged; the
> assistant stays unauthenticated until the auth decision lands (F-5).
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> STEP 2 `ACTION_API_INVENTORY.md` (actions 1, 2, 3, 29, 28, 31), STEP 3
> `FANSIVIBE_DOMAIN_MODEL_V1.md` (E1 `User`, E1.1 `UserState`), STEP 4
> `TABLE_DEFINITIONS.md` (`users`, `user_state`), `TRANSACTION_BOUNDARIES.md`
> (TRX-8 erasure), `SECURITY_PRIVACY_DESIGN.md` (§2 ownership, §5 erasure,
> MS10.3), STEP 5 `AUTH_AUTHORIZATION_ARCHITECTURE.md` (D-AUTH-1 seam,
> OW-1, 404-not-403), `APPLICATION_USE_CASES.md` (UC-1…UC-4, UC-6),
> `ERROR_HANDLING.md` (12-category taxonomy), and STEP 6
> `API_CONTRACT_RULES.md` (canonical catalog) + `API_INVENTORY.md`.

---

## 1. Purpose and scope

This document defines, for every **required** authentication / account-identity
operation, the eight contract attributes the STEP 6 design task asks for:

1. **method**
2. **path**
3. **request schema**
4. **response schema**
5. **authentication requirements**
6. **validation**
7. **errors**
8. **security considerations**

It also **selects the operation set**: of the candidate operations (sign in,
sign up, refresh session, sign out, current user, account deletion), only
those the actual Fansivibe product and the accepted inventory support are
defined here. Nothing is invented beyond the feature/data inventory.

**What it does not do:** implement authentication, add the auth provider,
create the session store, write schemas or routers, modify Flutter, or change
the live assistant contract. The auth module (M1) is P0 but **waits on the
provider decision D-AUTH-1**; this doc fixes the contract and seams so the
adapter is replaceable.

### 1.1 Grounding facts (re-verified)

- The backend today has **no auth at all**: the only live endpoint is
  unauthenticated `POST /v1/assistant/chat` (+ `GET /health`);
  `backend/app/main.py` has no auth dependency.
- The Flutter app has no real sign-in yet: registration navigates straight
  home, and the profile "Sign out" menu item (`profile_screen.dart:134`) only
  shows a snackbar — there is no token, no session, no account API call.
- The `users` table is **designed-for** auth: `auth_provider` +
  `auth_subject` (opaque external-boundary identity, `UNIQUE
  (auth_provider, auth_subject)`), `display_name`, timestamps — **no email or
  password columns** (TABLE_DEFINITIONS §4.1; the auth pair IS the stored
  identity).
- **Backend never stores passwords or refresh secrets** — identity is
  delegated to an external provider behind the `verify_access_token ->
  Principal` seam (AUTH_AUTHORIZATION §4.1, decision **D-AUTH-1**).
- Sessions live in the **R51 session/token store** (non-DB, out of the 23
  tables) — a `user_auth_tokens` row per device/session for revocation.
- Account erasure is a **complete right to erasure**: one `DELETE users`
  cascades across all 12 user-owned children + async blob cleanup of
  `users/{user_id}/...` + external subscription cancellation (TRX-8).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `API_CONTRACT_RULES.md` | Canonical catalog §12 (method/path/auth/UC/errors), §13.1 auth DTO sketches, §5 Bearer/authz, §9 error contract. |
| `API_INVENTORY.md` | Endpoints 02–05 (§5.2 auth), 06–10 (§5.3 users), §6.4 erasure note. |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` | D-AUTH-1 seam, token validation, current-user resolution (`deps.py`), OW-1, 404-not-403. |
| `APPLICATION_USE_CASES.md` | UC-1 `RegisterAccount`, UC-2 `SocialSignIn`, UC-3 `SignIn`, UC-4 `SignOut`, UC-6 `GetProfile`. |
| `TABLE_DEFINITIONS.md` | `users` (auth pair, `display_name` CHECK 1..100), `user_state` (ProfileView fields). |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401 + `WWW-Authenticate`), AUTHORIZATION_ERROR (403), NOT_FOUND (404), CONFLICT (409), RATE_LIMITED (429 + `Retry-After`), EXTERNAL_SERVICE_FAILURE (502/503). |
| `SECURITY_PRIVACY_DESIGN.md` / `TRANSACTION_BOUNDARIES.md` | Ownership boundary (PR-10), erasure TRX-8, token/email never-logged, MS10.3. |
| `OBSERVABILITY.md` | Never-logged boundary ER-4 (auth tokens, credentials). |

---

## 3. Operation selection (define only the required operations)

The six candidate operations were each evaluated against the product
requirements and the accepted inventory. **Six are required (one gated) and
defined in §5; one is deliberately NOT defined today.**

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| O-1 | **Sign up** | **Required** — `POST /v1/auth/register` | UC-1, action 1, AccountCreationScreen; P0 (M1). |
| O-2 | **Sign in (social)** | **Required** — `POST /v1/auth/social` | UC-2, action 2; upsert covers both sign-in and sign-up for Google/Apple. |
| O-3 | **Sign in (email/password)** | **Required** — `POST /v1/auth/login` | UC-3, action 3, EntryScreen; P0 (M1). |
| O-4 | **Sign out** | **Required** — `POST /v1/auth/logout` | UC-4, action 29 (profile menu "Sign out"); P0 (M1). |
| O-5 | **Current user (account identity)** | **Required** — `GET /v1/users/me` | UC-6, action 28 read; resolves the session back to the account at app start / session restore. M2 owns the module; identity semantics live in this contract. |
| O-6 | **Account deletion** | **Required (documented, gated)** — `DELETE /v1/users/me` | Erasure is a product/legal requirement (TRX-8); the API exposes **only the user's own path**. Not in the Flutter contract today; **NOT mounted** until the erasure pipeline lands (see §5.6). |
| — | **Refresh session** | **NOT required now** | See §3.1. |

### 3.1 Why refresh session is not required today

The backend never stores refresh secrets and the provider is an open seam
(D-AUTH-1). Today's product keeps the session on-device and re-authenticates
via `POST /v1/auth/login` when the access token expires; there is no session
table, no refresh-token state, and no provider contract that would define a
refresh flow. Per the contract's **additive-only** rule (API-2) no placeholder
endpoint is reserved or created.

**When it would become required:** only if D-AUTH-1 lands a provider with
short-lived access tokens + refresh tokens (then the R51 session store or the
provider validates the refresh token, and `POST /v1/auth/refresh` is added
as a normal additive endpoint with its own §5 entry). Until that decision, a
refresh endpoint is an **invented API** and is excluded — recorded as an open
decision (§8).

---

## 4. Shared auth semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19).
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- `POST /v1/auth/register` requires `Idempotency-Key` (C-12, API-33): a
  network retry must not create a second account.
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1).

### 4.2 Tokens

| Property | Contract |
| --- | --- |
| **What is issued** | `accessToken` — one per device/session, recorded in the R51 session store for revocation. |
| **Format** | Provider-dependent (JWT or opaque), **decided at D-AUTH-1**; not frozen here (API_CONTRACT_RULES §13.1 note). |
| **Claims** | Resolved by `api/deps.py` to a **principal** → `user_id` (UUID) only. Domain never sees email/name/tokens (F-3, DR-1). |
| **Expiry** | `expiresIn` seconds returned with the token; expiry enforced on every protected call. |
| **Revocation** | `POST /v1/auth/logout` revokes the caller's session; logout-all is an R51 server-side capability, **not** an endpoint. |
| **Storage** | The backend keeps **no password or refresh secret** (AUTH_AUTHORIZATION §4.1). Device-side storage is the client's secure-store concern. |

### 4.3 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): for auth, field names + allowed values
(422), kind (`duplicate`/`version`/`sync`/`account_linking`, 409),
`retry_after` (429). **Never** tokens, passwords, provider internals, or
provider/model names (C-7/C-8, ER-0).

### 4.4 Public vs auth

| Requirement | Endpoints |
| --- | --- |
| **Public** (no token; returns a token) | `POST /v1/auth/register`, `POST /v1/auth/social`, `POST /v1/auth/login` (API-7). |
| **Auth** (Bearer → `user_id`) | `POST /v1/auth/logout`, `GET /v1/users/me`, `DELETE /v1/users/me`. |

Authorization on user-data endpoints is **owner-only (OW-1)** with
**404-not-403** (API-10); 403 is reserved for authenticated-but-disallowed
(never used in this surface — no admin paths here).

---

## 5. Operation contracts

### 5.1 O-1 — Sign up (`RegisterAccount`, UC-1)

- **Method / path:** `POST /v1/auth/register`
- **Request schema** (`application/json`; `Idempotency-Key` **required**):

```
{
  "email":       "alex@example.com",   // string, required, normalized lowercase
  "password":    "…",                  // string, required, 8..128 chars, never persisted
  "displayName": "Alex",               // string, optional, 1..100 chars
}
```

- **Response schema** — `201 Created` (bare, no envelope, API-17):

```
{
  "accessToken": "…",                  // issued session token (D-AUTH-1 format)
  "tokenType":   "bearer",
  "expiresIn":   3600,                 // seconds (provider/config-driven)
  "profile": {
    "displayName": "Alex",
    "styleProfile": {},                // empty at registration
    "preferences":  {},                // empty at registration
    "settings":     {},                // defaults
    "flags":        {},                // defaults
    "version":      0
  }
}
```

- **Authentication requirements:** public — no token accepted; a new session
  is issued on success.
- **Validation:**
  - `email` — RFC-valid, normalized to lowercase, ≤ 254 chars; uniqueness is
    the email-as-provider-subject → duplicate → **409**.
  - `password` — length 8–128 with at least one letter and one digit
    (config-driven policy, finalized at D-AUTH-1); **never stored** by the
    backend (identity provider hashes it).
  - `displayName` — trimmed, 1–100 chars (BC-9).
  - Unknown/absent required fields → **422** with `details` field errors.
- **Errors:** `201`; `409 CONFLICT` (`details.kind="duplicate"`, email taken);
  `422 VALIDATION_ERROR` (field errors + allowed values); `429 RATE_LIMITED`
  (+ `Retry-After`).
- **Security considerations:**
  - Idempotency: a retried request with the same `Idempotency-Key` returns
    the **same account** (never a duplicate); retries must not create accounts.
  - Rate limit per IP **and** per email (credential-stuffing / enumeration
    control). The `409` for a taken email is the accepted contract; the
    enumeration concern is mitigated by rate limits and the uniform **401 on
    login** (see O-3).
  - Password, full email, and token **never logged** (ER-4); only the
    normalized email is a loggable field name, and even then minimize.
  - The returned `profile` is the caller's own minimal state; no appearance
    data exists yet at this point.

---

### 5.2 O-2 — Sign in via social provider (`SocialSignIn`, UC-2)

- **Method / path:** `POST /v1/auth/social`
- **Request schema:**

```
{
  "provider":      "google" | "apple",  // string, required, allow-list
  "providerToken": "…"                  // string, required, OIDC/Apple identity token
}
```

- **Response schema:** `AuthResponse` (identical shape to §5.1) — `200 OK`
  for an **existing** account, `201 Created` for a **new** account created by
  the upsert.
- **Authentication requirements:** public — the app has no Fansivibe token
  yet; the **provider token** is exchanged server-side. No app Bearer token
  is accepted on input.
- **Validation:**
  - `provider` ∈ {`google`, `apple`} (controlled allow-list; else **422**
    with allowed values).
  - `providerToken` non-empty; verified by the `IdentityProvider` adapter:
    invalid / expired / wrong audience → **401**.
  - Uniqueness enforced by `UNIQUE (auth_provider, auth_subject)` on `users`
    (BC-1): the same provider subject always maps to the same account.
- **Errors:** `200` / `201`; `401 AUTHENTICATION_ERROR` (invalid/expired
  provider token); `409 CONFLICT` (`details.kind="account_linking"` — provider
  subject already bound to a different local identity; linking is an explicit
  user-confirmed flow, never automatic); `422 VALIDATION_ERROR`;
  `429 RATE_LIMITED`; `502 EXTERNAL_SERVICE_FAILURE` (provider unreachable).
- **Security considerations:**
  - The provider token is exchanged and **discarded** — never stored, never
    logged, never echoed.
  - The app learns only the issued `accessToken`; it never sees the
    provider's own access/refresh tokens.
  - Account-linking conflicts return **409**, not auto-merge, and never leak
    whether the linked account belongs to the caller.
  - No 404 path: a failed exchange is always **401/409**, never an existence
    oracle.

---

### 5.3 O-3 — Sign in (`SignIn`, UC-3)

- **Method / path:** `POST /v1/auth/login`
- **Request schema:**

```
{
  "email":    "alex@example.com",   // string, required
  "password": "…",                  // string, required
}
```

- **Response schema:** `AuthResponse` — `200 OK`. The `profile` field also
  serves **device restore** (UC-3: the last stored profile snapshot comes back
  with the session so a re-install or new device can rehydrate).
- **Authentication requirements:** public — credentials are exchanged for a
  session; no token on input.
- **Validation:**
  - `email` normalized lowercase (same rules as §5.1); `password` non-empty.
  - Credentials verified by the `IdentityProvider` (hashing is provider-side;
    the backend has no password column — §1.1).
- **Errors:** `200`; `401 AUTHENTICATION_ERROR` (wrong credentials —
  **recommended** uniform response, see below); `404 NOT_FOUND` (per UC-3 /
  inventory §5.2; kept for contract consistency); `422 VALIDATION_ERROR`
  (format); `429 RATE_LIMITED` (+ `Retry-After`).
- **Security considerations:**
  - **Account-enumeration control:** the preferred behavior is a uniform
    `401` for both "no such account" and "wrong password". The `404` entry is
    inherited from UC-3 and must be avoided at implementation unless a
    product reason overrides it.
  - Rate limit per IP **and** per account with backoff; credentials never
    logged; token never logged (ER-4).
  - Session is per-device (R51); login on a new device creates a new session
    without invalidating others (device list is a profile-side concern, P1).

---

### 5.4 O-4 — Sign out (`SignOut`, UC-4)

- **Method / path:** `POST /v1/auth/logout`
- **Request schema:** none — the session is identified by the
  `Authorization: Bearer <token>` header. No body.
- **Response schema:** `204 No Content` (empty body).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — revokes the caller's own session only (OW-1).
- **Validation:** the presented token must resolve; revocation is
  **idempotent** — revoking an already-revoked/expired session is still a
  clean `401` (the client treats its local logout as complete regardless).
- **Errors:** `204`; `401 AUTHENTICATION_ERROR` (missing/expired/revoked —
  idempotent).
- **Security considerations:**
  - Revocation happens in the **R51 session store**; a revoked token is
    rejected on every subsequent call (not just client-side deletion).
  - The token is never logged; only a token-id hash on the revocation event
    (ERROR_HANDLING §5.2).
  - Logout-all is an R51 server-side capability documented but **not exposed**
    as an endpoint; the client calls this endpoint once per active device.
  - After `204`, the client deletes its local credentials/secure-store entry.

---

### 5.5 O-5 — Current user (`GetProfile`, UC-6)

- **Method / path:** `GET /v1/users/me`
- **Request schema:** none (no query params).
- **Response schema:** `200 OK` — `ProfileView` (bare, no envelope):

```
{
  "displayName": "Alex",
  "styleProfile": { /* faceShape?, skinTone?, bodyType?, styleType?, sourceRunId? */ },
  "preferences":  { /* sparse vocab-id lists */ },
  "settings":     { /* sparse, controlled keys */ },
  "flags":        { /* derived flags */ },
  "version":      3
}
```

- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — the response is always the caller's own identity (OW-1).
- **Validation:** none beyond token resolution. If the token is valid but the
  account no longer exists (deleted elsewhere), the server returns `404` and
  the client must sign out locally.
- **Errors:** `200`; `401 AUTHENTICATION_ERROR`; `404 NOT_FOUND` (token valid
  but account gone).
- **Security considerations:**
  - Purpose: the canonical "who am I" read — app start / session restore,
    identity resolution, and (with O-1/O-3) the profile that backs the
    returned session.
  - `styleProfile` is **CRITICAL-sensitivity** appearance data
    (SECURITY_PRIVACY_DESIGN §3): HTTPS only, owner-only, never cached on
    shared storage, never in logs (ER-4, MS10.3).
  - No existence leak: this endpoint never exposes another user's identity;
    the 404 path only ever refers to the caller's own (now-absent) account.

---

### 5.6 O-6 — Account deletion (erasure, TRX-8)

- **Method / path:** `DELETE /v1/users/me`
- **Request schema:** none (empty body). `Idempotency-Key` is accepted so a
  retried deletion is safe; confirmation is the product/UI layer's job (the
  token must be freshly valid, so an expired session forces re-auth before
  deletion).
- **Response schema:** `204 No Content` — the account is gone.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — deletes only the caller's own account (OW-1). A user can never delete
  another account (404-not-403).
- **Validation:** the token must resolve to a live account; an active
  subscription is a hard precondition (see errors).
- **Errors:** `204`; `401 AUTHENTICATION_ERROR` (expired session → re-auth
  required); `404 NOT_FOUND` (already deleted — idempotent); `409 CONFLICT`
  (active subscription must be cancelled first — external entitlement, R51);
  `429 RATE_LIMITED`.
- **Security considerations / behavior:**
  - **Erasure semantics (TRX-8):** one `DELETE users` cascades across all 12
    user-owned children (incl. AI history), async blob cleanup of every
    `users/{user_id}/...` object, and external subscription cancellation /
    notification (R51). No soft-delete, no resurrection
    (RELATIONSHIP_CONSTRAINTS §3.2).
  - **Status — documented but NOT mounted.** This is the "user's own path"
    for erasure called out in `API_INVENTORY.md` §6.4. It is **not** in the
    Flutter contract today and ships only when the erasure pipeline (MS10.3
    gate, blob sweep, external cancellation) exists. Until then the route does
    **not** exist and returns **no fake 200** (API-12 — same convention as
    sealed modules M11/M16).
  - Erasure of CRITICAL appearance data is access-logged
    (SECURITY_PRIVACY_DESIGN §6.2); tokens are never logged (ER-4).

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `email` | RFC-valid, normalized lowercase, ≤ 254 chars | D-AUTH-1 config |
| `password` | 8–128 chars, ≥ 1 letter + ≥ 1 digit; provider-hashed, never stored | D-AUTH-1 config |
| `displayName` | trimmed, 1–100 chars | `users` CHECK BC-9 |
| `provider` | ∈ {`google`, `apple`} | controlled allow-list (API-14) |
| `providerToken` | non-empty, provider-verified | `IdentityProvider` adapter |
| Field errors | `422` + `details: [{field, error, allowed?}]` | API-30, ERROR_HANDLING §5.1 |

All validation is **server-side** (Flutter never enforces security) and
returns the **safe client message** from the error contract, never internal
details (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | malformed email/password/displayName/provider | field errors in `details` |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token; wrong credentials; invalid provider token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | login (UC-3), `/users/me` when account gone, deletion of absent account | 404-not-403; never an existence oracle on another user |
| `CONFLICT` | 409 | email taken (register), account-linking (social), active subscription (delete) | `details.kind` |
| `RATE_LIMITED` | 429 | register/login/social/delete | + `Retry-After` |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | identity provider unreachable | 502 on the social exchange (per inventory §5.2) |
| `AUTHORIZATION_ERROR` | 403 | **not used** in this surface | reserved for admin paths elsewhere |

---

## 8. Open decisions (carried forward, unchanged)

1. **D-AUTH-1 — auth provider** — email/password vs social OAuth, token
   format (JWT vs opaque session), token lifetime. Determines the
   `AuthResponse` **claims** (not the wire shape) and the password policy
   values in §6.
2. **Refresh session** — added only if/when D-AUTH-1 introduces short-lived
   access tokens + refresh tokens (§3.1). Explicitly **not** designed now to
   avoid inventing an API.
3. **User fields / profile view contents** — the `ProfileView` shape above
   matches the current sketch and evolves additively (API-2).
4. **Account deletion gating** — erasure ships when the MS10.3 gate and the
   external-cancellation pipeline land (§5.6).
5. All other open decisions from `API_CONTRACT_RULES.md` §16 remain open and
   are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/AUTH_API.md` — the field-level
API contract for authentication and account identity: 6 required operations
(sign up, social sign-in, sign in, sign out, current user, account deletion)
each with method/path/request/response/auth/validation/errors/security, plus
the documented exclusion of a refresh-session endpoint. Authentication is
**not** implemented.

**Skills used:** repository + documentation analysis (ACTION_API actions
1/2/3/29/28/31, domain E1/E1.1, `TABLE_DEFINITIONS` `users`/`user_state`,
TRX-8 erasure, D-AUTH-1 seam, UC-1…4/6, ERROR_HANDLING 12-category taxonomy,
API_INVENTORY §5.2/§5.3/§6.4, live `profile_screen.dart` sign-out stub) —
documentation only.

**Files changed:** `docs/api/AUTH_API.md` (new); `CURRENT_STATE.md` (status).

**Validation run:**
- **Every defined operation traces to the accepted inventory** — O-1→UC-1 /
  endpoint 02, O-2→UC-2 / 03, O-3→UC-3 / 04, O-4→UC-4 / 05, O-5→UC-6 / 06,
  O-6→TRX-8 erasure (§6.4 "user's own path"). No invented endpoints: refresh
  session is explicitly excluded (§3.1), account deletion is documented but
  NOT mounted (API-12), and paths/methods/auth/UC/errors are identical to
  `API_CONTRACT_RULES.md` §12 and `API_INVENTORY.md` §5.2/§5.3.
- **Wire shapes match the P0 sketches** — `AuthResponse`,
  `RegisterRequest`, `LoginRequest`, `SocialSignIn`, `ProfileView` identical
  to `API_CONTRACT_RULES.md` §13.1/§13.2; no field removed, renamed, or
  retyped (API-2). Error `code` values are the frozen 12-category taxonomy
  from `ERROR_HANDLING.md`; 401 + `WWW-Authenticate`, 429 + `Retry-After`.
- **Auth/authorization consistent** — public list (register/social/login) and
  auth list (logout/users-me) match API-7; OW-1 owner-scoping + 404-not-403
  on every user-data read; F-3 (identity = `user_id` only); no admin paths.
- **Security posture grounded** — no password/refresh-secret storage
  (AUTH_AUTHORIZATION §4.1), never-logged boundary ER-4, CRITICAL appearance
  data owner-only (MS10.3), erasure TRX-8 semantics, account-enumeration
  note on login.
- **`git status --short`:** only `docs/api/AUTH_API.md` (untracked) +
  `CURRENT_STATE.md`; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- D-AUTH-1 (provider, token format, lifetime) is still open and gates the
  auth module; this contract fixes the seams so the adapter is replaceable.
- Refresh-session stays excluded until D-AUTH-1 (§3.1); the login `404`
  (UC-3) should be collapsed to a uniform `401` at implementation.
- Field-level DTOs for the auth module are first implemented at M4 with
  `deps.py` + UC-1…UC-4 (per `API_CONTRACT_RULES.md` §17).
- Other open decisions unchanged: User fields, Today'sLookRecord (P1),
  RecommendationHistory (P3), conversation retention, K9.1 knowledge shape,
  media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- Identity for domain logic is always the `user_id`; the backend never stores
  passwords or refresh secrets (delegated identity, D-AUTH-1).
- The session/token store is R51 (non-DB); account erasure is full CASCADE +
  async blob cleanup + external cancellation (TRX-8).
- Public/auth and owner-only scoping follow API-7/API-10 unchanged.

**Constraints honored:** no implementation (auth NOT created), the live
assistant contract untouched (F-5), no invented APIs (refresh excluded;
erasure is the inventory's own "user's own path"), scope limited to
`docs/api/AUTH_API.md` + `CURRENT_STATE.md`.
