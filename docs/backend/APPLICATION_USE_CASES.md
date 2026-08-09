# Fansivibe — Application Use Cases

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines the **application use
> cases** for the production FastAPI backend, derived from **STEP 2's
> `ACTION_API_INVENTORY.md`** (the 32 verified user actions). Each major user
> action becomes a named application-layer use case (the `app/application/*`
> services from `BACKEND_FOLDER_STRUCTURE.md`), specified so implementation
> (M1–M6) and tests can be written directly from it.
>
> For every use case: **name, input, required domain data, domain operations,
> repositories involved, external services involved, output, possible errors,
> transaction boundary.**
>
> The use cases are **design only. Nothing is implemented, no endpoints are
> created, no code, directories, or files are changed.**
>
> **Source of truth:** the real Fansivibe repository. Grounded in STEP 2
> (`ACTION_API_INVENTORY.md`, `FEATURE_INVENTORY.md`), STEP 3
> (`FANSIVIBE_DOMAIN_MODEL_V1.md`), STEP 4 (`TABLE_DEFINITIONS.md`,
> `TRANSACTION_BOUNDARIES.md`, `SECURITY_PRIVACY_DESIGN.md`), and STEP 5
> (`BACKEND_MODULE_MAP.md` M1–M16, `DEPENDENCY_RULES.md` DR-1…DR-6,
> `BACKEND_FOLDER_STRUCTURE.md`).

---

## 1. Purpose and scope

This document defines the **application layer contract**: the set of named
use cases that `app/api` routers call (DR-1) and that `app/domain` serves
(DR-2). It answers, for every major user action from STEP 2:

