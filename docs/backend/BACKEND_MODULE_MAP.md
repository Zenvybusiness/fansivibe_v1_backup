# Fansivibe — Backend Module Map

> **STEP 5 (continuation) — BACKEND ARCHITECTURE.** Defines the **backend
> module structure** for the production FastAPI backend, derived from the
> completed STEP 2 inventories (`FEATURE_INVENTORY.md`,
> `ACTION_API_INVENTORY.md`, `DATA_MODEL_INVENTORY.md`), the STEP 3 canonical
> domain model (`FANSIVIBE_DOMAIN_MODEL_V1.md`), and the STEP 4 PostgreSQL
> design (`DATABASE_DESIGN_RULES.md`, `TABLE_DEFINITIONS.md`,
> `TRANSACTION_BOUNDARIES.md`, `SECURITY_PRIVACY_DESIGN.md`), under the
> architecture rules of `BACKEND_ARCHITECTURE_RULES.md` (BA-1…BA-15).
>
> **Status: architecture design only. No module is implemented.** No existing
> code is modified, no endpoints are created, no repositories, no migrations,
> no dependencies, nothing is deleted.
>
> **Source of truth:** the real Fansivibe repository
> (`newproject/flutter_application_1` + `backend/`). The separate reference
> project is reference material only and is **not** merged into this design.

---

## 1. Purpose and scope

This step maps the Fansivibe **domain and product surface** onto **backend
modules**: named units within the modular monolith (BA-1) that group one
feature's responsibility, owned domain concepts, application use cases, API
routers, repositories, external dependencies, and background jobs.

It answers:

1. **Which modules exist?** — the accepted module set, screened against the
   product and domain model (candidates that duplicate, have no entity, or are
   P3/future are folded or rejected, not invented).
2. **What does each module own?** — responsibility, domain concepts
   (entities/value objects from the domain model), use cases, routers,
   repositories (STEP 4 tables), external interfaces (BA-6), and jobs.
3. **What ships first?** — modules classified P0 (first production vertical
   slice per `MVP_SCOPE.md` Part 1), P1 (next core features, Part 2), and P2
   (supporting, Part 3).

It does **not** answer endpoint signatures, repository implementations, or SQL
— later steps implement the modules against this map.

**Module selection rule (BMM-0):** a module exists only if the **actual
product and the finalized domain model support it** — it must own at least one
domain concept from `FANSIVIBE_DOMAIN_MODEL_V1.md` or be a required
architecture seam (auth, media, knowledge). UI-only concepts, value objects
owned by another module, P3-gated entities, and capabilities that are pure
AI output get **no module**; they are documented as folded or rejected (§3).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities E1–E10 + conditional, value objects, ownership (§7), lifecycle, phasing (§17). |
| `TABLE_DEFINITIONS.md` | The 23 tables a module's repositories read/write; conditional tables gate modules. |
| `DATABASE_DESIGN_RULES.md` | PR-1…PR-12, append-only grants, JSONB/media policy, phased build order (§14). |
| `ACTION_API_INVENTORY.md` | The 32 user actions → endpoint clusters (Part 1/Part 4 §3) that routers must cover. |
| `MVP_SCOPE.md` | P0/P1/P2/P3 phasing of what is built first. |
| `ARCHITECTURE_GAP_REPORT.md` | REQUIRED_BEFORE_BACKEND seams: auth (AU11.x), knowledge source (K9.1), repositories (R4.2), errors (A3.3/E13.1), scoping (AZ12.3). |
| `TRANSACTION_BOUNDARIES.md` | TRX-1…TRX-8 — which use cases are true transactions; external effects after-commit. |
| `SECURITY_PRIVACY_DESIGN.md` | user_id scoping, erasure, MS10.3 gate for media. |
| `BACKEND_ARCHITECTURE_RULES.md` | BA-1…BA-15 the modules must satisfy (layers, ports, no-premature-complexity). |
| Flutter feature tree | `lib/features/` — the 14 product features the backend modules serve. |

Re-verified source facts that anchor module ownership:

- **14 Flutter features** exist (`assistant`, `discover`, `events`, `grooming`,
  `hairstyle`, `home`, `learning`, `onboarding`, `outfit_builder`,
  `outfit_scan`, `profile`, `scan_center`, `stylist`, `wardrobe`) plus the
  router shell — the backend module set is designed against the features that
  actually surface data (`scan_center` and `stylist` are launcher/empty and
  map to no module of their own).
