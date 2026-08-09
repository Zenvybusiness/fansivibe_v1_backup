# Fansivibe — Authentication & Authorization Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines **authentication and
> authorization boundaries** for Fansivibe: authentication provider, access
> token validation, user identity, current-user resolution, authorization,
> resource ownership, and admin/system access.
>
> **Every user-owned resource is scoped to the authenticated user.** The
> resource examples (Wardrobe, Scans, Photos, Recommendations, Saved Looks,
> Feedback, Events, Assistant Conversations) are all mapped in §5.
>
> **Status: architecture design only. Authentication is NOT implemented.**
> No code, tables, dependencies, or endpoints are created. The live assistant
> contract (`POST /v1/assistant/chat`) is unchanged — it stays unauthenticated
> until the auth decision lands (this is called out explicitly in §6 and
> `BACKEND_ARCHITECTURE_RULES.md` §8).

---

## 1. Purpose and scope

This document specifies the **auth boundary** for the real Fansivibe
backend: how a request becomes an authenticated **user identity**, how that
identity is enforced on **every user-owned resource**, and how
**admin/system access** is distinguished from user access.

It covers:

1. **Authentication provider** — who issues identities/tokens.
2. **Access token validation** — how the backend trusts a token.
3. **User identity** — what the identity is (id, and only id for domain logic).
4. **Current-user resolution** — `deps.py` → `user_id`, per-request.
5. **Authorization** — who may do what (owner-only 404-not-403; admin scope).
6. **Resource ownership** — the invariant that every user-owned row is
   `user_id`-scoped and filtered through the authenticated user.
7. **Admin/system access** — machine-to-machine path, separate from users.

**Status:** the auth module (**M1**) is a **P0** module but its **exact
provider is an open decision** (user fields/auth, `BACKEND_ARCHITECTURE_RULES.md`
§8/§10). This doc therefore defines the **contract and boundaries** — the
seams and invariants — and marks the provider-specific parts as decisions.