- **What the use case is called** (the function/class in `app/application/`).
- **What input it takes** (the router's typed request).
- **What domain data it needs** (entities/value objects it loads via ports).
- **What the domain does** (decision-engine/rules operations).
- **Which repositories it uses** (the `domain/ports/repositories.py`
  interfaces — never concrete, DR-9).
- **Which external services** (only through `domain/ports/external.py`, BA-6).
- **What it returns** (the typed result the router maps to a DTO).
- **What can go wrong** (typed domain exceptions → HTTP via `api/errors.py`).
- **Its transaction boundary** (TRX-* from `TRANSACTION_BOUNDARIES.md`, or
  "single-row / non-transactional").

It does **not** define router signatures, DTO shapes, SQL, or code.

**Grounding facts (BAR-0):** today the backend has exactly **one live
operation** (`POST /v1/assistant/chat` → UC-22) and **no auth**; every other
use case is a **derived future requirement** from STEP 2's inventory (Part 1,
32 actions). The assistant use case (UC-22) is the **live contract** (A3.1)
that must never break. The use-case names below match the module map's
application files so the folder structure and this spec agree 1:1.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `ACTION_API_INVENTORY.md` | The 32 user actions (screens, inputs, current state, future operation, errors) — the primary driver. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities E1–E10 + value objects (StyleProfile, FaceProfile, MediaRef, outfit, Today'sLook) that "required domain data" cites. |
| `TABLE_DEFINITIONS.md` | The 23 tables each repository reads/writes. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1…TRX-8 + §4 single-row + §5 non-transactional — the transaction-boundary field. |
| `SECURITY_PRIVACY_DESIGN.md` | user_id scoping (BA-8), MS10.3 media gate, erasure. |
| `BACKEND_MODULE_MAP.md` | M1–M16: which module owns each use case + which repositories exist. |
| `DEPENDENCY_RULES.md` | DR-1/DR-2/DR-9: use cases depend only on domain; routers call exactly one use case. |
| `BACKEND_FOLDER_STRUCTURE.md` | `app/application/*` file names the use cases live in. |

---

## 3. Conventions

### 3.1 Naming

- Use cases are named **verb-first, PascalCase** (e.g. `AddWardrobeItem`,
  `GenerateEventOutfit`), one per major user action; clustered actions
  (saved-look paths 12/14/17/22/24 → one `SaveRecommendation`) are
  consolidated deliberately (ACTION_API Part 4, note 3).
- Each maps to exactly one **application file** in `app/application/` and one
  module in the module map (M1–M16).

### 3.2 The nine fields

| Field | What it means |
| --- | --- |
| **Input** | The typed request payload the router passes in (incl. `user_id` resolved by the auth dependency). |
| **Required domain data** | Entities/value objects the use case loads **via repository ports** before deciding. |
| **Domain operations** | What the domain layer does (decision engine, rules, invariants, derivation). |
| **Repositories involved** | The **port interfaces** used (never concrete classes — DR-9); names match `TABLE_DEFINITIONS.md`. |
| **External services involved** | Only via `domain/ports/external.py` ports (BA-6/BA-8) — AI, knowledge, storage, weather, billing, identity. |
| **Output** | The typed result returned to the router (domain→DTO mapping in the API layer). |
| **Possible errors** | Typed domain exceptions the use case can raise; HTTP mapping done in `api/errors.py` (A3.3/E13.1). |
| **Transaction boundary** | TRX-* / single-row / non-transactional from `TRANSACTION_BOUNDARIES.md`. |

### 3.3 Error vocabulary

Cross-action error conditions come from `ACTION_API_INVENTORY.md` Part 3:

| Condition | HTTP | Domain exception (example) |
| --- | --- | --- |
| Not authenticated / expired | 401 | `UnauthenticatedError` |
| Not found | 404 | `NotFoundError` |
| Invalid input (vocab, validation, dates) | 422 | `InvalidInputError` |
| Duplicate / conflict | 409 | `ConflictError` |
| Backend / external failure | 503 | `ExternalServiceError` |
| Media invalid / too large | 413 / 422 | `MediaValidationError` |
| Rate limit | 429 | `RateLimitError` |
| Payment failure | 402 / 424 | `PaymentError` |

---

## 4. Use-case inventory (master table)

| UC | Use case | Module | Actions | Phase |
| --- | --- | --- | --- | --- |
| UC-1 | `RegisterAccount` | M1 auth | 1 | P0 |
| UC-2 | `SocialSignIn` | M1 auth | 2 | P0 |
| UC-3 | `SignIn` | M1 auth | 3 | P0 |
| UC-4 | `SignOut` | M1 auth | 29 | P0 |
| UC-5 | `CompleteOnboarding` | M2 users | 4 | P0 |
| UC-6 | `GetProfile` | M2 users | 28 | P0 |
| UC-7 | `UpdateProfile` | M2 users | 28 | P0 |
| UC-8 | `UpdatePreferences` | M2 users | 28 | P0 |
| UC-9 | `SyncLocalData` | M2 users | 32 | P0 |
| UC-10 | `AddWardrobeItem` | M3 wardrobe | 5 | P0 |
| UC-11 | `ToggleWardrobeItemFavorite` | M3 wardrobe | 6 | P0 |
| UC-12 | `UpdateWardrobeItem` | M3 wardrobe | 7 | P0 |
| UC-13 | `DeleteWardrobeItem` | M3 wardrobe | 7 | P0 |
| UC-14 | `GetWardrobeInsight` | M3 wardrobe | 8 | P0 |
| UC-15 | `SaveRecommendation` | M7 saved_looks | 12,14,17,22,24 | P1 |
| UC-16 | `GenerateDailyOutfit` | M9 daily_outfit | 13 | P1 |
| UC-17 | `GetTodayLook` | M9 daily_outfit | 13,12 | P1 |
| UC-18 | `CreateEvent` | M8 events | 9 | P1 |
| UC-19 | `UpdateEvent` | M8 events | 10 | P1 |
| UC-20 | `DeleteEvent` | M8 events | 10 | P1 |
| UC-21 | `GenerateEventOutfit` | M8 events + M13 outfits | 11 | P1 |
| UC-22 | `SendAssistantMessage` | M4 assistant | 25 | P0 (live) |
| UC-23 | `SubmitAssistantCardFeedback` | M4 assistant | 26 | P0/P1 |
| UC-24 | `AnalyzeOutfit` | M12 analysis | 16 | P2 |
| UC-25 | `AnalyzeAppearance` | M12 analysis | 21 (face) | P2 |
| UC-26 | `GenerateHairstyleRecommendations` | M12 analysis | 21 | P2 |
| UC-27 | `GenerateGroomingRecommendations` | M12 analysis | 23 | P2 |
| UC-28 | `CreateOutfit` | M13 outfits | 18 | P2 |
| UC-29 | `RegenerateOutfit` | M13 outfits | 20 | P2 |
| UC-30 | `SaveOutfit` | M13 outfits | 19 | P2 |
| UC-31 | `GetLookFeed` | M14 discover | 15 | P2 |
| UC-32 | `SubmitRecommendationFeedback` | M11 feedback | 31 | P1 (gated) |
| UC-33 | `SubscribeToPlan` | M15 subscriptions | 30 | P2 |

Actions 27 (navigate via assistant) and 4 (save locally) are **not** separate
use cases: 27 is carried inside `AssistantReply.navigation` (UC-22); 4 is the
anonymous-entry precondition to `CompleteOnboarding`/`SyncLocalData` (UC-5/9).

---

## 5. Use-case definitions

### 5.1 `auth` — M1

#### UC-1 — `RegisterAccount`

- **Input:** email, password, display_name (optional).
- **Required domain data:** none loaded (fresh session); creates E1 `User`.
- **Domain operations:** validate email/password policy; ensure email not
  taken; create identity; issue a session.
- **Repositories involved:** `UserRepository` (create row only).
- **External services involved:** `IdentityProvider` port (hash/verify
  credentials) — the auth module's seam.
- **Output:** session token + profile (name).
- **Possible errors:** email taken (409 `ConflictError`), invalid email/weak
  password (422 `InvalidInputError`), rate limit (429 `RateLimitError`).
- **Transaction boundary:** single-row (`users` INSERT); session issuance is a
  separate non-DB step (R51 token store).

#### UC-2 — `SocialSignIn`

- **Input:** provider + provider token.
- **Required domain data:** upsert `User` by provider subject id.
- **Domain operations:** exchange provider token via `IdentityProvider`;
  upsert user; issue app session.
- **Repositories involved:** `UserRepository`.
- **External services involved:** `IdentityProvider` (Google/Apple).
- **Output:** session token + profile (200 existing / 201 new).
- **Possible errors:** provider unavailable (502 `ExternalServiceError`),
  invalid/expired provider token (401 `UnauthenticatedError`), account-linking
  conflict (409 `ConflictError`).
- **Transaction boundary:** single-row upsert (`users`).

#### UC-3 — `SignIn`

- **Input:** email + password.
- **Required domain data:** E1 `User` (credentials).
- **Domain operations:** verify credentials; load profile + last model
  snapshot for device restore; issue session.
- **Repositories involved:** `UserRepository`, `UserStateRepository`.
- **External services involved:** `IdentityProvider` (verify).
- **Output:** session token + profile (+ stored model snapshot).
- **Possible errors:** wrong credentials (401 `UnauthenticatedError`), not
  found (404 `NotFoundError`), rate limit (429 `RateLimitError`).
- **Transaction boundary:** read-only; session issuance non-DB.

#### UC-4 — `SignOut`

- **Input:** session token.
- **Required domain data:** the session.
- **Domain operations:** revoke the token/session.
- **Repositories involved:** session/token store (R51).
- **External services involved:** none.
- **Output:** 204 ack.
- **Possible errors:** already logged out (401 `UnauthenticatedError`,
  idempotent).
- **Transaction boundary:** single-row session revocation (non-DB token store).

### 5.2 `users` — M2

#### UC-5 — `CompleteOnboarding`

- **Input:** `user_id`; the initial client `UserModel` snapshot
  (display_name, preferences, optional style_profile seed).
- **Required domain data:** E1 `User`; E1.1 `UserState`
  (`StyleProfile`, `UserPreferences`, `Settings`, flags) — created fresh.
- **Domain operations:** validate snapshot; **merge** initial local state into
  the server `user_state` (P7.1 sync path); set `onboarding_complete` flag.
- **Repositories involved:** `UserRepository`, `UserStateRepository`.
- **External services involved:** none.
- **Output:** sync receipt / merged `UserState` view.
- **Possible errors:** invalid snapshot (422 `InvalidInputError`), conflict on
  timestamps (409 `ConflictError`).
- **Transaction boundary:** TRX-4-style single-row `user_state` upsert
  (one JSONB write; the sync flush).

#### UC-6 — `GetProfile`

- **Input:** `user_id`.
- **Required domain data:** E1 `User`; E1.1 `UserState`
  (profile + style_profile + preferences + settings).
- **Domain operations:** assemble the profile view (name, style DNA, dominant
  palette via `StyleDnaView` derivation if present).
- **Repositories involved:** `UserRepository`, `UserStateRepository`.
- **External services involved:** none.
- **Output:** profile view (DTO-mapped).
- **Possible errors:** not found (404 `NotFoundError`).
- **Transaction boundary:** read-only (non-transactional).

#### UC-7 — `UpdateProfile`

- **Input:** `user_id`; changed profile fields (name, avatar `MediaRef`,
  style DNA fields).
- **Required domain data:** E1 `User`; E1.1 `UserState`.
- **Domain operations:** validate fields; apply the update (replace whole
  projection, optimistic `version` guard).
- **Repositories involved:** `UserRepository`, `UserStateRepository`.
- **External services involved:** none (avatar upload via M16 when MS10.3
  lifts; blob uploaded before the row write).
- **Output:** updated profile.
- **Possible errors:** invalid values (422 `InvalidInputError`), version
  conflict (409 `ConflictError`).
- **Transaction boundary:** single-row `UPDATE` (TRX-6 pattern: guarded by
  `version`; a 0-row effect → rollback).

#### UC-8 — `UpdatePreferences`

- **Input:** `user_id`; changed preference key/values.
- **Required domain data:** E1.1 `UserState.preferences` (JSONB).
- **Domain operations:** validate against the controlled preference keys;
  merge into the JSONB document.
- **Repositories involved:** `UserStateRepository`.
- **External services involved:** none.
- **Output:** updated preferences.
- **Possible errors:** invalid preference values (422 `InvalidInputError`).
- **Transaction boundary:** single-row JSONB `UPDATE` (one value, tier 1).

#### UC-9 — `SyncLocalData`

- **Input:** `user_id`; full local `UserModel` blob (JSONB candidate).
- **Required domain data:** E1 `User`; E1.1 `UserState`; wardrobes, events,
  saved looks, signals contained in the blob.
- **Domain operations:** **upsert** the snapshot; split relational rows
  (wardrobe/events/signals/saved-looks); resolve server-vs-device timestamp
  conflicts (latest-wins on projections, append-only on history).
- **Repositories involved:** `UserRepository`, `UserStateRepository`,
  `WardrobeItemRepository`, `UserEventRepository`, `SavedLookRepository`,
  `LearningSignalRepository`.
- **External services involved:** none.
- **Output:** sync receipt / merged model.
- **Possible errors:** conflict (409 `ConflictError` → resolution payload),
  payload too large (413 `MediaValidationError`).
- **Transaction boundary:** **true transaction** — the snapshot upsert +
  relational split commit together (TRX-3/TRX-6 style); history rows are
  INSERT-only (BA-9).

### 5.3 `wardrobe` — M3

#### UC-10 — `AddWardrobeItem`

- **Input:** `user_id`; name, category, color, texture (optional), notes
  (optional), optional image `MediaRef`.
- **Required domain data:** E2 `WardrobeItem`; vocabulary via `Look`/
  `ItemReference` (valid category/color codes).
- **Domain operations:** validate category/color against the controlled
  vocabulary; create the item; emit `ItemAdded` domain event (→
  `learning` signal, P1).
- **Repositories involved:** `WardrobeItemRepository`; reads `items` via the
  knowledge repository contract.
- **External services involved:** M16 `ObjectStorage` **if** an image is
  supplied (blob uploaded **before** the INSERT; MS10.3-gated).
- **Output:** created item (+ refreshed counts).
- **Possible errors:** invalid category/color (422 `InvalidInputError`),
  duplicate/limit (409 `ConflictError`).
- **Transaction boundary:** TRX-1 — single `INSERT wardrobe_items`
  (tier 1); blob upload outside the transaction, orphan swept by job.

#### UC-11 — `ToggleWardrobeItemFavorite`

- **Input:** `user_id`, item id, new favorite state.
- **Required domain data:** E2 `WardrobeItem` (row, user-scoped).
- **Domain operations:** set `favorite`; favorites feed insight/counts.
- **Repositories involved:** `WardrobeItemRepository`.
- **External services involved:** none.
- **Output:** updated item.
- **Possible errors:** not found (404 `NotFoundError`).
- **Transaction boundary:** single-row `UPDATE` (tier 1; §4 canonical).

#### UC-12 — `UpdateWardrobeItem`

- **Input:** `user_id`, item id, updated fields.
- **Required domain data:** E2 `WardrobeItem`; vocabulary codes.
- **Domain operations:** validate; replace fields.
- **Repositories involved:** `WardrobeItemRepository`.
- **External services involved:** none.
- **Output:** updated item.
- **Possible errors:** not found (404 `NotFoundError`), invalid vocab (422
  `InvalidInputError`).
- **Transaction boundary:** single-row `UPDATE` (tier 1).

#### UC-13 — `DeleteWardrobeItem`

- **Input:** `user_id`, item id.
- **Required domain data:** E2 `WardrobeItem` (owned).
- **Domain operations:** validate ownership; delete the row (images cascade
  out-of-DB); re-derive wardrobe stats.
- **Repositories involved:** `WardrobeItemRepository`.
- **External services involved:** M16 `ObjectStorage` cleanup **after**
  commit (async job).
- **Output:** 204 / updated insight.
- **Possible errors:** not found (404 `NotFoundError`), FK references (409
  `ConflictError`).
- **Transaction boundary:** single `DELETE` (TRX-1 pattern); "deleting
  current state never deletes history" (BC-41) — history untouched.

#### UC-14 — `GetWardrobeInsight`

- **Input:** `user_id`.
- **Required domain data:** wardrobe + knowledge catalog.
- **Domain operations:** derive gaps/insight (e.g. "consider a lightweight
  jacket") via the assistant's wardrobe rule.
- **Repositories involved:** `WardrobeItemRepository`; reads catalog via
  knowledge contract.
- **External services involved:** none.
- **Output:** insight card (title/insight/action/route).
- **Possible errors:** empty wardrobe (204/empty insight).
- **Transaction boundary:** read-only (non-transactional).

### 5.4 `saved_looks` — M7

#### UC-15 — `SaveRecommendation`

- **Input:** `user_id`; look reference (catalog `look_id` or style ref) +
  source context (from discover / daily outfit / scan analysis / hair /
  grooming) + snapshot payload.
- **Required domain data:** E4 `SavedLook` (append-only snapshot; value
  object `LookSnapshot`); optional `look_id`→E5 `Look` (SET NULL FK).
- **Domain operations:** freeze the snapshot (score/reasons immutable);
  create the saved-look row + its `look_saved` learning signal.
- **Repositories involved:** `SavedLookRepository`,
  `LearningSignalRepository`; optionally `AnalysisRunRepository`
  (provenance `source_run_id`).
- **External services involved:** none (image blobs via M16 when present,
  uploaded before the INSERT).
- **Output:** saved-look id.
- **Possible errors:** look not found/expired (404 `NotFoundError`),
  duplicate (409 `ConflictError` or idempotent).
- **Transaction boundary:** **TRX-3 — true transaction**: `INSERT
  saved_looks` + `INSERT learning_signals(look_saved)` commit together;
  `recommendation_history.saved` flip only when the P3 table exists.

### 5.5 `daily_outfit` — M9

#### UC-16 — `GenerateDailyOutfit`

- **Input:** `user_id`; regeneration variant/seed (optional).
- **Required domain data:** E1.1 `UserState` (StyleProfile, preferences),
  wardrobe (E2), optional nearest E3 `UserEvent`, E5 `Look` catalog.
- **Domain operations:** derive **Today'sLook** (value object) from
  StyleProfile + wardrobe + event + weather hint via the decision engine
  (R49); produce a different result per seed.
- **Repositories involved:** reads via `UserStateRepository`,
  `WardrobeItemRepository`, `UserEventRepository`, `LookRepository`.
- **External services involved:** `WeatherProvider` port (BA-6) — external
  weather used only as a hint, never authoritative.
- **Output:** a fresh today's-look card.
- **Possible errors:** no looks available (404 `NotFoundError`/empty),
  generation failure (503 `ExternalServiceError`).
- **Transaction boundary:** **non-transactional** (computation; §5
  `TRANSACTION_BOUNDARIES.md`); optional `today_look_records` INSERT when the
  P1 table exists (single-row).

#### UC-17 — `GetTodayLook`

- **Input:** `user_id`; optional variant.
- **Required domain data:** current today's look (derived) or the stored
  `today_look_records` snapshot.
- **Domain operations:** serve today's look (derive or read snapshot).
- **Repositories involved:** `TodayLookRepository` (P1 table).
- **External services involved:** none.
- **Output:** today's-look card.
- **Possible errors:** none found (404 `NotFoundError`).
- **Transaction boundary:** read-only (non-transactional).

### 5.6 `events` — M8

#### UC-18 — `CreateEvent`

- **Input:** `user_id`; event name, date (past-date invalid), time, event
  type.
- **Required domain data:** E3 `UserEvent`; vocabulary `EventType`.
- **Domain operations:** validate type against controlled vocabulary + date
  not in past; record the occasion preference (`preferred_occasions`).
- **Repositories involved:** `UserEventRepository`, `UserStateRepository`
  (occasion preference).
- **External services involved:** none.
- **Output:** created event (echoed).
- **Possible errors:** missing/invalid fields (422 `InvalidInputError`), past
  date (422 `InvalidInputError`).
- **Transaction boundary:** **TRX-7** — single `INSERT user_events` (tier 1);
  the event-driven recommendation is derived, not stored (BC-56).

#### UC-19 — `UpdateEvent`

- **Input:** `user_id`, event id, updated fields.
- **Required domain data:** E3 `UserEvent` (owned).
- **Domain operations:** validate fields; update.
- **Repositories involved:** `UserEventRepository`.
- **External services involved:** none.
- **Output:** updated event.
- **Possible errors:** not found (404 `NotFoundError`), invalid (422
  `InvalidInputError`).
- **Transaction boundary:** single-row `UPDATE` (tier 1).

#### UC-20 — `DeleteEvent`

- **Input:** `user_id`, event id.
- **Required domain data:** E3 `UserEvent` (owned).
- **Domain operations:** delete the event (history untouched).
- **Repositories involved:** `UserEventRepository`.
- **External services involved:** none.
- **Output:** 204.
- **Possible errors:** not found (404 `NotFoundError`).
- **Transaction boundary:** single `DELETE` (tier 1).

#### UC-21 — `GenerateEventOutfit`

- **Input:** `user_id`, event id.
- **Required domain data:** E3 `UserEvent` (type/occasion as seed), wardrobe
  (E2), StyleProfile (E1.1).
- **Domain operations:** delegate to the outfit generation engine pre-seeded
  with the event occasion (fixes the current data-loss, ACTION_API note 6);
  return a recommendation.
- **Repositories involved:** reads via `UserEventRepository`,
  `WardrobeItemRepository`, `UserStateRepository`.
- **External services involved:** `ai_engine` (M6) generation rules; never a
  provider directly (BA-8).
- **Output:** an outfit recommendation.
- **Possible errors:** event not found (404 `NotFoundError`), generation
  failure (503 `ExternalServiceError`).
- **Transaction boundary:** **non-transactional** (TRX-7: recommendation is
  regenerable, not stored unless saved via UC-15).

### 5.7 `assistant` — M4

#### UC-22 — `SendAssistantMessage`  *(the live contract, A3.1)*

- **Input:** `user_id`; message text + conversation history + `AssistantUserContext`
  (wardrobe/face/savedLooks/occasions) — the shape **must never change** (F-13).
- **Required domain data:** `AssistantUserContext` (derived DTO, R47) — loaded
  from repositories once auth/DB land (today: client-sent, unchanged).
- **Domain operations:** intent classification → tool selection (knowledge
  lookup, wardrobe lookup, outfit generation) → dialogue policy (clarification
  flow) → structured reply (cards, navigation, text). Optional LLM text
  enrichment via `AIProvider`; degrades gracefully to the rules engine.
- **Repositories involved:** `AssistantMessageRepository` (conversation
  persistence — R51), reads `LookRepository`/`WardrobeItemRepository` via
  engine tools.
- **External services involved:** `AIProvider` port (M6, BA-8) — **only** via
  the domain engine; never from this use case.
- **Output:** `AssistantReply` (intent/text/cards/clarifications/navigation).
- **Possible errors:** invalid context (422 `InvalidInputError`), auth (401);
  backend-unreachable → client offline fallback (not a surfaced error).
- **Transaction boundary:** **non-transactional** (§5: conversation is
  transient by default; retention undecided).

#### UC-23 — `SubmitAssistantCardFeedback`

- **Input:** `user_id`; card title/id + interaction type (opened/navigated).
- **Required domain data:** the card reference.
- **Domain operations:** record the card-interaction signal for learning.
- **Repositories involved:** `LearningSignalRepository` (via M10 seam).
- **External services involved:** none.
- **Output:** 204 ack.
- **Possible errors:** auth (401).
- **Transaction boundary:** single `INSERT learning_signals` (tier 1; §4
  canonical).

### 5.8 `analysis` — M12

#### UC-24 — `AnalyzeOutfit`

- **Input:** `user_id`; captured outfit image (multipart; transient today).
- **Required domain data:** E6 `AnalysisRun` (pending) + source `MediaRef`.
- **Domain operations:** create the run; run outfit analysis rules
  (`ai_engine`/M12 rules) → sections, detected items, scores, confidence;
  guarded completion (write-once).
- **Repositories involved:** `AnalysisRunRepository`.
- **External services involved:** M16 `ObjectStorage` (blob uploaded before
  the run row; MS10.3-gated); `ai_engine` rules.
- **Output:** `OutfitAnalysisData` + confidence.
- **Possible errors:** image too large/unsupported (413/422
  `MediaValidationError`), no clothing detected (422 `InvalidInputError`),
  service failure (503 `ExternalServiceError`), timeout.
- **Transaction boundary:** **TRX-5** — run row INSERT (tier 1) then the
  **single guarded completion** `UPDATE ... WHERE status='pending'` (write-once,
  PR-6); blob outside the transaction.

#### UC-25 — `AnalyzeAppearance`

- **Input:** `user_id`; face image (or existing `FaceProfile`).
- **Required domain data:** E6 `AnalysisRun` (face); E1.1 `StyleProfile.
  FaceProfile` (value object, R15).
- **Domain operations:** face analysis → appearance attributes; produce/
  update `FaceProfile` (replaced whole on acceptance, latest-wins on the
  projection, never on history).
- **Repositories involved:** `AnalysisRunRepository`,
  `UserStateRepository`.
- **External services involved:** M16 `ObjectStorage` (face media is private);
  `ai_engine` appearance rules.
- **Output:** appearance attributes + confidence.
- **Possible errors:** poor image / face not detected (422
  `InvalidInputError`), service failure (503 `ExternalServiceError`).
- **Transaction boundary:** **TRX-5** (run completion) then **TRX-6**
  (profile projection update + `analysis_updated`/`style_updated` signal in
  one true transaction).

#### UC-26 — `GenerateHairstyleRecommendations`

- **Input:** `user_id`; face image/profile; scan readiness.
- **Required domain data:** `FaceProfile` (from UC-25 or stored), E5 `Look`
  (hairstyle catalog), E6 `AnalysisRun` (hairstyle).
- **Domain operations:** run UC-25's appearance analysis (if needed) then
  hairstyle recommendation rules → top pick + alternatives + scores +
  reasons.
- **Repositories involved:** `AnalysisRunRepository`,
  `UserStateRepository`, `LookRepository`.
- **External services involved:** `ai_engine` rules; M16 if media.
- **Output:** `HairstyleAnalysisResult` (top + alternatives, scores, reasons).
- **Possible errors:** poor image (422 `InvalidInputError`), service failure
  (503 `ExternalServiceError`).
- **Transaction boundary:** TRX-5 (run) → TRX-6 (FaceProfile projection) —
  both as documented above.

#### UC-27 — `GenerateGroomingRecommendations`

- **Input:** `user_id`; grooming options (face shape, beard style, density,
  color).
- **Required domain data:** `FaceProfile` (grooming fields), E5 `Look`
  (grooming catalog), E6 `AnalysisRun` (grooming).
- **Domain operations:** grooming recommendation rules → result + reasons +
  scores.
- **Repositories involved:** `AnalysisRunRepository`, `UserStateRepository`,
  `LookRepository`.
- **External services involved:** `ai_engine` rules.
- **Output:** `GroomingAnalysisResult`.
- **Possible errors:** invalid inputs (422 `InvalidInputError`), service
  failure (503 `ExternalServiceError`).
- **Transaction boundary:** TRX-5 (run completion); no projection update
  unless a style is accepted (→ TRX-6).

### 5.9 `outfits` — M13

#### UC-28 — `CreateOutfit`

- **Input:** `user_id`; occasion/mood/fit/color-palette preference selections.
- **Required domain data:** E1.1 `UserState` (preferences, StyleProfile),
  wardrobe (E2), knowledge catalog (E5).
- **Domain operations:** validate preference values; generation rules
  (`ai_engine`/M6) → outfit (value object: item list + rationale + scores).
- **Repositories involved:** reads via `UserStateRepository`,
  `WardrobeItemRepository`, `LookRepository`.
- **External services involved:** `ai_engine` (M6) — never a provider
  directly (BA-8).
- **Output:** `OutfitRecommendation`.
- **Possible errors:** invalid preference values (422 `InvalidInputError`),
  no matching wardrobe (204/empty), generation failure (503
  `ExternalServiceError`).
- **Transaction boundary:** **non-transactional** (TRX-2: outfit is a value
  object, regenerable; nothing persisted unless saved).

#### UC-29 — `RegenerateOutfit`

- **Input:** `user_id`; same preferences + a variety/seed parameter.
- **Required domain data:** as UC-28.
- **Domain operations:** re-run generation with the seed for a different
  result.
- **Repositories involved:** as UC-28.
- **External services involved:** `ai_engine`.
- **Output:** a different recommendation.
- **Possible errors:** generation failure (503 `ExternalServiceError`).
- **Transaction boundary:** non-transactional (TRX-2).

#### UC-30 — `SaveOutfit`

- **Input:** `user_id`; the recommendation (component snapshot).
- **Required domain data:** E4 `SavedLook` (snapshot of the outfit value
  object).
- **Domain operations:** freeze the outfit snapshot; persist as a saved
  outfit (via M7's repository contract).
- **Repositories involved:** `SavedLookRepository`,
  `LearningSignalRepository`.
- **External services involved:** none.
- **Output:** saved-outfit id.
- **Possible errors:** auth (401), duplicate (409 `ConflictError`/idempotent).
- **Transaction boundary:** **TRX-3** — saved-look row + `look_saved` signal
  in one transaction.

### 5.10 `discover` — M14

#### UC-31 — `GetLookFeed`

- **Input:** `user_id` (for personalization), filter set
  (occasion/style/fit), pagination.
- **Required domain data:** E5 `Look` catalog (filtered), wardrobe (E2) for
  `isOwned`/match scores, learning signals (E7) for personalization.
- **Domain operations:** filter the catalog; personalize ordering (match
  scores via `learning` + `ai_engine` ordering rules).
- **Repositories involved:** reads via `LookRepository`,
  `CategoryRepository`; `WardrobeItemRepository`,
  `LearningSignalRepository` (personalization).
- **External services involved:** none.
- **Output:** paginated look cards (filtered, ordered).
- **Possible errors:** invalid filter values (422 `InvalidInputError`), auth
  required for personalized fields (401).
- **Transaction boundary:** read-only (non-transactional).

### 5.11 `feedback` — M11 (feature-gated)

#### UC-32 — `SubmitRecommendationFeedback`

- **Input:** `user_id`; rating + optional comment + look/outfit reference.
- **Required domain data:** E4-adjacent `FeedbackEvent` (value object).
- **Domain operations:** validate; store; optionally link to a signal/look id.
- **Repositories involved:** `FeedbackRepository` (`feedback_events`).
- **External services involved:** none.
- **Output:** 201/204 ack.
- **Possible errors:** invalid payload (422 `InvalidInputError`), rate limit
  (429 `RateLimitError`).
- **Transaction boundary:** single `INSERT feedback_events` (tier 1).
- **Note:** **feature-gated** — no UI exists (ACTION_API #31, missing
  feature); this use case ships only when the feedback UI is accepted
  (module map M11).

### 5.12 `subscriptions` — M15

#### UC-33 — `SubscribeToPlan`

- **Input:** `user_id`; plan id.
- **Required domain data:** E10 `Subscription` (0..1 per user, BC-3), plan
  reference.
- **Domain operations:** initiate purchase via the billing provider; update
  entitlement state on provider callback (webhook).
- **Repositories involved:** `SubscriptionRepository`.
- **External services involved:** `BillingProvider` port (R51) — idempotent,
  retryable; **never** called inside a DB transaction.
- **Output:** plan activation + entitlement.
- **Possible errors:** payment failure (402/424 `PaymentError`), plan not
  found (404 `NotFoundError`), store unreachable (503 `ExternalServiceError`).
- **Transaction boundary:** **non-transactional DB-side** (§5: external
  payment call runs after commit; the entitlement row `UPDATE` is single-row
  tier 1).

---

## 6. Cross-cutting notes

- **Every user-data use case is scoped by `user_id`** resolved in `api/deps.py`
  and enforced inside the use case (BA-8); repositories filter by it.
- **History is INSERT-only** (BA-9, PR-7): no use case ever updates or deletes
  a history row except the single guarded analysis completion (TRX-5).
- **External effects happen after commit** (TRX-1…TRX-8): blob uploads
  before the DB write, blob deletes/payment/webhooks after via
  `infrastructure/jobs.py` or the events dispatcher.
- **Feature-gated use cases** (`UC-32`, and media-dependent flows) ship only
  when their UI/table exists (module map M11/M16).
- **The assistant is the only live use case today** (UC-22); all others are
  derived requirements to be implemented in M4 (P0: UC-1…UC-14) and later
  phases (P1: UC-15…UC-23; P2: UC-24…UC-33).

---

## 7. Report, assumptions, constraints

**What changed (this step):** added `APPLICATION_USE_CASES.md` — the
application-layer use-case contract derived from the STEP 2 Action/API
Inventory. No implementation.

**Skills used:** repository analysis (ACTION/API inventory, domain model,
transaction boundaries, module map, dependency rules) — architecture
documentation only.

**Files changed:** `docs/backend/APPLICATION_USE_CASES.md` (new).

**Validation run:**
- Every use case traces to a STEP 2 action (table in §4 covers actions
  1–32); every action maps to ≥1 use case (27 and 4 are covered inside
  UC-22/UC-5/UC-9 as documented).
- Every repository name matches a `TABLE_DEFINITIONS.md` table and a module
  map M1–M16 repository; every transaction boundary cites a TRX-* id or a §4/§5
  category from `TRANSACTION_BOUNDARIES.md`.
- Every external service reference goes through a `domain/ports/external.py`
  port (AI/knowledge/storage/weather/billing/identity) — BA-6, no provider
  leakage (F-7).
- `git status --short` shows only this new doc + `CURRENT_STATE.md` update
  (below); no code, dirs, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Next implementation step (per `BACKEND_ARCHITECTURE_RULES.md` §9): M1 folder
  skeleton (UC-22's file moves first), then M2 typed errors, then M3
  migrations, then M4 P0 vertical slice (UC-1…UC-14) once auth/contract
  decisions land.
- The 13 example use cases requested are all present: `CompleteOnboarding`
  (UC-5), `GetProfile` (UC-6), `UpdatePreferences` (UC-8), `AnalyzeAppearance`
  (UC-25), `GenerateHairstyleRecommendations` (UC-26), `SaveRecommendation`
  (UC-15), `SubmitRecommendationFeedback` (UC-32), `AddWardrobeItem` (UC-10),
  `CreateOutfit` (UC-28), `GenerateDailyOutfit` (UC-16), `CreateEvent`
  (UC-18), `GenerateEventOutfit` (UC-21), `SendAssistantMessage` (UC-22).
- No `DECISIONS.md` entry needed: no accepted architectural decision was made
  (documentation only); open items remain in `BACKEND_ARCHITECTURE_RULES.md`
  §10 and `BACKEND_FOLDER_STRUCTURE.md` §9.

**Assumptions recorded:**
- "Major user action" = one of the 32 STEP 2 actions; trivial state reads
  (e.g. navigation, filter-toggling with no server call) are not separate use
  cases.
- Use-case names are the canonical application-service names; the API router
  files (from the folder structure) are the delivery vehicles, not the names.
- Phase assignment follows `MVP_SCOPE.md` and the module map (P0: auth/users/
  wardrobe/assistant/knowledge/ai_engine; P1: saved_looks/events/daily_outfit/
  learning/feedback; P2: analysis/outfits/discover/subscriptions/media).

**Constraints honored:** BAR-0 (domain-driven; assistant DTOs the KEEP
mirror — UC-22's contract unchanged), BA-6/BA-8 (external via ports, AI only
via engine), BA-9/BA-14 (append-only history, transaction boundaries),
DR-1/DR-2/DR-9 (routers call one use case; use cases depend only on domain),
the UI Change Safety Rule (no UI touched), and the Scope rule (this document
only).