- **One live API** (`POST /v1/assistant/chat`) and **no auth** — every other
  module is a derived, future requirement (`ACTION_API_INVENTORY.md` ground
  truth).
- **Only 5 durable entities exist in product data today** (E1 `User`,
  E2 `WardrobeItem`, E4 `SavedLook`, E7 `LearningSignal`, E5 `Look`) — the P0
  module set is built on exactly these; P1/P2 modules add the rest per
  `MVP_SCOPE.md`.
- **No entity for:** outfit (value object), recommendation (AI output),
  appearance profile (value object in `user_state`), preference set
  (`user_state.preferences` JSONB) — these never become modules (§3).
- **`assistant` DTOs mirror backend 1:1** (`schemas.py` ↔ models.dart) — the
  assistant module owns this live contract (A3.1).

---

## 3. Candidate screening (BMM-0 applied)

Candidate modules raised during analysis, and their resolution. **Only the
"kept" rows become modules.** `analysis_runs` gate vs `recommendation_history`
gate is copied from `FANSIVIBE_DOMAIN_MODEL_V1.md` §17.

| Candidate | Resolution | Justification |
| --- | --- | --- |
| `auth` | **Keep (P0)** | Required seam: `REQUIRED_BEFORE_BACKEND` AU11.1/AU11.2 (OAuth2 + user-row). No backend works without a session. |
| `users` / profile / preferences / appearance | **Keep `users` (P0); fold preferences + appearance into it** | One `User` entity (E1) + one `user_state` row per user (JSONB: `style_profile`, `preferences`, `settings`, `flags`). Preferences and appearance are value objects, not entities — no own table, no own module (PR-6, P7.1). |
| `scans` | **Rename to `analysis` (P2)** | One `AnalysisRun` entity (E6) covers outfit/hairstyle/grooming runs; face is planned value-only. |
| `recommendations` | **Fold into `ai_engine` + surface modules** | A recommendation is **AI output, never a source of truth** (BAR-0, §8.2). No `Recommendation` entity; only P3-gated `recommendation_history` (§17). |
| `wardrobe` | **Keep (P0)** | `WardrobeItem` (E2) is product data today; P0 CRUD + phase-2 insight. |
| `outfits` | **Keep (P2)** | Outfit is a value object (`outfit` JSONB in `analysis_runs`), but "generate an outfit for me" is a real user action (`POST /outfits/generate`, `POST /outfits/saved`). Kept as a generation capability module. |
| `saved looks` | **Keep (P1)** | `SavedLook` (E4) is product data today; persistence becomes P1 per `MVP_SCOPE.md` (append-only snapshot, no cascade). |
| `events` | **Keep (P1)** | `UserEvent` (E3) + `generate-for-event` action; P1 per scope. |
| `daily outfit` | **Keep (P1)** | Derived today's look + conditional `today_look_records` (P1-gated, §17). |
| `discover` | **Keep (P2)** | `GET /looks` feed over knowledge module; filters + personalization; P2 per scope. |
| `feedback` | **Keep (P1, feature-gated)** | `feedback_events` table exists but is **feature-gated**: no module code until the UI ships it. |
| `assistant` | **Keep (P0)** | The **only live API** today (`POST /v1/assistant/chat`) + `POST /assistant/feedback`; owns the A3.1 contract. |
| `subscriptions` | **Keep (P2)** | `Subscription` (E10), entitlement is external (R51); P2. |
| `media` | **Keep (P2, MS10.3-gated)** | Media columns exist but are **MS10.3-gated** (SECURITY_PRIVACY_DESIGN) — module is sealed until the gate lifts. |
| `knowledge` | **Keep (P0→P2)** | `Look` (E5) + vocabularies = `REQUIRED_BEFORE_BACKEND` K9.1. P0 subset (categories/colors/occasions/looks list), full rollout P2. |
| `ai_engine` / decision engine | **Keep (P0, domain-layer)** | Intent/tool/dialogue + recommendation & analysis rules; owns the `AIProvider`/`KnowledgeSource` ports. No API router, no repository — a domain service every feature module calls. |
| *(extra)* `learning` | **Add (P1)** | `LearningSignal` (E7) is durable product data; `StyleScoreRecord` (E8) + `ActivityDay` (E9) are P1 derived. Emitted/consumed across modules via the shared signal seam (§8.2). |

