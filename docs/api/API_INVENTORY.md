# Fansivibe — API Inventory

> **STEP 6 — API INVENTORY.** The complete inventory of every HTTP API the
> Fansivibe product requires, derived **only** from the completed STEP 2–5
> deliverables (feature/action inventory, domain model, database design,
> backend architecture) and the accepted contract in
> `API_CONTRACT_RULES.md`. No endpoint is invented that the feature/data
> inventory does not support; no endpoint is implemented.
>
> **Status: inventory only. Nothing is implemented.** No endpoints are
> created, no routers/DTOs/SQL written, no Flutter/routing/UI modified, no
> repositories/services, no dependencies, no existing endpoint removed. The
> live contract (`GET /health`, `POST /v1/assistant/chat`) is preserved
> unchanged.
>
> **Source of truth:** the real Fansivibe repository and the accepted docs:
> STEP 2 `ACTION_API_INVENTORY.md` (32 actions + Part 3 errors),
> STEP 3 `FANSIVIBE_DOMAIN_MODEL_V1.md` (E1–E10),
> STEP 4 `TABLE_DEFINITIONS.md` / `TRANSACTION_BOUNDARIES.md` /
> `SECURITY_PRIVACY_DESIGN.md`, STEP 5 `APPLICATION_USE_CASES.md`
> (UC-1…UC-33), `BACKEND_MODULE_MAP.md` (M1–M16), `API_LAYER_ARCHITECTURE.md`
> (API-1…44), `ERROR_HANDLING.md`, `AUTH_AUTHORIZATION_ARCHITECTURE.md`
> (OW-1), `KNOWLEDGE_ARCHITECTURE.md`, `BACKGROUND_JOB_ARCHITECTURE.md`,
> `MEDIA_UPLOAD_ARCHITECTURE.md`, and STEP 6 `API_CONTRACT_RULES.md` (the
> canonical endpoint catalog §12).

---

## 1. Purpose and scope

This document is the **master inventory** of every API Fansivibe needs. It
complements `API_CONTRACT_RULES.md` (the *rules* + wire shapes) with the
**catalog**: for every required API it identifies all thirteen inventory
fields:

1. **API name**
2. **HTTP method**
3. **path**
4. **feature** (product surface + owning module)
5. **purpose**
6. **authentication requirement**
7. **authorization requirement**
8. **synchronous/asynchronous**
9. **input data**
10. **output data**
11. **errors**
12. **related domain entities**
13. **priority (P0/P1/P2)**

Scope rules:

- The inventory covers **only** APIs supported by the feature/data inventory:
  the 32 STEP 2 actions → the 33 application use cases → the module map
  M1–M16. No `POST /foo` is added that no screen, action, entity, or use case
  justifies.
- The **live contract is fixed**: `GET /health` and `POST /v1/assistant/chat`
  appear exactly as they exist today.
- Sealed/gated modules (**M11 feedback**, **M16 media**) appear in the
  inventory (so the full surface is known) but are marked **NOT mounted** —
  their routes do not exist until their gate lifts (API-12).