**Grounding rules from accepted docs:**
- **API-9/10 (`API_LAYER_ARCHITECTURE.md`):** Bearer auth via
  `api/deps.py` → `user_id`; **404-not-403** scoping (an authenticated user
  must not learn that another user's resource exists).
- **F-3/DR-1:** auth context is **infrastructure**, never in domain logic;
  domain gets a `user_id` only.
- **MODULE_MAP M1:** auth = P0 module; `infrastructure/auth` adapter,
  `api/deps.py`, `SECURITY_PRIVACY_DESIGN.md` (MS10.3) governs user data.
- **ERROR_HANDLING.md:** `AUTHENTICATION_ERROR` (401 + `WWW-Authenticate`),
  `AUTHORIZATION_ERROR` (403); allow-listed messages, no token/secret logs.
- **APPLICATION_USE_CASES.md:** UC-1 (create user), UC-2 (sign in) are P0;
  all other UC-3…33 assume an authenticated `user_id`.
- **PR rules (`DATABASE_DESIGN_RULES.md`):** every user-owned table carries
  `user_id` (FK) + per-user indexes; no cross-user writes.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app/main.py` | Confirms live assistant endpoint is currently unauthenticated. |
| `API_LAYER_ARCHITECTURE.md` | API-9/10 (Bearer, deps.py→user_id, 404-not-403), API-5/6 (error codes). |
| `BACKEND_MODULE_MAP.md` | M1 auth module (P0), M2 users (P0); module boundaries. |
| `ERROR_HANDLING.md` | AUTHENTICATION_ERROR/AUTHORIZATION_ERROR semantics. |
| `APPLICATION_USE_CASES.md` | UC-1/2 (identity lifecycle) — P0, not implemented. |
| `SECURITY_PRIVACY_DESIGN.md` | MS10.3 (erasure, privacy), token handling rules. |
| `DATABASE_DESIGN_RULES.md` | PR-4/5 (user_id FK, per-user indexes). |
| `DECISIONS.md` / rules §8 | "User fields/auth" is an open decision — provider unspecified. |

---

## 3. Definitions

| Term | Definition |
| --- | --- |
| **Authenticated user** | The `user_id` established for a request via a valid access token. |
| **Principal** | What a token asserts: a `user_id` (user principal) or a `system_principal` (service principal). |
| **Resource owner** | The `user_id` recorded on the resource row; resource belongs to that user only. |
| **Scope** | The authorization dimension: `user` (own resources only) or `admin`/`system` (bounded elevated paths). |
| **Identity** | For domain logic: **only the `user_id`** (UUID). No email/name flows into domain (F-3). |

---

## 4. Auth architecture

### 4.1 Authentication provider

- Fansivibe **outsources identity** to an external provider (delegated
  authentication — e.g. email/password or social OAuth) — **decision D-AUTH-1**
  (provider identity is open; the seam is fixed here).
- The backend **never stores passwords or refresh secrets**. It stores only:
  `users.user_id`, provider subject (`provider_sub`), and a **user auth token**
  (`user_auth_tokens`) row per device/session.
- The **seam**: `infrastructure/auth/` provides
  `verify_access_token(token) -> Principal`; the concrete provider is an
  adapter behind it (composable, replaceable — no provider in domain).
- **AI-0-style honesty:** this doc defines the contract; the concrete
  provider adapter is **not implemented** until D-AUTH-1 lands.

### 4.2 Access token validation

- Every protected endpoint requires `Authorization: Bearer <token>`.
- Validation (in `api/deps.py`, via the auth adapter):
  1. **Signature/format** — reject malformed/expired tokens → 401
     `AUTHENTICATION_ERROR` + `WWW-Authenticate: Bearer`.
  2. **Revocation** — consult the session store (revoked tokens → 401).
  3. **Expiry/audience** — token must be within its `exp`, correct `aud`.
- Validation result is a **principal** (`user_id`), nothing more. No user
  profile data is loaded at this stage (that's the user module's job).
- **No secrets are logged** (ERROR_HANDLING ER-2; token values never logged).

### 4.3 User identity

- The canonical identity is `users.user_id` (UUID). It is:
  - the **only** identity passed into domain logic (F-3/DR-1);
  - the FK on every user-owned table (PR-4);
  - never derivable from the token alone beyond what the provider asserts —
  the backend maps provider subject → internal `user_id` on first sign-in
  (UC-1/UC-2).
- **User profile** (name, email, avatar) lives in the **users module (M2)**
  and is accessed through its public contract — never smuggled through the
  auth boundary.

### 4.4 Current-user resolution

- `api/deps.py` exposes `get_current_user_id` (FastAPI dependency) that runs
  token validation and returns `user_id`.
- Every user-owned endpoint **declares this dependency**; the resolved
  `user_id` is threaded through application → domain (DR-1).
- **Resolution is per-request; there is no global/singleton user.**
- Where the endpoint may be called without a user (only the assistant until
  D-AUTH-1, and health), `user_id` is `None` and the call path must not touch
  user-owned resources.

### 4.5 Authorization

Authorization is **two layers**:

| Layer | Decision | Mechanism |
| --- | --- | --- |
| **Identity/scope** | Is the caller authenticated + allowed the scope? | `get_current_user_id` (401/403), admin dependency for admin endpoints. |
| **Resource ownership** | Does the requested resource belong to the caller? | **Every query filters by `user_id`** — the "404-not-403" rule. |

- **Owner-only access, enforced at the query:** a user requests
  `GET /v1/wardrobe/items/{item_id}`; the query is
  `WHERE id = :id AND user_id = :uid` (API-10). Missing row → **404**
  `NOT_FOUND` (never 403, never reveals existence of another user's data).
- **403 `AUTHORIZATION_ERROR`** is reserved for **authenticated but
  disallowed** cases: a user calling an **admin** endpoint, or crossing a
  scope boundary. 401 is reserved for **unauthenticated**.
- **Authorization is enforced in application/domain, never only in the UI**
  (Flutter never enforces security).

### 4.6 Resource ownership

**Invariant OW-1:** every user-owned resource is created, read, updated, and
deleted **strictly under the authenticated user's `user_id`** — on insert
(the `user_id` is always set from the authenticated principal, never from
client input), on query (always filtered), on write (upsert/update/delete
guarded by `user_id`), and on cascade (children inherit the parent's owner).

| Resource | Owner column | Scoped by |
| --- | --- | --- |
| Wardrobe (items) | `wardrobe_items.user_id` | owner filter on every item query |
| Scans (analysis) | `analysis_runs.user_id` | run_id queries always include `user_id` |
| Photos (media) | `media.user_id` (M16/MS10.3) | every media GET/update filtered |
| Recommendations | `recommendations.user_id` (P3) | owner filter |
| Saved Looks | `saved_looks.user_id` | owner filter |
| Feedback | `feedback.user_id` | owner filter; read-back only by owner (or admin anon) |
| Events | `events.user_id` | owner filter |
| Assistant Conversations | `conversations.user_id` (M4) | assistant DTOs carry no user data (A3.1) but conversation storage is per-user |

**Child/parent chains** inherit ownership: analysis sections, media tasks,
recommendation items are always read/written through the parent's owner
check — no child endpoint ever accepts a raw foreign id without the owning
`user_id` in the query.

### 4.7 Admin/system access

- **Admin** is a distinct principal scope for operational concerns
  (erasure/MS10.3, moderation of anonymous feedback) — narrow, separate
  dependency (`require_admin`), separate token/audience.
- **System** (service-to-service, e.g. an internal worker) uses a
  **service principal** token with its own audience; it never impersonates a
  user and never accesses user-owned rows except through the same
  ownership-guarded application use cases.
- **Default is closed:** there are no user-accessible admin paths; admin and
  system paths are additive and audited (who/what/when via events).

---

## 5. Resource scope map (examples)

| Example | Class | Owner scope | Notes |
| --- | --- | --- | --- |
| Wardrobe | user-owned | `wardrobe_items.user_id` | UC-5…14; every item/outfit query filtered |
| Scans | user-owned | `analysis_runs.user_id` | UC-24…27; run polling owner-guarded |
| Photos | user-owned | `media.user_id` (M16) | MS10.3; upload-then-insert, owner-guarded |
| Recommendations | user-owned | `recommendations.user_id` (P3) | regenerable (TRX-7); still owner-scoped |
| Saved Looks | user-owned | `saved_looks.user_id` | UC-15/30; owner-only lists |
| Feedback | user-owned | `feedback.user_id` | write by owner; anonymous read for admin moderation |
| Events | user-owned | `events.user_id` | UC-18…20; owner-only |
| Assistant Conversations | user-owned | `conversations.user_id` (M4) | storage per-user; assistant DTOs stay user-free (A3.1) |

Every row in a user-owned table **must** have `user_id` populated from the
authenticated principal at insert; a request that omits or forges it fails
authorization (OW-1).

---

## 6. Current state and sequencing

- **Today:** the assistant endpoint is unauthenticated (`backend/app/main.py`)
  — correct for a demo AI service; it carries no user-owned data (A3.1).
- **M1 (migration):** no auth yet; assistant unchanged (19 tests stay green).
- **M2–M4:** typed errors land first; auth (M1 module) is a **P0** slice that
  **waits on D-AUTH-1** (provider) + UC-1/UC-2 (users). Until then, every
  P0 use case that needs `user_id` uses the unauthenticated assistant path or
  a stubbed principal — and **no user-owned resource is exposed** until the
  ownership invariant (OW-1) is in place.
- **Contract note:** the first protected endpoints ship with the auth module;
  the assistant may gain optional auth later without breaking its wire shape.

---

## 7. Report, assumptions, constraints

**What changed (this step):** added `AUTH_AUTHORIZATION_ARCHITECTURE.md` —
the auth/authorization boundary design. Authentication is NOT implemented.

**Skills used:** repository analysis (live `main.py` confirms assistant is
unauthenticated; accepted API-9/10, M1 module, ERROR_HANDLING codes) —
architecture documentation only.

**Files changed:** `docs/backend/AUTH_AUTHORIZATION_ARCHITECTURE.md` (new).

**Validation run:**
- Ownership invariant OW-1 mapped to every user-owned resource, including
  all eight required examples (Wardrobe, Scans, Photos, Recommendations,
  Saved Looks, Feedback, Events, Assistant Conversations) — each with its
  owner column and scope mechanism.
- Authorization contract matches accepted docs: deps.py→user_id (API-9),
  404-not-403 (API-10), AUTHENTICATION_ERROR/AUTHORIZATION_ERROR
  (ERROR_HANDLING), F-3 (identity = user_id only), PR-4 (user_id FK).
- Admin/system access is bounded, additive, and audited; default closed.
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created. No pytest run needed (no code change).

**Remaining issues / follow-ups:**
- **D-AUTH-1 (open decision):** the concrete authentication provider
  (email/password vs social OAuth, token format/JWT vs opaque session) is
  unspecified; this doc fixes the seam (`verify_access_token -> Principal`)
  and the invariants so the adapter is replaceable. Record in `DECISIONS.md`
  when the provider is accepted.
- "User fields/auth" remains open in `BACKEND_ARCHITECTURE_RULES.md` §8;
  the auth module is P0 but its exact shape depends on UC-1/UC-2.
- Conversations: assistant DTOs are user-free (A3.1), but conversation
  storage per-user (M4) is a P1 concern; ownership map covers the design.
- No `DECISIONS.md` entry added here (documentation only).

**Assumptions recorded:**
- Identity for domain logic is always the `user_id` (never email/name/token).
- 401 = unauthenticated, 403 = authenticated-but-disallowed, 404 = the only
  response to another user's resource (no existence oracle).
- The auth provider is external/delegated; the backend never stores
  passwords or refresh secrets.
- Admin/system access is a separate, narrow, audited scope — never reachable
  from a normal user token.

**Constraints honored:** F-3/DR-1 (no auth in domain), PR-4 (user_id FK),
ERROR_HANDLING (401/403 semantics, no token logging), MS10.3 (privacy/
erasure applies to user-owned data), API-9/10 (Bearer + 404-not-403), the
Scope rule (this document only), and no implementation (auth NOT created).