**Rejected outright (no module):** marketplace / e-commerce / social feed /
messaging — not part of the product (BAR-0). Weather: external provider,
consumed via `WeatherProvider` port inside `daily outfit`, never a module.

Resulting module set (18):

```
auth, users, wardrobe, assistant, knowledge, ai_engine,          # P0 (6)
saved_looks, events, daily_outfit, learning, feedback,           # P1 (5)
analysis, outfits, discover, subscriptions, media                 # P2 (5)  -> total 16 modules + ai_engine (domain) + media (sealed)
```

> `ai_engine` is a **domain-layer** module (no api/application slice of its
> own); `media` is a **sealed** P2 module. All others are full
> api→application→domain slices (BA-2, BA-4).

---

## 4. Module inventory (master table)

| # | Module | Layer slice | Phase | Owns (domain) | Primary tables |
| --- | --- | --- | --- | --- | --- |
| M1 | `auth` | api+app+domain | P0 | session/identity (no entity) | `users` (row creation), `sessions`/tokens (R51 note) |
| M2 | `users` | api+app+domain | P0 | E1 `User`, `user_state` | `users`, `user_state` |
| M3 | `wardrobe` | api+app+domain | P0 | E2 `WardrobeItem` | `wardrobe_items`, `items` (ref) |
| M4 | `assistant` | api+app+domain | P0 | chat session, cards (DTO) | `assistant_messages` (R51 note), `learning_signals` (emit) |
| M5 | `knowledge` | api+app+domain | P0→P2 | E5 `Look`, vocabularies | `looks`, `categories`, `colors`, `occasions`, `size_categories` |
| M6 | `ai_engine` | domain only | P0 | intent, tools, dialogue, generation rules | *(no tables)* |
| M7 | `saved_looks` | api+app+domain | P1 | E4 `SavedLook` | `saved_looks` |
| M8 | `events` | api+app+domain | P1 | E3 `UserEvent` | `user_events` |
| M9 | `daily_outfit` | api+app+domain | P1 | today's look (derived), E9 `ActivityDay` | `today_look_records` (cond.), `activity_days` |
| M10 | `learning` | app+domain | P1 | E7 `LearningSignal`, E8 `StyleScoreRecord`, E9 `ActivityDay` | `learning_signals`, `style_score_records`, `activity_days` |
| M11 | `feedback` | api+app+domain | P1 (gated) | E4-adjacent feedback | `feedback_events` |
| M12 | `analysis` | api+app+domain | P2 | E6 `AnalysisRun` | `analysis_runs` |
| M13 | `outfits` | api+app+domain | P2 | outfit (value object), generation | `analysis_runs.outfit` (write), `saved_looks` (save) |
| M14 | `discover` | api+app+domain | P2 | look feed, filters, personalization | `looks` (read), `categories` (read) |
| M15 | `subscriptions` | api+app+domain | P2 | E10 `Subscription` | `subscriptions` |
| M16 | `media` | api+app+domain | P2 (sealed) | MediaRef / blobs | media columns (MS10.3), `ObjectStorage` port |

Cross-cutting seams (not modules): **signals** (M10-owned, emitted by
assistant/wardrobe/daily_outfit), **events/background jobs** (M16/M9/M15),
**errors** (A3.3/E13.1), **transaction boundaries** (TRX-1…TRX-8).

---

## 5. Module definitions — P0 (first production vertical slice)

### M1 — `auth`  (P0)

- **Responsibility:** identity and session. Creates the `users` row on
  register, issues and validates bearer sessions, logs out.
- **Owned domain concepts:** session/identity (no entity; identity lives in
  `User` E1 which is *owned* by `users`; auth only creates the row at AU11.1).
- **Application use cases:** register (email/password), social login
  (OAuth2, AU11.2), login, logout, token validation for the whole API
  (dependency on `users`).
- **API routers:** `auth.py` → `POST /auth/register`, `POST /auth/social`,
  `POST /auth/login`, `POST /auth/logout`.
- **Repositories:** `UserRepository.create` (at registration only — the users
  module owns all other access); session/token store (R51: durable).
- **External dependencies:** OAuth2 identity providers (Google/Apple), via an
  explicit `IdentityProvider` port (BA-6).