- This document defines *what* the API is; it does not write implementation.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `ACTION_API_INVENTORY.md` | The 32 user actions → the required future endpoints + Part 3 error summary. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities E1–E10 + value objects; the "related domain entities" field. |
| `TABLE_DEFINITIONS.md` | Canonical field names for input/output DTOs. |
| `APPLICATION_USE_CASES.md` | UC-1…UC-33 — the operation each endpoint invokes (DR-1); names the API. |
| `BACKEND_MODULE_MAP.md` | M1–M16 ownership + P0/P1/P2 phase → the priority field. |
| `API_CONTRACT_RULES.md` | The canonical endpoint catalog (§12) — method/path/auth/UC/sync/errors. |
| `API_LAYER_ARCHITECTURE.md` | API-1…44 (versioning, envelopes, pagination, idempotency, async). |
| `ERROR_HANDLING.md` | The 12-category frozen error taxonomy (`error.code` values). |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` | OW-1 ownership, 404-not-403, Bearer resolution. |
| `BACKGROUND_JOB_ARCHITECTURE.md` | SYNC vs ASYNC classification. |
| `MEDIA_UPLOAD_ARCHITECTURE.md` / `KNOWLEDGE_ARCHITECTURE.md` | M16 media flow (sealed), M5 public catalog. |

---

## 3. Conventions used in this inventory

- **API name:** verb-first PascalCase, matching the application use case
  (UC-*) where one exists; read/list endpoints that fold multiple actions use
  a resource-based name (e.g. `ListWardrobeItems`).
- **Path:** all endpoints except `GET /health` are under `/v1` (API-1).
- **Auth:** `public` = no token (API-7 list); `auth` = Bearer token resolved
  by `deps.py` → `user_id` (API-5/6). Assistant `chat` is public **today**
  (F-5) and is marked `public (today)`.
- **Authorization:** `none` (public), `owner` (OW-1: every query/write
  filtered by `user_id`, 404-not-403), `admin` (knowledge seed, M5 P2 —
  not part of the Flutter contract).
- **Sync/async:** `sync` by default (API-40); `async` = `202 {run_id}` +
  `GET /v1/analysis/runs/{run_id}` polling (API-41/42, TRX-5) — image
  analysis only.
- **Errors:** frozen 12-category `error.code` values from `ERROR_HANDLING.md`
  (identical to `API_CONTRACT_RULES.md` §9.1). 401 is implied on every
  `auth` endpoint and omitted from per-endpoint lists for brevity.
- **Entities:** E1–E10 from `FANSIVIBE_DOMAIN_MODEL_V1.md`; `—` = none
  (auth/session/infra, or value objects only).
- **Priority:** module phase from `BACKEND_MODULE_MAP.md` (P0: M1–M6; P1:
  M7–M11; P2: M12–M16). `health` is infrastructure (live today).
- **Idempotency:** noted in *input data* when `Idempotency-Key` is required
  (C-12, API-33).

---

## 4. Master inventory (all endpoints)

| # | API name | Method | Path | Feature (module) | UC | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | `HealthCheck` | GET | `/health` | infra (all) | — | live |
| 02 | `RegisterAccount` | POST | `/v1/auth/register` | onboarding (M1) | UC-1 | P0 |
| 03 | `SocialSignIn` | POST | `/v1/auth/social` | onboarding (M1) | UC-2 | P0 |
| 04 | `SignIn` | POST | `/v1/auth/login` | onboarding (M1) | UC-3 | P0 |
| 05 | `SignOut` | POST | `/v1/auth/logout` | profile (M1) | UC-4 | P0 |
| 06 | `GetProfile` | GET | `/v1/users/me` | profile (M2) | UC-6 | P0 |
| 07 | `UpdateProfile` | PATCH | `/v1/users/me` | profile (M2) | UC-7 | P0 |
| 08 | `UpdatePreferences` | PUT | `/v1/users/me/preferences` | profile (M2) | UC-8 | P0 |
| 09 | `UpdateSettings` | PUT | `/v1/users/me/settings` | profile (M2) | (28) | P0 |
| 10 | `SyncLocalData` | POST | `/v1/users/me/sync` | onboarding/profile (M2) | UC-9 | P0 |
| 11 | `ListWardrobeItems` | GET | `/v1/wardrobe/items` | wardrobe (M3) | (5,6,7) | P0 |
| 12 | `AddWardrobeItem` | POST | `/v1/wardrobe/items` | wardrobe (M3) | UC-10 | P0 |
| 13 | `UpdateWardrobeItem` | PATCH | `/v1/wardrobe/items/{item_id}` | wardrobe (M3) | UC-11/12 | P0 |
| 14 | `DeleteWardrobeItem` | DELETE | `/v1/wardrobe/items/{item_id}` | wardrobe (M3) | UC-13 | P0 |
| 15 | `GetWardrobeInsight` | GET | `/v1/wardrobe/insight` | wardrobe (M3) | UC-14 | P0 |
| 16 | `SendAssistantMessage` | POST | `/v1/assistant/chat` | assistant (M4) | UC-22 | P0 (live) |
| 17 | `SubmitAssistantCardFeedback` | POST | `/v1/assistant/feedback` | assistant (M4) | UC-23 | P0/P1 |
| 18 | `ListKnowledgeLooks` | GET | `/v1/knowledge/looks` | discover/wardrobe (M5) | — | P0 |
| 19 | `ListKnowledgeCategories` | GET | `/v1/knowledge/categories` | wardrobe/discover (M5) | — | P0 |
| 20 | `ListKnowledgeColors` | GET | `/v1/knowledge/colors` | wardrobe (M5) | — | P0 |
| 21 | `ListKnowledgeOccasions` | GET | `/v1/knowledge/occasions` | events/discover (M5) | — | P0 |
| 22 | `ListKnowledgeItems` | GET | `/v1/knowledge/items` | wardrobe (M5) | — | P0 |
| 23 | `SaveRecommendation` | POST | `/v1/looks/saved` | home/discover/scan/hair/groom (M7) | UC-15 | P1 |
| 24 | `ListSavedLooks` | GET | `/v1/looks/saved` | profile/home (M7) | (14,17) | P1 |
| 25 | `DeleteSavedLook` | DELETE | `/v1/looks/saved/{saved_look_id}` | profile/home (M7) | — | P1 |
| 26 | `CreateEvent` | POST | `/v1/events` | events (M8) | UC-18 | P1 |
| 27 | `ListEvents` | GET | `/v1/events` | events (M8) | (9) | P1 |
| 28 | `UpdateEvent` | PUT | `/v1/events/{event_id}` | events (M8) | UC-19 | P1 |
| 29 | `DeleteEvent` | DELETE | `/v1/events/{event_id}` | events (M8) | UC-20 | P1 |
| 30 | `GenerateEventOutfit` | POST | `/v1/events/{event_id}/outfit` | events (M8/M13) | UC-21 | P1 |
| 31 | `GetTodayLook` | GET | `/v1/looks/today` | home (M9) | UC-17 | P1 |
| 32 | `GenerateDailyOutfit` | POST | `/v1/looks/today` | home (M9) | UC-16 | P1 |
| 33 | `SaveTodayLook` | POST | `/v1/looks/today/save` | home (M9) | (12) | P1 |
| 34 | `GetLearningSummary` | GET | `/v1/learning/summary` | learning/profile (M10) | (8,28) | P1 |
| 35 | `SubmitRecommendationFeedback` | POST | `/v1/feedback` | (missing feature) (M11) | UC-32 | P1 (gated) |
| 36 | `AnalyzeOutfit` | POST | `/v1/analysis/outfit` | outfit_scan (M12) | UC-24 | P2 |
| 37 | `AnalyzeAppearance` | POST | `/v1/analysis/hairstyle` | hairstyle (M12) | UC-25/26 | P2 |
| 38 | `GenerateGroomingRecommendations` | POST | `/v1/analysis/grooming` | grooming (M12) | UC-27 | P2 |
| 39 | `GetAnalysisRun` | GET | `/v1/analysis/runs/{run_id}` | scan/hair/groom (M12) | (16,21,23) | P2 |
| 40 | `ListAnalysisRuns` | GET | `/v1/analysis/runs` | scan/hair/groom (M12) | — | P2 |
| 41 | `CreateOutfit` | POST | `/v1/outfits/generate` | outfit_builder (M13) | UC-28/29 | P2 |
| 42 | `SaveOutfit` | POST | `/v1/outfits/saved` | outfit_builder (M13) | UC-30 | P2 |
| 43 | `GetLookFeed` | GET | `/v1/looks` | discover (M14) | UC-31 | P2 |
| 44 | `GetLookDetail` | GET | `/v1/looks/{look_id}` | discover (M14) | (14) | P2 |
| 45 | `GetSubscription` | GET | `/v1/subscriptions/me` | profile (M15) | (30 read) | P2 |
| 46 | `SubscribeToPlan` | POST | `/v1/subscriptions` | profile (M15) | UC-33 | P2 |
| 47 | `CreateMediaUpload` | POST | `/v1/media/uploads` | wardrobe/scan (M16) | — | P2 (sealed) |
| 48 | `CompleteMediaUpload` | POST | `/v1/media/uploads/{upload_id}/complete` | wardrobe/scan (M16) | — | P2 (sealed) |

> Server-to-server (not part of the Flutter contract): the **subscriptions
> billing webhook** (M15) and **admin knowledge seed** (M5 P2) are documented
> in §6.4, not as client-facing APIs.

---

## 5. Per-endpoint detail

### 5.1 Infra

#### 01 — `HealthCheck`

- **API name:** `HealthCheck`
- **HTTP method:** `GET`
- **Path:** `/health`
- **Feature:** infrastructure (all features probe it)
- **Purpose:** liveness check; no state, no user data.
- **Authentication requirement:** public (none).
- **Authorization requirement:** none.
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `{"status":"ok"}` — bare, versionless, envelope-free
  (unchanged live contract).
- **Errors:** none defined (unhandled → 500 `INTERNAL_ERROR`).
- **Related domain entities:** —.
- **Priority:** live today (infrastructure).

---

### 5.2 Auth — M1 (P0)

#### 02 — `RegisterAccount`

- **API name:** `RegisterAccount` (UC-1)
- **HTTP method:** `POST`
- **Path:** `/v1/auth/register`
- **Feature:** onboarding (AccountCreationScreen, action 1)
- **Purpose:** create an account: validate email/password, create the `users`
  row, issue a session token.
- **Authentication requirement:** public (no token; returns a token).
- **Authorization requirement:** none (public endpoint).
- **Synchronous/asynchronous:** sync.
- **Input data:** `RegisterRequest { email, password, displayName? }`;
  `Idempotency-Key` required (C-12).
- **Output data:** `AuthResponse { accessToken, tokenType, expiresIn,
  profile: ProfileView }` — 201.
- **Errors:** 409 `CONFLICT` (email taken), 422 `VALIDATION_ERROR`, 429
  `RATE_LIMITED`.
- **Related domain entities:** E1 `User`.
- **Priority:** P0.

#### 03 — `SocialSignIn`

- **API name:** `SocialSignIn` (UC-2)
- **HTTP method:** `POST`
- **Path:** `/v1/auth/social`
- **Feature:** onboarding (AccountCreationScreen, action 2)
- **Purpose:** exchange a Google/Apple provider token, upsert the user by
  provider subject id, issue an app session.
- **Authentication requirement:** public (provider token exchanged; no app
  token yet).
- **Authorization requirement:** none (public endpoint).
- **Synchronous/asynchronous:** sync.
- **Input data:** `SocialSignInRequest { provider: google|apple,
  providerToken }`.
- **Output data:** `AuthResponse` — 200 (existing) / 201 (new).
- **Errors:** 502 `EXTERNAL_SERVICE_FAILURE` (provider unavailable), 401
  `AUTHENTICATION_ERROR` (invalid/expired provider token), 409 `CONFLICT`
  (account-linking).
- **Related domain entities:** E1 `User`.
- **Priority:** P0.

#### 04 — `SignIn`

- **API name:** `SignIn` (UC-3)
- **HTTP method:** `POST`
- **Path:** `/v1/auth/login`
- **Feature:** onboarding (EntryScreen, action 3)
- **Purpose:** verify credentials, issue a token, return the stored profile
  (+ last model snapshot for device restore).
- **Authentication requirement:** public (credentials exchange).
- **Authorization requirement:** none (public endpoint).
- **Synchronous/asynchronous:** sync.
- **Input data:** `LoginRequest { email, password }`.
- **Output data:** `AuthResponse` (+ stored model snapshot) — 200.
- **Errors:** 401 `AUTHENTICATION_ERROR` (wrong credentials), 404
  `NOT_FOUND`, 429 `RATE_LIMITED`.
- **Related domain entities:** E1 `User`; E1.1 `UserState`.
- **Priority:** P0.

#### 05 — `SignOut`

- **API name:** `SignOut` (UC-4)
- **HTTP method:** `POST`
- **Path:** `/v1/auth/logout`
- **Feature:** profile (ProfileScreen menu, action 29)
- **Purpose:** revoke the session token.
- **Authentication requirement:** auth (Bearer token).
- **Authorization requirement:** owner (revokes the caller's own session).
- **Synchronous/asynchronous:** sync.
- **Input data:** none (token in header).
- **Output data:** 204 no-content.
- **Errors:** 401 `AUTHENTICATION_ERROR` (already logged out — idempotent).
- **Related domain entities:** — (session store, R51).
- **Priority:** P0.

---

### 5.3 Users — M2 (P0)

#### 06 — `GetProfile`

- **API name:** `GetProfile` (UC-6)
- **HTTP method:** `GET`
- **Path:** `/v1/users/me`
- **Feature:** profile (ProfileScreen, action 28 read)
- **Purpose:** read the current user's profile view (name, style profile,
  preferences, settings, flags).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `ProfileView { displayName, styleProfile, preferences,
  settings, flags, version }` — 200.
- **Errors:** 404 `NOT_FOUND`.
- **Related domain entities:** E1 `User`; E1.1 `UserState` (StyleProfile,
  Preferences, Settings).
- **Priority:** P0.

#### 07 — `UpdateProfile`

- **API name:** `UpdateProfile` (UC-7)
- **HTTP method:** `PATCH`
- **Path:** `/v1/users/me`
- **Feature:** profile (ProfileScreen, action 28)
- **Purpose:** partial update of profile fields (name, avatar `MediaRef`,
  style DNA), guarded by optimistic `version`.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `ProfileUpdateRequest { displayName?, avatarMediaRef?,
  styleDna? }`.
- **Output data:** `ProfileView` — 200.
- **Errors:** 422 `VALIDATION_ERROR`, 409 `CONFLICT` (version).
- **Related domain entities:** E1 `User`; E1.1 `UserState`.
- **Priority:** P0.

#### 08 — `UpdatePreferences`

- **API name:** `UpdatePreferences` (UC-8)
- **HTTP method:** `PUT`
- **Path:** `/v1/users/me/preferences`
- **Feature:** profile (PreferencesScreen, action 28)
- **Purpose:** merge changed preference key/values into the `user_state`
  JSONB document; vocabulary-validated.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `Preferences` (sparse key/values, vocab-validated).
- **Output data:** updated `Preferences` — 200.
- **Errors:** 422 `VALIDATION_ERROR`.
- **Related domain entities:** E1.1 `UserState.preferences`.
- **Priority:** P0.

#### 09 — `UpdateSettings`

- **API name:** `UpdateSettings`
- **HTTP method:** `PUT`
- **Path:** `/v1/users/me/settings`
- **Feature:** profile (SettingsScreen, action 28)
- **Purpose:** replace app settings (controlled keys) in `user_state`.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `Settings` (sparse, controlled keys).
- **Output data:** updated `Settings` — 200.
- **Errors:** 422 `VALIDATION_ERROR`.
- **Related domain entities:** E1.1 `UserState.settings`.
- **Priority:** P0.

#### 10 — `SyncLocalData`

- **API name:** `SyncLocalData` (UC-9; P7.1 sync path)
- **HTTP method:** `POST`
- **Path:** `/v1/users/me/sync`
- **Feature:** onboarding/profile (post-account merge, action 32)
- **Purpose:** upsert the full local `UserModel` snapshot and split relational
  rows (wardrobe/events/saved-looks) + `user_state` projection in **one true
  transaction** (TRX-3/TRX-6); resolve server-vs-device conflicts.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `SyncRequest` (full `UserModel` blob: wardrobe, savedLooks,
  events, preferences, styleProfile, flags, clientTimestamp);
  `Idempotency-Key` required.
- **Output data:** `SyncReceipt { mergedProfile, conflicts[], syncedAt }` —
  200.
- **Errors:** 409 `CONFLICT` (sync conflict), 413 `MEDIA_FAILURE` (payload
  too large).
- **Related domain entities:** E1, E1.1, E2 `WardrobeItem`, E3 `UserEvent`,
  E4 `SavedLook`, E7 `LearningSignal`.
- **Priority:** P0.

---

### 5.4 Wardrobe — M3 (P0)

#### 11 — `ListWardrobeItems`

- **API name:** `ListWardrobeItems`
- **HTTP method:** `GET`
- **Path:** `/v1/wardrobe/items`
- **Feature:** wardrobe (WardrobeScreen, actions 5/6/7 reads)
- **Purpose:** list the user's wardrobe items with filter/pagination/sort.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?category=&color=&sort=&page=&page_size=`
  (vocab-validated; page 1-based, ≤100).
- **Output data:** `WardrobeItemList` (envelope `{items,page,page_size,
  total}`) — 200.
- **Errors:** 422 `VALIDATION_ERROR` (filters/pagination).
- **Related domain entities:** E2 `WardrobeItem`.
- **Priority:** P0.

#### 12 — `AddWardrobeItem`

- **API name:** `AddWardrobeItem` (UC-10)
- **HTTP method:** `POST`
- **Path:** `/v1/wardrobe/items`
- **Feature:** wardrobe (WardrobeScreen → Add Item, action 5)
- **Purpose:** create a wardrobe item, validating category/color against the
  controlled vocabulary; emit `ItemAdded` domain event → learning signal.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `WardrobeItemCreate { name, category, color, material?,
  imageRef? }` (blob upload before INSERT when M16 lifts, TRX-1).
- **Output data:** `WardrobeItem` — 201.
- **Errors:** 422 `VALIDATION_ERROR` (vocab, allowed values in `details`),
  409 `CONFLICT` (dup/limit).
- **Related domain entities:** E2 `WardrobeItem`; E5 `Look`/
  `ItemReference` (vocab).
- **Priority:** P0.

#### 13 — `UpdateWardrobeItem`

- **API name:** `UpdateWardrobeItem` (UC-11/12)
- **HTTP method:** `PATCH`
- **Path:** `/v1/wardrobe/items/{item_id}`
- **Feature:** wardrobe (item detail, actions 6/7)
- **Purpose:** partial update incl. favorite toggle; validate vocab.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403).
- **Synchronous/asynchronous:** sync.
- **Input data:** `WardrobeItemPatch { name?, category?, color?, material?,
  isFavorite? }`.