- **Events/background jobs:** none. Session invalidation on logout is
  synchronous.
- **Boundary:** never reads/returns user profile beyond the identity claim;
  profile display is `users` (BAR-0, single responsibility).

### M2 — `users`  (P0)

- **Responsibility:** the user record and its full per-user state: profile,
  preferences, settings, appearance style profile. Owns `POST /users/me/sync`
  (P7.1) — the sync contract that flushes local app state to the backend.
- **Owned domain concepts:** E1 `User`; value objects `UserProfile`,
  `StyleProfile` (appearance), `Preferences`, `Settings`, flags.
- **Application use cases:** read/update profile, update preferences
  (`PUT /users/me/preferences`), update settings, sync (P7.1), merge local
  state with server truth.
- **API routers:** `users.py` → `GET /users/me`,
  `PATCH /users/me`, `PUT /users/me/preferences`,
  `PUT /users/me/settings`, `POST /users/me/sync`.
- **Repositories:** `UserRepository`, `UserStateRepository`
  (`users`, `user_state`). Sync writes `user_state` in one transaction
  (TRX-4).
- **External dependencies:** none (except OAuth2 claim source via `auth`).
- **Events/background jobs:** none. Erasure (privacy) triggers
  cross-module cascade via a domain event (`UserDeleted`) consumed by all
  modules with per-user tables (R50/R51 erasure).
- **Boundary:** owns the *entire* `user_state` JSONB; no other module writes
  `user_state`.

### M3 — `wardrobe`  (P0)

- **Responsibility:** the user's wardrobe item catalog — CRUD, favorite
  toggle, list, item lookup for outfit generation and analysis.
- **Owned domain concepts:** E2 `WardrobeItem` (plus `ItemReference` value
  object pointing at the knowledge `items` reference catalog).
- **Application use cases:** add item, update item, delete item, list items
  (with filter), toggle favorite (E2.favorite), look up an item for
  generation/analysis (dependency for M13/M12), wardrobe insight summary.
- **API routers:** `wardrobe.py` → `POST /wardrobe/items`,
  `PATCH /wardrobe/items/{item_id}`, `DELETE /wardrobe/items/{item_id}`,
  `GET /wardrobe/items`, `GET /wardrobe/insight`.
- **Repositories:** `WardrobeItemRepository` (`wardrobe_items`);
  reads `items` (reference) via `knowledge` repository contract.
- **External dependencies:** none.
- **Events/background jobs:** on item create, emit an `ItemAdded` domain
  event → `learning` records a `LearningSignal` (P1). No jobs in P0.
- **Boundary:** item *validation* (color/type match) lives in `ai_engine`
  rules, not here; this module persists and serves items.

### M4 — `assistant`  (P0)

- **Responsibility:** the conversational assistant — the **live contract**
  (`POST /v1/assistant/chat`) that must never break (BAR-0 §8.2, A3.1).
  Routes the request to `ai_engine`, returns typed structured cards/DTOs.
- **Owned domain concepts:** chat session (session_id), assistant
  message DTOs (KEEP mirror A3.1), SuggestionCard, card interaction.
- **Application use cases:** chat (instruct + respond with tools, K9.1),
  list messages, record card feedback (`POST /assistant/feedback`), clear
  session.
- **API routers:** `assistant.py` → `POST /v1/assistant/chat`,
  `POST /assistant/feedback`.
- **Repositories:** `AssistantMessageRepository` (`assistant_messages`,
  R51), emits `LearningSignal` via `learning` (P1).
- **External dependencies:** `ai_engine` (domain service) only — never
  calls the AI provider directly (BA-8).
- **Events/background jobs:** card interaction → `learning` signal
  (P1). None in P0 beyond response streaming.
- **Boundary:** owns the DTO shape; `ai_engine` never constructs
  Flutter-facing JSON — it returns domain-level decisions the assistant
  module maps to DTOs.

### M5 — `knowledge`  (P0→P2)

- **Responsibility:** the curated knowledge base — categories, colors,
  occasions, sizes, and the reference `looks` catalog (K9.1). This is the
  "backend represents the domain model, not the UI" seam: the assistant and
  discover read *knowledge*, not hardcoded client lists.
- **Owned domain concepts:** E5 `Look`, vocabularies (Category, Color,
  Occasion, Size), `ItemReference` catalog.