- **Output data:** updated `WardrobeItem` — 200.
- **Errors:** 404 `NOT_FOUND`, 422 `VALIDATION_ERROR`, 409 `CONFLICT`.
- **Related domain entities:** E2 `WardrobeItem`.
- **Priority:** P0.

#### 14 — `DeleteWardrobeItem`

- **API name:** `DeleteWardrobeItem` (UC-13)
- **HTTP method:** `DELETE`
- **Path:** `/v1/wardrobe/items/{item_id}`
- **Feature:** wardrobe (item detail, action 7)
- **Purpose:** delete the item (images cascade out-of-DB after commit);
  history untouched (BC-41).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** 204 no-content.
- **Errors:** 404 `NOT_FOUND`, 409 `CONFLICT` (FK refs).
- **Related domain entities:** E2 `WardrobeItem`.
- **Priority:** P0.

#### 15 — `GetWardrobeInsight`

- **API name:** `GetWardrobeInsight` (UC-14)
- **HTTP method:** `GET`
- **Path:** `/v1/wardrobe/insight`
- **Feature:** wardrobe (WardrobeScreen "View Analysis", action 8)
- **Purpose:** derive wardrobe gaps/insight (e.g. "consider a lightweight
  jacket") from wardrobe + knowledge catalog.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `WardrobeInsight { title, insight, action?, route? }` —
  200; **204** (empty wardrobe — empty is not an error).
- **Errors:** —.
- **Related domain entities:** E2 `WardrobeItem`; E5 (catalog).
- **Priority:** P0.

---

### 5.5 Assistant — M4 (P0, live contract)

#### 16 — `SendAssistantMessage`

- **API name:** `SendAssistantMessage` (UC-22 — **the live contract, A3.1**)
- **HTTP method:** `POST`
- **Path:** `/v1/assistant/chat`
- **Feature:** assistant (AssistantScreen, action 25)
- **Purpose:** the conversational assistant: intent classification → tool
  selection → dialogue policy → structured reply; optional LLM text
  enrichment that degrades to the rules engine. **Frozen wire shape (F-13).**
- **Authentication requirement:** public **today** (F-5); may gain auth later
  without changing the wire shape.
- **Authorization requirement:** none today; authenticated routing later.
- **Synchronous/asynchronous:** sync (client falls back to offline assistant
  on network failure — not a surfaced error).
- **Input data:** `AssistantRequest { messages: ChatMessage[], user?:
  UserContext }` — frozen verbatim from `schemas.py`.
- **Output data:** `AssistantReply { intent, text, cards, clarifications,
  navigation? }` — bare, no envelope, frozen (F-13) — 200.
- **Errors:** 422 `VALIDATION_ERROR` (invalid context); network failure →
  client offline fallback.
- **Related domain entities:** E2 `WardrobeItem` (in context), E4
  `SavedLook` (in context), E5 `Look` (catalog), E1.1 (preferred occasions).
- **Priority:** P0 (live).

#### 17 — `SubmitAssistantCardFeedback`

- **API name:** `SubmitAssistantCardFeedback` (UC-23)
- **HTTP method:** `POST`
- **Path:** `/v1/assistant/feedback`
- **Feature:** assistant (AssistantScreen suggestion card, action 26)
- **Purpose:** record a card-interaction signal (`opened`/`navigated`) for
  learning (M10 is the sole writer of `learning_signals`, PR-7).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `AssistantCardFeedback { cardTitle|cardId,
  interactionType }`.
- **Output data:** 204 no-content.
- **Errors:** 401 (only).
- **Related domain entities:** E7 `LearningSignal`.
- **Priority:** P0/P1 (module P0; signal persistence P1).

---

### 5.6 Knowledge — M5 (P0, public catalog)

All knowledge reads are **public** (API-7), **read-mostly**, never expose
user data, and carry `X-Knowledge-Version` (KN-1). Admin/seed writes (M5 P2)
are admin-only and **not** part of the Flutter contract.

#### 18 — `ListKnowledgeLooks`

- **API name:** `ListKnowledgeLooks`
- **HTTP method:** `GET`
- **Path:** `/v1/knowledge/looks`
- **Feature:** discover (feed content), wardrobe/assistant (lookup), K9.1
- **Purpose:** serve the curated look catalog (filtered, paginated).
- **Authentication requirement:** public.
- **Authorization requirement:** none.
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?occasion=&style=&page=&page_size=`
  (vocab-validated).
- **Output data:** `LookList` (envelope) — 200; `X-Knowledge-Version` header.
- **Errors:** 422 `VALIDATION_ERROR` (filters).
- **Related domain entities:** E5 `Look`.
- **Priority:** P0 (subset; full rollout P2).

#### 19 — `ListKnowledgeCategories`

- **API name:** `ListKnowledgeCategories`
- **HTTP method:** `GET`
- **Path:** `/v1/knowledge/categories`
- **Feature:** wardrobe (Add Item vocab), discover
- **Purpose:** serve the controlled category vocabulary.
- **Authentication requirement:** public.
- **Authorization requirement:** none.
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `VocabularyItem[]` — 200.
- **Errors:** —.
- **Related domain entities:** E5 `Category` (vocab).
- **Priority:** P0.

#### 20 — `ListKnowledgeColors`

- **API name:** `ListKnowledgeColors`
- **HTTP method:** `GET`
- **Path:** `/v1/knowledge/colors`
- **Feature:** wardrobe (Add Item swatches)
- **Purpose:** serve the controlled color vocabulary.
- **Authentication requirement:** public.
- **Authorization requirement:** none.
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `VocabularyItem[]` — 200.
- **Errors:** —.
- **Related domain entities:** E5 `Color` (vocab).
- **Priority:** P0.

#### 21 — `ListKnowledgeOccasions`

- **API name:** `ListKnowledgeOccasions`
- **HTTP method:** `GET`
- **Path:** `/v1/knowledge/occasions`
- **Feature:** events (event types), discover, daily outfit
- **Purpose:** serve the controlled occasion vocabulary.
- **Authentication requirement:** public.
- **Authorization requirement:** none.
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `VocabularyItem[]` — 200.
- **Errors:** —.
- **Related domain entities:** E5 `Occasion` (vocab).
- **Priority:** P0.

#### 22 — `ListKnowledgeItems`

- **API name:** `ListKnowledgeItems`
- **HTTP method:** `GET`
- **Path:** `/v1/knowledge/items`
- **Feature:** wardrobe (reference catalog), assistant
- **Purpose:** serve the controlled item-reference catalog.
- **Authentication requirement:** public.
- **Authorization requirement:** none.
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `ItemReference[]` — 200.
- **Errors:** —.
- **Related domain entities:** E5 `ItemReference`.
- **Priority:** P0.

---

### 5.7 Saved Looks — M7 (P1)

#### 23 — `SaveRecommendation`

- **API name:** `SaveRecommendation` (UC-15)
- **HTTP method:** `POST`
- **Path:** `/v1/looks/saved`
- **Feature:** home (daily outfit), discover (look details), outfit_scan
  (generate look), hairstyle/grooming (save style) — actions 12/14/17/22/24
- **Purpose:** freeze an immutable snapshot of a look/recommendation + write
  the `look_saved` learning signal in **one true transaction** (TRX-3).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `SaveLookRequest { lookId?, title, sourceContext?,
  snapshot }`; `Idempotency-Key` required.
- **Output data:** `SavedLook` — 201.
- **Errors:** 404 `NOT_FOUND` (look), 409 `CONFLICT` (duplicate).
- **Related domain entities:** E4 `SavedLook`; E7 `LearningSignal`; optional
  E5 `Look` (SET NULL FK); optional E6 `AnalysisRun` (source_run_id).
- **Priority:** P1.

#### 24 — `ListSavedLooks`

- **API name:** `ListSavedLooks`
- **HTTP method:** `GET`
- **Path:** `/v1/looks/saved`
- **Feature:** profile/home (Saved Looks view), discover
- **Purpose:** list the user's saved looks (paginated, sorted).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?sort=created_at&page=&page_size=`.
- **Output data:** `SavedLookList` (envelope) — 200.
- **Errors:** —.
- **Related domain entities:** E4 `SavedLook`.
- **Priority:** P1.

#### 25 — `DeleteSavedLook`

- **API name:** `DeleteSavedLook`
- **HTTP method:** `DELETE`
- **Path:** `/v1/looks/saved/{saved_look_id}`
- **Feature:** profile/home (Saved Looks view)
- **Purpose:** delete a saved look (append-only storage; history rules apply).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** 204 no-content.
- **Errors:** 404 `NOT_FOUND`.
- **Related domain entities:** E4 `SavedLook`.
- **Priority:** P1.

---

### 5.8 Events — M8 (P1)

#### 26 — `CreateEvent`

- **API name:** `CreateEvent` (UC-18)
- **HTTP method:** `POST`
- **Path:** `/v1/events`
- **Feature:** events (AddEventScreen, action 9)
- **Purpose:** create a dated event; validate type against the controlled
  vocabulary + date not in the past; record the occasion preference
  (TRX-7).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `EventCreate { title, eventType, eventDate, time?,
  location?, notes? }`.
- **Output data:** `UserEvent` — 201.
- **Errors:** 422 `VALIDATION_ERROR` (past date / invalid type).
- **Related domain entities:** E3 `UserEvent`; E1.1 (preferred occasions).
- **Priority:** P1.

#### 27 — `ListEvents`

- **API name:** `ListEvents`
- **HTTP method:** `GET`
- **Path:** `/v1/events`
- **Feature:** events (EventListScreen, action 9 read)
- **Purpose:** list the user's events (upcoming), paginated/sorted.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?from=&sort=event_date&page=&page_size=`.
- **Output data:** `UserEventList` (envelope) — 200.
- **Errors:** 422 `VALIDATION_ERROR` (pagination/filters).
- **Related domain entities:** E3 `UserEvent`.
- **Priority:** P1.

#### 28 — `UpdateEvent`

- **API name:** `UpdateEvent` (UC-19)
- **HTTP method:** `PUT`
- **Path:** `/v1/events/{event_id}`
- **Feature:** events (EventDetailsScreen, action 10)
- **Purpose:** replace an event's fields (full-object PUT).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403).
- **Synchronous/asynchronous:** sync.
- **Input data:** `EventUpdate` (full replace).
- **Output data:** updated `UserEvent` — 200.
- **Errors:** 404 `NOT_FOUND`, 422 `VALIDATION_ERROR`.
- **Related domain entities:** E3 `UserEvent`.
- **Priority:** P1.

#### 29 — `DeleteEvent`

- **API name:** `DeleteEvent` (UC-20)
- **HTTP method:** `DELETE`
- **Path:** `/v1/events/{event_id}`
- **Feature:** events (EventDetailsScreen, action 10)
- **Purpose:** delete an event (history untouched, BC-41).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** 204 no-content.
- **Errors:** 404 `NOT_FOUND`.
- **Related domain entities:** E3 `UserEvent`.
- **Priority:** P1.

#### 30 — `GenerateEventOutfit`

- **API name:** `GenerateEventOutfit` (UC-21)
- **HTTP method:** `POST`
- **Path:** `/v1/events/{event_id}/outfit`
- **Feature:** events (EventDetailsScreen, action 11 — fixes the current
  event-context loss)
- **Purpose:** generate an outfit recommendation grounded in the event
  occasion + wardrobe via the outfit generation engine; regenerable, never
  persisted unless saved (TRX-7).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403 on event).
- **Synchronous/asynchronous:** sync.
- **Input data:** none (event id + occasion seed the generation).
- **Output data:** `OutfitRecommendation` — 200.
- **Errors:** 404 `NOT_FOUND` (event), 503 `EXTERNAL_SERVICE_FAILURE`
  (generation).
- **Related domain entities:** E3 `UserEvent`; E2 `WardrobeItem`; E1.1
  `StyleProfile`.
- **Priority:** P1.

---

### 5.9 Today's Look — M9 (P1)

> Path-collision guard (API contract §7): routers must register
> `/v1/looks/today`, `/v1/looks/today/save`, `/v1/looks/saved`,
> `/v1/looks/saved/{id}` **before** `/v1/looks` and `/v1/looks/{look_id}`.

#### 31 — `GetTodayLook`

- **API name:** `GetTodayLook` (UC-17)
- **HTTP method:** `GET`
- **Path:** `/v1/looks/today`
- **Feature:** home (Daily OutfitScreen, actions 13/12 read)
- **Purpose:** serve today's derived look (derive or read the stored
  snapshot).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?variant=`.
- **Output data:** `TodayLook` — 200.
- **Errors:** 404 `NOT_FOUND` (none found).
- **Related domain entities:** today's look (value object); E2, E1.1, E5;
  conditional `TodayLookRecord` (P1 decision).
- **Priority:** P1.

#### 32 — `GenerateDailyOutfit`

- **API name:** `GenerateDailyOutfit` (UC-16)
- **HTTP method:** `POST`
- **Path:** `/v1/looks/today`
- **Feature:** home (Daily OutfitScreen "Generate Another Look", action 13)
- **Purpose:** derive a fresh today's look from StyleProfile + wardrobe +
  optional nearest event + weather hint (weather never authoritative);
  different result per seed.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync (BJ-0: rules-based).
- **Input data:** query `?seed=`.
- **Output data:** `TodayLook` — 200.
- **Errors:** 503 `EXTERNAL_SERVICE_FAILURE` (generation).
- **Related domain entities:** E1.1, E2, E3 (optional), E5; today's look
  (value object).
- **Priority:** P1.

#### 33 — `SaveTodayLook`

- **API name:** `SaveTodayLook`
- **HTTP method:** `POST`
- **Path:** `/v1/looks/today/save`
- **Feature:** home (Daily OutfitScreen "Save Look", action 12)
- **Purpose:** save the displayed today's look as a saved look (snapshot
  + `look_saved` signal, TRX-3).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** the today-look reference/snapshot; `Idempotency-Key`
  required.
- **Output data:** `SavedLook` — 201.
- **Errors:** 404 `NOT_FOUND`, 409 `CONFLICT` (duplicate).
- **Related domain entities:** E4 `SavedLook`; E7 `LearningSignal`.
- **Priority:** P1.

---

### 5.10 Learning — M10 (P1)

#### 34 — `GetLearningSummary`

- **API name:** `GetLearningSummary`
- **HTTP method:** `GET`
- **Path:** `/v1/learning/summary`
- **Feature:** learning/profile (style score display, actions 8/28 profile)
- **Purpose:** serve the derived style score + streak + recent signals
  summary.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `LearningSummary { styleScore, breakdown, streak,
  recentSignals }` — 200.
- **Errors:** —.
- **Related domain entities:** E7 `LearningSignal`, E8 `StyleScoreRecord`,
  E9 `ActivityDay`.
- **Priority:** P1.

> Signals are written by the backend (from other use cases), never by the
> client directly (M10 is the sole writer, PR-7). There is **no** public
> signal-submit endpoint.

---

### 5.11 Feedback — M11 (P1, feature-gated — NOT mounted)

#### 35 — `SubmitRecommendationFeedback`

- **API name:** `SubmitRecommendationFeedback` (UC-32)
- **HTTP method:** `POST`
- **Path:** `/v1/feedback`
- **Feature:** **missing feature** — no feedback UI exists (ACTION_API #31,
  verified); requirement derived, not observed.
- **Purpose:** validate and store user rating/feedback on a look/outfit,
  optionally linked to a signal/look id.
- **Authentication requirement:** auth (or public with rate limits — future
  decision).
- **Authorization requirement:** owner (OW-1) once shipped.
- **Synchronous/asynchronous:** sync.
- **Input data:** `FeedbackCreate { rating, reason?, targetLookId?,
  targetSavedLookId? }`; `Idempotency-Key` required when it ships.
- **Output data:** 201/204.
- **Errors:** 422 `VALIDATION_ERROR`, 429 `RATE_LIMITED`.
- **Related domain entities:** `FeedbackEvent` (value object); E7
  (optional link).
- **Priority:** P1 (gated — **not mounted**, API-12; ships only when the
  feedback UI is accepted).

---

### 5.12 Analysis — M12 (P2, async)

All analysis submissions are **async**: `202 {run_id}` then poll
`GET /v1/analysis/runs/{run_id}` until `completed | failed` (API-41/42,
TRX-5 write-once). Each call creates a new run — never idempotent.

#### 36 — `AnalyzeOutfit`

- **API name:** `AnalyzeOutfit` (UC-24)
- **HTTP method:** `POST`
- **Path:** `/v1/analysis/outfit`
- **Feature:** outfit_scan (OutfitScanScreen → OutfitAnalysisScreen, action
  16)
- **Purpose:** submit an outfit image; create an `AnalysisRun` (pending);
  run outfit analysis rules → sections, detected items, scores, confidence;
  guarded write-once completion.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; media private).
- **Synchronous/asynchronous:** **async** (202 + run_id).
- **Input data:** `multipart/form-data` (`image` + typed fields); blob
  uploaded before the run row when M16 lifts (TRX-1).
- **Output data:** `202 { run_id }`.
- **Errors:** 413/422 `MEDIA_FAILURE` (too large/unsupported), 422
  `VALIDATION_ERROR` (no clothing detected), 503 `EXTERNAL_SERVICE_FAILURE`;
  `PROCESSING_FAILURE` on the run poll (`status=failed`).
- **Related domain entities:** E6 `AnalysisRun`; `MediaRef` (input).
- **Priority:** P2.

#### 37 — `AnalyzeAppearance`

- **API name:** `AnalyzeAppearance` (UC-25/26)
- **HTTP method:** `POST`
- **Path:** `/v1/analysis/hairstyle`
- **Feature:** hairstyle (HairstyleProcessingScreen → HairstyleResultScreen,
  action 21)
- **Purpose:** face image (or profile) → appearance analysis producing/
  updating `FaceProfile` (TRX-6 projection) + hairstyle recommendations;
  run model with write-once completion.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; face media is private).
- **Synchronous/asynchronous:** **async** (202 + run_id).
- **Input data:** `multipart/form-data` (`image` or profile).
- **Output data:** `202 { run_id }`.
- **Errors:** 422 `VALIDATION_ERROR` (poor image / face not detected), 503
  `EXTERNAL_SERVICE_FAILURE`; `PROCESSING_FAILURE` on poll.
- **Related domain entities:** E6 `AnalysisRun`; E1.1 `StyleProfile.FaceProfile`;
  E5 `Look` (hairstyle catalog).
- **Priority:** P2.

#### 38 — `GenerateGroomingRecommendations`

- **API name:** `GenerateGroomingRecommendations` (UC-27)
- **HTTP method:** `POST`
- **Path:** `/v1/analysis/grooming`
- **Feature:** grooming (GroomingProcessingScreen → GroomingResultScreen,
  action 23)
- **Purpose:** grooming recommendation rules from the grooming options
  (face shape/beard/density/color) → result + reasons + scores; stays on the
  run model for uniformity (BJ-0).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** **async** (202 + run_id).
- **Input data:** `GroomingAnalysisRequest` (options).
- **Output data:** `202 { run_id }`.
- **Errors:** 422 `VALIDATION_ERROR` (invalid inputs), 503
  `EXTERNAL_SERVICE_FAILURE`; `PROCESSING_FAILURE` on poll.
- **Related domain entities:** E6 `AnalysisRun`; E1.1 `FaceProfile`; E5
  `Look` (grooming catalog).
- **Priority:** P2.

#### 39 — `GetAnalysisRun`

- **API name:** `GetAnalysisRun`
- **HTTP method:** `GET`
- **Path:** `/v1/analysis/runs/{run_id}`
- **Feature:** outfit_scan / hairstyle / grooming (result polling, actions
  16/21/23)
- **Purpose:** poll a run: `pending → completed | failed`; completed returns
  the immutable result snapshot + `engine_version` (PR-6); failed returns the
  typed error.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; 404-not-403).
- **Synchronous/asynchronous:** sync (polling read).
- **Input data:** none (run_id in path).
- **Output data:** `AnalysisRun { run_id, run_type, status, result?, error?,
  created_at }` — 200.
- **Errors:** 404 `NOT_FOUND`.
- **Related domain entities:** E6 `AnalysisRun`.
- **Priority:** P2.

#### 40 — `ListAnalysisRuns`

- **API name:** `ListAnalysisRuns`
- **HTTP method:** `GET`
- **Path:** `/v1/analysis/runs`
- **Feature:** outfit_scan / hairstyle / grooming (history)
- **Purpose:** list the user's analysis runs (filtered by run_type,
  paginated).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?run_type=&sort=created_at&page=&page_size=`.