- **Application use cases:** list/filter looks, list categories, list
  occasions, look up items for reference, admin/seed of curated data (P2).
- **API routers:** `knowledge.py` → `GET /knowledge/looks`,
  `GET /knowledge/categories`, `GET /knowledge/occasions`,
  `GET /knowledge/colors`, `GET /knowledge/items`.
- **Repositories:** `LookRepository`, `CategoryRepository`,
  `ColorRepository`, `OccasionRepository`, `ItemRepository`
  (`looks`, `categories`, `colors`, `occasions`, `size_categories`, `items`).
- **External dependencies:** none (curated content seeded by the team, not
  an external AI provider).
- **Events/background jobs:** content update → optional reindex for
  personalization (P2). None in P0.
- **Boundary:** read-mostly; writes only via admin/seed (BA-3). Owns the
  vocabularies so no module invents its own category list.

### M6 — `ai_engine`  (P0, domain-layer)

- **Responsibility:** the decision engine behind assistant, generation, and
  analysis — intent classification, tool selection, dialogue policy, and the
  **recommendation/analysis generation rules**. This is where AI output is
  *produced and validated* (typed structured data, never a source of truth —
  BAR-0 §8.2).
- **Owned domain concepts:** intent, tools (knowledge lookup, wardrobe
  lookup, outfit generation), dialogue state, recommendation rules, analysis
  rules. No entity — pure domain service.
- **Application use cases:** (none directly — no API router). Consumed by
  `assistant`, `outfits`, `daily_outfit`, `analysis` via application-layer
  use cases. Owns the `AIProvider` and `KnowledgeSource` ports (BA-6).
- **API routers:** none.
- **Repositories:** none (reads knowledge/wardrobe via ports).
- **External dependencies:** `AIProvider` (e.g. Ollama) — the **only**
  module allowed to touch an AI provider (BA-8); `KnowledgeSource` port.
- **Events/background jobs:** none. Responses are synchronous/typed.
- **Boundary:** never talks to Flutter; never persists its own output;
  output validity (enum matches, DTO shape) is enforced here before any
  module maps it (A3.3).

---

## 6. Module definitions — P1 (core features, `MVP_SCOPE.md` Part 2)

### M7 — `saved_looks`  (P1)

- **Responsibility:** durable storage of user-saved looks (snapshots), so
  "save this look" works across devices and re-engagements.
- **Owned domain concepts:** E4 `SavedLook` (append-only snapshot; value
  object `LookSnapshot`).
- **Application use cases:** save a look, list saved looks, delete a saved
  look (soft-delete, append-only), lookup a look for assistant reuse.
- **API routers:** `saved_looks.py` → `POST /looks/saved`,
  `GET /looks/saved`, `DELETE /looks/saved/{saved_look_id}`.
- **Repositories:** `SavedLookRepository` (`saved_looks`).
- **External dependencies:** none.
- **Events/background jobs:** none.
- **Boundary:** stores *snapshots* only — it never re-derives a look; the
  generating module (assistant/outfits) owns the live values.

### M8 — `events`  (P1)

- **Responsibility:** the user's event calendar and the "generate an outfit
  for this event" flow.
- **Owned domain concepts:** E3 `UserEvent` (type, title, date, note,
  wardrobe_required).
- **Application use cases:** create/update/delete event, list events,
  generate-for-event (delegates to `outfits`), attach today's look.
- **API routers:** `events.py` → `POST /events`,
  `PUT /events/{event_id}`, `DELETE /events/{event_id}`,
  `GET /events`, `POST /events/{event_id}/outfit`.
- **Repositories:** `UserEventRepository` (`user_events`).
- **External dependencies:** none (weather goes through `daily_outfit`).
- **Events/background jobs:** none in P1.
- **Boundary:** the outfit *generation* is `outfits`; this module only
  triggers it (TRX-7 boundary).

### M9 — `daily_outfit`  (P1)

- **Responsibility:** derive and serve "today's look" (a recommended outfit
  for the current day) and record daily activity/streak inputs.
- **Owned domain concepts:** today's look (derived value object), E9
  `ActivityDay` (record of an active day), conditional `today_look_records`
  (P1-gated, §17).
- **Application use cases:** get today's look, regenerate today's look,
  mark today as active (streak), save today's look.