- **Output data:** `AnalysisRunList` (envelope) — 200.
- **Errors:** 422 `VALIDATION_ERROR`.
- **Related domain entities:** E6 `AnalysisRun`.
- **Priority:** P2.

---

### 5.13 Outfits — M13 (P2)

#### 41 — `CreateOutfit`

- **API name:** `CreateOutfit` (UC-28/29)
- **HTTP method:** `POST`
- **Path:** `/v1/outfits/generate`
- **Feature:** outfit_builder (OutfitBuilderScreen → OutfitRecommendation
  Screen, actions 18/20)
- **Purpose:** generate an outfit (value object: item list + rationale +
  scores) from preferences + wardrobe via the decision engine; `seed`
  yields a different result for Regenerate (UC-29). Regenerable, never
  persisted unless saved (TRX-2).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync (BJ-0: rules-based).
- **Input data:** `OutfitGenerateRequest { occasion, mood, fit,
  colorPalette, seed? }`.
- **Output data:** `OutfitRecommendation` — 200; **204** (no matching
  wardrobe — empty is not an error).
- **Errors:** 422 `VALIDATION_ERROR`, 503 `EXTERNAL_SERVICE_FAILURE`
  (generation).
- **Related domain entities:** E1.1, E2 `WardrobeItem`, E5 `Look`; outfit
  (value object).
- **Priority:** P2.

#### 42 — `SaveOutfit`

- **API name:** `SaveOutfit` (UC-30)
- **HTTP method:** `POST`
- **Path:** `/v1/outfits/saved`
- **Feature:** outfit_builder (OutfitRecommendationScreen "Save Outfit",
  action 19)
- **Purpose:** freeze the outfit recommendation as a saved outfit
  (snapshot + `look_saved` signal, TRX-3 via M7's contract).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** `SaveOutfitRequest` (recommendation snapshot);
  `Idempotency-Key` required.
- **Output data:** `SavedLook` — 201.
- **Errors:** 409 `CONFLICT` (duplicate).
- **Related domain entities:** E4 `SavedLook`; E7 `LearningSignal`; outfit
  (value object snapshot).
- **Priority:** P2.

---

### 5.14 Discover — M14 (P2)

#### 43 — `GetLookFeed`

- **API name:** `GetLookFeed` (UC-31)
- **HTTP method:** `GET`
- **Path:** `/v1/looks`
- **Feature:** discover (DiscoverScreen, action 15)
- **Purpose:** personalized look feed over the knowledge catalog with
  filters + engine-ranked ordering (`isOwned`, match scores).
- **Authentication requirement:** auth (personalization requires the user).
- **Authorization requirement:** owner (OW-1 for personalized fields).
- **Synchronous/asynchronous:** sync.
- **Input data:** query `?occasion=&style=&fit=&cursor=&limit=`
  (cursor pagination for feeds, API-21).
- **Output data:** `LookFeed` (envelope, engine-ranked) — 200.
- **Errors:** 422 `VALIDATION_ERROR` (filters).
- **Related domain entities:** E5 `Look`; E2 `WardrobeItem` (`isOwned`);
  E7 `LearningSignal` (personalization).
- **Priority:** P2.

#### 44 — `GetLookDetail`

- **API name:** `GetLookDetail`
- **HTTP method:** `GET`
- **Path:** `/v1/looks/{look_id}`
- **Feature:** discover (LookDetailsScreen, action 14)
- **Purpose:** single look detail (ensemble, scores, `isOwned`
  personalization).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1 for personalized fields).
- **Synchronous/asynchronous:** sync.
- **Input data:** none (look_id in path).
- **Output data:** `LookDetail` — 200.
- **Errors:** 404 `NOT_FOUND`.
- **Related domain entities:** E5 `Look`; E2 (isOwned).
- **Priority:** P2.

---

### 5.15 Subscriptions — M15 (P2)

#### 45 — `GetSubscription`

- **API name:** `GetSubscription`
- **HTTP method:** `GET`
- **Path:** `/v1/subscriptions/me`
- **Feature:** profile (SubscriptionScreen / UpgradeScreen, action 30 read)
- **Purpose:** read the user's entitlement state (plan, status, dates).
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** none.
- **Output data:** `Subscription { planCode, status, startedAt, renewsAt }`
  — 200.
- **Errors:** 404 `NOT_FOUND` (no subscription).
- **Related domain entities:** E10 `Subscription`.
- **Priority:** P2.

#### 46 — `SubscribeToPlan`

- **API name:** `SubscribeToPlan` (UC-33)
- **HTTP method:** `POST`
- **Path:** `/v1/subscriptions`
- **Feature:** profile (SubscriptionScreen / UpgradeScreen, action 30)
- **Purpose:** initiate a purchase via the billing provider; entitlement
  state updates on the provider callback. Payment call after commit, never
  inside a DB transaction.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync (initiation; callback is server-to-
  server).
- **Input data:** `SubscribeRequest { planCode }`; `Idempotency-Key`
  required.
- **Output data:** `Subscription` — 200/201.
- **Errors:** 402/424 `EXTERNAL_SERVICE_FAILURE` (payment outcome), 404
  `NOT_FOUND` (plan), 503 `EXTERNAL_SERVICE_FAILURE` (store unreachable).
- **Related domain entities:** E10 `Subscription`.
- **Priority:** P2.

---

### 5.16 Media — M16 (P2, sealed — MS10.3)

> **Sealed until MS10.3 lifts** (API-12). These endpoints are inventoried so
> the surface is complete, but they are **not mounted** — no fake 200, the
> routes do not exist. Flow (TRX-1, PR-8): Flutter PUTs bytes directly to
> object storage (zero FastAPI RAM), then `/complete` verifies via
> HEAD/size/hash and records the `MediaRef`. Signed URLs are short-lived,
> owner-scoped, never persisted.

#### 47 — `CreateMediaUpload`

- **API name:** `CreateMediaUpload`
- **HTTP method:** `POST`
- **Path:** `/v1/media/uploads`
- **Feature:** wardrobe (item images), outfit_scan / hairstyle (input media)
- **Purpose:** request a signed upload URL for an image.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1; private by default).
- **Synchronous/asynchronous:** sync.
- **Input data:** `UploadRequest { purpose, filename, size, contentType }`.
- **Output data:** `201 { upload_id, signedPutUrl, expiresAt }`.
- **Errors:** 413/422 `MEDIA_FAILURE` (media validation).
- **Related domain entities:** `MediaRef` (value object).
- **Priority:** P2 (sealed).