- **API routers:** `daily_outfit.py` → `GET /looks/today`,
  `POST /looks/today`, `POST /looks/today/save`.
- **Repositories:** `TodayLookRepository` (`today_look_records`),
  `ActivityDayRepository` (`activity_days`); reads `wardrobe` via port.
- **External dependencies:** `WeatherProvider` port (BA-6) — external
  weather data used only as a *hint* inside rules, never authoritative.
- **Events/background jobs:** on "today active" → emit signal to
  `learning` (streak derivation, P1).
- **Boundary:** derived data only — it is never the source of truth; the
  signal feed is `learning`.

### M10 — `learning`  (P1)

- **Responsibility:** the cross-cutting learning/feedback seam — records
  signals (emitted by assistant, wardrobe, daily_outfit, discover),
  derives style score and streak from signals, and serves them for
  personalization.
- **Owned domain concepts:** E7 `LearningSignal` (append-only history),
  E8 `StyleScoreRecord` (derived), E9 `ActivityDay` (derived).
- **Application use cases:** record signal (internal API for other
  modules), derive style score, derive streak/activity, read learning state
  for personalization (M14/M4).
- **API routers:** none public (internal seam; may expose a
  `GET /learning/summary` later for profile display).
- **Repositories:** `LearningSignalRepository`
  (`learning_signals`), `StyleScoreRepository`
  (`style_score_records`), `ActivityDayRepository` (`activity_days`).
- **External dependencies:** none.
- **Events/background jobs:** derived-score recomputation triggered by
  signal batches (deferred/aggregate, P1).
- **Boundary:** the **only** module that writes `learning_signals`;
  all other modules emit via the signal port (BA-6). Append-only by
  design (PR-7).

### M11 — `feedback`  (P1, feature-gated)

- **Responsibility:** user rating/feedback on looks and outfits
  (`feedback_events`), when the feature UI ships.
- **Owned domain concepts:** E4-adjacent `FeedbackEvent` (value object:
  look_id, rating, comment).
- **Application use cases:** submit feedback on a look/outfit, list feedback
  (admin), read average rating.
- **API routers:** `feedback.py` → `POST /feedback`,
  `GET /feedback` (admin).
- **Repositories:** `FeedbackRepository` (`feedback_events`).
- **External dependencies:** none.
- **Events/background jobs:** none.
- **Boundary:** **feature-gated** — table may exist (BMM-5) but the module
  has **no code and no router until the Flutter feedback UI is accepted**
  (PR-11, scope guard). Sealed.

---

## 7. Module definitions — P2 (supporting, `MVP_SCOPE.md` Part 3)

### M12 — `analysis`  (P2)

- **Responsibility:** scan/analysis runs — outfit scan, hairstyle, grooming
  (E6 `AnalysisRun`), each producing typed results via `ai_engine` rules.
- **Owned domain concepts:** E6 `AnalysisRun` (status, result, payload),
  result value objects (outfit analysis, hair analysis, grooming analysis).
- **Application use cases:** submit a scan/analysis run, get run result,
  list run history.
- **API routers:** `analysis.py` → `POST /analysis/outfit`,
  `POST /analysis/hairstyle`, `POST /analysis/grooming`,
  `GET /analysis/runs/{run_id}`, `GET /analysis/runs`.
- **Repositories:** `AnalysisRunRepository` (`analysis_runs`).
- **External dependencies:** `ai_engine` rules (never the AI provider
  directly, BA-8); media via M16 (image blob reference) when MS10.3 lifts.
- **Events/background jobs:** async run completion (image analysis is slow) —
  run stays `pending` until `ai_engine` returns; then a completion event
  updates status (TRX-6, delayed). P2.
- **Boundary:** payload may be large JSON (media references, results); still
  never stores raw AI output as truth (BAR-0).

### M13 — `outfits`  (P2)

- **Responsibility:** outfit *generation* — build an outfit from
  preferences + context (event, today, scan) via `ai_engine`, and save it.