#### 48 — `CompleteMediaUpload`

- **API name:** `CompleteMediaUpload`
- **HTTP method:** `POST`
- **Path:** `/v1/media/uploads/{upload_id}/complete`
- **Feature:** wardrobe (item images), outfit_scan / hairstyle (input media)
- **Purpose:** verify the uploaded blob and record the `MediaRef`.
- **Authentication requirement:** auth.
- **Authorization requirement:** owner (OW-1).
- **Synchronous/asynchronous:** sync.
- **Input data:** none (upload_id in path).
- **Output data:** `MediaRef` — 200.
- **Errors:** 404 `NOT_FOUND`, 413/422 `MEDIA_FAILURE`, 503
  `EXTERNAL_SERVICE_FAILURE`.
- **Related domain entities:** `MediaRef` (value object).
- **Priority:** P2 (sealed).

---

## 6. Cross-cutting summary

### 6.1 Authentication matrix

| Requirement | Endpoints |
| --- | --- |
| **Public** | `/health`, `/v1/auth/register`, `/v1/auth/social`, `/v1/auth/login`, all `/v1/knowledge/*`, `/v1/assistant/chat` (public **today**, F-5) |
| **Auth** | everything else (every user-data endpoint) |

### 6.2 Authorization matrix

| Requirement | Endpoints |
| --- | --- |
| None (public, no user data) | knowledge reads, health, auth issue endpoints |
| Owner (OW-1, 404-not-403) | every `/v1/users/me*`, `/v1/wardrobe/*`, `/v1/looks/saved*`, `/v1/events/*`, `/v1/looks/today*`, `/v1/learning/*`, `/v1/analysis/*`, `/v1/outfits/*`, `/v1/looks`, `/v1/subscriptions/*`, `/v1/media/*` (sealed) |
| Admin (not in Flutter contract) | knowledge seed/admin writes (M5 P2), feedback list (M11 admin) |

### 6.3 Sync / async matrix

| Type | Endpoints |
| --- | --- |
| **Sync** | everything except the three analysis submissions |
| **Async** (`202` + run_id polling) | `POST /v1/analysis/outfit`, `POST /v1/analysis/hairstyle`, `POST /v1/analysis/grooming` |

### 6.4 Server-to-server / non-Flutter endpoints (documented, not client APIs)

- **Subscriptions billing webhook** (M15): provider callback, system
  principal, idempotent, never inside a DB transaction (R51).
- **Admin knowledge seed** (M5 P2): admin-only content writes (`require_admin`),
  audited, default closed — not part of the Flutter contract.
- **Account deletion / erasure** (SECURITY_PRIVACY_DESIGN §5): server-side
  cascade; the API exposes only the user's own path, not in the Flutter
  contract today.

### 6.5 Idempotency-Key required (C-12, API-33)

`POST /v1/auth/register`, `POST /v1/users/me/sync`, `POST /v1/looks/saved`,
`POST /v1/looks/today/save`, `POST /v1/outfits/saved`,
`POST /v1/feedback` (when live), `POST /v1/subscriptions`. **Never** on
`/v1/assistant/chat` or `/v1/analysis/*`.

---

## 7. Report, assumptions, constraints

**What changed (this step):** added `docs/api/API_INVENTORY.md` — the
complete API inventory (48 client-facing endpoints + health) with all
thirteen fields per endpoint, derived exclusively from the STEP 2–5
deliverables and `API_CONTRACT_RULES.md`. No implementation.

**Skills used:** repository/document analysis (ACTION_API 32 actions,
domain model E1–E10, TABLE_DEFINITIONS, APPLICATION_USE_CASES UC-1…33,
MODULE_MAP M1–M16, API_CONTRACT_RULES §12 catalog, ERROR_HANDLING 12
categories, AUTH OW-1, BACKGROUND_JOB sync/async) — documentation only.

**Files changed:** `docs/api/API_INVENTORY.md` (new).

**Validation run:**
- **Every STEP 2 action (1–32) maps to ≥1 inventory endpoint** (master
  table §4; action 27 = navigation inside `AssistantReply` / endpoint 16;
  action 4 = precondition to endpoint 10 `SyncLocalData`).
- **Every UC-1…UC-33 maps to an endpoint** (UC-5 onboarding → endpoint 10
  sync path; UC-17 → endpoint 31; UC-29 → endpoint 41 `?seed=`).
- **Cross-checked against the canonical catalog** `API_CONTRACT_RULES.md`
  §12 — method/path/auth/sync/idempotency/errors identical; path-collision
  guard honored (§5.9 note).
- **Consistent with STEP 5:** module phases M1–M16 → priority column;
  API-40/41 sync/async; API-33 idempotency; OW-1 owner-scoping; the frozen
  12-category error codes identical to `ERROR_HANDLING.md`.
- **No invented APIs:** every endpoint traces to an action/use case/entity
  in the inventory docs; sealed modules (M11/M16) are inventoried but marked
  NOT mounted (API-12).
- **Live contract preserved:** `GET /health` and `POST /v1/assistant/chat`
  unchanged (endpoints 01 and 16).
- **`git status --short`:** only `docs/api/API_INVENTORY.md` (untracked) +
  `CURRENT_STATE.md`; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Field-level DTO definitions beyond the contract's P0 sketches are set at
  M2/M4 implementation, guided by `API_CONTRACT_RULES.md` §13 and
  `TABLE_DEFINITIONS.md`.
- Sealed modules (M11 feedback, M16 media) remain **not mounted** until their
  gates lift; their rows above are forward documentation.
- `GET /v1/looks` (discover, M14) vs `GET /v1/knowledge/looks` (public
  catalog, M5) coexist as two read surfaces — confirmed against MODULE_MAP.
- No `DECISIONS.md` entry: documentation only; open items remain in
  `API_CONTRACT_RULES.md` §16.

**Assumptions recorded:**
- "Feature" = the Flutter feature(s) that surface the action (per
  `ACTION_API_INVENTORY.md` screens) + the owning module M#.
- Endpoints are grouped by module and inherit the module's P0/P1/P2 phase.
- Analysis submissions are the only async endpoints; everything else sync
  (API-40/41).
- Auth is introduced with the auth module; until then `deps.py` is a stub
  and the assistant endpoint stays public (F-5).

**Constraints honored:** BAR-0 (assistant DTOs frozen; API is a thin
projection of the domain), DR-1 (one use case per endpoint), F-6 (DTO-only
responses), F-13 (assistant contract unchanged), C-7/C-8 (no DB or AI
internals), OW-1/API-10 (owner-scoped, 404-not-403), API-28…31 (typed
errors), API-40/41 (sync/async), API-12 (sealed modules not mounted), TRX-1/
3/5 (upload-then-insert, save+signal transaction, write-once completion), the
UI Change Safety Rule (no Flutter modified), and the Scope rule (inventory
only — nothing implemented).