- **Owned domain concepts:** outfit (value object — item list + rationale),
  generation context (preferences, event, today's look).
- **Application use cases:** generate outfit, regenerate outfit, save
  outfit (to `saved_looks`), generate-for-event (delegated from M8).
- **API routers:** `outfits.py` → `POST /outfits/generate`,
  `POST /outfits/saved`, `POST /events/{event_id}/outfit` (delegated).
- **Repositories:** writes `analysis_runs.outfit` payload on generation;
  `saved_looks` via M7's repository contract for save.
- **External dependencies:** `ai_engine` (generation rules), `wardrobe`
  (item catalog), `knowledge` (reference catalog).
- **Events/background jobs:** none (generation is synchronous in P2; async
  only if a slow AI provider is introduced).
- **Boundary:** generation is a *recommendation* — never persists as truth;
  only the user's explicit *save* creates a durable record (M7).

### M14 — `discover`  (P2)

- **Responsibility:** the look feed — curated looks from `knowledge`, with
  filters and personalization, feeding the Discover screen.
- **Owned domain concepts:** look feed, filters (category/occasion/color),
  personalization score (derived via `learning` + `ai_engine`).
- **Application use cases:** get looks feed, filter looks, personalized
  ordering (via `learning`), get look detail.
- **API routers:** `discover.py` → `GET /looks`, `GET /looks/{look_id}`.
- **Repositories:** reads `looks`/`categories` via `knowledge` contract;
  reads `learning_signals` (via M10) for personalization.
- **External dependencies:** `knowledge` (content), `learning`
  (personalization signals), `ai_engine` (ordering rules).
- **Events/background jobs:** optional reindex for personalization (P2).
- **Boundary:** never writes — a read-only presentation of `knowledge` +
  `learning` (BAR-0).

### M15 — `subscriptions`  (P2)

- **Responsibility:** entitlements — premium/paid features, linked to an
  external billing provider; the backend verifies and caches entitlement.
- **Owned domain concepts:** E10 `Subscription` (status, plan, expires_at).
- **Application use cases:** get subscription status, create/update
  subscription (via provider webhook), verify entitlement for premium
  features.
- **API routers:** `subscriptions.py` → `GET /subscriptions/me`,
  `POST /subscriptions` (initiate), webhook endpoint (provider callback).
- **Repositories:** `SubscriptionRepository` (`subscriptions`).
- **External dependencies:** billing provider (Stripe/etc.) via an explicit
  `BillingProvider` port (BA-6); idempotent webhook handling.
- **Events/background jobs:** webhook → update entitlement + emit event for
  premium feature gating (R51 note).
- **Boundary:** never stores payment details; only entitlement state.

### M16 — `media`  (P2, sealed — MS10.3)

- **Responsibility:** object-storage-backed media (images for items, scans,
  looks) — upload/download/cleanup. **Sealed**: no code until MS10.3 lifts.
- **Owned domain concepts:** MediaRef value object (key, mime, size),
  blob lifecycle.
- **Application use cases:** upload image, get image URL, delete image,
  orphan-blob cleanup.
- **API routers:** `media.py` → `POST /media/images`,
  `GET /media/images/{ref}` (or pre-signed URL), `DELETE /media/images/{ref}`.
- **Repositories:** media-metadata store (media columns on owning tables,
  R51) — not a separate table.
- **External dependencies:** `ObjectStorage` port (S3-compatible, BA-6).
- **Events/background jobs:** orphan-blob cleanup job after commit
  (TRX-6, R51) — deletes blobs whose owning row was removed.
- **Boundary:** gated by MS10.3 (privacy gate in
  `SECURITY_PRIVACY_DESIGN.md`); images are privacy-sensitive and never
  logged (SAFETY rules).

---

## 8. Cross-cutting seams (not modules)

These are shared mechanisms used by many modules; they do not get a module
slice of their own.

| Seam | Owner | Consumers | Rule |
| --- | --- | --- | --- |
| **Signals** (`LearningSignal`) | M10 `learning` | M4, M3, M9, M14 | Emitted via the signal port (BA-6); `learning` is the only writer of `learning_signals` (PR-7). |
| **Errors** (typed, A3.3/E13.1) | shared infra | all | Module errors map to API error DTOs; never raw provider errors. |
| **Transaction boundaries** (TRX-1…TRX-8) | shared infra (db unit) | all | `user_state` sync, blobs, and external calls use TRX boundaries. |
| **Events/background jobs** | M16/M15/M9 | dependent | Post-commit events (blob cleanup, webhook, streak). |
| **Erasure / privacy** (R50/R51) | shared | all modules with per-user tables | `UserDeleted` domain event cascades across modules. |

---

## 9. Phasing summary (BMM-4)

| Phase | Modules | What unlocks |
| --- | --- | --- |
| **P0 slice** | M1 auth, M2 users, M3 wardrobe, M4 assistant, M5 knowledge, M6 ai_engine | First production vertical: auth + sync (P7.1) + wardrobe CRUD + the live assistant contract (K9.1) + knowledge vocabulary. The only slice that can ship today (PR-9 no-premature-complexity). |
| **P1** | M7 saved_looks, M8 events, M9 daily_outfit, M10 learning, M11 feedback (gated) | Core retention features: save looks, events + generate, today's look, signals → score/streak. |
| **P2** | M12 analysis, M13 outfits, M14 discover, M15 subscriptions, M16 media (sealed) | Generation + discovery + commerce surface. `media` stays sealed until MS10.3. |

**Sequencing note:** modules are built in the order above, not in dependency
graph order alone. §9 of `BACKEND_ARCHITECTURE_RULES.md` migration M4/M5 is
followed: layers-first within each module, then typed errors, then local-only
PostgreSQL, then each module's P0 slice. Modules must remain independently
testable (BA-11) and independently migratable (PR-11).

---

## 10. Open decisions (carried from BACKEND_ARCHITECTURE_RULES.md §10)

1. **Auth provider** — OAuth2 (Google/Apple) vs email/password first
   (AU11.1/AU11.2) affects M1 scope.
2. **AI provider** — Ollama local vs hosted affects M6 latency and
   `assistant` streaming shape.
3. **`user_state` split** — single JSONB row vs broken-out columns (P7.1)
   affects M2 repository shape.
4. **Knowledge seeding** — how curated looks/categories are seeded (M5 P2
   admin) and where the content comes from.
5. **Media gate (MS10.3)** — when it lifts, M16 unlocks.
6. **Billing provider** — chosen provider determines M15 webhook shape.
7. **`recommendation_history`** — P3-gated (domain §17); M10/M14 will
   revisit only after learning is proven.

None block the P0 slice (M1–M6), which is provider-agnostic.

---

## 11. Report, assumptions, constraints

**What changed (this step):** added `BACKEND_MODULE_MAP.md` — the module map
for the production FastAPI backend. No code, no schema, no dependencies.

**Skills used:** repository analysis (Flutter feature tree, domain model,
ACTION/API, DB tables) — architecture documentation only.

**Files changed:** `docs/backend/BACKEND_MODULE_MAP.md` (new).

**Validation run:** 
- Read/cross-checked `FANSIVIBE_DOMAIN_MODEL_V1.md`, `MVP_SCOPE.md`,
  `ACTION_API_INVENTORY.md`, `TABLE_DEFINITIONS.md`,
  `DATABASE_DESIGN_RULES.md`, `TRANSACTION_BOUNDARIES.md`,
  `SECURITY_PRIVACY_DESIGN.md`, `BACKEND_ARCHITECTURE_RULES.md`.
- Confirmed the 14 Flutter feature names ground module naming (ground truth).
- Confirmed `git status --short` shows only the new file + previously
  reported `M CURRENT_STATE.md` / `?? docs/backend/` (no code touched).

**Remaining issues / follow-ups:**
- `CURRENT_STATE.md` is the only file to update next (state log entry for
  the module map).
- No implementation until the next step: each P0 module (M1–M6) is
  implemented against this map in the backend after review.
- Any decision that materially affects architecture, privacy, auth,
  storage, or product behavior per the Scope rule is deferred to the
  `DECISIONS.md` process — none accepted in this step (only
  documentation).

**Assumptions recorded:**
- "Module" = a `backend/app/modules/<name>/` unit with an api/application/
  domain slice (BA-4), or a domain-only slice (M6) or sealed module
  (M11/M16).
- Module boundaries follow the domain model ownership (§7) — not the Flutter
  feature tree. Flutter features are the *consumer surface*, not the module
  list (BAR-0).
- P0/P1/P2 classification follows `MVP_SCOPE.md` and the domain-model
  conditional-gating (§17), not feature-teaching order.

**Constraints honored:** BAR-0 (backend represents the domain model, not the
UI; assistant DTOs are the KEEP mirror), BA-2 layering, BA-6 external via
ports, BA-8 AI only in `ai_engine`, BA-10 no-premature-complexity,
no-premature-architecture, and the UI Change Safety Rule (this document does
not modify UI).





